"""v2 tracer — 集中管理 trace 寫入.

依據 §4.3 (Logging) + §5.9 (ContextVar) 定義：
- 模型呼叫的輸入輸出，由 model_client 自動記錄
- 禁止 print（原則 13），改用 logger.error
- 本地 log 寫入不算 I/O（原則 6）
"""

import json
import logging
import time
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import config
from models.blueprints import UnitStatus, UnitResult

logger = logging.getLogger(__name__)

_session_id_var: ContextVar[Optional[str]] = ContextVar("session_id", default=None)


def new_session() -> str:
    """產生新的 session_id"""
    session_id = str(uuid.uuid4())
    _session_id_var.set(session_id)
    return session_id


def log_model_call(
    caller: Optional[str],
    model: str,
    messages: List[Dict[str, Any]],
    response: str,
    tool_calls: List[Any],
    unit_id: Optional[str] = None,
    step_id: Optional[str] = None,
) -> None:
    """將模型呼叫記錄寫入 logs/traces/{session_id}.jsonl（按 session 分檔）"""
    session_id = _session_id_var.get()
    trace_dir = Path(config.LOGS_DIR) / "traces"
    trace_path = trace_dir / f"{session_id}.jsonl"
    try:
        trace_dir.mkdir(parents=True, exist_ok=True)
        trace_entry = {
            "session_id": session_id,
            "ts": time.time(),
            "caller": caller,
            "model": model,
            "messages": messages,
            "response": response,
            "tool_calls": tool_calls,
            "unit_id": unit_id,
            "step_id": step_id,
        }
        with open(trace_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(trace_entry, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.error("[tracer] 寫入 trace 失敗: %s", e, exc_info=True)


def log_task(
    task_type: str,
    user_input: str,
    goal: str,
    results: Dict[str, Any],
    units: List[Any],
    clarifier_constraints: Optional[List[str]] = None,
    skill_version: Optional[int] = None,
) -> None:
    """將任務層 trace 寫入 task_trace.jsonl（append 模式），包含 session_id"""
    from models.blueprints import UnitStatus, UnitResult

    # 計算 final_status：任何 unit FAILED → failed，否則 success
    any_failed = any(
        r.status == UnitStatus.FAILED
        for r in _extract_unit_results(results)
    ) if results else False
    final_status = "failed" if any_failed else "success"

    # 提取 units 資訊
    unit_list = []
    for unit in units:
        uid = str(unit.unit_id)
        result = results.get(uid) if results else None
        unit_info = {
            "unit_id": uid,
            "goal": unit.goal,
            "status": _get_status_value(result),
            "output_type": unit.output_type,
            "error": _get_error(result),
            "replan_count": _get_replan_count(result),
            "total_loop_count": _get_total_loop_count(result),
            "step_loop_counts": _get_step_loop_counts(result),
            "constraint_checks": _get_constraint_checks(result),
            "assigned_constraints": getattr(unit, 'assigned_constraints', None) or [],
        }
        unit_list.append(unit_info)

    tz_tw = timedelta(hours=8)
    record = {
        "session_id": _session_id_var.get(),
        "task_id": str(uuid.uuid4()),
        "ts": datetime.now(timezone(tz_tw)).isoformat(),
        "task_type": task_type,
        "user_input": user_input,
        "goal": goal,
        "clarifier_constraints": clarifier_constraints or [],
        "skill_version": skill_version,
        "final_status": final_status,
        "units": unit_list,
    }

    task_trace_path = Path(getattr(config, 'TASK_TRACE_PATH', 'task_trace.jsonl'))
    try:
        task_trace_path.parent.mkdir(parents=True, exist_ok=True)
        with open(task_trace_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.error("[tracer] 寫入 task_trace.jsonl 失敗: %s", e, exc_info=True)


# ── 私有函式 ──

def _extract_unit_results(results: Dict[str, Any]) -> List[UnitResult]:
    """從 results dict 提取 UnitResult 物件列表"""
    results_list: List[UnitResult] = []
    for v in results.values():
        if isinstance(v, UnitResult):
            results_list.append(v)
    return results_list


def _get_status_value(result: Any) -> str:
    if result and result.status:
        return result.status.value
    return "UNKNOWN"


def _get_error(result: Any) -> str:
    if result and result.error:
        return result.error
    return ""


def _get_replan_count(result: Any) -> int:
    if result:
        return result.replan_count
    return 0


def _get_total_loop_count(result: Any) -> int:
    if result:
        return result.total_loop_count
    return 0


def _get_step_loop_counts(result: Any) -> List[int]:
	if result:
		return result.step_loop_counts
	return []


def _get_constraint_checks(result: Any) -> List[dict]:
	if result:
		return result.constraint_checks
	return []


class Tracer:
    """Tracer 類別封裝，供 model_client 注入使用。"""

    def log_model_call(
        self,
        caller: Optional[str],
        model: str,
        messages: List[Dict[str, Any]],
        response: str,
        tool_calls: List[Any],
        unit_id: Optional[str] = None,
        step_id: Optional[str] = None,
    ) -> None:
        log_model_call(caller, model, messages, response, tool_calls, unit_id, step_id)