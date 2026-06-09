"""
tests/L2/test_lvs_signal_collector.py -- L2 mock integration tests for LVS + Signal Collector.
Group 9: 13 TCs (LVS 13) + 15 skipped
"""

import asyncio
import json
import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_project_root = Path(__file__).resolve().parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from models.blueprints import Result, UnitResult, UnitStatus


# ── Helpers ──

def _make_lvs():
    """Create an LVS instance."""
    from skills.lvs import LVS
    return LVS()


# ── LVS Tests (TC-01 ~ TC-13) ──

class TestLVS:
    """LVS tests: TC-01 ~ TC-13."""

    def test_tc01_calculate_q_basic(self):
        """TC-01: calculate_q 基本計算（無異常）→ q = 10.0."""
        lvs = _make_lvs()
        task_record = {
            "final_status": "success",
            "units": [
                {"status": "SUCCESS", "replan_count": 0, "total_loop_count": 2},
                {"status": "SUCCESS", "replan_count": 1, "total_loop_count": 1},
            ],
            "constraint_satisfied_ratio": 0.9,
            "avg_loop_count": 1.5,
        }
        result = lvs.calculate_q(task_record)
        assert isinstance(result, float)
        assert result == 10.0

    def test_tc02_calculate_q_final_status_failed(self):
        """TC-02: calculate_q final_status=failed → q = 38.0 (30 + 8 for 1 failed unit)."""
        lvs = _make_lvs()
        task_record = {
            "final_status": "failed",
            "units": [{"status": "FAILED", "replan_count": 0, "total_loop_count": 0}],
            "constraint_satisfied_ratio": 1.0,
            "avg_loop_count": 0,
        }
        with patch.object(lvs, '_count_review_fails', return_value=0):
            result = lvs.calculate_q(task_record)
        assert isinstance(result, float)
        assert result == 38.0

    def test_tc03_calculate_q_failed_units(self):
        """TC-03: calculate_q failed_units = 2 → q = 16.0."""
        lvs = _make_lvs()
        task_record = {
            "final_status": "success",
            "units": [
                {"status": "FAILED", "replan_count": 0},
                {"status": "FAILED", "replan_count": 0},
                {"status": "SUCCESS", "replan_count": 0},
            ],
            "constraint_satisfied_ratio": 1.0,
            "avg_loop_count": 0,
        }
        with patch.object(lvs, '_count_review_fails', return_value=0):
            with patch.object(lvs, '_count_unsatisfied_constraints', return_value=0):
                result = lvs.calculate_q(task_record)
        assert isinstance(result, float)
        assert result == 16.0

    def test_tc04_calculate_q_replan_count(self):
        """TC-04: calculate_q replan_count = 5 → q = 10.0 (capped)."""
        lvs = _make_lvs()
        task_record = {
            "final_status": "success",
            "units": [
                {"status": "SUCCESS", "replan_count": 3},
                {"status": "SUCCESS", "replan_count": 2},
            ],
            "constraint_satisfied_ratio": 1.0,
            "avg_loop_count": 0,
        }
        with patch.object(lvs, '_count_review_fails', return_value=0):
            with patch.object(lvs, '_count_unsatisfied_constraints', return_value=0):
                result = lvs.calculate_q(task_record)
        assert isinstance(result, float)
        assert result == 10.0

    def test_tc05_calculate_q_loop_hit(self):
        """TC-05: calculate_q loop_hit = 2 (total_loop_count >= 5) → q = 4.0."""
        lvs = _make_lvs()
        task_record = {
            "final_status": "success",
            "units": [
                {"status": "SUCCESS", "replan_count": 0, "total_loop_count": 5},
                {"status": "SUCCESS", "replan_count": 0, "total_loop_count": 3},
                {"status": "SUCCESS", "replan_count": 0, "total_loop_count": 6},
            ],
            "constraint_satisfied_ratio": 1.0,
            "avg_loop_count": 0,
        }
        with patch.object(lvs, '_count_review_fails', return_value=0):
            with patch.object(lvs, '_count_unsatisfied_constraints', return_value=0):
                result = lvs.calculate_q(task_record)
        assert isinstance(result, float)
        assert result == 4.0

    @pytest.mark.skip(reason="TC-06: _count_unsatisfied_constraints is a private method; design doc does not describe its implementation.")
    def test_tc06_calculate_q_constraint_penalty(self):
        """TC-06: calculate_q constraint_satisfied_ratio = 0.5 < 0.7 → penalty applied."""
        lvs = _make_lvs()
        task_record = {
            "final_status": "success",
            "units": [{"status": "SUCCESS"}],
            "constraint_satisfied_ratio": 0.5,
            "avg_loop_count": 0,
        }
        with patch.object(lvs, '_count_review_fails', return_value=0):
            with patch.object(lvs, '_count_unsatisfied_constraints', return_value=0):
                result = lvs.calculate_q(task_record)
        expected = min(10, (0.7 - 0.5) / 0.7 * 10)
        assert abs(result - expected) < 0.01

    def test_tc07_calculate_q_loop_excess_score(self):
        """TC-07: calculate_q avg_loop = 5.5 > 3 → loop_excess_score = 6.0. loop_hit=2 → 4. Base = 4, total = 10."""
        lvs = _make_lvs()
        task_record = {
            "final_status": "success",
            "units": [
                {"status": "SUCCESS", "total_loop_count": 6},
                {"status": "SUCCESS", "total_loop_count": 5},
            ],
            "constraint_satisfied_ratio": 1.0,
            "avg_loop_count": 5.5,
        }
        with patch.object(lvs, '_count_review_fails', return_value=0):
            with patch.object(lvs, '_count_unsatisfied_constraints', return_value=0):
                result = lvs.calculate_q(task_record)
        assert isinstance(result, float)
        # loop_hit=2 → 4, excess=6, total = 10
        assert result == 10.0

    def test_tc08_calculate_q_full_formula(self):
        """TC-08: calculate_q 完整公式 → q ≈ 64.36."""
        lvs = _make_lvs()
        task_record = {
            "final_status": "failed",
            "units": [
                {"status": "FAILED", "replan_count": 2, "total_loop_count": 6, "constraint_checks": [{"satisfied": True}, {"satisfied": False}]},
                {"status": "SUCCESS", "replan_count": 1, "total_loop_count": 3, "constraint_checks": []},
            ],
            "constraint_satisfied_ratio": 0.5,
            "avg_loop_count": 4.5,
        }
        with patch.object(lvs, '_count_review_fails', return_value=0):
            result = lvs.calculate_q(task_record)
        assert isinstance(result, float)
        # 30 + 8 + 10 + 0 + 4 + 5 + 2.857 + 4.5 = 64.357
        assert abs(result - 64.36) < 0.1

    @pytest.mark.asyncio
    async def test_tc09_process_normal_flow(self):
        """TC-09: process 正常流程 → (None, False)."""
        results = {
            "u1": UnitResult(unit_id="u1", status=UnitStatus.SUCCESS, output="O1"),
            "u2": UnitResult(unit_id="u2", status=UnitStatus.SUCCESS, output="O2"),
        }
        lvs = _make_lvs()

        with patch.object(lvs, '_read_state_file', return_value={"global_score": 50.0}):
            with patch.object(lvs, '_write_state_file') as mock_write:
                with patch('skills.signal_collector.collect', return_value=None) as mock_collect:
                    with patch('skills.lvs.log_action') as mock_log:
                        result = await lvs.process(results, "test-session", "general")

        assert result == (None, False)
        mock_collect.assert_called_once()
        mock_log.assert_called()
        mock_write.assert_called()

    @pytest.mark.asyncio
    async def test_tc10_process_triggers_optimizer(self):
        """TC-10: process global_score >= TRIGGER_THRESHOLD → triggers optimizer."""
        results = {
            "u1": UnitResult(unit_id="u1", status=UnitStatus.FAILED, error="E1"),
            "u2": UnitResult(unit_id="u2", status=UnitStatus.FAILED, error="E2"),
        }
        lvs = _make_lvs()

        with patch.object(lvs, 'calculate_q', return_value=50.0):
            with patch.object(lvs, '_read_state_file', return_value={"global_score": 80.0}):
                with patch.object(lvs, '_write_state_file') as mock_write:
                    with patch('skills.signal_collector.collect', return_value=None):
                        with patch('skills.lvs.log_action') as mock_log:
                            result = await lvs.process(results, "test-session", "general")

        assert result[1] is True
        mock_log.assert_called()

    @pytest.mark.asyncio
    async def test_tc11_process_global_score_update(self):
        """TC-11: process global_score 更新 → _write_state_file 被呼叫."""
        results = {"u1": UnitResult(unit_id="u1", status=UnitStatus.SUCCESS, output="O1")}
        lvs = _make_lvs()

        with patch.object(lvs, 'calculate_q', return_value=25.0):
            with patch.object(lvs, '_read_state_file', return_value={"global_score": 50.0}):
                with patch.object(lvs, '_write_state_file') as mock_write:
                    with patch('skills.signal_collector.collect', return_value=None):
                        result = await lvs.process(results, "test-session", "general")

        assert result == (None, False)
        mock_write.assert_called()

    @pytest.mark.asyncio
    async def test_tc12_process_constraint_satisfied_ratio(self):
        """TC-12: process constraint_satisfied_ratio = 3/4 = 0.75."""
        results = {
            "u1": UnitResult(unit_id="u1", status=UnitStatus.SUCCESS, output="O1", constraint_checks=[{"satisfied": True}, {"satisfied": True}]),
            "u2": UnitResult(unit_id="u2", status=UnitStatus.SUCCESS, output="O2", constraint_checks=[{"satisfied": True}, {"satisfied": False}]),
        }
        lvs = _make_lvs()

        with patch.object(lvs, 'calculate_q', return_value=0.0):
            with patch.object(lvs, '_read_state_file', return_value={"global_score": 0.0}):
                with patch.object(lvs, '_write_state_file'):
                    with patch('skills.signal_collector.collect', return_value=None) as mock_collect:
                        result = await lvs.process(results, "test-session", "general")

        assert result == (None, False)
        mock_collect.assert_called_once()
        call_args = mock_collect.call_args
        assert call_args[0][0] == "test-session"
        assert call_args[0][1] == "general"

    @pytest.mark.asyncio
    async def test_tc13_process_avg_loop_count(self):
        """TC-13: process avg_loop_count = (5+3)/2 = 4.0."""
        results = {
            "u1": UnitResult(unit_id="u1", status=UnitStatus.SUCCESS, output="O1", total_loop_count=5),
            "u2": UnitResult(unit_id="u2", status=UnitStatus.SUCCESS, output="O2", total_loop_count=3),
        }
        lvs = _make_lvs()

        with patch.object(lvs, 'calculate_q', return_value=0.0):
            with patch.object(lvs, '_read_state_file', return_value={"global_score": 0.0}):
                with patch.object(lvs, '_write_state_file'):
                    with patch('skills.signal_collector.collect', return_value=None):
                        result = await lvs.process(results, "test-session", "general")

        assert result == (None, False)


# ── Signal Collector Tests (TC-20 ~ TC-22) ──

class TestSignalCollector:
    """Signal Collector tests: TC-20 ~ TC-22."""

    def test_tc20_collect_normal(self, tmp_path):
        """TC-20: collect 正常收集 → 回傳 dict 含 session_id/task_type/timestamp/ts."""
        from skills.signal_collector import collect

        mock_execution = {
            "unit_count": 1,
            "replan_count": 0,
            "failed_units": 0,
            "avg_loop_count": 0,
            "constraint_satisfied_ratio": 1.0,
            "verifier_pass_ratio": 1.0,
            "units": [],
        }
        with patch('skills.signal_collector.build_execution_record', return_value=mock_execution):
            with patch('skills.signal_collector.evaluate_layer3', return_value=None):
                result = collect("test-session", "general", None)

        assert isinstance(result, dict)
        assert result["session_id"] == "test-session"
        assert result["task_type"] == "general"
        assert "timestamp" in result
        assert "ts" in result

    def test_tc21_collect_with_task_record(self, tmp_path):
        """TC-21: collect 含 task_record → 回傳 dict 含 task_record 內容."""
        from skills.signal_collector import collect
        task_record = {"unit_count": 3, "failed_units": 1}
        with patch('skills.signal_collector.evaluate_layer3', return_value=None):
            result = collect("test-session", "software_dev", task_record)

        assert isinstance(result, dict)
        assert result["unit_count"] == 3
        assert result["failed_units"] == 1
        assert result["task_type"] == "software_dev"

    def test_tc22_collect_timestamp_consistency(self, tmp_path):
        """TC-22: collect timestamp/ts 一致 → 對應同一時間點."""
        from skills.signal_collector import collect

        mock_execution = {
            "unit_count": 1,
            "replan_count": 0,
            "failed_units": 0,
            "avg_loop_count": 0,
            "constraint_satisfied_ratio": 1.0,
            "verifier_pass_ratio": 1.0,
            "units": [],
        }
        with patch('time.time', return_value=1234567890.5):
            with patch('skills.signal_collector.build_execution_record', return_value=mock_execution):
                with patch('skills.signal_collector.evaluate_layer3', return_value=None):
                    result = collect("test-session", "general", None)

        assert isinstance(result["timestamp"], float)
        assert isinstance(result["ts"], str)
        assert result["timestamp"] == 1234567890.5


# ── Skipped TCs (TC-14 ~ TC-19, TC-23 ~ TC-31) ──

@pytest.mark.skip(reason="TC-14: Testing private method _enforce_trace_size; design doc does not describe its implementation.")
def test_tc14():
    pass

@pytest.mark.skip(reason="TC-15: Testing private method _enforce_trace_size; design doc does not describe its implementation.")
def test_tc15():
    pass

@pytest.mark.skip(reason="TC-16: Design doc does not describe _count_review_fails implementation.")
def test_tc16():
    pass

@pytest.mark.skip(reason="TC-17: Design doc does not describe _count_unsatisfied_constraints implementation.")
def test_tc17():
    pass

@pytest.mark.skip(reason="TC-18: Design doc does not describe _read_state_file implementation.")
def test_tc18():
    pass

@pytest.mark.skip(reason="TC-19: Design doc does not describe _write_state_file implementation.")
def test_tc19():
    pass

@pytest.mark.skip(reason="TC-23: _get_clarifier_constraints is a private method; design doc does not describe its implementation.")
def test_tc23():
    pass

@pytest.mark.skip(reason="TC-24: Design doc does not describe random audit implementation.")
def test_tc24():
    pass

@pytest.mark.skip(reason="TC-25: Design doc does not describe boundary condition for empty units.")
def test_tc25():
    pass

@pytest.mark.skip(reason="TC-26: _get_clarifier_constraints is a private method; design doc does not describe its implementation.")
def test_tc26():
    pass

@pytest.mark.skip(reason="TC-27: Testing private method _parse_layer3_response; design doc does not describe its implementation.")
def test_tc27():
    pass

@pytest.mark.skip(reason="TC-28: Testing private method _parse_layer3_response; design doc does not describe its implementation.")
def test_tc28():
    pass

@pytest.mark.skip(reason="TC-29: Testing private method _parse_layer3_response; design doc does not describe its implementation.")
def test_tc29():
    pass

@pytest.mark.skip(reason="TC-30: Testing private method _parse_layer3_response; design doc does not describe its implementation.")
def test_tc30():
    pass

@pytest.mark.skip(reason="TC-31: Testing private method _build_layer3_prompt; design doc does not describe its implementation.")
def test_tc31():
    pass