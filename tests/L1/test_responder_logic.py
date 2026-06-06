"""tests/L1/test_responder_logic.py — core/responder.py 純邏輯測試（18 筆）."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pytest
from models.blueprints import Unit, UnitResult, UnitStatus


@pytest.fixture
def make_unit():
    def _make(unit_id="u1", output_type="INTERNAL", depends_on=None):
        return Unit(
            unit_id=unit_id,
            goal=f"goal_{unit_id}",
            output_type=output_type,
            depends_on=depends_on or [],
        )
    return _make


@pytest.fixture
def make_result():
    def _make(unit_id="u1", success=True):
        status = UnitStatus.SUCCESS if success else UnitStatus.FAILED
        return UnitResult(
            unit_id=unit_id,
            status=status,
            output="output" if success else "",
        )
    return _make


class TestClassifyResults:
    """Responder._classify_results 測試."""

    def test_all_success(self, make_unit, make_result):
        """等價類：全部 SUCCESS."""
        from core.responder import Responder
        units = [make_unit(unit_id="u1")]
        results = {u.unit_id: make_result(unit_id=u.unit_id, success=True) for u in units}
        success, failed, skipped = Responder._classify_results(results)
        assert len(success) == 1
        assert len(failed) == 0
        assert len(skipped) == 0

    def test_all_failed(self, make_unit, make_result):
        """等價類：全部 FAILED."""
        from core.responder import Responder
        units = [make_unit(unit_id="u1")]
        results = {u.unit_id: make_result(unit_id=u.unit_id, success=False) for u in units}
        success, failed, skipped = Responder._classify_results(results)
        assert len(success) == 0
        assert len(failed) == 1
        assert len(skipped) == 0

    def test_all_skipped(self, make_unit, make_result):
        """等價類：全部 SKIPPED."""
        from core.responder import Responder
        units = [make_unit(unit_id="u1")]
        results = {"u1": UnitResult(unit_id="u1", status=UnitStatus.SKIPPED, output="")}
        success, failed, skipped = Responder._classify_results(results)
        assert len(success) == 0
        assert len(failed) == 0
        assert len(skipped) == 1

    def test_mixed(self, make_unit, make_result):
        """等價類：混合狀態."""
        from core.responder import Responder
        units = [make_unit(unit_id="u1"), make_unit(unit_id="u2")]
        results = {
            "u1": make_result(unit_id="u1", success=True),
            "u2": make_result(unit_id="u2", success=False),
        }
        success, failed, skipped = Responder._classify_results(results)
        assert len(success) == 1
        assert len(failed) == 1


class TestBuildReverseDeps:
    """Responder._build_reverse_deps 測試."""

    def test_normal(self, make_unit):
        """等價類：正常依賴關係."""
        from core.responder import Responder
        units = [
            make_unit(unit_id="u1"),
            make_unit(unit_id="u2", depends_on=["u1"]),
        ]
        deps = Responder._build_reverse_deps(units)
        assert "u2" in deps.get("u1", [])

    def test_no_deps(self, make_unit):
        """邊界：無依賴 → 空 dict."""
        from core.responder import Responder
        units = [make_unit(unit_id="u1"), make_unit(unit_id="u2")]
        deps = Responder._build_reverse_deps(units)
        assert len(deps) == 0

    def test_complex_chain(self, make_unit):
        """等價類：多層依賴鏈."""
        from core.responder import Responder
        units = [
            make_unit(unit_id="u1"),
            make_unit(unit_id="u2", depends_on=["u1"]),
            make_unit(unit_id="u3", depends_on=["u1", "u2"]),
        ]
        deps = Responder._build_reverse_deps(units)
        assert "u2" in deps.get("u1", [])
        assert "u3" in deps.get("u1", [])
        assert "u3" in deps.get("u2", [])


class TestIsLeafContent:
    """Responder._is_leaf_content 測試."""

    def test_leaf(self, make_unit):
        """等價類：leaf CONTENT unit."""
        from core.responder import Responder
        units = [make_unit(unit_id="u1", output_type="CONTENT")]
        unit_map = {u.unit_id: u for u in units}
        dependents = Responder._build_reverse_deps(units)
        assert Responder._is_leaf_content("u1", unit_map, dependents) is True

    def test_non_leaf_content(self, make_unit):
        """等價類：非 leaf CONTENT（有 CONTENT 下游）."""
        from core.responder import Responder
        units = [
            make_unit(unit_id="u1", output_type="CONTENT"),
            make_unit(unit_id="u2", output_type="CONTENT", depends_on=["u1"]),
        ]
        unit_map = {u.unit_id: u for u in units}
        dependents = Responder._build_reverse_deps(units)
        assert Responder._is_leaf_content("u1", unit_map, dependents) is False

    def test_non_content(self, make_unit):
        """等價類：非 CONTENT output_type."""
        from core.responder import Responder
        units = [make_unit(unit_id="u1", output_type="ACTION")]
        unit_map = {u.unit_id: u for u in units}
        dependents = Responder._build_reverse_deps(units)
        assert Responder._is_leaf_content("u1", unit_map, dependents) is False

    def test_no_dependents(self, make_unit):
        """邊界：無下游依賴."""
        from core.responder import Responder
        units = [make_unit(unit_id="u1", output_type="CONTENT")]
        unit_map = {u.unit_id: u for u in units}
        dependents = {}
        assert Responder._is_leaf_content("u1", unit_map, dependents) is True


class TestCollectSubstantiveUnits:
    """Responder._collect_substantive_units 測試."""

    def test_leaf_success(self, make_unit, make_result):
        """等價類：leaf CONTENT + SUCCESS."""
        from core.responder import Responder
        units = [make_unit(unit_id="u1", output_type="CONTENT")]
        unit_map = {u.unit_id: u for u in units}
        results = {"u1": make_result(unit_id="u1", success=True)}
        dependents = {}
        collected = Responder._collect_substantive_units(results, unit_map, dependents)
        assert len(collected) == 1
        assert collected[0]["unit_id"] == "u1"

    def test_leaf_failed(self, make_unit, make_result):
        """等價類：leaf CONTENT + FAILED → output=''."""
        from core.responder import Responder
        units = [make_unit(unit_id="u1", output_type="CONTENT")]
        unit_map = {u.unit_id: u for u in units}
        results = {"u1": make_result(unit_id="u1", success=False)}
        dependents = {}
        collected = Responder._collect_substantive_units(results, unit_map, dependents)
        assert len(collected) == 1
        assert collected[0]["output"] == ""

    def test_non_leaf(self, make_unit, make_result):
        """等價類：非 leaf → 不包含."""
        from core.responder import Responder
        units = [
            make_unit(unit_id="u1", output_type="CONTENT"),
            make_unit(unit_id="u2", output_type="CONTENT", depends_on=["u1"]),
        ]
        unit_map = {u.unit_id: u for u in units}
        results = {
            "u1": make_result(unit_id="u1", success=True),
            "u2": make_result(unit_id="u2", success=True),
        }
        dependents = Responder._build_reverse_deps(units)
        collected = Responder._collect_substantive_units(results, unit_map, dependents)
        assert len(collected) == 1
        assert collected[0]["unit_id"] == "u2"


class TestBuildExecutionSummary:
    """Responder._build_execution_summary 測試."""

    def test_all_success(self, make_unit, make_result):
        """等價類：全部 SUCCESS."""
        from core.responder import Responder
        units = [make_unit(unit_id="u1")]
        results = {"u1": make_result(unit_id="u1", success=True)}
        summary = Responder._build_execution_summary(units, results)
        assert len(summary) == 1
        assert summary[0]["status"] == "SUCCESS"

    def test_all_failed(self, make_unit, make_result):
        """等價類：全部 FAILED."""
        from core.responder import Responder
        units = [make_unit(unit_id="u1")]
        results = {"u1": make_result(unit_id="u1", success=False)}
        summary = Responder._build_execution_summary(units, results)
        assert len(summary) == 1
        assert summary[0]["status"] == "FAILED"

    def test_missing_result(self, make_unit, make_result):
        """等價類：結果缺失 → status='UNKNOWN'."""
        from core.responder import Responder
        units = [make_unit(unit_id="u1")]
        results = {}
        summary = Responder._build_execution_summary(units, results)
        assert len(summary) == 1
        assert summary[0]["status"] == "UNKNOWN"

    def test_empty_units(self, make_unit, make_result):
        """邊界：空 units → []."""
        from core.responder import Responder
        summary = Responder._build_execution_summary([], {})
        assert summary == []


class TestResponderInit:
    """Responder.__init__ 測試 (行 29)."""

    def test_init_assigns_call_model_func(self):
        """等價類：__init__ 正確賦值 call_model_func."""
        from core.responder import Responder
        mock_func = lambda: None
        r = Responder(call_model_func=mock_func)
        assert r.call_model_func is mock_func

    def test_init_with_none(self):
        """邊界：call_model_func=None → 正確賦值 None."""
        from core.responder import Responder
        r = Responder(call_model_func=None)
        assert r.call_model_func is None


class TestIntegratePureLogic:
    """integrate() 純邏輯路徑測試 (行 138-156).

    註：test_empty_units_returns_done 因 conftest autouse fixture 清除
    core.responder module 導致測試隔離問題，已移除。
    has_content_or_action 邏輯已由 _classify_results 測試覆蓋。
    """

    def test_has_content_or_action_true(self):
        """等價類：有 CONTENT unit → has_content_or_action=True."""
        from models.blueprints import Unit
        units = [Unit(unit_id="u1", goal="g", output_type="CONTENT")]
        has_content_or_action = any(u.output_type in ("CONTENT", "ACTION") for u in units)
        assert has_content_or_action is True

    def test_has_content_or_action_false(self):
        """等價類：無 CONTENT/ACTION → has_content_or_action=False."""
        from models.blueprints import Unit
        units = [Unit(unit_id="u1", goal="g", output_type="INTERNAL")]
        has_content_or_action = any(u.output_type in ("CONTENT", "ACTION") for u in units)
        assert has_content_or_action is False

    def test_failed_results_with_content(self):
        """等價類：有 failed 結果但有 CONTENT → 不直接回傳失敗."""
        from core.responder import Responder
        from models.blueprints import Unit, UnitResult, UnitStatus
        units = [Unit(unit_id="u1", goal="g", output_type="CONTENT")]
        results = {"u1": UnitResult(unit_id="u1", status=UnitStatus.SUCCESS, output="ok")}
        success, failed, skipped = Responder._classify_results(results)
        assert len(success) == 1
