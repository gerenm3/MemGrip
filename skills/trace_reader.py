"""
trace_reader.py
從 task_trace.jsonl 和 trace.jsonl 組裝 execution_record。
"""

import json
from collections import defaultdict
from pathlib import Path

from config import TASK_TRACE_PATH, TRACE_LOG_PATH


def _load_jsonl(path: str) -> list[dict]:
    """讀取 JSONL 檔案，回傳所有列的列表。"""
    p = Path(path)
    if not p.exists():
        return []
    results: list[dict] = []
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


def _extract_tool_calls_from_messages(messages: list[dict]) -> list[dict]:
    """從 messages 中提取 tool_calls（assistant 角色的 tool_calls）。"""
    tool_calls_list: list[dict] = []
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


def _extract_tool_results_from_messages(messages: list[dict]) -> list[str]:
    """從 messages 中提取 tool 回傳的結果（role="tool" 的 content）。"""
    results: list[str] = []
    for msg in messages:
        if msg.get("role") == "tool":
            content = msg.get("content", "")
            if content:
                results.append(content)
    return results


def _extract_last_assistant_response(messages: list[dict]) -> str:
    """從 messages 中提取最後一個 assistant 的 content（非 tool_calls）。"""
    last_content = ""
    for msg in messages:
        if msg.get("role") == "assistant":
            content = msg.get("content", "")
            if content:
                last_content = content
    return last_content


def build_execution_record(session_id: str) -> dict | None:
    """
    從 task_trace.jsonl 和 trace.jsonl 組裝 execution_record。
    回傳格式：
    {
      "task_type": "...",
      "goal": "...",
      "units": [
        {
          "unit_id": "1",
          "planned_goal": "...",
          "expected_output": "...",
          "actual_output": "...",
          "status": "...",
          "steps": [
            {
              "step_id": "1",
              "planned_goal": "...",
              "expected_output": "...",
              "agentic_loop": [
                {
                  "turn": 1,
                  "tool_called": "tool_name 或 null",
                  "tool_result": "...",
                  "output": "..."
                }
              ]
            }
          ]
        }
      ]
    }
    """
    # --- 1. 讀取資料 ---
    task_records = _load_jsonl(TASK_TRACE_PATH)
    trace_records = _load_jsonl(TRACE_LOG_PATH)

    # --- 2. 從 task_trace 找 session_id 對應的記錄 ---
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

    # --- 3. 過濾 trace 中對應 session_id 的記錄 ---
    session_traces = [t for t in trace_records if t.get("session_id") == session_id]

    # --- 4. 依 caller 分組 ---
    planner_l1_list = [t for t in session_traces if t.get("caller") == "planner_l1"]
    planner_l2_list = [t for t in session_traces if t.get("caller") == "planner_l2"]
    executor_list = [t for t in session_traces if t.get("caller") == "executor"]

    # --- 5. 解析 planner_l1 response 取得每個 unit 的 planned_goal 和 expected_output ---
    unit_planner_info: dict[str, dict] = {}
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

    # --- 6. 解析 planner_l2 response 並用 step count 對應到 unit ---
    # planner_l2 的 response 每個是一個 unit 的 steps，透過 step count 與 executor 的 step 數對應
    parsed_l2: list[dict] = []
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

    # 依 executor 的 step count 對 parsed_l2 排序（step count 大的排在前面）
    # 建立 (unit_id, step_count) 對應關係
    executor_unit_steps: dict[str, int] = {}
    for trace in executor_list:
        uid = str(trace.get("unit_id", ""))
        sid = str(trace.get("step_id", ""))
        executor_unit_steps[uid] = max(executor_unit_steps.get(uid, 0), int(sid) if sid.isdigit() else 0)

    # 將 parsed_l2 按 step count 排序，與 task_units 順序對應
    unit_steps_data: dict[str, list[dict]] = {}
    if parsed_l2 and executor_unit_steps:
        # 取得 executor unit_id 並依 step count 排序（大到小）
        sorted_unit_ids = sorted(
            executor_unit_steps.keys(),
            key=lambda x: executor_unit_steps[x],
            reverse=True,
        )

        # 將 parsed_l2 也依 step count 排序（大到小）
        sorted_l2 = sorted(parsed_l2, key=lambda x: len(x), reverse=True)

        # 一一對應
        for i, uid in enumerate(sorted_unit_ids):
            if i < len(sorted_l2):
                unit_steps_data[uid] = sorted_l2[i]

    # --- 7. 解析 executor 記錄 ---
    # 依 unit_id + step_id 分組
    executor_by_step: dict[str, list[dict]] = {}
    for trace in executor_list:
        uid = str(trace.get("unit_id", ""))
        sid = str(trace.get("step_id", ""))
        key = f"{uid}/{sid}"
        if key not in executor_by_step:
            executor_by_step[key] = []
        executor_by_step[key].append(trace)

    # --- 8. 組裝 execution record ---
    units_output = []

    for task_unit in task_units:
        unit_id = str(task_unit.get("unit_id", ""))
        status = task_unit.get("status", "unknown")
        output_type = task_unit.get("output_type", "")
        error = task_unit.get("error", "")
        actual_output = ""

        # planned_goal / expected_output（來自 planner_l1）
        planned_goal = ""
        expected_output = ""
        if unit_id in unit_planner_info:
            planned_goal = unit_planner_info[unit_id].get("planned_goal", "")
            expected_output = unit_planner_info[unit_id].get("expected_output", "")

        # steps
        steps_output = []
        if unit_id in unit_steps_data:
            for step_info in unit_steps_data[unit_id]:
                step_id = str(step_info.get("id", ""))

                # agentic_loop：從 executor_by_step 取對應的記錄
                step_key = f"{unit_id}/{step_id}"
                agentic_loop = []

                if step_key in executor_by_step:
                    traces_for_step = executor_by_step[step_key]
                    turn = 1
                    last_response = ""

                    for trace in traces_for_step:
                        # tool_called：若有 tool_calls 取第一個 tool 的 name
                        tool_calls = trace.get("tool_calls", [])
                        tool_called = None
                        if tool_calls and isinstance(tool_calls[0], dict) and tool_calls[0].get("name"):
                            tool_called = tool_calls[0]["name"]

                        # tool_result：從 messages 裡找 role=tool 的 content
                        tool_result = ""
                        for msg in trace.get("messages", []):
                            if msg.get("role") == "tool":
                                content = msg.get("content", "")
                                if content:
                                    tool_result = content
                                    break

                        # output：直接用 trace["response"]
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

                    # actual_output：取該 step 最後一筆 trace 記錄的 response
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

    return {
        "task_type": task_type,
        "goal": goal,
        "units": units_output,
    }
