"""tests/L1/test_base -- 6 筆測試."""

import pytest


class TestSerializeToolCalls:
    """serialize_tool_calls 測試 (1-6)."""

    def test_serialize_tool_calls_dict_input(self):
        from clients.base import serialize_tool_calls

        tc_dict = {"function": {"name": "test"}}
        result = serialize_tool_calls([tc_dict])
        assert result == [tc_dict]

    def test_serialize_tool_calls_model_dump_input(self):
        from clients.base import serialize_tool_calls

        class MockObj:
            def model_dump(self):
                return {"dumped": True}

        result = serialize_tool_calls([MockObj()])
        assert result[0] == {"dumped": True}

    def test_serialize_tool_calls_dict_method_input(self):
        from clients.base import serialize_tool_calls

        class MockObj:
            def dict(self):
                return {"via_dict": True}

        result = serialize_tool_calls([MockObj()])
        assert result[0] == {"via_dict": True}

    def test_serialize_tool_calls_vars_input(self):
        from clients.base import serialize_tool_calls

        class MockObj:
            def __init__(self):
                self.x = 1
                self.y = 2

        result = serialize_tool_calls([MockObj()])
        assert result[0] == {"x": 1, "y": 2}

    def test_serialize_tool_calls_raw_string_input(self):
        from clients.base import serialize_tool_calls

        # 使用 __slots__ 讓物件沒有 __dict__
        class RawObj:
            __slots__ = ()
            def __str__(self):
                return "raw_str"

        result = serialize_tool_calls([RawObj()])
        assert result == [{"raw": "raw_str"}]

    def test_serialize_tool_calls_empty_list(self):
        from clients.base import serialize_tool_calls

        result = serialize_tool_calls([])
        assert result == []
