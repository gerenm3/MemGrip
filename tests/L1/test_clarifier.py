"""Test plan L1 - Clarifier (#10)

L1 scope (per l1_scope.md): _format_input, _parse_json_response, _default_clarify
Excluded: clarify, _clarify (depend on LLM)

Total: 9 test cases (TC-10-01 ~ TC-10-09)
"""

import pytest
from core.clarifier import Clarifier


# ── Clarifier._format_input ──────────────────────────────────────────────

class TestClarifierFormatInput:
    """TC-10-01 ~ TC-10-04"""

    def test_TC_10_01_format_input_all_non_empty(self):
        clarifier = Clarifier(call_model_func=lambda *a, **k: None, buffer=None, summary=None)
        result = clarifier._format_input("B", "S", "U")
        assert "[BUFFER]B[/BUFFER]" in result
        assert "[SUMMARY]S[/SUMMARY]" in result
        assert "[USER_INPUT]U[/USER_INPUT]" in result

    def test_TC_10_02_format_input_buffer_empty(self):
        clarifier = Clarifier(call_model_func=lambda *a, **k: None, buffer=None, summary=None)
        result = clarifier._format_input("", "S", "U")
        assert "[BUFFER]" not in result
        assert "[SUMMARY]S[/SUMMARY]" in result
        assert "[USER_INPUT]U[/USER_INPUT]" in result

    def test_TC_10_03_format_input_summary_empty(self):
        clarifier = Clarifier(call_model_func=lambda *a, **k: None, buffer=None, summary=None)
        result = clarifier._format_input("B", "", "U")
        assert "[BUFFER]B[/BUFFER]" in result
        assert "[SUMMARY]" not in result
        assert "[USER_INPUT]U[/USER_INPUT]" in result

    def test_TC_10_04_format_input_all_empty(self):
        clarifier = Clarifier(call_model_func=lambda *a, **k: None, buffer=None, summary=None)
        result = clarifier._format_input("", "", "")
        assert "[BUFFER]" not in result
        assert "[SUMMARY]" not in result
        assert "[USER_INPUT]" in result


# ── Clarifier._parse_json_response ──────────────────────────────────────────────

class TestClarifierParseJsonResponse:
    """TC-10-05 ~ TC-10-07"""

    def test_TC_10_05_parse_json_response_normal(self):
        result = Clarifier._parse_json_response('{"goal": "test"}')
        assert result == {"goal": "test"}

    def test_TC_10_06_parse_json_response_empty_string(self):
        result = Clarifier._parse_json_response("")
        assert result is None

    def test_TC_10_07_parse_json_response_invalid(self):
        result = Clarifier._parse_json_response("{invalid}")
        assert result is None


# ── Clarifier._default_clarify ──────────────────────────────────────────────

class TestClarifierDefaultClarify:
    """TC-10-08 ~ TC-10-09"""

    def test_TC_10_08_default_clarify_normal_input(self):
        result = Clarifier._default_clarify("test goal")
        assert result["goal"] == "test goal"
        assert result["entities"] == []
        assert result["scope"] == ""
        assert result["constraints"] == []
        assert result["rules"] == []
        assert result["success_criteria"] == []
        assert result["questions"] == []

    def test_TC_10_09_default_clarify_empty_input(self):
        result = Clarifier._default_clarify("")
        assert result["goal"] == ""
        assert result["entities"] == []
        assert result["scope"] == ""
        assert result["constraints"] == []
        assert result["rules"] == []
        assert result["success_criteria"] == []
        assert result["questions"] == []
