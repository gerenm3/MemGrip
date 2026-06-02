"""v2 LVS — Learning Value Score 任務品質評估模組

依據 §3.11 (LVS) 定義：
- class LVS，供 Orchestrator 透過 DI 注入
- process(results, session_id, task_type) -> tuple[str | None, bool]
- 只在 complex 路徑所有 Unit 執行結束後結算分數
- TRIGGER_THRESHOLD = 100 為固定設計決策
- 符合原則 6（本地 log 寫入不需包 Result）
- 符合 v2 logging 規範
"""

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Optional

from core.health import log_action
from models.blueprints import UnitStatus

logger = logging.getLogger(__name__)

# ── 常量定義 ──

LVS_STATE_PATH = Path("skills/lvs_state.json")
TRACE_LOG_PATH = Path("trace.jsonl")
TASK_TRACE_PATH = Path("task_trace.jsonl")

# 觸發閾值（固定設計決策）
TRIGGER_THRESHOLD = 100

# 事件分數定義
EVENT_SCORES = {
    "task_failed": 30,
    "unit_failed": 8,
    "replan": 10,
    "review_fail": 3,
    "loop_hit": 4,
}

# Q 分總上限
MAX_Q_SCORE = 96

# 每條未滿足 constraint 的 Q 分懲罰
CONSTRAINT_PENALTY = 5

# Constraint violation Q 分維度上限
CONSTRAINT_Q_CAP = 15

# trace.jsonl 檔案大小上限（10 MB）
MAX_TRACE_SIZE = 10 * 1024 * 1024
TRACE_KEEP_LINES = 5000

# ── 狀態鎖 ──

_LVS_STATE_LOCK = asyncio.Lock()


class LVS:
    """Learning Value Score 評估器."""

    def calculate_q(self, task_record: dict) -> float:
        """根據任務 trace 記錄計算 Q 分。

        新增維度：
        - constraint_satisfied_ratio < 0.7 → +5 分（上限 10 分）
        - avg_loop_count > 3 → +3 分（上限 6 分）
        """
        final_fail = 1 if task_record.get("final_status") == "failed" else 0
        units = task_record.get("units", [])
        failed_units = sum(1 for u in units if u.get("status") == "FAILED")
        replan_count = sum(u.get("replan_count", 0) for u in units)
        loop_hit = sum(1 for u in units if u.get("total_loop_count", 0) >= 5)
        review_fail = self._count_review_fails(task_record)
        unsatisfied = self._count_unsatisfied_constraints(task_record)

        # 新維度：constraint_satisfied_ratio
        constraint_ratio = task_record.get("constraint_satisfied_ratio", 1.0)
        constraint_penalty_score = 0.0
        if constraint_ratio < 0.7:
            # 越低分數越高，0.0 → 10 分，0.7 → 0 分
            constraint_penalty_score = min(10.0, (0.7 - constraint_ratio) / 0.7 * 10.0)

        # 新維度：avg_loop_count
        avg_loop = task_record.get("avg_loop_count", 0)
        loop_excess_score = 0.0
        if avg_loop > 3:
            # 超過 3 的部分，每 1 單位 +3 分，上限 6 分
            loop_excess_score = min(6.0, (avg_loop - 3) * 3.0)

        q = (
            min(30, final_fail * 30)
            + min(20, failed_units * 8)
            + min(10, replan_count * 10)
            + min(6, review_fail * 3)
            + min(4, loop_hit * 4)
            + min(CONSTRAINT_Q_CAP, unsatisfied * CONSTRAINT_PENALTY)
            + constraint_penalty_score
            + loop_excess_score
        )
        return min(q, MAX_Q_SCORE)

    def _enforce_trace_size(self) -> None:
        """確保 trace.jsonl 不超過 MAX_TRACE_SIZE."""
        if not TRACE_LOG_PATH.exists():
            return
        file_size = TRACE_LOG_PATH.stat().st_size
        if file_size <= MAX_TRACE_SIZE:
            return
        try:
            with open(TRACE_LOG_PATH, "r", encoding="utf-8") as f:
                lines = f.readlines()
            kept_lines = lines[-TRACE_KEEP_LINES:] if len(lines) > TRACE_KEEP_LINES else lines
            with open(TRACE_LOG_PATH, "w", encoding="utf-8") as f:
                f.writelines(kept_lines)
        except Exception as e:
            logger.warning("[LVS] trace.jsonl 裁切失敗：%s", e)

    def _count_review_fails(self, task_record: dict) -> int:
        """從 trace.jsonl 統計本次任務的審核失敗次數."""
        self._enforce_trace_size()
        session_id = task_record.get("session_id")
        if not session_id:
            return 0
        count = 0
        try:
            with open(TRACE_LOG_PATH, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if entry.get("session_id") != session_id:
                        continue
                    if entry.get("caller") != "executor_verify":
                        continue
                    messages = entry.get("messages", [])
                    passed = self._extract_verify_passed(messages)
                    if passed is False:
                        count += 1
        except FileNotFoundError:
            pass
        except Exception as e:
            logger.warning("[LVS] 讀取 trace.jsonl 統計 review_fail 失敗：%s", e)
        return count

    def _count_unsatisfied_constraints(self, task_record: dict) -> int:
        """統計所有 units 中 satisfied=false 的 constraint checks 總數."""
        count = 0
        units = task_record.get("units", [])
        for u in units:
            checks = u.get("constraint_checks", [])
            for check in checks:
                if isinstance(check, dict) and check.get("satisfied") is False:
                    count += 1
        return count

    def _extract_verify_passed(self, messages: list) -> Optional[bool]:
        """從 executor_verify 的 messages 中提取審核結果."""
        for msg in messages:
            content = msg.get("content", "")
            if not isinstance(content, str):
                continue
            from core.json_utils import parse_first_json
            obj = parse_first_json(content)
            if isinstance(obj, dict) and "passed" in obj:
                return bool(obj["passed"])
        return None

    def _read_state_file(self) -> dict:
        """讀取 lvs_state.json."""
        if LVS_STATE_PATH.exists():
            try:
                with open(LVS_STATE_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if "global_score" in data:
                        return data
            except (json.JSONDecodeError, Exception) as e:
                logger.warning("[LVS] lvs_state.json 格式錯誤，重建檔案：%s", e)
        return {"global_score": 0.0, "last_optimizer_run": None}

    def _write_state_file(self, state: dict) -> None:
        """寫入 lvs_state.json."""
        LVS_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(LVS_STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)

    async def process(
        self,
        results: dict,
        session_id: str,
        task_type: str,
    ) -> tuple[str | None, bool]:
        """綜合 LVS 流程：計算 Q → 更新分數 → 嘗試觸發 optimizer.

        Args:
            results: executor 回傳的 results dict
            session_id: 本次任務的 session ID
            task_type: 任務類型

        Returns:
            (warning_message | None, triggered)
        """
        any_failed = any(r.status == UnitStatus.FAILED for r in results.values())
        units_list = [
            {
                "unit_id": uid,
                "status": r.status.value,
                "replan_count": r.replan_count if hasattr(r, 'replan_count') else 0,
                "total_loop_count": r.total_loop_count if hasattr(r, 'total_loop_count') else 0,
                "constraint_checks": r.constraint_checks if hasattr(r, 'constraint_checks') else [],
            }
            for uid, r in results.items()
        ]

        # 計算 constraint_satisfied_ratio 和 avg_loop_count
        total_checks = 0
        satisfied_checks = 0
        for u in units_list:
            for check in u.get("constraint_checks", []):
                if isinstance(check, dict):
                    total_checks += 1
                    if check.get("satisfied") is True:
                        satisfied_checks += 1
        constraint_satisfied_ratio = satisfied_checks / total_checks if total_checks > 0 else 1.0

        total_loop = sum(u.get("total_loop_count", 0) for u in units_list)
        avg_loop_count = total_loop / len(units_list) if units_list else 0

        task_record = {
            "session_id": session_id,
            "final_status": "failed" if any_failed else "success",
            "units": units_list,
            "constraint_satisfied_ratio": constraint_satisfied_ratio,
            "avg_loop_count": avg_loop_count,
        }

        # 在計算 Q 分前收集 signal
        try:
            from skills import signal_collector
            signal_collector.collect(str(session_id), task_type)
        except Exception as e:
            logger.warning("[LVS] signal_collector.collect 失敗：%s", e)

        q = self.calculate_q(task_record)

        async with _LVS_STATE_LOCK:
            state = self._read_state_file()
            state["global_score"] += q
            triggered = state["global_score"] >= TRIGGER_THRESHOLD
            if triggered:
                state["global_score"] *= 0.2
                now = time.strftime("%Y-%m-%dT%H:%M:%S%z", time.gmtime())
                now_formatted = now[:-2] + ":" + now[-2:]
                state["last_optimizer_run"] = now_formatted
                self._write_state_file(state)
            else:
                self._write_state_file(state)

        log_action("lvs", "score_calculated", "OK", f"Q={q:.0f}, G={state['global_score']:.1f}")

        if triggered:
            log_action("lvs", "optimizer_triggered", "OK")
            logger.info("[LVS] 觸發 optimizer (G=%.1f, Q=%.1f)", state["global_score"], q)
            # optimizer 觸發已移至 Orchestrator，LVS 只負責計算分數與回傳 triggered
            warning = f"\u26a0\ufe0f \u672c\u4efb\u52d5\u54c1\u8cea\u4e0d\u4f73\uff08Q={q:.0f}\uff09\uff0c\u5df2\u89f8\u767c optimizer \u512a\u5316 skill guide\u3002"
        else:
            g = state["global_score"]
            logger.debug("[LVS] 未觸發 optimizer (G=%.1f, Q=%.1f)", g, q)
            warning = None

        return (warning, triggered)
