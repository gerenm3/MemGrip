"""Test plan L1 - StepPlanner (#12)

L1 scope (per l1_scope.md): _extract_function_tools, _parse_steps, _build_input
Also tests: __init__, plan_unit (via mock)

Total: 25 test cases (TC-12-01 ~ TC-12-25)
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from core.step_planner import StepPlanner
from models.blueprints import Unit, Step, Result


# ── StepPlanner.__init__ ──

class TestStepPlannerInit:
    """TC-12-01 ~ TC-12-02"""

    def test_TC_12_01_init_normal(self):
        """TC-12-01: __init__ - 正常初始化"""
        mock_func = MagicMock()
        sp = StepPlanner(mock_func)
        assert sp.call_model_func is mock_func

    def test_TC_12_02_init_not_callable(self):
        """TC-12-02: __init__ - call_model_func 不可呼叫"""
        with pytest.raises(TypeError):
            StepPlanner("not_callable")


# ── StepPlanner._extract_function_tools ──

class TestStepPlannerExtractFunctionTools:
    """TC-12-03 ~ TC-12-08"""

    def test_TC_12_03_extract_function_tools_normal(self):
        """TC-12-03: _extract_function_tools - 正常提取"""
        tools_list = [
            {"type": "function", "function": {"name": "read_file", "description": "R", "parameters": {}}}
        ]
        slim_tools, tool_map = StepPlanner._extract_function_tools(tools_list)
        assert len(slim_tools) == 1
        assert "read_file" in tool_map

    def test_TC_12_04_extract_function_tools_type_not_function(self):
        """TC-12-04: _extract_function_tools - type != "function" 跳過"""
        tools_list = [{"type": "image"}]
        slim_tools, tool_map = StepPlanner._extract_function_tools(tools_list)
        assert slim_tools == []
        assert tool_map == {}

    def test_TC_12_05_extract_function_tools_function_not_dict(self):
        """TC-12-05: _extract_function_tools - function 非 dict 跳過"""
        tools_list = [{"type": "function", "function": "not_a_dict"}]
        slim_tools, tool_map = StepPlanner._extract_function_tools(tools_list)
        assert slim_tools == []
        assert tool_map == {}

    def test_TC_12_06_extract_function_tools_name_missing(self):
        """TC-12-06: _extract_function_tools - name 不存在跳過"""
        tools_list = [{"type": "function", "function": {"description": "D", "parameters": {}}}]
        slim_tools, tool_map = StepPlanner._extract_function_tools(tools_list)
        assert slim_tools == []
        assert tool_map == {}

    def test_TC_12_07_extract_function_tools_duplicate_name(self):
        """TC-12-07: _extract_function_tools - 重複 tool name（實際行為：append 而非覆蓋）"""
        tools_list = [
            {"type": "function", "function": {"name": "t", "description": "A", "parameters": {}}},
            {"type": "function", "function": {"name": "t", "description": "B", "parameters": {}}}
        ]
        slim_tools, tool_map = StepPlanner._extract_function_tools(tools_list)
        # 實際行為：append 而非覆蓋，所以長度為 2
        assert len(slim_tools) == 2

    def test_TC_12_08_extract_function_tools_empty_list(self):
        """TC-12-08: _extract_function_tools - 空列表"""
        slim_tools, tool_map = StepPlanner._extract_function_tools([])
        assert slim_tools == []
        assert tool_map == {}


# ── StepPlanner._parse_steps ──

class TestStepPlannerParseSteps:
    """TC-12-09 ~ TC-12-16, TC-12-18, TC-12-19"""

    def test_TC_12_09_parse_steps_normal(self):
        """TC-12-09: _parse_steps - 正常解析（key: content）"""
        steps_data = [{"id": 1, "content": "G1", "output_type": "INTERNAL", "tools": "read_file"}]
        tool_map = {"read_file": {...}}
        result = StepPlanner._parse_steps(steps_data, tool_map)
        assert len(result) == 1
        assert isinstance(result[0], Step)
        assert result[0].step_id == "1"
        assert result[0].goal == "G1"
        assert result[0].output_type == "INTERNAL"

    def test_TC_12_10_parse_steps_element_not_dict(self):
        """TC-12-10: _parse_steps - element 非 dict 跳過"""
        steps_data = ["string_element", {"id": 2, "content": "G2", "output_type": "INTERNAL"}]
        tool_map = {}
        result = StepPlanner._parse_steps(steps_data, tool_map)
        assert len(result) == 1
        assert result[0].step_id == "2"
        assert result[0].goal == "G2"

    def test_TC_12_11_parse_steps_tools_not_str_or_none(self):
        """TC-12-11: _parse_steps - tools 非 str/None 記錄 warning"""
        steps_data = [{"id": 1, "content": "G1", "output_type": "INTERNAL", "tools": 123}]
        tool_map = {}
        result = StepPlanner._parse_steps(steps_data, tool_map)
        assert len(result) == 1
        assert result[0].tool is None

    def test_TC_12_12_parse_steps_tool_not_registered(self):
        """TC-12-12: _parse_steps - tool 未註冊記錄 warning + DEGRADED"""
        steps_data = [{"id": 1, "content": "G1", "output_type": "INTERNAL", "tools": "unknown_tool"}]
        tool_map = {}
        result = StepPlanner._parse_steps(steps_data, tool_map)
        assert len(result) == 1
        assert result[0].tool is None

    def test_TC_12_13_parse_steps_output_type_no_validation(self):
        """TC-12-13: _parse_steps - output_type 無驗證"""
        steps_data = [{"id": 1, "content": "G1", "output_type": "INVALID_VALUE"}]
        tool_map = {}
        result = StepPlanner._parse_steps(steps_data, tool_map)
        assert result[0].output_type == "INVALID_VALUE"

    def test_TC_12_14_parse_steps_id_is_none(self):
        """TC-12-14: _parse_steps - id 為 None"""
        steps_data = [{"content": "G1", "output_type": "INTERNAL", "id": None}]
        tool_map = {}
        result = StepPlanner._parse_steps(steps_data, tool_map)
        assert result[0].step_id == "None"

    def test_TC_12_15_parse_steps_id_missing(self):
        """TC-12-15: _parse_steps - id 不存在"""
        steps_data = [{"content": "G1", "output_type": "INTERNAL"}]
        tool_map = {}
        result = StepPlanner._parse_steps(steps_data, tool_map)
        assert result[0].step_id == ""

    def test_TC_12_16_parse_steps_default_output_type(self):
        """TC-12-16: _parse_steps - 預設 output_type INTERNAL"""
        steps_data = [{"id": 1, "content": "G1"}]
        tool_map = {}
        result = StepPlanner._parse_steps(steps_data, tool_map)
        assert result[0].output_type == "INTERNAL"

    def test_TC_12_18_parse_steps_depends_on_int(self):
        """TC-12-18: _parse_steps - depends_on 元素為 int"""
        steps_data = [{"id": 1, "content": "G1", "depends_on": [1, 2]}]
        tool_map = {}
        result = StepPlanner._parse_steps(steps_data, tool_map)
        assert result[0].depends_on == ["1", "2"]

    def test_TC_12_19_parse_steps_upstream_depends_prefix(self):
        """TC-12-19: _parse_steps - upstream_depends 去除 "unit:" 前綴"""
        steps_data = [{"id": 1, "content": "G1", "upstream_depends": ["unit:1", "unit:2", "3"]}]
        tool_map = {}
        result = StepPlanner._parse_steps(steps_data, tool_map)
        assert result[0].upstream_depends == ["1", "2", "3"]


# ── StepPlanner._build_input ──

class TestStepPlannerBuildInput:
    """TC-12-17, TC-12-20, TC-12-21"""

    def test_TC_12_17_build_input_normal(self):
        """TC-12-17: _build_input - unit 正常"""
        unit = Unit(unit_id="1", goal="G", expected_input="E", expected_output="O")
        result = StepPlanner._build_input(unit, None, None)
        assert "單元目標" in result
        assert "預期輸入" in result
        assert "預期輸出" in result

    def test_TC_12_20_build_input_failed_step_info_missing_gaps(self):
        """TC-12-20: _build_input - failed_step_info 缺 gaps"""
        unit = Unit(unit_id="1", goal="G")
        failed_step_info = {"constraint_checks": ["C1"]}
        result = StepPlanner._build_input(unit, None, failed_step_info)
        # Should not inject gaps block
        assert "GAP" not in result

    def test_TC_12_21_build_input_failed_step_info_missing_constraint_checks(self):
        """TC-12-21: _build_input - failed_step_info 缺 constraint_checks"""
        unit = Unit(unit_id="1", goal="G")
        failed_step_info = {"gaps": ["G1"]}
        result = StepPlanner._build_input(unit, None, failed_step_info)
        # Should not inject constraint_checks block
        assert "CONSTRAINT" not in result


# ── StepPlanner.plan_unit ──

class TestStepPlannerPlanUnit:
    """TC-12-22 ~ TC-12-25"""

    @pytest.mark.asyncio
    async def test_TC_12_22_plan_unit_normal(self):
        """TC-12-22: plan_unit - 正常規劃"""
        mock_llm = AsyncMock()
        mock_llm.return_value = Result(
            success=True,
            data='[{"id": 1, "content": "G1", "output_type": "INTERNAL", "tools": "read_file"}]'
        )
        sp = StepPlanner(mock_llm)
        unit = Unit(unit_id="1", goal="G")
        result = await sp.plan_unit(unit, [])
        assert result.success is True
        assert len(result.data) == 1

    @pytest.mark.asyncio
    async def test_TC_12_23_plan_unit_timeout(self):
        """TC-12-23: plan_unit - LLM 逾時"""
        mock_llm = AsyncMock()
        mock_llm.side_effect = asyncio.TimeoutError("timeout")
        sp = StepPlanner(mock_llm)
        unit = Unit(unit_id="1", goal="G")
        result = await sp.plan_unit(unit, [])
        assert result.success is False
        assert "逾時" in result.error

    @pytest.mark.asyncio
    async def test_TC_12_24_plan_unit_available_tools_empty(self):
        """TC-12-24: plan_unit - available_tools 為空"""
        mock_llm = AsyncMock()
        mock_llm.return_value = Result(success=True, data='[{"id": 1, "content": "G1", "output_type": "INTERNAL"}]')
        sp = StepPlanner(mock_llm)
        unit = Unit(unit_id="1", goal="G")
        result = await sp.plan_unit(unit, [])
        assert result.success is True

    @pytest.mark.asyncio
    async def test_TC_12_25_plan_unit_empty_result(self):
        """TC-12-25: plan_unit - 解析結果為空"""
        mock_llm = AsyncMock()
        mock_llm.return_value = Result(success=True, data="")
        sp = StepPlanner(mock_llm)
        unit = Unit(unit_id="1", goal="G")
        result = await sp.plan_unit(unit, [])
        assert result.success is False
        assert "為空" in result.error