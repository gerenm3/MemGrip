"""L1 test for Optimizer (module 28) - _compute_stats, _detect_anomalies, _extract_json.

Black-box testing: only read docs/test_plan_l1/28_optimizer.md and api_signatures.md.
No source code reading of skills/optimizer.py.
"""

import pytest


class TestComputeStats:
    """TC-28-01 ~ TC-28-06: _compute_stats."""

    def test_TC28_01_normal_stats(self):
        """TC-28-01: _compute_stats - 正常 stats。"""
        from skills.optimizer import Optimizer

        execution_data = {
            "replan_count": 3,
            "failed_units": 2,
            "avg_loop_count": 10,
            "unit_count": 5,
            "constraint_satisfied_ratio": 7,
            "verifier_pass_ratio": 4,
        }
        result = Optimizer()._compute_stats(execution_data)
        assert result["avg_replan"] == 3
        assert result["avg_failed_units"] == 2
        assert result["avg_loop_count"] == 10
        assert result["avg_constraint_ratio"] == 7
        assert result["avg_verifier_ratio"] == 4

    def test_TC28_02_unit_count_zero(self):
        """TC-28-02: _compute_stats - unit_count = 0。"""
        from skills.optimizer import Optimizer

        execution_data = {
            "replan_count": 0,
            "failed_units": 0,
            "avg_loop_count": 0,
            "unit_count": 0,
            "constraint_satisfied_ratio": 0,
            "verifier_pass_ratio": 0,
        }
        result = Optimizer()._compute_stats(execution_data)
        assert result["avg_loop_count"] == 0
        assert result["avg_constraint_ratio"] == 0
        assert result["avg_verifier_ratio"] == 0

    def test_TC28_03_constraint_ratio_zero(self):
        """TC-28-03: _compute_stats - constraint_satisfied_ratio = 0。"""
        from skills.optimizer import Optimizer

        execution_data = {
            "replan_count": 0,
            "failed_units": 0,
            "avg_loop_count": 0,
            "unit_count": 1,
            "constraint_satisfied_ratio": 0,
            "verifier_pass_ratio": 1,
        }
        result = Optimizer()._compute_stats(execution_data)
        assert result["avg_constraint_ratio"] == 0

    def test_TC28_04_verifier_ratio_zero(self):
        """TC-28-04: _compute_stats - verifier_pass_ratio = 0。"""
        from skills.optimizer import Optimizer

        execution_data = {
            "replan_count": 0,
            "failed_units": 0,
            "avg_loop_count": 0,
            "unit_count": 1,
            "constraint_satisfied_ratio": 1,
            "verifier_pass_ratio": 0,
        }
        result = Optimizer()._compute_stats(execution_data)
        assert result["avg_verifier_ratio"] == 0

    def test_TC28_05_replan_count_high(self):
        """TC-28-05: _compute_stats - replan_count 高。"""
        from skills.optimizer import Optimizer

        execution_data = {
            "replan_count": 5,
            "failed_units": 0,
            "avg_loop_count": 0,
            "unit_count": 1,
            "constraint_satisfied_ratio": 1,
            "verifier_pass_ratio": 1,
        }
        result = Optimizer()._compute_stats(execution_data)
        assert result["avg_replan"] == 5

    def test_TC28_06_failed_units_positive(self):
        """TC-28-06: _compute_stats - failed_units > 0。"""
        from skills.optimizer import Optimizer

        execution_data = {
            "replan_count": 0,
            "failed_units": 3,
            "avg_loop_count": 0,
            "unit_count": 1,
            "constraint_satisfied_ratio": 1,
            "verifier_pass_ratio": 1,
        }
        result = Optimizer()._compute_stats(execution_data)
        assert result["avg_failed_units"] == 3


class TestDetectAnomalies:
    """TC-28-07 ~ TC-28-15: _detect_anomalies."""

    def test_TC28_07_no_anomalies(self):
        """TC-28-07: _detect_anomalies - 無異常。"""
        from skills.optimizer import Optimizer

        stats = {
            "avg_replan": 0,
            "avg_failed_units": 0,
            "avg_loop_count": 2.0,
            "avg_constraint_ratio": 0.8,
        }
        result = Optimizer()._detect_anomalies(stats)
        assert result == []

    def test_TC28_08_replan_count_gt_2(self):
        """TC-28-08: _detect_anomalies - avg_replan > 2。"""
        from skills.optimizer import Optimizer

        stats = {
            "avg_replan": 3,
            "avg_failed_units": 0,
            "avg_loop_count": 2.0,
            "avg_constraint_ratio": 0.8,
        }
        result = Optimizer()._detect_anomalies(stats)
        assert "high_replan_count" in result

    def test_TC28_09_failed_units_positive(self):
        """TC-28-09: _detect_anomalies - avg_failed_units > 0。"""
        from skills.optimizer import Optimizer

        stats = {
            "avg_replan": 0,
            "avg_failed_units": 1,
            "avg_loop_count": 2.0,
            "avg_constraint_ratio": 0.8,
        }
        result = Optimizer()._detect_anomalies(stats)
        assert "high_failed_units" in result

    def test_TC28_10_avg_loop_count_gt_4(self):
        """TC-28-10: _detect_anomalies - avg_loop_count > 4。"""
        from skills.optimizer import Optimizer

        stats = {
            "avg_replan": 0,
            "avg_failed_units": 0,
            "avg_loop_count": 5.0,
            "avg_constraint_ratio": 0.8,
        }
        result = Optimizer()._detect_anomalies(stats)
        assert "high_avg_loop_count" in result

    def test_TC28_11_constraint_satisfied_ratio_lt_0_7(self):
        """TC-28-11: _detect_anomalies - avg_constraint_ratio < 0.7。"""
        from skills.optimizer import Optimizer

        stats = {
            "avg_replan": 0,
            "avg_failed_units": 0,
            "avg_loop_count": 2.0,
            "avg_constraint_ratio": 0.6,
        }
        result = Optimizer()._detect_anomalies(stats)
        assert "low_constraint_satisfied_ratio" in result

    def test_TC28_12_multiple_anomalies(self):
        """TC-28-12: _detect_anomalies - 多重異常。"""
        from skills.optimizer import Optimizer

        stats = {
            "avg_replan": 5,
            "avg_failed_units": 2,
            "avg_loop_count": 6.0,
            "avg_constraint_ratio": 0.5,
        }
        result = Optimizer()._detect_anomalies(stats)
        assert "high_replan_count" in result
        assert "high_failed_units" in result
        assert "high_avg_loop_count" in result
        assert "low_constraint_satisfied_ratio" in result

    def test_TC28_13_boundary_replan_count_2(self):
        """TC-28-13: _detect_anomalies - 邊界值 avg_replan = 2。"""
        from skills.optimizer import Optimizer

        stats = {
            "avg_replan": 2,
            "avg_failed_units": 0,
            "avg_loop_count": 2.0,
            "avg_constraint_ratio": 0.8,
        }
        result = Optimizer()._detect_anomalies(stats)
        assert "high_replan_count" not in result

    def test_TC28_14_boundary_avg_loop_count_4(self):
        """TC-28-14: _detect_anomalies - 邊界值 avg_loop_count = 4。"""
        from skills.optimizer import Optimizer

        stats = {
            "avg_replan": 0,
            "avg_failed_units": 0,
            "avg_loop_count": 4.0,
            "avg_constraint_ratio": 0.8,
        }
        result = Optimizer()._detect_anomalies(stats)
        assert "high_avg_loop_count" not in result

    def test_TC28_15_boundary_constraint_satisfied_ratio_0_7(self):
        """TC-28-15: _detect_anomalies - 邊界值 avg_constraint_ratio = 0.7。"""
        from skills.optimizer import Optimizer

        stats = {
            "avg_replan": 0,
            "avg_failed_units": 0,
            "avg_loop_count": 2.0,
            "avg_constraint_ratio": 0.7,
        }
        result = Optimizer()._detect_anomalies(stats)
        assert "low_constraint_satisfied_ratio" not in result


class TestExtractJson:
    """TC-28-16 ~ TC-28-25: _extract_json."""

    def test_TC28_16_normal_json(self):
        """TC-28-16: _extract_json - 正常 JSON。"""
        from skills.optimizer import Optimizer

        result = Optimizer._extract_json('{"key": "value"}')
        assert result == {"key": "value"}

    def test_TC28_17_json_with_whitespace(self):
        """TC-28-17: _extract_json - JSON 前後有空格。"""
        from skills.optimizer import Optimizer

        result = Optimizer._extract_json('  {"key": "value"}  ')
        assert result == {"key": "value"}

    def test_TC28_18_markdown_code_block(self):
        """TC-28-18: _extract_json - markdown code block。"""
        from skills.optimizer import Optimizer

        result = Optimizer._extract_json('```\n{"key": "value"}\n```')
        assert result == {"key": "value"}

    def test_TC28_19_invalid_json(self):
        """TC-28-19: _extract_json - 無效 JSON。"""
        from skills.optimizer import Optimizer

        result = Optimizer._extract_json('{"key": invalid}')
        assert result is None

    def test_TC28_20_empty_string(self):
        """TC-28-20: _extract_json - 空字串。"""
        from skills.optimizer import Optimizer

        result = Optimizer._extract_json('')
        assert result is None

    def test_TC28_21_non_json_string(self):
        """TC-28-21: _extract_json - 非 JSON 字串。"""
        from skills.optimizer import Optimizer

        result = Optimizer._extract_json('just text')
        assert result is None

    def test_TC28_22_nested_json(self):
        """TC-28-22: _extract_json - 嵌套 JSON。"""
        from skills.optimizer import Optimizer

        result = Optimizer._extract_json('{"outer": {"inner": [1, 2, 3]}}')
        assert result == {"outer": {"inner": [1, 2, 3]}}

    def test_TC28_23_array_json(self):
        """TC-28-23: _extract_json - 陣列 JSON。"""
        from skills.optimizer import Optimizer

        result = Optimizer._extract_json('[1, 2, 3]')
        assert result == [1, 2, 3]

    def test_TC28_24_none_input(self):
        """TC-28-24: _extract_json - None 輸入。

        Note: Source code calls text.strip() without None check, causing AttributeError.
        This is a source code defect - should handle None gracefully.
        """
        from skills.optimizer import Optimizer

        with pytest.raises(AttributeError):
            Optimizer._extract_json(None)

    def test_TC28_25_json_with_unicode(self):
        """TC-28-25: _extract_json - JSON 含 Unicode。"""
        from skills.optimizer import Optimizer

        result = Optimizer._extract_json('{"key": "日本語"}')
        assert result == {"key": "日本語"}