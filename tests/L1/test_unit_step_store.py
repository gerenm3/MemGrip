"""Test plan L1 - UnitStore + StepStore (#7)

Covers: UnitStore (save_unit, get_unit, get_all_units),
        StepStore (save_step, get_step, get_steps_by_unit, clear_unit_steps)

Total: 21 test cases (TC-07-01 ~ TC-07-21, 2 skipped)

Black-box principle: No direct access to _store / _unit_steps.
All state built via public APIs.
"""

import pytest
from core.storage import UnitStore, StepStore
from models.blueprints import UnitResult, StepResult, UnitStatus, StepStatus


# ── UnitStore ───────────────────────────────────────────────────────────

class TestUnitStore:
    """TC-07-01 ~ TC-07-10"""

    def test_TC_07_01_save_unit_normal(self):
        store = UnitStore()
        unit_result = UnitResult(unit_id="u0", status=UnitStatus.SUCCESS)
        store.save_unit("s1", "u0", unit_result)
        # Verify via public API
        assert store.get_unit("s1", "u0") == unit_result

    def test_TC_07_02_save_unit_overwrite(self):
        store = UnitStore()
        r1 = UnitResult(unit_id="u0", status=UnitStatus.SUCCESS)
        r2 = UnitResult(unit_id="u0", status=UnitStatus.FAILED)
        store.save_unit("s1", "u0", r1)
        store.save_unit("s1", "u0", r2)
        assert store.get_unit("s1", "u0") == r2

    def test_TC_07_03_save_unit_new_session(self):
        store = UnitStore()
        unit_result = UnitResult(unit_id="u0", status=UnitStatus.SUCCESS)
        store.save_unit("s2", "u0", unit_result)
        assert store.get_unit("s2", "u0") == unit_result

    def test_TC_07_04_save_unit_none_result(self):
        store = UnitStore()
        store.save_unit("s1", "u0", None)
        assert store.get_unit("s1", "u0") is None

    def test_TC_07_05_get_unit_exists(self):
        store = UnitStore()
        unit_result = UnitResult(unit_id="u0", status=UnitStatus.SUCCESS)
        store.save_unit("s1", "u0", unit_result)
        result = store.get_unit("s1", "u0")
        assert result == unit_result

    def test_TC_07_06_get_unit_session_not_exists(self):
        store = UnitStore()
        result = store.get_unit("s2", "u0")
        assert result is None

    def test_TC_07_07_get_unit_id_not_exists(self):
        store = UnitStore()
        unit_result = UnitResult(unit_id="u0", status=UnitStatus.SUCCESS)
        store.save_unit("s1", "u0", unit_result)
        result = store.get_unit("s1", "u99")
        assert result is None

    def test_TC_07_08_get_all_units_normal(self):
        store = UnitStore()
        r1 = UnitResult(unit_id="u0", status=UnitStatus.SUCCESS)
        r2 = UnitResult(unit_id="u1", status=UnitStatus.FAILED)
        store.save_unit("s1", "u0", r1)
        store.save_unit("s1", "u1", r2)
        result = store.get_all_units("s1")
        assert r1 in result
        assert r2 in result
        assert len(result) == 2

    def test_TC_07_09_get_all_units_session_not_exists(self):
        store = UnitStore()
        result = store.get_all_units("s2")
        assert result == []

    def test_TC_07_10_get_all_units_empty_session(self):
        # SKIPPED: Cannot create an empty session via public API.
        # The store only creates session keys when save_unit is called.
        # This test requires a state that is not reachable through public APIs.
        pytest.skip("Cannot create empty session via public API (black-box constraint)")


# ── StepStore ───────────────────────────────────────────────────────────

class TestStepStore:
    """TC-07-11 ~ TC-07-23 (2 skipped)"""

    def test_TC_07_11_save_step_normal(self):
        store = StepStore()
        step_result = StepResult(step_id="step_0", status=StepStatus.SUCCESS)
        store.save_step("s1", "u0", "step_0", step_result)
        # Verify via public API
        assert store.get_step("s1", "step_0") == step_result

    def test_TC_07_12_save_step_overwrite(self):
        store = StepStore()
        r1 = StepResult(step_id="step_0", status=StepStatus.SUCCESS)
        r2 = StepResult(step_id="step_0", status=StepStatus.FAILED)
        store.save_step("s1", "u0", "step_0", r1)
        store.save_step("s1", "u0", "step_0", r2)
        assert store.get_step("s1", "step_0") == r2

    def test_TC_07_13_save_step_creates_unit_steps(self):
        store = StepStore()
        step_result = StepResult(step_id="step_0", status=StepStatus.SUCCESS)
        store.save_step("s1", "u0", "step_0", step_result)
        # save_step should auto-create _unit_steps entry
        result = store.get_steps_by_unit("s1", "u0")
        assert len(result) == 1
        assert result[0] == step_result

    def test_TC_07_14_get_step_exists(self):
        store = StepStore()
        step_result = StepResult(step_id="step_0", status=StepStatus.SUCCESS)
        store.save_step("s1", "u0", "step_0", step_result)
        result = store.get_step("s1", "step_0")
        assert result == step_result

    def test_TC_07_15_get_step_session_not_exists(self):
        store = StepStore()
        result = store.get_step("s2", "step_0")
        assert result is None

    def test_TC_07_16_get_step_id_not_exists(self):
        store = StepStore()
        step_result = StepResult(step_id="step_0", status=StepStatus.SUCCESS)
        store.save_step("s1", "u0", "step_0", step_result)
        result = store.get_step("s1", "step_99")
        assert result is None

    def test_TC_07_17_get_steps_by_unit_normal(self):
        store = StepStore()
        r0 = StepResult(step_id="step_0", status=StepStatus.SUCCESS)
        r1 = StepResult(step_id="step_1", status=StepStatus.SUCCESS)
        store.save_step("s1", "u0", "step_0", r0)
        store.save_step("s1", "u0", "step_1", r1)
        result = store.get_steps_by_unit("s1", "u0")
        assert r0 in result
        assert r1 in result
        assert len(result) == 2

    def test_TC_07_18_get_steps_by_unit_session_not_exists(self):
        store = StepStore()
        result = store.get_steps_by_unit("s2", "u0")
        assert result == []

    def test_TC_07_19_get_steps_by_unit_unit_not_exists(self):
        store = StepStore()
        step_result = StepResult(step_id="step_0", status=StepStatus.SUCCESS)
        store.save_step("s1", "u0", "step_0", step_result)
        result = store.get_steps_by_unit("s1", "u99")
        assert result == []

    def test_TC_07_20_get_steps_by_unit_step_deleted(self):
        # SKIPPED: Cannot create a state where unit_steps references a deleted step
        # via public APIs. This requires internal manipulation.
        pytest.skip("Cannot create deleted-step state via public API (black-box constraint)")

    def test_TC_07_21_clear_unit_steps_normal(self):
        store = StepStore()
        step_result = StepResult(step_id="step_0", status=StepStatus.SUCCESS)
        store.save_step("s1", "u0", "step_0", step_result)
        store.clear_unit_steps("s1", "u0")
        # Verify via public API
        assert store.get_step("s1", "step_0") is None

    def test_TC_07_22_clear_unit_steps_session_not_exists(self):
        store = StepStore()
        store.clear_unit_steps("s2", "u0")
        # Should not raise

    def test_TC_07_23_clear_unit_steps_unit_not_exists(self):
        store = StepStore()
        store.clear_unit_steps("s1", "u99")
        # Should not raise