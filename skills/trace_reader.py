"""trace_reader — 從 task_trace.jsonl 和 trace.jsonl 組裝 execution_record.

符合 logging 規範
"""

import json
import logging
from pathlib import Path

import config

logger = logging.getLogger(__name__)


def _load_jsonl(path: str) -> list:
    """讀取 JSONL 檔案，回傳所有列的列表."""
    p = Path(path)
    if not p.exists():
        return []
    results = []
    with p.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                results.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return results


def _extract_tool_calls_from_messages(messages: list) -> list:
    """從 messages 中提取 tool_calls."""
    tool_calls_list = []
    for msg in messages:
        if msg.get("role") == "assistant" and msg.get("tool_calls"):
            for tc in msg["tool_calls"]:
                if isinstance(tc, dict) and tc.get("function"):
                    func = tc["function"]
                    tool_calls_list.append({
                        "name": func.get("name"),
                        "arguments": func.get("arguments", "{}"),
                    })
    return tool_calls_list


def build_execution_record(session_id: str) -> dict | None:
    """從 task_trace.jsonl 和 trace.jsonl 組裝 execution_record."""
    task_records = _load_jsonl(config.TASK_TRACE_PATH)
    trace_records = _load_jsonl(config.TRACE_LOG_PATH)

    task_record = None
    for rec in task_records:
        if rec.get("session_id") == session_id:
            task_record = rec
            break

    if not task_record:
        return None

    task_type = task_record.get("task_type", "")
    goal = task_record.get("goal", "")
    task_units = task_record.get("units", [])

    session_traces = [t for t in trace_records if t.get("session_id") == session_id]

    planner_l1_list = [t for t in session_traces if t.get("caller") == "planner_l1"]
    planner_l2_list = [t for t in session_traces if t.get("caller") == "planner_l2"]
    executor_list = [t for t in session_traces if t.get("caller") == "executor"]

    unit_planner_info = {}
    for trace in planner_l1_list:
        resp = trace.get("response", "")
        if not resp:
            continue
        try:
            units_data = json.loads(resp)
            if isinstance(units_data, list):
                for u in units_data:
                    uid = str(u.get("id", ""))
                    unit_planner_info[uid] = {
                        "planned_goal": u.get("content", ""),
                        "expected_output": u.get("expected_output", ""),
                    }
        except json.JSONDecodeError:
            continue

    parsed_l2 = []
    for trace in planner_l2_list:
        resp = trace.get("response", "")
        if not resp:
            continue
        try:
            steps_data = json.loads(resp)
            if isinstance(steps_data, list) and steps_data:
                parsed_l2.append(steps_data)
        except json.JSONDecodeError:
            continue

    executor_unit_steps = {}
    for trace in executor_list:
        uid = str(trace.get("unit_id", ""))
        sid = str(trace.get("step_id", ""))
        executor_unit_steps[uid] = max(executor_unit_steps.get(uid, 0), int(sid) if sid.isdigit() else 0)

    unit_steps_data = {}
    if parsed_l2 and executor_unit_steps:
        sorted_unit_ids = sorted(
            executor_unit_steps.keys(),
            key=lambda x: executor_unit_steps[x],
            reverse=True,
        )
        sorted_l2 = sorted(parsed_l2, key=lambda x: len(x), reverse=True)
        for i, uid in enumerate(sorted_unit_ids):
            if i < len(sorted_l2):
                unit_steps_data[uid] = sorted_l2[i]

    executor_by_step = {}
    for trace in executor_list:
        uid = str(trace.get("unit_id", ""))
        sid = str(trace.get("step_id", ""))
        key = f"{uid}/{sid}"
        if key not in executor_by_step:
            executor_by_step[key] = []
        executor_by_step[key].append(trace)

    units_output = []
    for task_unit in task_units:
        unit_id = str(task_unit.get("unit_id", ""))
        status = task_unit.get("status", "unknown")
        output_type = task_unit.get("output_type", "")
        error = task_unit.get("error", "")
        actual_output = ""

        planned_goal = ""
        expected_output = ""
        if unit_id in unit_planner_info:
            planned_goal = unit_planner_info[unit_id].get("planned_goal", "")
            expected_output = unit_planner_info[unit_id].get("expected_output", "")

        steps_output = []
        if unit_id in unit_steps_data:
            for step_info in unit_steps_data[unit_id]:
                step_id = str(step_info.get("id", ""))
                step_key = f"{unit_id}/{step_id}"
                agentic_loop = []

                if step_key in executor_by_step:
                    traces_for_step = executor_by_step[step_key]
                    turn = 1
                    last_response = ""
                    for trace in traces_for_step:
                        tool_calls = trace.get("tool_calls", [])
                        tool_called = None
                        if tool_calls and isinstance(tool_calls[0], dict) and tool_calls[0].get("name"):
                            tool_called = tool_calls[0]["name"]
                        tool_result = ""
                        for msg in trace.get("messages", []):
                            if msg.get("role") == "tool":
                                content = msg.get("content", "")
                                if content:
                                    tool_result = content
                                    break
                        output = trace.get("response", "")
                        if output:
                            last_response = output
                        agentic_loop.append({
                            "turn": turn,
                            "tool_called": tool_called,
                            "tool_result": tool_result,
                            "output": output,
                        })
                        turn += 1
                    if traces_for_step:
                        actual_output = last_response

                steps_output.append({
                    "step_id": step_id,
                    "planned_goal": step_info.get("content", ""),
                    "expected_output": step_info.get("expected_output", ""),
                    "agentic_loop": agentic_loop,
                })

        units_output.append({
            "unit_id": unit_id,
            "planned_goal": planned_goal,
            "expected_output": expected_output,
            "actual_output": actual_output,
            "status": status,
            "output_type": output_type,
            "error": error,
            "steps": steps_output,
        })

    # ── 聚合指標計算 ──
    unit_count = len(task_units)
    total_replan = sum(u.get("replan_count", 0) for u in task_units)
    failed_units = sum(1 for u in task_units if u.get("status") == "FAILED")
    total_loop = sum(u.get("total_loop_count", 0) for u in task_units)
    avg_loop_count = total_loop / unit_count if unit_count > 0 else 0

    # constraint 滿足率
    total_checks = 0
    satisfied_checks = 0
    constraint_details = []
    for u in task_units:
        checks = u.get("constraint_checks", [])
        assigned = u.get("assigned_constraints", [])
        for c in checks:
            if isinstance(c, dict):
                total_checks += 1
                if c.get("satisfied") is True:
                    satisfied_checks += 1
                constraint_details.append({
                    "unit_id": u.get("unit_id", ""),
                    "constraint": c.get("constraint", ""),
                    "satisfied": c.get("satisfied", False),
                })

    constraint_satisfied_ratio = satisfied_checks / total_checks if total_checks > 0 else 1.0

    # verifier_pass_ratio: 從 trace.jsonl 統計 executor_verify 的 passed=true 比例
    verifier_pass = 0
    verifier_total = 0
    for t in session_traces:
        if t.get("caller") == "executor_verify":
            verifier_total += 1
            msgs = t.get("messages", [])
            for msg in msgs:
                content = msg.get("content", "")
                if not isinstance(content, str):
                    continue
                try:
                    # 使用 parse_first_json 正確解析 JSON（而非子字串匹配）
                    from core.json_utils import parse_first_json
                    obj = parse_first_json(content)
                    if isinstance(obj, dict) and obj.get("passed") is True:
                        verifier_pass += 1
                except Exception:
                    pass
                    break

    verifier_pass_ratio = verifier_pass / verifier_total if verifier_total > 0 else 1.0

    return {
        "task_type": task_type,
        "goal": goal,
        "units": units_output,
        # 聚合指標
        "unit_count": unit_count,
        "replan_count": total_replan,
        "failed_units": failed_units,
        "avg_loop_count": avg_loop_count,
        "constraint_satisfied_ratio": constraint_satisfied_ratio,
        "verifier_pass_ratio": verifier_pass_ratio,
        "constraint_details": constraint_details,
    }
