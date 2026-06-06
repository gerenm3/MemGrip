"""tests/L1/test_executor_logic.py — core/executor.py 純邏輯測試（18 筆）."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from models.blueprints import Step


class TestResolvePlaceholders:
    """Executor._resolve_unit_placeholders 測試."""

    def test_existing_unit(self):
        """等價類：<unit:1> → '單元 1'."""
        from core.executor import Executor
        result = Executor._resolve_unit_placeholders("goal <unit:1>", {"1": "單元 1"})
        assert "單元 1" in result

    def test_missing_unit(self):
        """等價類：<unit:99> → '上游單元 99 未執行，無可用輸出'."""
        from core.executor import Executor
        result = Executor._resolve_unit_placeholders("goal <unit:99>", {})
        assert "上游單元 99 未執行" in result

    def test_mixed(self):
        """等價類：部分存在部分缺失."""
        from core.executor import Executor
        result = Executor._resolve_unit_placeholders(
            "goal <unit:1> and <unit:99>",
            {"1": "單元 1"}
        )
        assert "單元 1" in result
        assert "上游單元 99 未執行" in result

    def test_no_placeholder(self):
        """邊界：無 placeholder → 原文."""
        from core.executor import Executor
        result = Executor._resolve_unit_placeholders("plain goal", {})
        assert result == "plain goal"


class TestBuildToolInstruction:
    """Executor._build_tool_instruction 測試."""

    def test_with_tool(self, make_step):
        """等價類：有 tool → 包含 tool name/desc/params."""
        from core.executor import Executor
        step = make_step(tool={"function": {"name": "test_tool", "description": "desc", "parameters": {}}})
        result = Executor._build_tool_instruction(step)
        assert "test_tool" in result
        assert "desc" in result

    def test_no_tool(self, make_step):
        """邊界：tool=None → '本步驟為純推理'."""
        from core.executor import Executor
        step = make_step(tool=None)
        result = Executor._build_tool_instruction(step)
        assert "純推理" in result

    def test_dict_tool(self, make_step):
        """等價類：tool 為 dict 格式."""
        from core.executor import Executor
        step = make_step(tool={"function": {"name": "tool2", "description": "desc2", "parameters": {}}})
        result = Executor._build_tool_instruction(step)
        assert "tool2" in result


class TestBuildUserMessages:
    """Executor._build_user_messages 測試."""

    def test_normal(self):
        """等價類：有 upstream → 回傳 user message."""
        from core.executor import Executor
        result = Executor._build_user_messages({"1": "output1"})
        assert isinstance(result, list)
        assert len(result) > 0

    def test_empty(self):
        """邊界：空 dict → []."""
        from core.executor import Executor
        result = Executor._build_user_messages({})
        assert result == []

    def test_multiple(self):
        """等價類：多個 upstream → 合併為 [來自上游 N]."""
        from core.executor import Executor
        result = Executor._build_user_messages({"1": "out1", "2": "out2"})
        assert isinstance(result, list)
        assert len(result) == 1
        assert "來自上游" in result[0]["content"]


class TestFormatToolCall:
    """Executor._format_tool_call 測試."""

    def test_function_attr(self):
        """等價類：tc.function 屬性."""
        from core.executor import Executor
        tc = type('obj', (object,), {'function': type('obj', (object,), {'name': 'test', 'arguments': '{}'})()})()
        result = Executor._format_tool_call(tc)
        assert result is not None
        assert result["name"] == "test"

    def test_dict(self):
        """等價類：tc 為 dict."""
        from core.executor import Executor
        tc = {"function": {"name": "test", "arguments": "{}"}}
        result = Executor._format_tool_call(tc)
        assert result is not None
        assert result["name"] == "test"

    def test_none_name(self):
        """邊界：name 空 → None."""
        from core.executor import Executor
        tc = {"function": {"name": None, "arguments": "{}"}}
        result = Executor._format_tool_call(tc)
        assert result is None

    def test_invalid_type(self):
        """等價類：無效類型 → None."""
        from core.executor import Executor
        result = Executor._format_tool_call(None)
        assert result is None


class TestParseToolArguments:
    """Executor._parse_tool_arguments 測試."""

    def test_dict(self):
        """等價類：dict → 原樣回傳."""
        from core.executor import Executor
        result = Executor._parse_tool_arguments({"key": "value"})
        assert result == {"key": "value"}

    def test_json_string(self):
        """等價類：JSON str → 解析為 dict."""
        from core.executor import Executor
        result = Executor._parse_tool_arguments('{"key": "value"}')
        assert result == {"key": "value"}

    def test_invalid_string(self):
        """等價類：無效 str → {}."""
        from core.executor import Executor
        result = Executor._parse_tool_arguments("not json")
        assert result == {}

    def test_none(self):
        """邊界：None → {}."""
        from core.executor import Executor
        result = Executor._parse_tool_arguments(None)
        assert result == {}