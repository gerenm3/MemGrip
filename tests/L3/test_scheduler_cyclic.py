"""Scheduler cyclic dependency tests"""

import asyncio
import logging
from io import StringIO
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.scheduler import topological_sort, apply_pruning
from core.executor import Executor
from models.blueprints import Unit, UnitResult, UnitStatus


# ── topological_sort ──────────────────────────────────────────


class TestTopologicalSortCyclic:
    """測試 topological_sort 回傳 cyclic_units 的行為"""

    def test_no_cyclic_returns_empty_cyclic(self) -> None:
        """無循環時，cyclic_units 應為空"""
        units = [
            Unit(unit_id="a", goal="goal_a"),
            Unit(unit_id="b", goal="goal_b", depends_on=["a"]),
            Unit(unit_id="c", goal="goal_c", depends_on=["b"]),
        ]
        sorted_units, cyclic_units = topological_sort(units)
        assert cyclic_units == []
        assert [u.unit_id for u in sorted_units] == ["a", "b", "c"]

    def test_simple_cycle_returns_cyclic_units(self) -> None:
        """A → B → A 循環"""
        units = [
            Unit(unit_id="a", goal="goal_a", depends_on=["b"]),
            Unit(unit_id="b", goal="goal_b", depends_on=["a"]),
        ]
        sorted_units, cyclic_units = topological_sort(units)
        assert len(cyclic_units) == 2
        assert {u.unit_id for u in cyclic_units} == {"a", "b"}
        assert sorted_units == []

    def test_three_way_cycle(self) -> None:
        """A → B → C → A 循環"""
        units = [
            Unit(unit_id="a", goal="goal_a", depends_on=["c"]),
            Unit(unit_id="b", goal="goal_b", depends_on=["a"]),
            Unit(unit_id="c", goal="goal_c", depends_on=["b"]),
        ]
        sorted_units, cyclic_units = topological_sort(units)
        assert len(cyclic_units) == 3
        assert {u.unit_id for u in cyclic_units} == {"a", "b", "c"}

    def test_mixed_cycle_and_dag(self) -> None:
        """部分 DAG + 部分循環：{a, b} 為 DAG，{c, d} 循環"""
        units = [
            Unit(unit_id="a", goal="goal_a"),
            Unit(unit_id="b", goal="goal_b", depends_on=["a"]),
            Unit(unit_id="c", goal="goal_c", depends_on=["d"]),
            Unit(unit_id="d", goal="goal_d", depends_on=["c"]),
        ]
        sorted_units, cyclic_units = topological_sort(units)
        assert len(sorted_units) == 2
        assert {u.unit_id for u in sorted_units} == {"a", "b"}
        assert len(cyclic_units) == 2
        assert {u.unit_id for u in cyclic_units} == {"c", "d"}


class TestTopologicalSortLogging:
    """測試 cyclic 時有 logger.warning"""

    def test_warning_logged_on_cycle(self, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level(logging.WARNING)
        units = [
            Unit(unit_id="a", goal="a", depends_on=["b"]),
            Unit(unit_id="b", goal="b", depends_on=["a"]),
        ]
        topological_sort(units)
        assert any("循環依賴" in entry.message for entry in caplog.records)


# ── Executor cyclic handling ──────────────────────────────────


class TestExecutorCyclicHandling:
    """測試 Executor.execute_units 收到 cyclic units 會標記 FAILED"""

    @pytest.mark.asyncio
    async def test_cyclic_units_marked_failed(self) -> None:
        executor = Executor()
        units = [
            Unit(unit_id="a", goal="goal_a", depends_on=["b"]),
            Unit(unit_id="b", goal="goal_b", depends_on=["a"]),
        ]
        # unit_steps 不需要為 cyclic units 提供（它們根本不會執行）
        results = await executor.execute_units(units, {}, server_schemas={})
        assert len(results) == 2
        assert results["a"].status == UnitStatus.FAILED
        assert results["a"].error == "循環依賴，無法執行"
        assert results["b"].status == UnitStatus.FAILED
        assert results["b"].error == "循環依賴，無法執行"

    @pytest.mark.asyncio
    async def test_mixed_dag_and_cycle(self) -> None:
        """DAG units 正常排序，cyclic units 標記 FAILED

        注意：L2 規劃已移至 orchestrator，所以 executor 不需要 mock planner.plan_unit。
        executor 內的 call_model_func mock 是供 _run_agentic_loop 使用。
        """
        from models.blueprints import Result

        mock_planner = MagicMock()
        mock_planner.plan_unit = AsyncMock(return_value=[MagicMock(step_id="1", goal="test", output_type="GLOBAL")])
        mock_execute_tool_func = AsyncMock(return_value="[ok] done")

        executor = Executor(planner=mock_planner, execute_tool_func=mock_execute_tool_func)

        # call_model_func 回傳 Result 物件（而非 tuple）
        mock_result = Result(success=True, data="test output")
        executor.call_model_func = AsyncMock(return_value=mock_result)
        units = [
            Unit(unit_id="a", goal="goal_a"),
            Unit(unit_id="b", goal="goal_b", depends_on=["a"]),
            Unit(unit_id="c", goal="goal_c", depends_on=["d"]),
            Unit(unit_id="d", goal="goal_d", depends_on=["c"]),
        ]
        unit_steps = {
            "a": [MagicMock(step_id="1", goal="goal_a", depends_on=[], upstream_depends=[])],
            "b": [MagicMock(step_id="1", goal="goal_b", depends_on=["a"], upstream_depends=[])],
        }
        results = await executor.execute_units(units, unit_steps, server_schemas={})
        assert len(results) == 4

        # cyclic units → FAILED
        assert results["c"].status == UnitStatus.FAILED
        assert results["c"].error == "循環依賴，無法執行"
        assert results["d"].status == UnitStatus.FAILED
        assert results["d"].error == "循環依賴，無法執行"

        # DAG units 不會被標記為 cyclic
        assert results["a"].status != UnitStatus.FAILED or results["a"].error != "循環依賴，無法執行"
        assert results["b"].status != UnitStatus.FAILED or results["b"].error != "循環依賴，無法執行"