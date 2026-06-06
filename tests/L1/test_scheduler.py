"""tests/L1/test_scheduler -- 20 筆測試."""

import pytest
from models.blueprints import Unit, Step, Result


class TestValidateDag:
    """validate_dag 測試 (1-12)."""

    def test_validate_dag_empty_list_returns_success(self):
        from core.scheduler import validate_dag

        result = validate_dag([])
        assert result.success is True

    def test_validate_dag_single_unit_returns_success(self, make_unit):
        from core.scheduler import validate_dag

        units = [make_unit("u1")]
        result = validate_dag(units)
        assert result.success is True

    def test_validate_dag_valid_chain_returns_success(self, make_unit):
        from core.scheduler import validate_dag

        a = make_unit("u1")
        b = make_unit("u2", depends_on=["u1"])
        c = make_unit("u3", depends_on=["u2"])
        result = validate_dag([a, b, c])
        assert result.success is True

    def test_validate_dag_diamond_returns_success(self, make_unit):
        from core.scheduler import validate_dag

        a = make_unit("u1")
        b = make_unit("u2", depends_on=["u1"])
        c = make_unit("u3", depends_on=["u1"])
        d = make_unit("u4", depends_on=["u2", "u3"])
        result = validate_dag([a, b, c, d])
        assert result.success is True

    def test_validate_dag_multiple_roots_returns_success(self, make_unit):
        from core.scheduler import validate_dag

        a = make_unit("u1")
        b = make_unit("u2")
        c = make_unit("u3", depends_on=["u1", "u2"])
        result = validate_dag([a, b, c])
        assert result.success is True

    def test_validate_dag_missing_dependency_returns_fail(self, make_unit):
        from core.scheduler import validate_dag

        a = make_unit("u1")
        b = make_unit("u2", depends_on=["u99"])
        result = validate_dag([a, b])
        assert result.success is False

    def test_validate_dag_cycle_returns_fail(self, make_unit):
        from core.scheduler import validate_dag

        a = make_unit("u1", depends_on=["u2"])
        b = make_unit("u2", depends_on=["u1"])
        result = validate_dag([a, b])
        assert result.success is False

    def test_validate_dag_complex_cycle_returns_fail(self, make_unit):
        from core.scheduler import validate_dag

        a = make_unit("u1", depends_on=["u3"])
        b = make_unit("u2", depends_on=["u1"])
        c = make_unit("u3", depends_on=["u2"])
        result = validate_dag([a, b, c])
        assert result.success is False

    def test_validate_dag_content_depends_action_returns_fail(self, make_unit):
        from core.scheduler import validate_dag

        action = make_unit("u1", output_type="ACTION")
        content = make_unit("u2", depends_on=["u1"], output_type="CONTENT")
        result = validate_dag([action, content])
        assert result.success is False

    def test_validate_dag_no_root_returns_fail(self, make_unit):
        from core.scheduler import validate_dag

        a = make_unit("u1", depends_on=["u2"])
        b = make_unit("u2", depends_on=["u1"])
        result = validate_dag([a, b])
        assert result.success is False

    def test_validate_dag_partial_missing_dep_returns_fail(self, make_unit):
        from core.scheduler import validate_dag

        a = make_unit("u1")
        b = make_unit("u2", depends_on=["u1", "u99"])
        result = validate_dag([a, b])
        assert result.success is False

    def test_validate_dag_cycle_error_contains_cyclic_ids(self, make_unit):
        from core.scheduler import validate_dag

        a = make_unit("u1", depends_on=["u2"])
        b = make_unit("u2", depends_on=["u1"])
        result = validate_dag([a, b])
        assert "循環" in result.error


class TestValidateSteps:
    """validate_steps 測試 (13-16)."""

    def test_validate_steps_empty_returns_fail(self):
        from core.scheduler import validate_steps

        result = validate_steps([])
        assert result.success is False

    def test_validate_steps_has_global_returns_success(self, make_step):
        from core.scheduler import validate_steps

        steps = [make_step(output_type="GLOBAL")]
        result = validate_steps(steps)
        assert result.success is True

    def test_validate_steps_no_global_returns_fail(self, make_step):
        from core.scheduler import validate_steps

        steps = [make_step(output_type="ACTION")]
        result = validate_steps(steps)
        assert result.success is False

    def test_validate_steps_multiple_global_returns_success(self, make_step):
        from core.scheduler import validate_steps

        steps = [
            make_step(step_id="s1", output_type="GLOBAL"),
            make_step(step_id="s2", output_type="GLOBAL"),
        ]
        result = validate_steps(steps)
        assert result.success is True


class TestSchedule:
    """Scheduler.schedule 測試 (17-20)."""

    def test_schedule_empty_returns_empty_order(self, make_unit, make_step, make_result):
        from core.scheduler import Scheduler

        scheduler = Scheduler()
        result = scheduler.schedule([], {})
        assert result.success is True
        assert result.data["execution_order"] == []

    def test_schedule_topological_order_correct(self, make_unit, make_step, make_result):
        from core.scheduler import Scheduler

        a = make_unit("u1")
        b = make_unit("u2", depends_on=["u1"])
        scheduler = Scheduler()
        result = scheduler.schedule([a, b], {"u1": [], "u2": []})
        assert result.success is True
        order = result.data["execution_order"]
        assert order[0].unit_id == "u1"
        assert order[1].unit_id == "u2"

    def test_schedule_cyclic_units_detected(self, make_unit, make_step, make_result):
        from core.scheduler import Scheduler

        a = make_unit("u1", depends_on=["u2"])
        b = make_unit("u2", depends_on=["u1"])
        scheduler = Scheduler()
        result = scheduler.schedule([a, b], {"u1": [], "u2": []})
        assert result.success is True
        assert len(result.data["cyclic_units"]) > 0

    def test_schedule_unit_step_orders_populated(self, make_unit, make_step, make_result):
        from core.scheduler import Scheduler

        a = make_unit("u1")
        s1 = make_step("s1", output_type="INTERNAL")
        s2 = make_step("s2", output_type="INTERNAL", depends_on=["s1"])
        scheduler = Scheduler()
        result = scheduler.schedule([a], {"u1": [s1, s2]})
        assert result.success is True
        assert "u1" in result.data["unit_step_orders"]
        assert len(result.data["unit_step_orders"]["u1"]) == 2
