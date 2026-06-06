"""tests/L1/test_scheduler_logic.py — core/scheduler.py 純邏輯測試（18 筆）."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import unittest.mock

from models.blueprints import Unit, Step, Result


class TestValidateDAG:
    """validate_dag 函式測試."""

    def test_empty_units(self):
        """邊界：空 units → success=True."""
        from core.scheduler import validate_dag
        result = validate_dag([])
        assert result.success is True

    def test_single_unit(self):
        """等價類：單一 unit → success=True."""
        from core.scheduler import validate_dag
        units = [Unit(unit_id="u1", goal="test")]
        result = validate_dag(units)
        assert result.success is True

    def test_valid_dag(self):
        """等價類：合法 DAG → success=True."""
        from core.scheduler import validate_dag
        units = [
            Unit(unit_id="u1", goal="root"),
            Unit(unit_id="u2", goal="child", depends_on=["u1"]),
        ]
        result = validate_dag(units)
        assert result.success is True

    def test_missing_dep(self):
        """等價類：依賴不存在 → success=False."""
        from core.scheduler import validate_dag
        units = [Unit(unit_id="u1", goal="test", depends_on=["u99"])]
        result = validate_dag(units)
        assert result.success is False
        assert "u99" in result.error

    def test_cycle(self):
        """等價類：循環依賴 → success=False."""
        from core.scheduler import validate_dag
        units = [
            Unit(unit_id="u1", goal="a", depends_on=["u2"]),
            Unit(unit_id="u2", goal="b", depends_on=["u1"]),
        ]
        result = validate_dag(units)
        assert result.success is False
        assert "循環" in result.error

    def test_content_depends_action(self):
        """等價類：CONTENT 依賴 ACTION → success=False."""
        from core.scheduler import validate_dag
        units = [
            Unit(unit_id="u1", goal="action", output_type="ACTION"),
            Unit(unit_id="u2", goal="content", output_type="CONTENT", depends_on=["u1"]),
        ]
        result = validate_dag(units)
        assert result.success is False
        assert "ACTION" in result.error

    def test_no_root_node(self):
        """等價類：無 root node → success=False."""
        from core.scheduler import validate_dag
        units = [
            Unit(unit_id="u1", goal="a", depends_on=["u2"]),
            Unit(unit_id="u2", goal="b", depends_on=["u1"]),
        ]
        result = validate_dag(units)
        assert result.success is False
        assert "root node" in result.error


class TestValidateSteps:
    """validate_steps 函式測試."""

    def test_empty_steps(self):
        """邊界：空 steps → success=False."""
        from core.scheduler import validate_steps
        result = validate_steps([])
        assert result.success is False

    def test_no_global(self):
        """等價類：無 GLOBAL step → success=False."""
        from core.scheduler import validate_steps
        steps = [Step(step_id="s1", goal="test", output_type="INTERNAL")]
        result = validate_steps(steps)
        assert result.success is False

    def test_has_global(self):
        """等價類：有 GLOBAL step → success=True."""
        from core.scheduler import validate_steps
        steps = [
            Step(step_id="s1", goal="test", output_type="INTERNAL"),
            Step(step_id="s2", goal="global", output_type="GLOBAL"),
        ]
        result = validate_steps(steps)
        assert result.success is True


class TestSchedulerSchedule:
    """Scheduler.schedule 測試."""

    @unittest.mock.patch("config.PATTERNS_PATH", "/dev/null")
    def test_simple_schedule(self):
        """等價類：簡單 DAG 排序正確."""
        from core.scheduler import Scheduler
        scheduler = Scheduler()
        units = [
            Unit(unit_id="u1", goal="root"),
            Unit(unit_id="u2", goal="child", depends_on=["u1"]),
        ]
        unit_steps = {"u1": [Step(step_id="s1", goal="s1")], "u2": [Step(step_id="s2", goal="s2")]}
        result = scheduler.schedule(units, unit_steps)
        assert result.success is True
        assert len(result.data["execution_order"]) == 2
        assert result.data["execution_order"][0].unit_id == "u1"

    @unittest.mock.patch("config.PATTERNS_PATH", "/dev/null")
    def test_cyclic_units_returned(self):
        """等價類：循環依賴 → cyclic_units 有值."""
        from core.scheduler import Scheduler
        scheduler = Scheduler()
        units = [
            Unit(unit_id="u1", goal="a", depends_on=["u2"]),
            Unit(unit_id="u2", goal="b", depends_on=["u1"]),
        ]
        unit_steps = {"u1": [], "u2": []}
        result = scheduler.schedule(units, unit_steps)
        assert result.data["cyclic_units"] != []

    def test_empty_input(self):
        """邊界：空輸入 → 空排序."""
        from core.scheduler import Scheduler
        scheduler = Scheduler()
        result = scheduler.schedule([], {})
        assert result.success is True
        assert result.data["execution_order"] == []


class TestTopologicalSortSteps:
    """Scheduler._topological_sort_steps 測試."""

    def test_simple_steps(self):
        """等價類：簡單 steps 排序."""
        from core.scheduler import Scheduler
        scheduler = Scheduler()
        steps = [
            Step(step_id="s1", goal="first"),
            Step(step_id="s2", goal="second", depends_on=["s1"]),
        ]
        sorted_steps, cyclic = scheduler._topological_sort_steps(steps)
        assert len(sorted_steps) == 2
        assert sorted_steps[0].step_id == "s1"

    def test_no_steps(self):
        """邊界：空 steps → 空列表."""
        from core.scheduler import Scheduler
        scheduler = Scheduler()
        sorted_steps, cyclic = scheduler._topological_sort_steps([])
        assert sorted_steps == []

    def test_step_cycle(self):
        """等價類：steps 循環 → cyclic 有值."""
        from core.scheduler import Scheduler
        scheduler = Scheduler()
        steps = [
            Step(step_id="s1", goal="a", depends_on=["s2"]),
            Step(step_id="s2", goal="b", depends_on=["s1"]),
        ]
        sorted_steps, cyclic = scheduler._topological_sort_steps(steps)
        assert cyclic != []


class TestRunKahns:
    """Scheduler._run_kahns 測試."""

    @unittest.mock.patch("config.PATTERNS_PATH", "/dev/null")
    def test_empty_items(self):
        """邊界：空 items → 空列表."""
        from core.scheduler import Scheduler
        scheduler = Scheduler()
        sorted_items, cyclic = scheduler._run_kahns(
            [], get_id=lambda x: x, get_deps=lambda x: []
        )
        assert sorted_items == []
        assert cyclic == []

    @unittest.mock.patch("config.PATTERNS_PATH", "/dev/null")
    def test_simple_items(self):
        """等價類：簡單 items 排序."""
        from core.scheduler import Scheduler
        scheduler = Scheduler()
        items = [
            {"id": "a", "deps": []},
            {"id": "b", "deps": ["a"]},
        ]
        sorted_items, cyclic = scheduler._run_kahns(
            items, get_id=lambda x: x["id"], get_deps=lambda x: x["deps"]
        )
        assert len(sorted_items) == 2
        assert sorted_items[0]["id"] == "a"