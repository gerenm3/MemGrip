"""Tracer — 集中管理 trace 寫入"""

import json
import time
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
from config import TRACE_LOG_PATH, TASK_TRACE_PATH


current_session_id: Optional[str] = None


def new_session() -> str:
    global current_session_id
    current_session_id = str(uuid.uuid4())
    return current_session_id


def log_model_call(
    caller: Optional[str],
    model: str,
    messages: List[Dict[str, Any]],
    response: str,
    tool_calls: List[Any],
    unit_id: Optional[str] = None,
    step_id: Optional[str] = None,
) -> None:
    """將模型呼叫記錄寫入 trace.jsonl"""
    trace_entry = {
        "session_id": current_session_id,
        "ts": time.time(),
        "caller": caller,
        "model": model,
        "messages": messages,
        "response": response,
        "tool_calls": tool_calls,
        "unit_id": unit_id,
        "step_id": step_id,
    }

    try:
        with open(TRACE_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(trace_entry, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"[Tracer.log_model_call] 寫入 trace.jsonl 失敗: {e}")


def log_task(
    task_type: str,
    user_input: str,
    goal: str,
    results: Dict[str, Any],
    units: List[Any],
) -> None:
    """將任務層 trace 寫入 task_trace.jsonl（append 模式），包含 session_id"""
    from models.blueprints import UnitStatus

    # 計算 final_status：任何 unit FAILED → failed，否則 success
    any_failed = any(r.status == UnitStatus.FAILED for r in results.values()) if results else False
    final_status = "failed" if any_failed else "success"

    # 提取 units 資訊
    unit_list = []
    for unit in units:
        uid = str(unit.unit_id)
        result = results.get(uid) if results else None
        unit_info = {
            "unit_id": uid,
            "goal": unit.goal,
            "status": result.status.value if result and result.status else "UNKNOWN",
            "output_type": unit.output_type,
            "error": result.error if result and result.error else "",
            "replan_count": result.replan_count if result else 0,
            "total_loop_count": result.total_loop_count if result else 0,
            "step_loop_counts": result.step_loop_counts if result else [],
        }
        unit_list.append(unit_info)

    tz_tw = timedelta(hours=8)
    record = {
        "session_id": current_session_id,
        "task_id": str(uuid.uuid4()),
        "ts": datetime.now(timezone(tz_tw)).isoformat(),
        "task_type": task_type,
        "user_input": user_input,
        "goal": goal,
        "final_status": final_status,
        "units": unit_list,
    }

    try:
        with open(TASK_TRACE_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"[Tracer.log_task] 寫入 task_trace.jsonl 失敗: {e}")
