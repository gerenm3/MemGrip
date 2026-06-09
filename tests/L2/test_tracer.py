"""
tests/L2/test_tracer.py -- L2 mock integration tests for Tracer.
Group 11: 9 TCs + 18 skipped
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_project_root = Path(__file__).resolve().parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from models.blueprints import UnitResult, UnitStatus


# ── Tracer Tests (TC-01 ~ TC-09) ──

class TestTracer:
    """Tracer tests: TC-01 ~ TC-09."""

    def test_tc01_new_session_generates_session_id(self):
        """TC-01: new_session 生成 session ID."""
        from core.tracer import new_session

        with patch('core.tracer.uuid') as mock_uuid_mod:
            mock_obj = MagicMock()
            mock_obj.hex = "test-session-id"
            mock_obj.__str__ = MagicMock(return_value="test-session-id")
            mock_uuid_mod.uuid4.return_value = mock_obj
            result = new_session()

        assert result == "test-session-id"

    def test_tc02_log_model_call_basic(self, tmp_path):
        """TC-02: log_model_call 基本記錄."""
        from core.tracer import log_model_call

        captured_content = []

        def mock_open_side_effect(*args, **kwargs):
            mock_file = MagicMock()

            def mock_write(content):
                captured_content.append(content)

            mock_file.write = mock_write
            mock_file.__enter__ = MagicMock(return_value=mock_file)
            mock_file.__exit__ = MagicMock(return_value=False)
            return mock_file

        with patch('builtins.open', side_effect=mock_open_side_effect):
            log_model_call(
                caller="router",
                model="qwen3.5:9b",
                messages=[{"role": "user", "content": "test"}],
                response="response content",
                tool_calls=[],
            )

        assert len(captured_content) > 0

    def test_tc03_log_model_call_with_tool_calls(self, tmp_path):
        """TC-03: log_model_call 含 tool_calls."""
        from core.tracer import log_model_call

        captured_content = []

        def mock_open_side_effect(*args, **kwargs):
            mock_file = MagicMock()

            def mock_write(content):
                captured_content.append(content)

            mock_file.write = mock_write
            mock_file.__enter__ = MagicMock(return_value=mock_file)
            mock_file.__exit__ = MagicMock(return_value=False)
            return mock_file

        with patch('builtins.open', side_effect=mock_open_side_effect):
            log_model_call(
                caller="executor",
                model="qwen3.6:35b-a3b",
                messages=[{"role": "assistant", "content": ""}],
                response="tool call response",
                tool_calls=[{"name": "brave_search", "arguments": {"query": "test"}}],
                unit_id="u1",
                step_id="s1",
            )

        assert len(captured_content) > 0
        all_content = " ".join(str(c) for c in captured_content)
        assert "brave_search" in all_content

    def test_tc04_log_model_call_with_unit_id_step_id(self, tmp_path):
        """TC-04: log_model_call 含 unit_id/step_id."""
        from core.tracer import log_model_call

        captured_content = []

        def mock_open_side_effect(*args, **kwargs):
            mock_file = MagicMock()

            def mock_write(content):
                captured_content.append(content)

            mock_file.write = mock_write
            mock_file.__enter__ = MagicMock(return_value=mock_file)
            mock_file.__exit__ = MagicMock(return_value=False)
            return mock_file

        with patch('builtins.open', side_effect=mock_open_side_effect):
            log_model_call(
                caller="verifier",
                model="qwen3.5:9b",
                messages=[{"role": "user", "content": "verify"}],
                response="verified",
                tool_calls=[],
                unit_id="u1",
                step_id="s2",
            )

        assert len(captured_content) > 0
        all_content = " ".join(str(c) for c in captured_content)
        assert "u1" in all_content

    def test_tc05_log_model_call_empty_messages(self, tmp_path):
        """TC-05: log_model_call 空 messages → 正常寫入不拋異常."""
        from core.tracer import log_model_call

        with patch('builtins.open', MagicMock()) as mock_open:
            mock_file = MagicMock()
            mock_file.__enter__ = MagicMock(return_value=None)
            mock_file.__exit__ = MagicMock(return_value=False)
            mock_open.return_value = mock_file

            # Should not raise
            log_model_call(
                caller="router",
                model="qwen3.5:9b",
                messages=[],
                response="response",
                tool_calls=[],
            )

            mock_open.assert_called()

    def test_tc06_log_task_basic(self, tmp_path):
        """TC-06: log_task 基本記錄."""
        from core.tracer import log_task

        results = {"u1": UnitResult(
            unit_id="u1",
            status=UnitStatus.SUCCESS,
            output="O1",
            error="",
            replan_count=0,
            total_loop_count=1,
            step_loop_counts=[1],
            constraint_checks=[],
        )}
        # units must have .unit_id, .goal, .output_type attributes
        mock_unit = MagicMock()
        mock_unit.unit_id = "u1"
        mock_unit.goal = "G1"
        mock_unit.output_type = "text"
        mock_unit.assigned_constraints = []
        units = [mock_unit]

        captured_content = []

        def mock_open_side_effect(*args, **kwargs):
            mock_file = MagicMock()

            def mock_write(content):
                captured_content.append(content)

            mock_file.write = mock_write
            mock_file.__enter__ = MagicMock(return_value=mock_file)
            mock_file.__exit__ = MagicMock(return_value=False)
            return mock_file

        with patch('builtins.open', side_effect=mock_open_side_effect):
            with patch('core.tracer._extract_unit_results', return_value=[results["u1"]]):
                log_task(
                    task_type="general",
                    user_input="測試輸入",
                    goal="測試目標",
                    results=results,
                    units=units,
                )

        assert len(captured_content) > 0

    def test_tc07_log_task_with_clarifier_constraints(self, tmp_path):
        """TC-07: log_task 含 clarifier_constraints."""
        from core.tracer import log_task

        captured_content = []

        def mock_open_side_effect(*args, **kwargs):
            mock_file = MagicMock()

            def mock_write(content):
                captured_content.append(content)

            mock_file.write = mock_write
            mock_file.__enter__ = MagicMock(return_value=mock_file)
            mock_file.__exit__ = MagicMock(return_value=False)
            return mock_file

        with patch('builtins.open', side_effect=mock_open_side_effect):
            log_task(
                task_type="general",
                user_input="測試輸入",
                goal="測試目標",
                results={},
                units=[],
                clarifier_constraints=["C1", "C2"],
            )

        assert len(captured_content) > 0
        all_content = " ".join(str(c) for c in captured_content)
        assert "C1" in all_content or "C2" in all_content

    def test_tc08_log_task_with_skill_version(self, tmp_path):
        """TC-08: log_task 含 skill_version."""
        from core.tracer import log_task

        captured_content = []

        def mock_open_side_effect(*args, **kwargs):
            mock_file = MagicMock()

            def mock_write(content):
                captured_content.append(content)

            mock_file.write = mock_write
            mock_file.__enter__ = MagicMock(return_value=mock_file)
            mock_file.__exit__ = MagicMock(return_value=False)
            return mock_file

        with patch('builtins.open', side_effect=mock_open_side_effect):
            log_task(
                task_type="general",
                user_input="測試輸入",
                goal="測試目標",
                results={},
                units=[],
                skill_version=5,
            )

        assert len(captured_content) > 0

    def test_tc09_log_task_empty_units(self, tmp_path):
        """TC-09: log_task units 為空 → 正常寫入."""
        from core.tracer import log_task

        with patch('builtins.open', MagicMock()) as mock_open:
            mock_file = MagicMock()
            mock_file.__enter__ = MagicMock(return_value=None)
            mock_file.__exit__ = MagicMock(return_value=False)
            mock_open.return_value = mock_file

            # Should not raise
            log_task(
                task_type="general",
                user_input="測試輸入",
                goal="測試目標",
                results={},
                units=[],
            )

            mock_open.assert_called()


# ── Skipped TCs (TC-10 ~ TC-27) ──

@pytest.mark.skip(reason="TC-10: 'behavior consistency' cannot be verified; design doc does not describe log_model_call class method behavior consistency.")
def test_tc10():
    pass

@pytest.mark.skip(reason="TC-11: Testing private method _extract_unit_results; design doc does not describe its implementation.")
def test_tc11():
    pass

@pytest.mark.skip(reason="TC-12: Testing private method _extract_unit_results; design doc does not describe its implementation.")
def test_tc12():
    pass

@pytest.mark.skip(reason="TC-13: Testing private method _get_status_value; design doc does not describe its implementation.")
def test_tc13():
    pass

@pytest.mark.skip(reason="TC-14: Testing private method _get_status_value; design doc does not describe its implementation.")
def test_tc14():
    pass

@pytest.mark.skip(reason="TC-15: Testing private method _get_status_value; design doc does not describe its implementation.")
def test_tc15():
    pass

@pytest.mark.skip(reason="TC-16: Testing private method _get_error; design doc does not describe its implementation.")
def test_tc16():
    pass

@pytest.mark.skip(reason="TC-17: Testing private method _get_error; design doc does not describe its implementation.")
def test_tc17():
    pass

@pytest.mark.skip(reason="TC-18: Testing private method _get_replan_count; design doc does not describe its implementation.")
def test_tc18():
    pass

@pytest.mark.skip(reason="TC-19: Testing private method _get_replan_count; design doc does not describe its implementation.")
def test_tc19():
    pass

@pytest.mark.skip(reason="TC-20: Testing private method _get_total_loop_count; design doc does not describe its implementation.")
def test_tc20():
    pass

@pytest.mark.skip(reason="TC-21: Testing private method _get_total_loop_count; design doc does not describe its implementation.")
def test_tc21():
    pass

@pytest.mark.skip(reason="TC-22: Testing private method _get_step_loop_counts; design doc does not describe its implementation.")
def test_tc22():
    pass

@pytest.mark.skip(reason="TC-23: Testing private method _get_step_loop_counts; design doc does not describe its implementation.")
def test_tc23():
    pass

@pytest.mark.skip(reason="TC-24: Testing private method _get_constraint_checks; design doc does not describe its implementation.")
def test_tc24():
    pass

@pytest.mark.skip(reason="TC-25: Testing private method _get_constraint_checks; design doc does not describe its implementation.")
def test_tc25():
    pass

@pytest.mark.skip(reason="TC-26: Testing private method _mask_messages; design doc does not describe masking rules.")
def test_tc26():
    pass

@pytest.mark.skip(reason="TC-27: Testing private method _mask_messages; design doc does not describe its implementation.")
def test_tc27():
    pass