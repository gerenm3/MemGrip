"""LVS — Learning Value Score 任務品質評估模組

提供 Q 分計算、全域分數管理、optimizer 觸發判斷與重置。
"""

import json
import logging
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

LVS_STATE_PATH = Path("skills/lvs_state.json")
TRACE_LOG_PATH = Path("trace.jsonl")
TASK_TRACE_PATH = Path("task_trace.jsonl")


# ──────────────────────────────────────────────
# Q 分計算
# ──────────────────────────────────────────────


def calculate_q(task_record: dict) -> float:
    """根據任務 trace 記錄計算 Q 分。

    參數：
        task_record：從 task_trace.jsonl 讀取的一筆記錄（dict），
                     需包含 final_status 和 units 列表。

    回傳：
        Q 分（float），上限 65。
    """
    final_fail = 1 if task_record.get("final_status") == "failed" else 0

    units = task_record.get("units", [])
    failed_units = sum(1 for u in units if u.get("status") == "FAILED")
    replan_count = sum(u.get("replan_count", 0) for u in units)
    loop_hit = sum(1 for u in units if u.get("total_loop_count", 0) >= 5)

    # review_fail：從 trace.jsonl 統計本次任務的審核失敗次數
    review_fail = _count_review_fails(task_record)

    q = (
        min(30, final_fail * 30)
        + min(20, failed_units * 8)
        + min(10, replan_count * 10)
        + min(6, review_fail * 3)
        + min(4, loop_hit * 4)
    )

    return min(q, 65)


def _count_review_fails(task_record: dict) -> int:
    """從 trace.jsonl 統計本次任務的審核失敗次數。

    以 session_id 關聯本次任務，篩選 caller="executor_verify"
    且審核結果 passed=false 的記錄。
    """
    session_id = task_record.get("session_id")
    if not session_id:
        return 0

    task_ts = task_record.get("ts", "")
    start_time = 0
    end_time = float("inf")
    if task_ts:
        try:
            start_time = time.time() - 86400  # 向前抓 24 小時
            end_time = time.time()
        except (ValueError, TypeError):
            pass

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

                # 檢查 session_id 是否匹配
                if entry.get("session_id") != session_id:
                    continue

                # 只統計 executor_verify 調用
                if entry.get("caller") != "executor_verify":
                    continue

                # 解析審核結果
                messages = entry.get("messages", [])
                passed = _extract_verify_passed(messages)
                if passed is False:
                    count += 1
    except FileNotFoundError:
        pass
    except Exception as e:
        logger.warning("[LVS] 讀取 trace.jsonl 統計 review_fail 失敗：%s", e)

    return count


def _extract_verify_passed(messages: list) -> Optional[bool]:
    """從 executor_verify 的 messages 中提取審核結果。

    LLM 會回傳 {"passed": true/false, "reason": "..."} 的 JSON。
    """
    for msg in messages:
        content = msg.get("content", "")
        if not isinstance(content, str):
            continue

        # 嘗試在內容中找到 JSON 物件
        import re
        match = re.search(r"\{[\s\S]*\"passed\"\s*:\s*(true|false)[\s\S]*\}", content, re.IGNORECASE)
        if match:
            return match.group(1).lower() == "true"

        # 也嘗試找嵌套的 JSON
        brace_start = content.find("{")
        if brace_start >= 0:
            brace_end = content.rfind("}")
            if brace_end > brace_start:
                try:
                    obj = json.loads(content[brace_start:brace_end + 1])
                    if "passed" in obj:
                        return bool(obj["passed"])
                except json.JSONDecodeError:
                    pass

    return None


# ──────────────────────────────────────────────
# 全域分數管理
# ──────────────────────────────────────────────


def _load_state() -> dict:
    """載入 lvs_state.json，檔案不存在時回傳預設值。"""
    if LVS_STATE_PATH.exists():
        try:
            with open(LVS_STATE_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                if "global_score" in data:
                    return data
        except (json.JSONDecodeError, Exception) as e:
            logger.warning("[LVS] lvs_state.json 格式錯誤，重建檔案：%s", e)
    return {"global_score": 0.0, "last_optimizer_run": None}


def _save_state(state: dict) -> None:
    """寫入 lvs_state.json。"""
    LVS_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LVS_STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def update_global_score(q: float) -> float:
    """更新全域分數並回傳更新後的值。

    參數：
        q：本次任務的 Q 分。

    回傳：
        更新後的 global_score。
    """
    state = _load_state()
    state["global_score"] += q
    _save_state(state)
    return state["global_score"]


def should_trigger() -> bool:
    """檢查是否應觸發 optimizer。

    回傳：
        True 若 global_score >= 100，否則 False。
    """
    state = _load_state()
    return state["global_score"] >= 100


def reset_after_trigger() -> Optional[str]:
    """觸發 optimizer 後的狀態重置。

    回傳：
        最近一次 optimizer 執行時間（ISO 字串）或 None。
    """
    state = _load_state()
    state["global_score"] *= 0.2
    now = time.strftime("%Y-%m-%dT%H:%M:%S%z", time.gmtime())
    # 格式化為 +08:00 形式
    now_formatted = now[:-2] + ":" + now[-2:]
    state["last_optimizer_run"] = now_formatted
    _save_state(state)
    return state["last_optimizer_run"]


def get_global_score() -> float:
    """取得當前 global_score（不修改）。"""
    state = _load_state()
    return state["global_score"]
