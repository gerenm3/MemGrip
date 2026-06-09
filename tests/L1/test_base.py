"""L1 test for serialize_tool_calls (module 22) - clients/base.py.

Black-box testing: only read docs/test_plan_l1/22_base_serialize_tool_calls.md and api_signatures.md.
No source code reading of clients/base.py.
"""

import pytest
from unittest.mock import MagicMock
from clients.base import serialize_tool_calls


class TestSerializeToolCallsNone:
    """TC-22-01: serialize_tool_calls - None."""

    def test_TC22_01_serialize_tool_calls_none(self):
        result = serialize_tool_calls(None)
        assert result == []


class TestSerializeToolCallsEmptyList:
    """TC-22-02: serialize_tool_calls - empty list."""

    def test_TC22_02_serialize_tool_calls_empty_list(self):
        result = serialize_tool_calls([])
        assert result == []


class TestSerializeToolCallsDict:
    """TC-22-03: serialize_tool_calls - dict type."""

    def test_TC22_03_serialize_tool_calls_dict(self):
        tool_calls = [{"name": "read_file", "arguments": {"path": "test"}}]
        result = serialize_tool_calls(tool_calls)
        assert result == [{"name": "read_file", "arguments": {"path": "test"}}]


class TestSerializeToolCallsModelDump:
    """TC-22-04: serialize_tool_calls - model_dump type.

    MagicMock has model_dump by default, so it matches first.
    """

    def test_TC22_04_serialize_tool_calls_model_dump(self):
        mock_obj = MagicMock()
        mock_obj.model_dump.return_value = {"name": "f", "arguments": "{}"}
        result = serialize_tool_calls([mock_obj])
        assert result == [{"name": "f", "arguments": "{}"}]


class TestSerializeToolCallsDictMethod:
    """TC-22-05: serialize_tool_calls - dict() method type.

    Use a plain class without model_dump to trigger dict() path.
    """

    def test_TC22_05_serialize_tool_calls_dict_method(self):
        class DictMethodObj:
            def dict(self):
                return {"name": "f", "arguments": "{}"}

        result = serialize_tool_calls([DictMethodObj()])
        assert result == [{"name": "f", "arguments": "{}"}]


class TestSerializeToolCallsDictAttr:
    """TC-22-06: serialize_tool_calls - __dict__ type.

    Use a plain class without model_dump or dict to trigger __dict__ path.
    """

    def test_TC22_06_serialize_tool_calls_dict_attr(self):
        class DictAttrObj:
            __dict__ = {"name": "f", "arguments": "{}"}

        result = serialize_tool_calls([DictAttrObj()])
        assert result == [{"name": "f", "arguments": "{}"}]


class TestSerializeToolCallsFallback:
    """TC-22-07: serialize_tool_calls - fallback type.

    Use a class without model_dump, dict, or __dict__.
    """

    def test_TC22_07_serialize_tool_calls_fallback(self):
        class FallbackObj:
            __slots__ = ()
            def __str__(self):
                return "MockObject(1)"

        result = serialize_tool_calls([FallbackObj()])
        assert result == [{"raw": "MockObject(1)"}]


class TestSerializeToolCallsMixedTypes:
    """TC-22-08: serialize_tool_calls - mixed types."""

    def test_TC22_08_serialize_tool_calls_mixed_types(self):
        # dict type
        dict_obj = {"name": "f1", "arguments": "a"}
        # model_dump type (MagicMock)
        mock_md = MagicMock()
        mock_md.model_dump.return_value = {"name": "f2", "arguments": "b"}
        # __dict__ type (plain class without model_dump/dict)
        class DictAttrObj:
            pass
        obj = DictAttrObj()
        obj.name = "f3"
        obj.arguments = "c"

        result = serialize_tool_calls([dict_obj, mock_md, obj])
        assert result[0] == {"name": "f1", "arguments": "a"}
        assert result[1] == {"name": "f2", "arguments": "b"}
        assert result[2] == {"name": "f3", "arguments": "c"}


class TestSerializeToolCallsDictArgsString:
    """TC-22-09: serialize_tool_calls - dict arguments is string."""

    def test_TC22_09_serialize_tool_calls_dict_args_string(self):
        tool_calls = [{"name": "f", "arguments": '{"key": "value"}'}]
        result = serialize_tool_calls(tool_calls)
        assert result == [{"name": "f", "arguments": '{"key": "value"}'}]


class TestSerializeToolCallsMultipleDict:
    """TC-22-10: serialize_tool_calls - multiple dicts."""

    def test_TC22_10_serialize_tool_calls_multiple_dicts(self):
        tool_calls = [{"name": "f1"}, {"name": "f2"}]
        result = serialize_tool_calls(tool_calls)
        assert result == [{"name": "f1"}, {"name": "f2"}]


class TestSerializeToolCallsModelDumpEmptyDict:
    """TC-22-11: serialize_tool_calls - model_dump returns empty dict."""

    def test_TC22_11_serialize_tool_calls_model_dump_empty_dict(self):
        mock_obj = MagicMock()
        mock_obj.model_dump.return_value = {}
        result = serialize_tool_calls([mock_obj])
        assert result == [{}]


class TestSerializeToolCallsDictAttrExtraFields:
    """TC-22-12: serialize_tool_calls - __dict__ with extra fields."""

    def test_TC22_12_serialize_tool_calls_dict_attr_extra_fields(self):
        class DictAttrObj:
            pass
        obj = DictAttrObj()
        obj.name = "f"
        obj.arguments = "{}"
        obj.extra = "data"

        result = serialize_tool_calls([obj])
        assert result == [{"name": "f", "arguments": "{}", "extra": "data"}]


class TestSerializeToolCallsFallbackStr:
    """TC-22-13: serialize_tool_calls - fallback str content."""

    def test_TC22_13_serialize_tool_calls_fallback_str(self):
        class FallbackObj:
            __slots__ = ()
            def __str__(self):
                return "MockObject(1)"

        result = serialize_tool_calls([FallbackObj()])
        assert result == [{"raw": "MockObject(1)"}]


class TestSerializeToolCallsAllTypesHaveNameArgs:
    """TC-22-14: serialize_tool_calls - all types have name/arguments."""

    def test_TC22_14_serialize_tool_calls_all_types_have_name_args(self):
        # dict type
        dict_obj = {"name": "f1", "arguments": "a"}
        # model_dump type
        mock_md = MagicMock()
        mock_md.model_dump.return_value = {"name": "f2", "arguments": "b"}
        # dict() method type
        class DictMethodObj:
            def dict(self):
                return {"name": "f3", "arguments": "c"}
        # __dict__ type
        class DictAttrObj:
            pass
        obj = DictAttrObj()
        obj.name = "f4"
        obj.arguments = "d"

        result = serialize_tool_calls([dict_obj, mock_md, DictMethodObj(), obj])
        for item in result:
            assert "name" in item
            assert "arguments" in item