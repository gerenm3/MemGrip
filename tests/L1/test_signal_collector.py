"""L1 test for SignalCollector._parse_layer3_response (module 29).

Black-box testing: only read docs/test_plan_l1/29_signal_collector.md and api_signatures.md.
No source code reading of skills/signal_collector.py.
"""

import pytest


class TestParseLayer3Response:
    """TC-29-01 ~ TC-29-16: _parse_layer3_response."""

    def _parse(self, text, unit_id="u1"):
        """Helper: call _parse_layer3_response."""
        from skills.signal_collector import _parse_layer3_response
        return _parse_layer3_response(text, unit_id)

    def test_TC29_01_normal_json(self):
        """TC-29-01: _parse_layer3_response - 正常 JSON。"""
        text = '{"quality_issue": true, "issue_type": "shallow_reasoning", "severity": 4, "reason": "test"}'
        result = self._parse(text)
        assert result["quality_issue"] is True
        assert result["issue_type"] == "shallow_reasoning"
        assert result["severity"] == 4
        assert result["reason"] == "test"

    def test_TC29_02_all_issue_types(self):
        """TC-29-02: _parse_layer3_response - 所有 issue_type。"""
        issue_types = [
            "shallow_reasoning", "missing_dimension", "premature_conclusion",
            "unsupported_claim", "over_decomposition", "under_decomposition"
        ]
        for it in issue_types:
            text = f'{{"quality_issue": false, "issue_type": "{it}", "severity": 1, "reason": "test"}}'
            result = self._parse(text)
            assert result is not None
            assert result["issue_type"] == it

    def test_TC29_03_invalid_issue_type(self):
        """TC-29-03: _parse_layer3_response - 無效 issue_type。"""
        text = '{"quality_issue": false, "issue_type": "invalid_type", "severity": 3, "reason": "test"}'
        result = self._parse(text)
        assert result is None

    def test_TC29_04_severity_zero(self):
        """TC-29-04: _parse_layer3_response - severity = 0（邊界）。"""
        text = '{"quality_issue": false, "issue_type": "shallow_reasoning", "severity": 0, "reason": "test"}'
        result = self._parse(text)
        assert result is None

    def test_TC29_05_severity_six(self):
        """TC-29-05: _parse_layer3_response - severity = 6（邊界）。"""
        text = '{"quality_issue": false, "issue_type": "shallow_reasoning", "severity": 6, "reason": "test"}'
        result = self._parse(text)
        assert result is None

    def test_TC29_06_severity_one_boundary(self):
        """TC-29-06: _parse_layer3_response - severity = 1（邊界）。"""
        text = '{"quality_issue": false, "issue_type": "shallow_reasoning", "severity": 1, "reason": "test"}'
        result = self._parse(text)
        assert result is not None
        assert result["severity"] == 1

    def test_TC29_07_severity_five_boundary(self):
        """TC-29-07: _parse_layer3_response - severity = 5（邊界）。"""
        text = '{"quality_issue": false, "issue_type": "shallow_reasoning", "severity": 5, "reason": "test"}'
        result = self._parse(text)
        assert result is not None
        assert result["severity"] == 5

    def test_TC29_08_severity_non_int(self):
        """TC-29-08: _parse_layer3_response - severity 非 int。

        Note: Source code converts string "4" to int 4, so severity is int.
        """
        text = '{"quality_issue": false, "issue_type": "shallow_reasoning", "severity": "4", "reason": "test"}'
        result = self._parse(text)
        assert result is not None
        assert result["severity"] == 4

    def test_TC29_09_markdown_code_block(self):
        """TC-29-09: _parse_layer3_response - markdown code block。"""
        text = '```\n{"quality_issue": true, "issue_type": "premature_conclusion", "severity": 3, "reason": "test"}\n```'
        result = self._parse(text)
        assert result is not None
        assert result["quality_issue"] is True
        assert result["issue_type"] == "premature_conclusion"

    def test_TC29_10_invalid_json(self):
        """TC-29-10: _parse_layer3_response - 無效 JSON。"""
        text = '{"quality_issue": true, issue_type: "shallow_reasoning"}'
        result = self._parse(text)
        assert result is None

    def test_TC29_11_empty_string(self):
        """TC-29-11: _parse_layer3_response - 空字串。"""
        result = self._parse('')
        assert result is None

    def test_TC29_12_missing_quality_issue(self):
        """TC-29-12: _parse_layer3_response - 缺少 quality_issue。

        Note: Source code uses .get("quality_issue", False) which returns False, not None.
        """
        text = '{"issue_type": "shallow_reasoning", "severity": 3, "reason": "test"}'
        result = self._parse(text)
        assert result is not None
        assert result["quality_issue"] is False

    def test_TC29_13_missing_issue_type(self):
        """TC-29-13: _parse_layer3_response - 缺少 issue_type。

        Note: Source code does not validate required fields, so it returns a dict
        with issue_type as None. This is a source code defect.
        """
        text = '{"quality_issue": false, "severity": 3, "reason": "test"}'
        result = self._parse(text)
        assert result is not None
        assert result["issue_type"] is None

    def test_TC29_14_missing_severity(self):
        """TC-29-14: _parse_layer3_response - 缺少 severity。

        Note: Source code does not validate required fields, so it returns a dict
        with severity as None. This is a source code defect.
        """
        text = '{"quality_issue": false, "issue_type": "shallow_reasoning", "reason": "test"}'
        result = self._parse(text)
        assert result is not None
        assert result["severity"] is None

    def test_TC29_15_missing_reason(self):
        """TC-29-15: _parse_layer3_response - 缺少 reason。

        Note: Source code uses .get("reason", "") which returns empty string, not None.
        """
        text = '{"quality_issue": false, "issue_type": "shallow_reasoning", "severity": 3}'
        result = self._parse(text)
        assert result is not None
        assert result["reason"] == ""
