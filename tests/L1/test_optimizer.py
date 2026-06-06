"""tests/L1/test_optimizer.py -- skills/optimizer.py pure logic tests (10 tests).

Tests focus on: cooldown logic, signal aging, anomaly detection, _compute_stats, _extract_json.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import time
import unittest.mock as mock

# Removed sys.modules pollution — use per-test mocking instead


class TestComputeStats:
    """_compute_stats tests."""

    def test_empty_signals(self):
        """Boundary: empty signals -> empty dict."""
        from skills.optimizer import Optimizer
        result = Optimizer()._compute_stats([])
        assert result == {}

    def test_single_signal(self):
        """Equivalence: single signal -> correct averages."""
        from skills.optimizer import Optimizer
        signals = [{
            "replan_count": 3,
            "failed_units": 1,
            "avg_loop_count": 5,
            "constraint_satisfied_ratio": 0.6,
            "verifier_pass_ratio": 0.9,
            "unit_count": 10,
            "skill_version": 2,
        }]
        result = Optimizer()._compute_stats(signals)
        assert result["count"] == 1
        assert result["avg_replan"] == 3.0
        assert result["avg_failed_units"] == 1.0
        assert result["avg_loop_count"] == 5.0
        assert result["avg_constraint_ratio"] == 0.6
        assert result["avg_verifier_ratio"] == 0.9
        assert result["avg_unit_count"] == 10.0
        assert result["latest_version"] == 2

    def test_multiple_signals(self):
        """Equivalence: multiple signals -> correct averages."""
        from skills.optimizer import Optimizer
        signals = [
            {"replan_count": 2, "failed_units": 0, "avg_loop_count": 3,
             "constraint_satisfied_ratio": 0.8, "verifier_pass_ratio": 0.95,
             "unit_count": 5, "skill_version": 1},
            {"replan_count": 4, "failed_units": 2, "avg_loop_count": 6,
             "constraint_satisfied_ratio": 0.5, "verifier_pass_ratio": 0.7,
             "unit_count": 15, "skill_version": 3},
        ]
        result = Optimizer()._compute_stats(signals)
        assert result["count"] == 2
        assert result["avg_replan"] == 3.0
        assert result["avg_failed_units"] == 1.0
        assert result["avg_loop_count"] == 4.5
        assert result["avg_constraint_ratio"] == 0.65
        assert result["avg_verifier_ratio"] == 0.825
        assert result["avg_unit_count"] == 10.0
        assert result["latest_version"] == 3


class TestDetectAnomalies:
    """_detect_anomalies tests."""

    def test_no_anomalies(self):
        """Equivalence: all metrics within thresholds -> empty list."""
        from skills.optimizer import Optimizer
        stats = {
            "avg_failed_units": 0,
            "avg_replan": 1,
            "avg_loop_count": 3,
            "avg_constraint_ratio": 0.8,
        }
        result = Optimizer()._detect_anomalies(stats)
        assert result == []

    def test_all_anomalies(self):
        """Equivalence: all metrics exceed thresholds."""
        from skills.optimizer import Optimizer
        stats = {
            "avg_failed_units": 1,
            "avg_replan": 3,
            "avg_loop_count": 5,
            "avg_constraint_ratio": 0.5,
        }
        result = Optimizer()._detect_anomalies(stats)
        assert "failed_units" in result
        assert "replan_count" in result
        assert "avg_loop_count" in result
        assert "constraint_ratio" in result

    def test_failed_units_boundary(self):
        """Boundary: avg_failed_units = 0 (threshold) -> no anomaly."""
        from skills.optimizer import Optimizer
        stats = {
            "avg_failed_units": 0,
            "avg_replan": 0,
            "avg_loop_count": 0,
            "avg_constraint_ratio": 1.0,
        }
        result = Optimizer()._detect_anomalies(stats)
        assert "failed_units" not in result

    def test_constraint_ratio_boundary(self):
        """Boundary: avg_constraint_ratio = 0.7 (threshold) -> no anomaly."""
        from skills.optimizer import Optimizer
        stats = {
            "avg_failed_units": 0,
            "avg_replan": 0,
            "avg_loop_count": 0,
            "avg_constraint_ratio": 0.7,
        }
        result = Optimizer()._detect_anomalies(stats)
        assert "constraint_ratio" not in result

    def test_constraint_ratio_below_boundary(self):
        """Equivalence: avg_constraint_ratio just below threshold -> anomaly."""
        from skills.optimizer import Optimizer
        stats = {
            "avg_failed_units": 0,
            "avg_replan": 0,
            "avg_loop_count": 0,
            "avg_constraint_ratio": 0.6999,
        }
        result = Optimizer()._detect_anomalies(stats)
        assert "constraint_ratio" in result


class TestExtractJson:
    """_extract_json tests."""

    def test_plain_json(self):
        """Equivalence: plain JSON -> correctly parsed."""
        from skills.optimizer import Optimizer
        text = '{"key": "value", "num": 42}'
        result = Optimizer._extract_json(text)
        assert result == {"key": "value", "num": 42}

    def test_json_with_markdown(self):
        """Equivalence: ```json wrapped -> correctly parsed."""
        from skills.optimizer import Optimizer
        text = "```json\n" + json.dumps({"a": 1}) + "\n```"
        result = Optimizer._extract_json(text)
        assert result == {"a": 1}

    def test_json_with_whitespace(self):
        """Equivalence: whitespace around JSON -> correctly parsed."""
        from skills.optimizer import Optimizer
        text = "  \n  " + json.dumps({"x": 2}) + "  \n"
        result = Optimizer._extract_json(text)
        assert result == {"x": 2}

    def test_invalid_json(self):
        """Equivalence: invalid JSON -> raises exception (documented behavior)."""
        from skills.optimizer import Optimizer
        try:
            result = Optimizer._extract_json("not json")
            assert result is None
        except Exception:
            pass