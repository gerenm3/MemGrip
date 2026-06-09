"""L1 test for Responder (module 24) - core/responder.py.

Black-box testing: only read docs/test_plan_l1/24_responder.md and api_signatures.md.
No source code reading of core/responder.py.
"""

import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock
from models.blueprints import Unit, UnitResult, UnitStatus, Result
from core.responder import Responder


class TestClassifyResultsAllSuccess:
    """TC-24-01: _classify_results - all SUCCESS.

    Actual signature: _classify_results(results: Dict[str, UnitResult])
    """

    def test_TC24_01_classify_results_all_success(self):
        results = {
            "u1": UnitResult(unit_id="u1", status=UnitStatus.SUCCESS),
            "u2": UnitResult(unit_id="u2", status=UnitStatus.SUCCESS),
        }

        success, failed, skipped = Responder._classify_results(results)
        assert len(success) == 2
        assert failed == []
        assert skipped == []


class TestClassifyResultsAllFailed:
    """TC-24-02: _classify_results - all FAILED."""

    def test_TC24_02_classify_results_all_failed(self):
        results = {
            "u1": UnitResult(unit_id="u1", status=UnitStatus.FAILED),
            "u2": UnitResult(unit_id="u2", status=UnitStatus.FAILED),
        }

        success, failed, skipped = Responder._classify_results(results)
        assert success == []
        assert len(failed) == 2
        assert skipped == []


class TestClassifyResultsAllSkipped:
    """TC-24-03: _classify_results - all SKIPPED."""

    def test_TC24_03_classify_results_all_skipped(self):
        results = {
            "u1": UnitResult(unit_id="u1", status=UnitStatus.SKIPPED),
            "u2": UnitResult(unit_id="u2", status=UnitStatus.SKIPPED),
        }

        success, failed, skipped = Responder._classify_results(results)
        assert success == []
        assert failed == []
        assert len(skipped) == 2


class TestClassifyResultsMixed:
    """TC-24-04: _classify_results - mixed status."""

    def test_TC24_04_classify_results_mixed(self):
        results = {
            "u1": UnitResult(unit_id="u1", status=UnitStatus.SUCCESS),
            "u2": UnitResult(unit_id="u2", status=UnitStatus.FAILED),
            "u3": UnitResult(unit_id="u3", status=UnitStatus.SKIPPED),
        }

        success, failed, skipped = Responder._classify_results(results)
        assert len(success) == 1
        assert len(failed) == 1
        assert len(skipped) == 1


class TestClassifyResultsEmpty:
    """TC-24-05: _classify_results - empty dict (BVA)."""

    def test_TC24_05_classify_results_empty(self):
        success, failed, skipped = Responder._classify_results({})
        assert success == []
        assert failed == []
        assert skipped == []


class TestBuildReverseDepsNormal:
    """TC-24-06: _build_reverse_deps - normal reverse deps.

    Actual: only keys units that appear in depends_on.
    """

    def test_TC24_06_build_reverse_deps_normal(self):
        units = [
            Unit("u1", "G1", depends_on=[]),
            Unit("u2", "G2", depends_on=["u1"]),
            Unit("u3", "G3", depends_on=["u1"]),
        ]

        result = Responder._build_reverse_deps(units)
        assert result["u1"] == ["u2", "u3"]


class TestBuildReverseDepsEmpty:
    """TC-24-07: _build_reverse_deps - empty list (BVA)."""

    def test_TC24_07_build_reverse_deps_empty(self):
        result = Responder._build_reverse_deps([])
        assert result == {}


class TestBuildReverseDepsNoDeps:
    """TC-24-08: _build_reverse_deps - no deps (BVA)."""

    def test_TC24_08_build_reverse_deps_no_deps(self):
        units = [
            Unit("u1", "G1", depends_on=[]),
            Unit("u2", "G2", depends_on=[]),
        ]

        result = Responder._build_reverse_deps(units)
        assert result == {}


class TestBuildReverseDepsManyToMany:
    """TC-24-09: _build_reverse_deps - many-to-many deps."""

    def test_TC24_09_build_reverse_deps_many_to_many(self):
        units = [
            Unit("u1", "G1", depends_on=[]),
            Unit("u2", "G2", depends_on=["u1"]),
            Unit("u3", "G3", depends_on=["u1", "u2"]),
        ]

        result = Responder._build_reverse_deps(units)
        assert result["u1"] == ["u2", "u3"]
        assert result["u2"] == ["u3"]


class TestIsLeafContentContentNoDownstream:
    """TC-24-10: _is_leaf_content - CONTENT with no downstream.

    Actual signature: _is_leaf_content(unit_id, unit_map, dependents)
    """

    def test_TC24_10_is_leaf_content_content_no_downstream(self):
        unit_map = {"u1": Unit("u1", "G1", output_type="CONTENT")}
        dependents = {}

        result = Responder._is_leaf_content("u1", unit_map, dependents)
        assert result is True


class TestIsLeafContentContentHasContentDownstream:
    """TC-24-11: _is_leaf_content - CONTENT with CONTENT downstream."""

    def test_TC24_11_is_leaf_content_content_has_content_downstream(self):
        unit_map = {
            "u1": Unit("u1", "G1", output_type="CONTENT"),
            "u2": Unit("u2", "G2", output_type="CONTENT"),
        }
        dependents = {"u1": ["u2"]}

        result = Responder._is_leaf_content("u1", unit_map, dependents)
        assert result is False


class TestIsLeafContentActionNotContent:
    """TC-24-12: _is_leaf_content - ACTION is not CONTENT type.

    Actual: _is_leaf_content returns False if output_type != CONTENT.
    """

    def test_TC24_12_is_leaf_content_action_not_content(self):
        unit_map = {
            "u1": Unit("u1", "G1", output_type="ACTION"),
            "u2": Unit("u2", "G2", output_type="CONTENT"),
        }
        dependents = {"u1": ["u2"]}

        result = Responder._is_leaf_content("u1", unit_map, dependents)
        assert result is False


class TestCollectSubstantiveUnitsWithLeafContent:
    """TC-24-13: _collect_substantive_units - has leaf CONTENT.

    Actual signature: _collect_substantive_units(results, unit_map, dependents)
    """

    def test_TC24_13_collect_substantive_units_with_leaf_content(self):
        results = {"u1": UnitResult(unit_id="u1", status=UnitStatus.SUCCESS, output="O1")}
        unit_map = {"u1": Unit("u1", "G1", output_type="CONTENT")}
        dependents = {}

        result = Responder._collect_substantive_units(results, unit_map, dependents)
        assert len(result) == 1
        assert result[0]["unit_id"] == "u1"
        assert result[0]["output"] == "O1"


class TestCollectSubstantiveUnitsNoLeafContent:
    """TC-24-14: _collect_substantive_units - no leaf CONTENT."""

    def test_TC24_14_collect_substantive_units_no_leaf_content(self):
        results = {"u1": UnitResult(unit_id="u1", status=UnitStatus.SUCCESS, output="O1")}
        unit_map = {"u1": Unit("u1", "G1", output_type="ACTION")}
        dependents = {}

        result = Responder._collect_substantive_units(results, unit_map, dependents)
        assert result == []


class TestCollectSubstantiveUnitsFailedNotIncluded:
    """TC-24-15: _collect_substantive_units - FAILED output is empty."""

    def test_TC24_15_collect_substantive_units_failed_not_included(self):
        results = {"u1": UnitResult(unit_id="u1", status=UnitStatus.FAILED)}
        unit_map = {"u1": Unit("u1", "G1", output_type="CONTENT")}
        dependents = {}

        result = Responder._collect_substantive_units(results, unit_map, dependents)
        assert len(result) == 1
        assert result[0]["output"] == ""


class TestCollectSubstantiveUnitsEmpty:
    """TC-24-16: _collect_substantive_units - empty dict (BVA)."""

    def test_TC24_16_collect_substantive_units_empty(self):
        result = Responder._collect_substantive_units({}, {}, {})
        assert result == []


class TestBuildExecutionSummaryNormal:
    """TC-24-17: _build_execution_summary - normal summary.

    Actual signature: _build_execution_summary(units, results)
    """

    def test_TC24_17_build_execution_summary_normal(self):
        units = [Unit("u1", "G1", output_type="CONTENT")]
        results = {"u1": UnitResult(unit_id="u1", status=UnitStatus.SUCCESS)}

        result = Responder._build_execution_summary(units, results)
        assert len(result) == 1
        assert result[0]["unit_id"] == "u1"
        assert result[0]["goal"] == "G1"
        assert result[0]["output_type"] == "CONTENT"
        assert result[0]["status"] == "SUCCESS"


class TestBuildExecutionSummaryAllStatuses:
    """TC-24-18: _build_execution_summary - all statuses."""

    def test_TC24_18_build_execution_summary_all_statuses(self):
        units = [
            Unit("u1", "G1", output_type="CONTENT"),
            Unit("u2", "G2", output_type="ACTION"),
            Unit("u3", "G3", output_type="INTERNAL"),
        ]
        results = {
            "u1": UnitResult(unit_id="u1", status=UnitStatus.SUCCESS),
            "u2": UnitResult(unit_id="u2", status=UnitStatus.FAILED),
            "u3": UnitResult(unit_id="u3", status=UnitStatus.SKIPPED),
        }

        result = Responder._build_execution_summary(units, results)
        assert len(result) == 3
        assert result[0]["status"] == "SUCCESS"
        assert result[1]["status"] == "FAILED"
        assert result[2]["status"] == "SKIPPED"


class TestBuildExecutionSummaryEmpty:
    """TC-24-19: _build_execution_summary - empty list (BVA)."""

    def test_TC24_19_build_execution_summary_empty(self):
        result = Responder._build_execution_summary([], {})
        assert result == []


class TestIntegrateNoUnits:
    """TC-24-20: integrate - no units (BVA).

    integrate is async, so we need to run it.
    """

    def test_TC24_20_integrate_no_units(self):
        responder = Responder()
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(
                responder.integrate({"goal": "T"}, {}, [])
            )
            assert result.success is True
            assert "任務已執行完成" in result.data
        finally:
            loop.close()


class TestIntegrateNoContentAction:
    """TC-24-21: integrate - no CONTENT/ACTION units."""

    def test_TC24_21_integrate_no_content_action(self):
        responder = Responder()
        results = {"u1": UnitResult(unit_id="u1", status=UnitStatus.SUCCESS)}
        units = [Unit("u1", "G1", output_type="INTERNAL")]

        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(
                responder.integrate({"goal": "T"}, results, units)
            )
            assert result.success is True
            assert "任務已執行完成" in result.data
        finally:
            loop.close()


class TestIntegrateHasFailedNoContentAction:
    """TC-24-22: integrate - has failed, no CONTENT/ACTION."""

    def test_TC24_22_integrate_has_failed_no_content_action(self):
        responder = Responder()
        results = {"u1": UnitResult(unit_id="u1", status=UnitStatus.FAILED)}
        units = [Unit("u1", "G1", output_type="INTERNAL")]

        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(
                responder.integrate({"goal": "T"}, results, units)
            )
            assert result.success is False
            assert "錯誤" in result.error
        finally:
            loop.close()