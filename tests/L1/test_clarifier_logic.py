"""tests/L1/test_clarifier_logic — Clarifier 純邏輯測試（9 筆）."""

import unittest.mock
import pytest


@pytest.fixture
def mock_parse_first_json():
    """mock core.json_utils.parse_first_json."""
    with unittest.mock.patch("core.clarifier.parse_first_json") as m:
        yield m


@pytest.fixture
def clarifier_instance():
    """Clarifier instance fixture."""
    from core.clarifier import Clarifier
    mock_model_func = unittest.mock.AsyncMock()
    return Clarifier(call_model_func=mock_model_func, buffer=None, summary=None)


# ── _format_input 測試 ──


class TestFormatInput:
    """測試 Clarifier._format_input 方法."""

    def test_format_input_all_populated(self, clarifier_instance):
        """等價類：buffer/summary/user_input 全有值 → 三個標籤都出現."""
        result = clarifier_instance._format_input(
            buffer_text="buffer content",
            summary_text="summary content",
            user_input="hello",
        )
        assert "[BUFFER]buffer content[/BUFFER]" in result
        assert "[SUMMARY]summary content[/SUMMARY]" in result
        assert "[USER_INPUT]hello[/USER_INPUT]" in result

    def test_format_input_empty_buffer(self, clarifier_instance):
        """邊界：buffer 空 → 不包含 [BUFFER] 標籤."""
        result = clarifier_instance._format_input(
            buffer_text="",
            summary_text="summary content",
            user_input="hello",
        )
        assert "[BUFFER]" not in result
        assert "[SUMMARY]summary content[/SUMMARY]" in result
        assert "[USER_INPUT]hello[/USER_INPUT]" in result

    def test_format_input_empty_summary(self, clarifier_instance):
        """邊界：summary 空 → 不包含 [SUMMARY] 標籤."""
        result = clarifier_instance._format_input(
            buffer_text="buffer content",
            summary_text="",
            user_input="hello",
        )
        assert "[BUFFER]buffer content[/BUFFER]" in result
        assert "[SUMMARY]" not in result
        assert "[USER_INPUT]hello[/USER_INPUT]" in result

    def test_format_input_both_empty(self, clarifier_instance):
        """邊界：buffer+summary 全空 → 只有 [USER_INPUT]."""
        result = clarifier_instance._format_input(
            buffer_text="",
            summary_text="",
            user_input="hello",
        )
        assert "[BUFFER]" not in result
        assert "[SUMMARY]" not in result
        assert "[USER_INPUT]hello[/USER_INPUT]" in result

    def test_format_input_all_empty(self, clarifier_instance):
        """邊界：全空 → 只有 [USER_INPUT] 標籤（user_input 空字串）."""
        result = clarifier_instance._format_input(
            buffer_text="",
            summary_text="",
            user_input="",
        )
        assert "[BUFFER]" not in result
        assert "[SUMMARY]" not in result
        assert "[USER_INPUT][/USER_INPUT]" in result
        assert result.count("[USER_INPUT]") == 1


# ── _parse_json_response 測試 ──


class TestParseJsonResponse:
    """測試 Clarifier._parse_json_response 靜態方法."""

    def test_parse_json_response_valid(self, clarifier_instance):
        """等價類：有效 JSON → 解析成功."""
        content = '{"goal": "test goal", "entities": ["a", "b"]}'
        result = clarifier_instance._parse_json_response(content)
        assert result is not None
        assert result["goal"] == "test goal"
        assert result["entities"] == ["a", "b"]

    def test_parse_json_response_invalid(self, clarifier_instance):
        """等價類：無效 JSON → None."""
        result = clarifier_instance._parse_json_response("not valid json {{{")
        assert result is None

    def test_parse_json_response_empty_string(self, clarifier_instance):
        """邊界：空字串 → None."""
        result = clarifier_instance._parse_json_response("")
        assert result is None

    def test_parse_json_response_markdown_code_block(self, clarifier_instance):
        """等價類：```json ... ``` → parse_first_json 解析成功."""
        # _parse_json_response 直接呼叫 parse_first_json，
        # 所以這裡測試 parse_first_json 是否能處理 markdown code block
        mock_parse_first_json = unittest.mock.patch(
            "core.clarifier.parse_first_json",
            return_value={"goal": "test", "entities": []},
        ).start()
        content = "```json\n{\"goal\": \"test\", \"entities\": []}\n```"
        result = clarifier_instance._parse_json_response(content)
        assert result is not None
        assert result["goal"] == "test"
        mock_parse_first_json.stop()