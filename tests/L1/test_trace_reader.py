"""L1 test for TraceReader._extract_tool_calls_from_messages (module 30).

Black-box testing: only read docs/test_plan_l1/30_trace_reader.md and api_signatures.md.
No source code reading of skills/trace_reader.py.
"""

import pytest


class TestExtractToolCallsFromMessages:
    """TC-30-01 ~ TC-30-15: _extract_tool_calls_from_messages."""

    def _extract(self, messages):
        """Helper: call _extract_tool_calls_from_messages."""
        from skills.trace_reader import _extract_tool_calls_from_messages
        return _extract_tool_calls_from_messages(messages)

    def test_TC30_01_normal_tool_calls(self):
        """TC-30-01: _extract_tool_calls_from_messages - 正常 tool_calls。"""
        messages = [{"role": "assistant", "tool_calls": [{"function": {"name": "test", "arguments": "{}"}}]}]
        result = self._extract(messages)
        assert result == [{"name": "test", "arguments": "{}"}]

    def test_TC30_02_empty_list(self):
        """TC-30-02: _extract_tool_calls_from_messages - 空列表。"""
        result = self._extract([])
        assert result == []

    def test_TC30_03_role_not_assistant(self):
        """TC-30-03: _extract_tool_calls_from_messages - role 非 assistant。"""
        messages = [{"role": "user", "tool_calls": [{"function": {"name": "test", "arguments": "{}"}}]}]
        result = self._extract(messages)
        assert result == []

    def test_TC30_04_no_tool_calls_key(self):
        """TC-30-04: _extract_tool_calls_from_messages - 無 tool_calls 鍵。"""
        messages = [{"role": "assistant", "content": "hello"}]
        result = self._extract(messages)
        assert result == []

    def test_TC30_05_tool_calls_empty(self):
        """TC-30-05: _extract_tool_calls_from_messages - tool_calls 為空。"""
        messages = [{"role": "assistant", "tool_calls": []}]
        result = self._extract(messages)
        assert result == []

    def test_TC30_06_tc_not_dict(self):
        """TC-30-06: _extract_tool_calls_from_messages - tc 非 dict。"""
        messages = [{"role": "assistant", "tool_calls": ["not_a_dict"]}]
        result = self._extract(messages)
        assert result == []

    def test_TC30_07_tc_no_function_key(self):
        """TC-30-07: _extract_tool_calls_from_messages - tc 無 function 鍵。"""
        messages = [{"role": "assistant", "tool_calls": [{"name": "test"}]}]
        result = self._extract(messages)
        assert result == []

    def test_TC30_08_arguments_empty(self):
        """TC-30-08: _extract_tool_calls_from_messages - arguments 為空（預設 {}）。"""
        messages = [{"role": "assistant", "tool_calls": [{"function": {"name": "test"}}]}]
        result = self._extract(messages)
        assert result == [{"name": "test", "arguments": "{}"}]

    def test_TC30_09_arguments_dict(self):
        """TC-30-09: _extract_tool_calls_from_messages - arguments 為 dict。"""
        messages = [{"role": "assistant", "tool_calls": [{"function": {"name": "test", "arguments": {"key": "value"}}}]}]
        result = self._extract(messages)
        assert result == [{"name": "test", "arguments": {"key": "value"}}]

    def test_TC30_10_arguments_string(self):
        """TC-30-10: _extract_tool_calls_from_messages - arguments 為字串。"""
        messages = [{"role": "assistant", "tool_calls": [{"function": {"name": "test", "arguments": '{"key": "value"}'}}]}]
        result = self._extract(messages)
        assert result == [{"name": "test", "arguments": '{"key": "value"}'}]

    def test_TC30_11_multiple_tool_calls(self):
        """TC-30-11: _extract_tool_calls_from_messages - 多個 tool_calls。"""
        messages = [{"role": "assistant", "tool_calls": [
            {"function": {"name": "t1", "arguments": "{}"}},
            {"function": {"name": "t2", "arguments": "{}"}}
        ]}]
        result = self._extract(messages)
        assert result == [{"name": "t1", "arguments": "{}"}, {"name": "t2", "arguments": "{}"}]

    def test_TC30_12_mixed_role(self):
        """TC-30-12: _extract_tool_calls_from_messages - 混合 role。"""
        messages = [
            {"role": "user", "tool_calls": []},
            {"role": "assistant", "tool_calls": [{"function": {"name": "test", "arguments": "{}"}}]},
            {"role": "system", "tool_calls": []}
        ]
        result = self._extract(messages)
        assert result == [{"name": "test", "arguments": "{}"}]

    def test_TC30_13_tc_is_none(self):
        """TC-30-13: _extract_tool_calls_from_messages - tc 為 None。"""
        messages = [{"role": "assistant", "tool_calls": [None]}]
        result = self._extract(messages)
        assert result == []

    def test_TC30_14_arguments_is_none(self):
        """TC-30-14: _extract_tool_calls_from_messages - arguments 為 None（預設 {}）。

        DEF-006 修正：arguments 為 None 時轉換為 "{}"。
        """
        messages = [{"role": "assistant", "tool_calls": [{"function": {"name": "test", "arguments": None}}]}]
        result = self._extract(messages)
        assert result == [{"name": "test", "arguments": "{}"}]

    def test_TC30_15_multiple_assistant_messages(self):
        """TC-30-15: _extract_tool_calls_from_messages - 多筆 assistant 訊息。"""
        messages = [
            {"role": "assistant", "tool_calls": [{"function": {"name": "t1", "arguments": "{}"}}]},
            {"role": "user", "content": "ok"},
            {"role": "assistant", "tool_calls": [{"function": {"name": "t2", "arguments": "{}"}}]}
        ]
        result = self._extract(messages)
        assert result == [{"name": "t1", "arguments": "{}"}, {"name": "t2", "arguments": "{}"}]