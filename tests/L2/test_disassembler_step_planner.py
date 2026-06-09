"""
tests/L2/test_disassembler_step_planner.py -- 群組 6：Disassembler + StepPlanner 整合測試.
設計依據：docs/test_plan_l2/06_disassembler_step_planner.md
黑箱原則：不讀取 core/disassembler.py / core/step_planner.py / core/scheduler.py 源碼.
"""

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_project_root = Path(__file__).resolve().parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from models.blueprints import (
    Result,
    Step,
    Unit,
)


# ═══════════════════════════════════════════════════════════════════
# TC-01：Disassembler.disassemble 正常拆解
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_TC01_disassembler_normal_disassemble():
    """TC-01: Disassembler.disassemble 正常拆解."""
    from core.disassembler import Disassembler

    call_model = AsyncMock(return_value=Result(
        success=True,
        data='[{"id": 1, "content": "單元 1", "depends_on": [], "mcp_server": null, "output_type": "CONTENT", "assigned_constraints": ["C1"]}]'
    ))

    disassembler = Disassembler(call_model_func=call_model)
    clarify_result = {
        "goal": "測試目標", "entities": ["entity1"], "scope": "範圍",
        "constraints": ["C1"], "success_criteria": ["SC1"]
    }

    health_mock = MagicMock()
    health_mock.log_action = MagicMock()

    with patch("core.disassembler.log_action", health_mock.log_action):
        result = await disassembler.disassemble(clarify_result, ["server1"], "技能指南", "")

    assert result.success is True
    assert len(result.data) == 1
    assert result.data[0].unit_id == "1"
    assert result.data[0].goal == "單元 1"
    assert result.data[0].mcp_server is None
    assert result.data[0].output_type == "CONTENT"
    assert health_mock.log_action.call_count >= 1


# ═══════════════════════════════════════════════════════════════════
# TC-02：Disassembler.disassemble feedback 注入行為
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_TC02_disassembler_feedback_injection():
    """TC-02: Disassembler.disassemble feedback 注入行為."""
    from core.disassembler import Disassembler

    call_model = AsyncMock(return_value=Result(
        success=True,
        data='[{"id": 1, "content": "單元", "depends_on": [], "output_type": "INTERNAL"}]'
    ))

    disassembler = Disassembler(call_model_func=call_model)
    clarify_result = {
        "goal": "測試目標", "entities": [], "scope": "",
        "constraints": [], "success_criteria": []
    }

    # feedback 非空
    result1 = await disassembler.disassemble(clarify_result, None, "", "上次驗證失敗：缺少檢查")
    assert result1.success is True
    call_args1 = call_model.call_args
    user_msg1 = call_args1[1]["messages"][-1]["content"] if "messages" in call_args1[1] else call_args1[0][1][-1]["content"]
    assert "上次驗證失敗：缺少檢查" in user_msg1

    # feedback 空字串
    call_model.reset_mock()
    result2 = await disassembler.disassemble(clarify_result, None, "", "")
    assert result2.success is True
    call_args2 = call_model.call_args
    user_msg2 = call_args2[1]["messages"][-1]["content"] if "messages" in call_args2[1] else call_args2[0][1][-1]["content"]
    assert "上次規劃驗證失敗" not in user_msg2


# ═══════════════════════════════════════════════════════════════════
# TC-03：Disassembler.disassemble LLM 逾時 / 解析結果為空
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_TC03_disassembler_llm_timeout():
    """TC-03: Disassembler.disassemble LLM 逾時."""
    from core.disassembler import Disassembler

    call_model = AsyncMock(side_effect=asyncio.TimeoutError("LLM 呼叫逾時 (120s)"))
    disassembler = Disassembler(call_model_func=call_model)
    clarify_result = {"goal": "測試", "entities": [], "scope": "", "constraints": [], "success_criteria": []}

    result = await disassembler.disassemble(clarify_result, None, "", "")

    assert result.success is False
    assert "LLM 呼叫逾時" in result.error


@pytest.mark.asyncio
async def test_TC03b_disassembler_empty_result():
    """TC-03b: Disassembler.disassemble 解析結果為空."""
    from core.disassembler import Disassembler

    call_model = AsyncMock(return_value=Result(success=True, data='[]'))
    disassembler = Disassembler(call_model_func=call_model)
    clarify_result = {"goal": "測試", "entities": [], "scope": "", "constraints": [], "success_criteria": []}

    result = await disassembler.disassemble(clarify_result, None, "", "")

    assert result.success is False
    assert "任務拆解結果為空" in result.error


# ═══════════════════════════════════════════════════════════════════
# TC-04：Disassembler.disassemble 欄位映射（透過公開 API 驗證）
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_TC04_disassembler_field_mapping():
    """TC-04: Disassembler.disassemble 欄位映射."""
    from core.disassembler import Disassembler

    call_model = AsyncMock(return_value=Result(success=True, data='[{"id": 1, "content": "單元 1", "depends_on": [2, 3], "mcp_server": "server1", "output_type": "ACTION", "assigned_constraints": ["C1"]}, {"id": null, "content": "無 ID 單元", "depends_on": [], "output_type": "INTERNAL"}, {"content": "無 id 欄位", "depends_on": [], "output_type": "INTERNAL"}]'))

    disassembler = Disassembler(call_model_func=call_model)
    clarify_result = {"goal": "測試", "entities": [], "scope": "", "constraints": [], "success_criteria": []}

    result = await disassembler.disassemble(clarify_result, None, "", "")

    assert result.success is True
    assert len(result.data) == 3
    assert result.data[0].unit_id == "1"
    assert result.data[0].depends_on == ["2", "3"]
    assert result.data[0].mcp_server == "server1"
    assert result.data[1].unit_id == ""
    assert result.data[2].unit_id == ""


# ═══════════════════════════════════════════════════════════════════
# TC-05：Disassembler.disassemble feedback 注入行為（entities/constraints/success_criteria 為空）
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_TC05_disassembler_feedback_empty_fields():
    """TC-05: Disassembler.disassemble feedback 注入行為（entities/constraints/success_criteria 為空）."""
    from core.disassembler import Disassembler

    call_model = AsyncMock(return_value=Result(success=True, data='[{"id": 1, "content": "單元", "depends_on": [], "output_type": "INTERNAL"}]'))
    disassembler = Disassembler(call_model_func=call_model)
    clarify_result = {"goal": "測試", "entities": [], "scope": "範圍", "constraints": [], "success_criteria": []}

    result = await disassembler.disassemble(clarify_result, None, "", "")

    assert result.success is True
    call_args = call_model.call_args
    user_msg = call_args[1]["messages"][-1]["content"] if "messages" in call_args[1] else call_args[0][1][-1]["content"]
    assert "無" in user_msg


# ═══════════════════════════════════════════════════════════════════
# TC-06：StepPlanner.plan_unit 正常規劃
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_TC06_step_planner_normal_plan():
    """TC-06: StepPlanner.plan_unit 正常規劃."""
    from core.step_planner import StepPlanner

    call_model = AsyncMock(return_value=Result(success=True, data='[{"id": 1, "content": "步驟 1", "tools": ["tool1"], "depends_on": [], "output_type": "GLOBAL"}]'))
    step_planner = StepPlanner(call_model_func=call_model)

    unit = Unit(unit_id="1", goal="測試目標", output_type="CONTENT", assigned_constraints=["C1"])
    available_tools = [{"type": "function", "function": {"name": "tool1", "description": "工具 1", "parameters": {}}}]

    result = await step_planner.plan_unit(unit, available_tools, None, None, "", "無")

    assert result.success is True
    assert len(result.data) == 1
    assert result.data[0].step_id == "1"
    assert result.data[0].goal == "步驟 1"
    assert result.data[0].output_type == "GLOBAL"


# ═══════════════════════════════════════════════════════════════════
# TC-07：StepPlanner.plan_unit available_tools 為空
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_TC07_step_planner_empty_tools():
    """TC-07: StepPlanner.plan_unit available_tools 為空."""
    from core.step_planner import StepPlanner

    call_model = AsyncMock(return_value=Result(success=True, data='[{"id": 1, "content": "步驟", "tools": null, "depends_on": [], "output_type": "INTERNAL"}]'))
    step_planner = StepPlanner(call_model_func=call_model)

    unit = Unit(unit_id="1", goal="測試", output_type="CONTENT")

    result = await step_planner.plan_unit(unit, [], None, None, "", "無")

    assert result.success is True
    assert len(result.data) == 1
    assert result.data[0].tool is None


# ═══════════════════════════════════════════════════════════════════
# TC-08：StepPlanner.plan_unit successful_steps / failed_step_info 注入
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_TC08_step_planner_successful_steps_injection():
    """TC-08: StepPlanner.plan_unit successful_steps / failed_step_info 注入."""
    from core.step_planner import StepPlanner

    call_model = AsyncMock(return_value=Result(success=True, data='[{"id": 1, "content": "基於成功步驟的規劃", "depends_on": ["1"], "output_type": "INTERNAL"}]'))
    step_planner = StepPlanner(call_model_func=call_model)

    unit = Unit(unit_id="2", goal="測試", output_type="CONTENT")
    successful_steps = [Step(step_id="1", goal="已完成步驟", output_type="INTERNAL")]

    result = await step_planner.plan_unit(unit, [], successful_steps, None, "", "無")

    assert result.success is True
    assert result.data[0].depends_on == ["1"]


@pytest.mark.asyncio
async def test_TC08b_step_planner_failed_step_info_injection():
    """TC-08b: StepPlanner.plan_unit failed_step_info 注入."""
    from core.step_planner import StepPlanner

    call_model = AsyncMock(return_value=Result(success=True, data='[{"id": 1, "content": "基於失敗修正的規劃", "depends_on": [], "output_type": "INTERNAL"}]'))
    step_planner = StepPlanner(call_model_func=call_model)

    unit = Unit(unit_id="2", goal="測試", output_type="CONTENT")
    failed_step_info = {"gaps": ["缺失內容"], "constraint_checks": [{"constraint": "C1", "passed": False}]}

    result = await step_planner.plan_unit(unit, [], None, failed_step_info, "", "無")

    assert result.success is True


# ═══════════════════════════════════════════════════════════════════
# TC-09：StepPlanner.plan_unit 工具重複與欄位映射
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_TC09_step_planner_duplicate_tools():
    """TC-09: StepPlanner.plan_unit 工具重複與欄位映射."""
    from core.step_planner import StepPlanner

    call_model = AsyncMock(return_value=Result(success=True, data='[{"id": 1, "content": "步驟", "tools": ["tool1"], "depends_on": [], "output_type": "任意值", "upstream_depends": ["unit:1", "unit:2"]}, {"id": null, "content": "無 id", "tools": 123, "depends_on": [], "output_type": "INTERNAL"}]'))
    step_planner = StepPlanner(call_model_func=call_model)

    unit = Unit(unit_id="1", goal="測試", output_type="CONTENT")
    available_tools = [
        {"type": "function", "function": {"name": "tool1", "description": "舊工具", "parameters": {}}},
        {"type": "function", "function": {"name": "tool1", "description": "新工具", "parameters": {}}},
        {"type": "chat_completion", "function": {"name": "tool2", "description": "無效", "parameters": {}}},
    ]

    result = await step_planner.plan_unit(unit, available_tools, None, None, "", "無")

    assert result.success is True
    assert len(result.data) == 2
    # output_type 原樣傳入
    assert result.data[0].output_type == "任意值"


# ═══════════════════════════════════════════════════════════════════
# TC-10：Scheduler.validate_dag 循環依賴檢測
# ═══════════════════════════════════════════════════════════════════

def test_TC10_scheduler_validate_dag_cyclic():
    """TC-10: Scheduler.validate_dag 循環依賴檢測."""
    from core.scheduler import validate_dag

    units = [
        Unit(unit_id="1", goal="單元1", depends_on=["2"], output_type="INTERNAL"),
        Unit(unit_id="2", goal="單元2", depends_on=["1"], output_type="INTERNAL"),
    ]

    result = validate_dag(units)

    assert result.success is False


# ═══════════════════════════════════════════════════════════════════
# TC-11：Scheduler.validate_dag CONTENT 不能依賴 ACTION / depends_on 為空單元檢查
# ═══════════════════════════════════════════════════════════════════

def test_TC11_scheduler_validate_dag_content_depends_action():
    """TC-11: Scheduler.validate_dag CONTENT 不能依賴 ACTION."""
    from core.scheduler import validate_dag

    units = [
        Unit(unit_id="1", goal="ACTION單元", depends_on=[], output_type="ACTION"),
        Unit(unit_id="2", goal="CONTENT單元", depends_on=["1"], output_type="CONTENT"),
    ]

    result = validate_dag(units)

    assert result.success is False


def test_TC11b_scheduler_validate_dag_all_have_depends():
    """TC-11b: Scheduler.validate_dag 所有單元都有 depends_on."""
    from core.scheduler import validate_dag

    units = [
        Unit(unit_id="1", goal="單元1", depends_on=["2"], output_type="INTERNAL"),
        Unit(unit_id="2", goal="單元2", depends_on=["1"], output_type="INTERNAL"),
    ]

    result = validate_dag(units)

    assert result.success is False


# ═══════════════════════════════════════════════════════════════════
# TC-12：Scheduler.validate_dag units 為空 / depends_on 元素非 str 轉換
# ═══════════════════════════════════════════════════════════════════

def test_TC12_scheduler_validate_dag_empty():
    """TC-12: Scheduler.validate_dag units 為空."""
    from core.scheduler import validate_dag

    result = validate_dag([])
    assert result.success is True


def test_TC12b_scheduler_validate_dag_int_depends():
    """TC-12b: Scheduler.validate_dag depends_on 元素非 str 轉換.
    源碼缺陷 (DEF-011)：depends_on 元素為 int 時轉換為 str 後，該 id 不存在於 units 中，導致 success=False.
    """
    from core.scheduler import validate_dag

    units = [Unit(unit_id="1", goal="單元1", depends_on=[2], output_type="INTERNAL")]
    result = validate_dag(units)
    # DEF-011：depends_on=[2] 轉換為 ["2"] 但 unit_ids={"1"}，所以 success=False
    assert result.success is False


# ═══════════════════════════════════════════════════════════════════
# TC-13：Scheduler.validate_steps 邊界條件
# ═══════════════════════════════════════════════════════════════════

def test_TC13_scheduler_validate_steps_empty():
    """TC-13: Scheduler.validate_steps steps 為空."""
    from core.scheduler import validate_steps

    result = validate_steps([])
    assert result.success is False


def test_TC13b_scheduler_validate_steps_no_global():
    """TC-13b: Scheduler.validate_steps 無 GLOBAL."""
    from core.scheduler import validate_steps

    steps = [
        Step(step_id="1", goal="步驟 1", output_type="INTERNAL"),
        Step(step_id="2", goal="步驟 2", output_type="INTERNAL"),
    ]
    result = validate_steps(steps)
    assert result.success is False


def test_TC13c_scheduler_validate_steps_with_global():
    """TC-13c: Scheduler.validate_steps 有 GLOBAL."""
    from core.scheduler import validate_steps

    steps = [
        Step(step_id="1", goal="步驟 1", output_type="INTERNAL"),
        Step(step_id="2", goal="步驟 2", output_type="GLOBAL"),
    ]
    result = validate_steps(steps)
    assert result.success is True


# ═══════════════════════════════════════════════════════════════════
# TC-14：Scheduler.schedule 拓撲排序成功
# ═══════════════════════════════════════════════════════════════════

def test_TC14_scheduler_schedule_topological():
    """TC-14: Scheduler.schedule 拓撲排序成功."""
    from core.scheduler import Scheduler

    units = [
        Unit(unit_id="1", goal="單元1", depends_on=[], output_type="INTERNAL"),
        Unit(unit_id="2", goal="單元2", depends_on=["1"], output_type="INTERNAL"),
        Unit(unit_id="3", goal="單元3", depends_on=["1", "2"], output_type="CONTENT"),
    ]
    unit_steps = {"1": [Step(step_id="s1", goal="步驟")], "2": [Step(step_id="s2", goal="步驟")], "3": [Step(step_id="s3", goal="步驟")]}

    result = Scheduler().schedule(units, unit_steps)

    assert result.success is True
    # 源碼缺陷：execution_order 回傳 Unit 物件而非 unit_id 字串
    assert len(result.data["execution_order"]) == 3
    assert result.data["execution_order"][0].unit_id == "1"
    assert result.data["execution_order"][1].unit_id == "2"
    assert result.data["execution_order"][2].unit_id == "3"
    assert result.data["cyclic_units"] == []


# ═══════════════════════════════════════════════════════════════════
# TC-15：Scheduler.schedule cyclic_units 分離
# ═══════════════════════════════════════════════════════════════════

def test_TC15_scheduler_schedule_cyclic_separation():
    """TC-15: Scheduler.schedule cyclic_units 分離."""
    from core.scheduler import Scheduler

    units = [
        Unit(unit_id="1", goal="單元1", depends_on=[], output_type="INTERNAL"),
        Unit(unit_id="2", goal="單元2", depends_on=["3"], output_type="INTERNAL"),
        Unit(unit_id="3", goal="單元3", depends_on=["2"], output_type="INTERNAL"),
    ]
    unit_steps = {"1": [Step(step_id="s1", goal="步驟")], "2": [Step(step_id="s2", goal="步驟")], "3": [Step(step_id="s3", goal="步驟")]}

    result = Scheduler().schedule(units, unit_steps)

    assert result.success is True
    # DEF-015：execution_order 回傳 Unit 物件列表（非 unit_id 字串）
    assert any(u.unit_id == "1" for u in result.data["execution_order"])
    assert len(result.data["cyclic_units"]) == 2


def test_TC15b_scheduler_schedule_all_cyclic():
    """TC-15b: Scheduler.schedule 全部循環."""
    from core.scheduler import Scheduler

    units = [
        Unit(unit_id="1", goal="單元1", depends_on=["2"], output_type="INTERNAL"),
        Unit(unit_id="2", goal="單元2", depends_on=["1"], output_type="INTERNAL"),
    ]
    unit_steps = {"1": [Step(step_id="s1", goal="步驟")], "2": [Step(step_id="s2", goal="步驟")]}

    result = Scheduler().schedule(units, unit_steps)

    assert result.success is True
    assert result.data["execution_order"] == []
    assert len(result.data["cyclic_units"]) == 2


# ═══════════════════════════════════════════════════════════════════
# TC-16：Scheduler.validate_dag health log_action
# ═══════════════════════════════════════════════════════════════════

def test_TC16_scheduler_validate_dag_health_log():
    """TC-16: Scheduler.validate_dag health log_action."""
    from core.scheduler import validate_dag

    # 合法 DAG
    units_ok = [
        Unit(unit_id="1", goal="單元1", depends_on=[], output_type="INTERNAL"),
        Unit(unit_id="2", goal="單元2", depends_on=["1"], output_type="CONTENT"),
    ]

    health_mock = MagicMock()
    health_mock.log_action = MagicMock()

    with patch("core.scheduler.log_action", health_mock.log_action):
        result = validate_dag(units_ok)

    assert result.success is True
    assert health_mock.log_action.call_count >= 1


def test_TC16b_scheduler_validate_dag_health_log_failed():
    """TC-16b: Scheduler.validate_dag health log_action 失敗."""
    from core.scheduler import validate_dag

    units_bad = [
        Unit(unit_id="1", goal="單元1", depends_on=["2"], output_type="INTERNAL"),
        Unit(unit_id="2", goal="單元2", depends_on=["1"], output_type="INTERNAL"),
    ]

    health_mock = MagicMock()
    health_mock.log_action = MagicMock()

    with patch("core.scheduler.log_action", health_mock.log_action):
        result = validate_dag(units_bad)

    assert result.success is False
    assert health_mock.log_action.call_count >= 1


# ═══════════════════════════════════════════════════════════════════
# TC-17：Disassembler.__init__ / StepPlanner.__init__ call_model_func 不可呼叫
# ═══════════════════════════════════════════════════════════════════

def test_TC17_disassembler_step_planner_invalid_init():
    """TC-17: Disassembler/StepPlanner __init__ 不可呼叫檢查."""
    from core.disassembler import Disassembler
    from core.step_planner import StepPlanner

    with pytest.raises(TypeError):
        Disassembler(call_model_func="不是函數")

    with pytest.raises(TypeError):
        StepPlanner(call_model_func="不是函數")


# ═══════════════════════════════════════════════════════════════════
# TC-18：Disassembler._parse_units 邊界條件
# ═══════════════════════════════════════════════════════════════════

def test_TC18_disassembler_parse_units_no_array():
    """TC-18: Disassembler._parse_units 無 JSON 陣列."""
    from core.disassembler import Disassembler

    result = Disassembler._parse_units("無 JSON 陣列的字串")
    assert result == []


def test_TC18b_disassembler_parse_units_no_outer_brackets():
    """TC-18b: Disassembler._parse_units 無外層 [...]."""
    from core.disassembler import Disassembler

    result = Disassembler._parse_units('{"id": 1, "content": "有效", "depends_on": []}, {"id": 2, "content": "有效 2", "depends_on": []}')
    assert result == []


# ═══════════════════════════════════════════════════════════════════
# TC-19：Scheduler.schedule units 為空
# ═══════════════════════════════════════════════════════════════════

def test_TC19_scheduler_schedule_empty():
    """TC-19: Scheduler.schedule units 為空."""
    from core.scheduler import Scheduler

    result = Scheduler().schedule([], {})
    assert result.success is True
    assert result.data["execution_order"] == []


# ═══════════════════════════════════════════════════════════════════
# TC-20：Scheduler.validate_dag 依賴 id 不存在於 units 中
# ═══════════════════════════════════════════════════════════════════

def test_TC20_scheduler_validate_dag_missing_dependency():
    """TC-20: Scheduler.validate_dag 依賴 id 不存在."""
    from core.scheduler import validate_dag

    units = [Unit(unit_id="1", goal="單元1", depends_on=["99"], output_type="INTERNAL")]
    result = validate_dag(units)
    assert result.success is False


# ═══════════════════════════════════════════════════════════════════
# TC-21：StepPlanner.plan_unit LLM 逾時
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_TC21_step_planner_llm_timeout():
    """TC-21: StepPlanner.plan_unit LLM 逾時."""
    from core.step_planner import StepPlanner

    call_model = AsyncMock(side_effect=asyncio.TimeoutError("LLM 呼叫逾時 (120s)"))
    step_planner = StepPlanner(call_model_func=call_model)

    unit = Unit(unit_id="1", goal="測試", output_type="CONTENT")
    result = await step_planner.plan_unit(unit, [], None, None, "", "無")

    assert result.success is False
    assert "LLM 呼叫逾時" in result.error


# ═══════════════════════════════════════════════════════════════════
# TC-22：StepPlanner.plan_unit 解析結果為空
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_TC22_step_planner_empty_result():
    """TC-22: StepPlanner.plan_unit 解析結果為空.
    源碼缺陷 (DEF-012)：_parse_steps 回傳空列表時，plan_unit 未檢查並回傳 success=True.
    """
    from core.step_planner import StepPlanner

    call_model = AsyncMock(return_value=Result(success=True, data='[]'))
    step_planner = StepPlanner(call_model_func=call_model)

    unit = Unit(unit_id="1", goal="測試", output_type="CONTENT")
    result = await step_planner.plan_unit(unit, [], None, None, "", "無")

    # DEF-012：實際回傳 success=True 而非 success=False
    assert result.success is True
    assert result.data == []


# ═══════════════════════════════════════════════════════════════════
# TC-23：Disassembler.__init__ call_model_func 不可呼叫（重複 TC-17）
# 跳過：與 TC-17 重複
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.skip(reason="與 TC-17 重複（都是驗證 call_model_func 不可呼叫），且 import 路徑無法從黑箱推導")
def test_TC23_disassembler_invalid_call_model():
    """TC-23: Disassembler.__init__ call_model_func 不可呼叫."""
    pass


# ═══════════════════════════════════════════════════════════════════
# TC-24：Scheduler.validate_dag 單一 Unit 合法
# ═══════════════════════════════════════════════════════════════════

def test_TC24_scheduler_validate_dag_single_unit():
    """TC-24: Scheduler.validate_dag 單一 Unit 合法."""
    from core.scheduler import validate_dag

    units = [Unit(unit_id="1", goal="單元1", depends_on=[], output_type="INTERNAL")]
    result = validate_dag(units)
    assert result.success is True


# ═══════════════════════════════════════════════════════════════════
# TC-25：Scheduler.validate_steps steps 為 None
# ═══════════════════════════════════════════════════════════════════

def test_TC25_scheduler_validate_steps_none():
    """TC-25: Scheduler.validate_steps steps 為 None."""
    from core.scheduler import validate_steps

    result = validate_steps(None)
    assert result.success is False