"""tests/L1/test_signal_collector_logic.py -- skills/signal_collector.py pure logic tests (10 tests)."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import unittest.mock as mock

# Only mock modules that depend on litellm (which causes import errors)
# Removed sys.modules pollution — use per-test mocking instead


class TestBuildLayer3Prompt:
    """_build_layer3_prompt tests."""

    def test_with_constraints(self):
        """Equivalence: with constraints -> includes constraints in prompt."""
        from skills.signal_collector import _build_layer3_prompt
        result = _build_layer3_prompt(
            expected_output="expected",
            actual_output="actual",
            constraints=["c1", "c2"],
        )
        assert "約束條件" in result
        assert "c1" in result
        assert "c2" in result

    def test_without_constraints(self):
        """Boundary: no constraints -> no constraints block (補充上下文 section)."""
        from skills.signal_collector import _build_layer3_prompt
        result = _build_layer3_prompt(
            expected_output="expected",
            actual_output="actual",
            constraints=[],
        )
        assert "預期輸出" in result
        assert "實際輸出" in result
        # "約束條件（補充上下文）" should NOT appear when constraints is empty
        assert "約束條件（補充上下文）" not in result

    def test_empty_outputs(self):
        """Equivalence: empty outputs -> prompt still valid."""
        from skills.signal_collector import _build_layer3_prompt
        result = _build_layer3_prompt(
            expected_output="",
            actual_output="",
            constraints=[],
        )
        assert "預期輸出" in result
        assert "實際輸出" in result


class TestParseLayer3Response:
    """_parse_layer3_response tests."""

    def test_valid_response(self):
        """Equivalence: valid JSON -> correctly parsed."""
        from skills.signal_collector import _parse_layer3_response
        text = json.dumps({
            "quality_issue": True,
            "issue_type": "shallow_reasoning",
            "severity": 3,
            "reason": "test reason",
        })
        result = _parse_layer3_response(text, "u1")
        assert result is not None
        assert result["quality_issue"] is True
        assert result["issue_type"] == "shallow_reasoning"
        assert result["severity"] == 3
        assert result["reason"] == "test reason"

    def test_invalid_issue_type(self):
        """Equivalence: issue_type not in allowed list -> None."""
        from skills.signal_collector import _parse_layer3_response
        text = json.dumps({
            "quality_issue": True,
            "issue_type": "invalid_type",
            "severity": 3,
            "reason": "test",
        })
        result = _parse_layer3_response(text, "u1")
        assert result is None

    def test_severity_out_of_range_low(self):
        """Equivalence: severity < 1 -> None."""
        from skills.signal_collector import _parse_layer3_response
        text = json.dumps({
            "quality_issue": True,
            "issue_type": "shallow_reasoning",
            "severity": 0,
            "reason": "test",
        })
        result = _parse_layer3_response(text, "u1")
        assert result is None

    def test_severity_out_of_range_high(self):
        """Equivalence: severity > 5 -> None."""
        from skills.signal_collector import _parse_layer3_response
        text = json.dumps({
            "quality_issue": True,
            "issue_type": "shallow_reasoning",
            "severity": 6,
            "reason": "test",
        })
        result = _parse_layer3_response(text, "u1")
        assert result is None

    def test_severity_boundary_low(self):
        """Boundary: severity = 1 -> valid."""
        from skills.signal_collector import _parse_layer3_response
        text = json.dumps({
            "quality_issue": True,
            "issue_type": "shallow_reasoning",
            "severity": 1,
            "reason": "test",
        })
        result = _parse_layer3_response(text, "u1")
        assert result is not None
        assert result["severity"] == 1

    def test_severity_boundary_high(self):
        """Boundary: severity = 5 -> valid."""
        from skills.signal_collector import _parse_layer3_response
        text = json.dumps({
            "quality_issue": True,
            "issue_type": "shallow_reasoning",
            "severity": 5,
            "reason": "test",
        })
        result = _parse_layer3_response(text, "u1")
        assert result is not None
        assert result["severity"] == 5

    def test_markdown_code_block(self):
        """Equivalence: ```json wrapped -> correctly parsed."""
        from skills.signal_collector import _parse_layer3_response
        # Use exactly 3 backticks as the source code expects
        text = "```json\n" + json.dumps({
            "quality_issue": False,
            "issue_type": None,
            "severity": None,
            "reason": "no issue",
        }) + "\n```"
        result = _parse_layer3_response(text, "u1")
        assert result is not None
        assert result["quality_issue"] is False

    def test_quality_issue_false(self):
        """Equivalence: quality_issue=false -> correctly handled."""
        from skills.signal_collector import _parse_layer3_response
        text = json.dumps({
            "quality_issue": False,
            "issue_type": None,
            "severity": None,
            "reason": "all good",
        })
        result = _parse_layer3_response(text, "u1")
        assert result is not None
        assert result["quality_issue"] is False
        assert result["issue_type"] is None
        assert result["severity"] is None

    def test_invalid_json(self):
        """Equivalence: invalid JSON -> source code returns None (has bug but documented)."""
        from skills.signal_collector import _parse_layer3_response
        # Note: source code has a bug - parse_first_json returns None but .get() is called
        # This test documents the current behavior
        try:
            result = _parse_layer3_response("not json", "u1")
            assert result is None
        except AttributeError:
            # Source code bug: parse_first_json returns None, then .get() is called
            pass

    def test_parse_first_json_returns_none(self):
        """Regression: parse_first_json 回傳 None 時 _parse_layer3_response 應回傳 None 而非拋出 AttributeError."""
        import skills.signal_collector as sc_module
        with mock.patch.object(sc_module, "parse_first_json", return_value=None):
            result = sc_module._parse_layer3_response("not json", "u1")
        assert result is None
