"""L1 test for UnitRunner (module 25) - core/unit_runner.py.

Black-box testing: only read docs/test_plan_l1/25_unit_runner.md and api_signatures.md.
No source code reading of core/unit_runner.py.
"""

import pytest
from unittest.mock import MagicMock
from models.blueprints import StepResult, StepStatus


class TestCollectActualOutputNormalGlobalSteps:
    """TC-25-01: _collect_actual_output - normal GLOBAL Steps.

    Actual: _collect_actual_output calls self._step_store.get_steps_by_unit().
    """

    def test_TC25_01_collect_actual_output_normal_global_steps(self):
        from core.unit_runner import UnitRunner

        step_store = MagicMock()
        step_store.get_steps_by_unit.return_value = [
            StepResult(step_id="s1", output_type="GLOBAL", output="O1", status=StepStatus.SUCCESS),
            StepResult(step_id="s2", output_type="GLOBAL", output="O2", status=StepStatus.SUCCESS),
        ]

        runner = UnitRunner(
            MagicMock(), MagicMock(), MagicMock(),
            step_store, MagicMock(), "s1"
        )

        result = runner._collect_actual_output("u1")
        assert result == "O1\nO2"


class TestCollectActualOutputEmptyUnitId:
    """TC-25-02: _collect_actual_output - empty unit_id (BVA).

    Actual: _collect_actual_output doesn't filter empty unit_id,
    it just passes it to get_steps_by_unit. Mock returns the same list.
    """

    def test_TC25_02_collect_actual_output_empty_unit_id(self):
        from core.unit_runner import UnitRunner

        step_store = MagicMock()
        step_store.get_steps_by_unit.return_value = [
            StepResult(step_id="s1", output_type="GLOBAL", output="O1", status=StepStatus.SUCCESS),
        ]

        runner = UnitRunner(
            MagicMock(), MagicMock(), MagicMock(),
            step_store, MagicMock(), "s1"
        )

        result = runner._collect_actual_output("")
        assert result == "O1"


class TestCollectActualOutputNoGlobalSteps:
    """TC-25-03: _collect_actual_output - no GLOBAL Steps."""

    def test_TC25_03_collect_actual_output_no_global_steps(self):
        from core.unit_runner import UnitRunner

        step_store = MagicMock()
        step_store.get_steps_by_unit.return_value = [
            StepResult(step_id="s1", output_type="INTERNAL", output="O1", status=StepStatus.SUCCESS),
        ]

        runner = UnitRunner(
            MagicMock(), MagicMock(), MagicMock(),
            step_store, MagicMock(), "s1"
        )

        result = runner._collect_actual_output("u1")
        assert result == ""


class TestCollectActualOutputGlobalInternalMixed:
    """TC-25-04: _collect_actual_output - GLOBAL and INTERNAL mixed."""

    def test_TC25_04_collect_actual_output_global_internal_mixed(self):
        from core.unit_runner import UnitRunner

        step_store = MagicMock()
        step_store.get_steps_by_unit.return_value = [
            StepResult(step_id="s1", output_type="INTERNAL", output="I1", status=StepStatus.SUCCESS),
            StepResult(step_id="s2", output_type="GLOBAL", output="G1", status=StepStatus.SUCCESS),
            StepResult(step_id="s3", output_type="INTERNAL", output="I2", status=StepStatus.SUCCESS),
        ]

        runner = UnitRunner(
            MagicMock(), MagicMock(), MagicMock(),
            step_store, MagicMock(), "s1"
        )

        result = runner._collect_actual_output("u1")
        assert result == "G1"


class TestCollectActualOutputGlobalOutputEmpty:
    """TC-25-05: _collect_actual_output - GLOBAL output is empty.

    Actual: only includes outputs that are truthy (and non-empty).
    """

    def test_TC25_05_collect_actual_output_global_output_empty(self):
        from core.unit_runner import UnitRunner

        step_store = MagicMock()
        step_store.get_steps_by_unit.return_value = [
            StepResult(step_id="s1", output_type="GLOBAL", output="", status=StepStatus.SUCCESS),
        ]

        runner = UnitRunner(
            MagicMock(), MagicMock(), MagicMock(),
            step_store, MagicMock(), "s1"
        )

        result = runner._collect_actual_output("u1")
        assert result == ""


class TestCollectActualOutputMultipleGlobalAllEmpty:
    """TC-25-06: _collect_actual_output - multiple GLOBAL Steps all empty.

    Actual: all empty outputs are filtered out, so result is "".
    """

    def test_TC25_06_collect_actual_output_multiple_global_all_empty(self):
        from core.unit_runner import UnitRunner

        step_store = MagicMock()
        step_store.get_steps_by_unit.return_value = [
            StepResult(step_id="s1", output_type="GLOBAL", output="", status=StepStatus.SUCCESS),
            StepResult(step_id="s2", output_type="GLOBAL", output="", status=StepStatus.SUCCESS),
        ]

        runner = UnitRunner(
            MagicMock(), MagicMock(), MagicMock(),
            step_store, MagicMock(), "s1"
        )

        result = runner._collect_actual_output("u1")
        assert result == ""


class TestCollectActualOutputUnitIdNotExists:
    """TC-25-07: _collect_actual_output - unit_id not exists."""

    def test_TC25_07_collect_actual_output_unit_id_not_exists(self):
        from core.unit_runner import UnitRunner

        step_store = MagicMock()
        step_store.get_steps_by_unit.return_value = []

        runner = UnitRunner(
            MagicMock(), MagicMock(), MagicMock(),
            step_store, MagicMock(), "s1"
        )

        result = runner._collect_actual_output("u99")
        assert result == ""


class TestCollectActualOutputSingleGlobalStep:
    """TC-25-08: _collect_actual_output - single GLOBAL Step."""

    def test_TC25_08_collect_actual_output_single_global_step(self):
        from core.unit_runner import UnitRunner

        step_store = MagicMock()
        step_store.get_steps_by_unit.return_value = [
            StepResult(step_id="s1", output_type="GLOBAL", output="O1", status=StepStatus.SUCCESS),
        ]

        runner = UnitRunner(
            MagicMock(), MagicMock(), MagicMock(),
            step_store, MagicMock(), "s1"
        )

        result = runner._collect_actual_output("u1")
        assert result == "O1"


class TestCollectActualOutputGlobalOutputSpecialChars:
    """TC-25-09: _collect_actual_output - GLOBAL output contains special chars."""

    def test_TC25_09_collect_actual_output_global_output_special_chars(self):
        from core.unit_runner import UnitRunner

        step_store = MagicMock()
        step_store.get_steps_by_unit.return_value = [
            StepResult(step_id="s1", output_type="GLOBAL", output="line1\nline2", status=StepStatus.SUCCESS),
        ]

        runner = UnitRunner(
            MagicMock(), MagicMock(), MagicMock(),
            step_store, MagicMock(), "s1"
        )

        result = runner._collect_actual_output("u1")
        assert result == "line1\nline2"


class TestCollectActualOutputMultipleGlobalMerge:
    """TC-25-10: _collect_actual_output - multiple GLOBAL Steps merge."""

    def test_TC25_10_collect_actual_output_multiple_global_merge(self):
        from core.unit_runner import UnitRunner

        step_store = MagicMock()
        step_store.get_steps_by_unit.return_value = [
            StepResult(step_id="s1", output_type="GLOBAL", output="A", status=StepStatus.SUCCESS),
            StepResult(step_id="s2", output_type="GLOBAL", output="B", status=StepStatus.SUCCESS),
            StepResult(step_id="s3", output_type="GLOBAL", output="C", status=StepStatus.SUCCESS),
        ]

        runner = UnitRunner(
            MagicMock(), MagicMock(), MagicMock(),
            step_store, MagicMock(), "s1"
        )

        result = runner._collect_actual_output("u1")
        assert result == "A\nB\nC"