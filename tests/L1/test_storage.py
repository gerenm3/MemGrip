"""tests/L1/test_storage -- 8 筆測試."""

import pytest
from models.blueprints import UnitResult, StepResult, UnitStatus, StepStatus


class TestUnitStore:
    """UnitStore 測試 (1-4)."""

    def test_unit_store_save_and_get(self, mock_flush_unit_store):
        from core.storage import UnitStore

        store = UnitStore()
        ur = UnitResult(unit_id="u1", status=UnitStatus.SUCCESS, output={"key": "val"})
        store.save_unit("s1", "u1", ur)
        result = store.get_unit("s1", "u1")
        assert result is not None
        assert result.unit_id == "u1"

    def test_unit_store_get_all_returns_list(self, mock_flush_unit_store):
        from core.storage import UnitStore

        store = UnitStore()
        store.save_unit("s1", "u1", UnitResult(unit_id="u1", status=UnitStatus.SUCCESS))
        store.save_unit("s1", "u2", UnitResult(unit_id="u2", status=UnitStatus.FAILED))
        units = store.get_all_units("s1")
        assert len(units) == 2

    def test_unit_store_session_isolation(self, mock_flush_unit_store):
        from core.storage import UnitStore

        store = UnitStore()
        store.save_unit("s1", "u1", UnitResult(unit_id="u1", status=UnitStatus.SUCCESS))
        result = store.get_unit("s2", "u1")
        assert result is None

    def test_unit_store_overwrite_updates(self, mock_flush_unit_store):
        from core.storage import UnitStore

        store = UnitStore()
        store.save_unit("s1", "u1", UnitResult(unit_id="u1", status=UnitStatus.SUCCESS))
        store.save_unit("s1", "u1", UnitResult(unit_id="u1", status=UnitStatus.FAILED))
        result = store.get_unit("s1", "u1")
        assert result.status == UnitStatus.FAILED


class TestStepStore:
    """StepStore 測試 (5-8)."""

    def test_step_store_save_and_get(self, mock_flush_step_store):
        from core.storage import StepStore

        store = StepStore()
        sr = StepResult(step_id="s1", status=StepStatus.SUCCESS, output="out")
        store.save_step("s1", "u1", "s1", sr)
        result = store.get_step("s1", "s1")
        assert result is not None
        assert result.step_id == "s1"

    def test_step_store_get_by_unit(self, mock_flush_step_store):
        from core.storage import StepStore

        store = StepStore()
        store.save_step("s1", "u1", "s1", StepResult(step_id="s1", status=StepStatus.SUCCESS))
        store.save_step("s1", "u1", "s2", StepResult(step_id="s2", status=StepStatus.FAILED))
        steps = store.get_steps_by_unit("s1", "u1")
        assert len(steps) == 2

    def test_step_store_clear_unit_steps(self, mock_flush_step_store):
        from core.storage import StepStore

        store = StepStore()
        store.save_step("s1", "u1", "s1", StepResult(step_id="s1", status=StepStatus.SUCCESS))
        store.clear_unit_steps("s1", "u1")
        steps = store.get_steps_by_unit("s1", "u1")
        assert len(steps) == 0

    def test_step_store_session_isolation(self, mock_flush_step_store):
        from core.storage import StepStore

        store = StepStore()
        store.save_step("s1", "u1", "s1", StepResult(step_id="s1", status=StepStatus.SUCCESS))
        result = store.get_step("s2", "s1")
        assert result is None
