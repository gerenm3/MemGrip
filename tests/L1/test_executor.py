"""Test plan L1 - Executor (#13)

Per api_signatures.md:
- __init__(call_model_func, execute_tool_func)
- execute(step, upstream_outputs, environment)
- _resolve_unit_placeholders(goal, upstream_outputs) — placeholder 格式改為 <unit:id>
- _build_tool_instruction(step) — tool 結構改為 {"function": {"name": "...}}，無 tool 回傳「本步驟為純推理，不得調用任何工具。」
- _build_user_messages(upstream_outputs) — 所有 upstream outputs 合併為單一 message
- _format_tool_call(tc)
- _parse_tool_arguments(raw)

Total: 26 test cases (TC-13-01 ~ TC-13-26)
"""

import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from core.executor import Executor
from models.blueprints import Step, Result


# ── Executor.__init__ ──

class TestExecutorInit:
    """TC-13-01, TC-13-01b"""

    def test_TC_13_01_init_normal(self):
        """TC-13-01: __init__ - 正常初始化"""
        mock_func = MagicMock()
        e = Executor(mock_func)
        assert e.call_model_func is mock_func

    def test_TC_13_01b_init_with_execute_tool(self):
        """TC-13-01b: __init__ - 帶 execute_tool_func"""
        mock_llm = MagicMock()
        mock_tool = MagicMock()
        e = Executor(mock_llm, mock_tool)
        assert e.call_model_func is mock_llm
        assert e.execute_tool_func is mock_tool


# ── Executor._resolve_unit_placeholders ──
# placeholder 格式改為 <unit:id>

class TestExecutorResolveUnitPlaceholders:
    """TC-13-02 ~ TC-13-05"""

    def test_TC_13_02_resolve_normal(self):
        """TC-13-02: _resolve_unit_placeholders - 正常替換"""
        goal = "Use <unit:output_1> to do X"
        upstream = {"output_1": "value1"}
        result = Executor._resolve_unit_placeholders(goal, upstream)
        assert "單元 output_1" in result

    def test_TC_13_03_resolve_no_placeholders(self):
        """TC-13-03: _resolve_unit_placeholders - 無 placeholder"""
        goal = "Just do X"
        upstream = {"output_1": "value1"}
        result = Executor._resolve_unit_placeholders(goal, upstream)
        assert result == "Just do X"

    def test_TC_13_04_resolve_missing_placeholder(self):
        """TC-13-04: _resolve_unit_placeholders - placeholder 不存在"""
        goal = "Use <unit:missing> to do X"
        upstream = {"output_1": "value1"}
        result = Executor._resolve_unit_placeholders(goal, upstream)
        assert "<unit:missing>" in result

    def test_TC_13_05_resolve_empty_upstream(self):
        """TC-13-05: _resolve_unit_placeholders - upstream 為空"""
        goal = "Use <unit:output_1> to do X"
        result = Executor._resolve_unit_placeholders(goal, {})
        assert "<unit:output_1>" in result


# ── Executor._build_tool_instruction ──
# tool 結構改為 {"function": {"name": "...}}，無 tool 回傳「本步驟為純推理，不得調用任何工具。」

class TestExecutorBuildToolInstruction:
    """TC-13-06 ~ TC-13-09"""

    def test_TC_13_06_build_tool_instruction_normal(self):
        """TC-13-06: _build_tool_instruction - 正常"""
        step = Step(step_id="1", goal="G", tool={"function": {"name": "read_file"}})
        result = Executor._build_tool_instruction(step)
        assert "read_file" in result

    def test_TC_13_07_build_tool_instruction_no_tool(self):
        """TC-13-07: _build_tool_instruction - 無 tool"""
        step = Step(step_id="1", goal="G", tool=None)
        result = Executor._build_tool_instruction(step)
        assert "本步驟為純推理，不得調用任何工具。" in result

    def test_TC_13_08_build_tool_instruction_tool_empty_dict(self):
        """TC-13-08: _build_tool_instruction - tool 為空 dict"""
        step = Step(step_id="1", goal="G", tool={})
        result = Executor._build_tool_instruction(step)
        assert "本步驟為純推理，不得調用任何工具。" in result

    def test_TC_13_09_build_tool_instruction_tool_no_function(self):
        """TC-13-09: _build_tool_instruction - tool 無 function"""
        step = Step(step_id="1", goal="G", tool={"description": "D"})
        result = Executor._build_tool_instruction(step)
        assert "使用工具 unknown" in result


# ── Executor._build_user_messages ──
# 所有 upstream outputs 合併為單一 message

class TestExecutorBuildUserMessages:
    """TC-13-10 ~ TC-13-13"""

    def test_TC_13_10_build_user_messages_normal(self):
        """TC-13-10: _build_user_messages - 正常（單一 message 合併所有 outputs）"""
        upstream = {"output_1": "value1", "output_2": "value2"}
        result = Executor._build_user_messages(upstream)
        assert isinstance(result, list)
        assert len(result) == 1

    def test_TC_13_11_build_user_messages_empty(self):
        """TC-13-11: _build_user_messages - 空 upstream"""
        result = Executor._build_user_messages({})
        assert result == []

    def test_TC_13_12_build_user_messages_one_item(self):
        """TC-13-12: _build_user_messages - 單一項目"""
        result = Executor._build_user_messages({"output_1": "v1"})
        assert len(result) == 1

    def test_TC_13_13_build_user_messages_format(self):
        """TC-13-13: _build_user_messages - 格式正確"""
        upstream = {"output_1": "value1"}
        result = Executor._build_user_messages(upstream)
        assert "output_1" in str(result)
        assert "value1" in str(result)


# ── Executor._format_tool_call ──

class TestExecutorFormatToolCall:
    """TC-13-14 ~ TC-13-17"""

    def test_TC_13_14_format_tool_call_normal(self):
        """TC-13-14: _format_tool_call - 正常"""
        tc = MagicMock()
        tc.function = MagicMock()
        tc.function.name = "read_file"
        tc.function.arguments = '{"path": "test"}'
        result = Executor._format_tool_call(tc)
        assert result is not None
        assert "name" in result

    def test_TC_13_15_format_tool_call_no_function(self):
        """TC-13-15: _format_tool_call - 無 function。

        DEF-001 修正：tc.function 為 None 時回傳 None。
        """
        tc = MagicMock()
        tc.function = None
        result = Executor._format_tool_call(tc)
        assert result is None

    def test_TC_13_16_format_tool_call_function_no_name(self):
        """TC-13-16: _format_tool_call - function 無 name。

        DEF-001 修正：func.name 為 None 時回傳 None。
        """
        tc = MagicMock()
        tc.function = MagicMock()
        tc.function.name = None
        result = Executor._format_tool_call(tc)
        assert result is None

    def test_TC_13_17_format_tool_call_function_no_arguments(self):
        """TC-13-17: _format_tool_call - function 無 arguments"""
        tc = MagicMock()
        tc.function = MagicMock()
        tc.function.name = "read_file"
        tc.function.arguments = None
        result = Executor._format_tool_call(tc)
        assert result is not None


# ── Executor._parse_tool_arguments ──

class TestExecutorParseToolArguments:
    """TC-13-18 ~ TC-13-21"""

    def test_TC_13_18_parse_tool_arguments_normal(self):
        """TC-13-18: _parse_tool_arguments - 正常"""
        result = Executor._parse_tool_arguments('{"path": "test"}')
        assert result["path"] == "test"

    def test_TC_13_19_parse_tool_arguments_empty_string(self):
        """TC-13-19: _parse_tool_arguments - 空字串"""
        result = Executor._parse_tool_arguments("")
        assert result == {}

    def test_TC_13_20_parse_tool_arguments_none(self):
        """TC-13-20: _parse_tool_arguments - None"""
        result = Executor._parse_tool_arguments(None)
        assert result == {}

    def test_TC_13_21_parse_tool_arguments_invalid_json(self):
        """TC-13-21: _parse_tool_arguments - 無效 JSON"""
        result = Executor._parse_tool_arguments("invalid")
        assert result == {}


# ── Executor.execute ──

class TestExecutorExecute:
    """TC-13-22 ~ TC-13-26"""

    @pytest.mark.asyncio
    async def test_TC_13_22_execute_normal(self):
        """TC-13-22: execute - 正常執行"""
        mock_llm = AsyncMock()
        mock_llm.return_value = Result(success=True, data="done")
        e = Executor(mock_llm)
        step = Step(step_id="1", goal="G")
        result = await e.execute(step, {})
        assert result.success is True

    @pytest.mark.asyncio
    async def test_TC_13_23_execute_timeout(self):
        """TC-13-23: execute - LLM 逾時"""
        mock_llm = AsyncMock()
        mock_llm.side_effect = asyncio.TimeoutError("timeout")
        e = Executor(mock_llm)
        step = Step(step_id="1", goal="G")
        result = await e.execute(step, {})
        assert result.success is False
        assert "逾時" in result.error

    @pytest.mark.asyncio
    async def test_TC_13_24_execute_llm_error(self):
        """TC-13-24: execute - LLM 錯誤"""
        mock_llm = AsyncMock()
        mock_llm.side_effect = Exception("LLM error")
        e = Executor(mock_llm)
        step = Step(step_id="1", goal="G")
        result = await e.execute(step, {})
        assert result.success is False
        assert result.error == "LLM error"

    @pytest.mark.asyncio
    async def test_TC_13_25_execute_upstream_placeholders(self):
        """TC-13-25: execute - upstream_outputs 替換"""
        mock_llm = AsyncMock()
        mock_llm.return_value = Result(success=True, data="done")
        e = Executor(mock_llm)
        step = Step(step_id="1", goal="Use <unit:output_1>")
        result = await e.execute(step, {"output_1": "replaced"})
        assert result.success is True
        mock_llm.assert_called()

    @pytest.mark.asyncio
    async def test_TC_13_26_execute_environment_param(self):
        """TC-13-26: execute - environment 參數"""
        mock_llm = AsyncMock()
        mock_llm.return_value = Result(success=True, data="done")
        e = Executor(mock_llm)
        step = Step(step_id="1", goal="G")
        result = await e.execute(step, {}, environment="prod")
        assert result.success is True