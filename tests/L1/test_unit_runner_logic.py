"""tests/L1/test_unit_runner_logic — UnitRunner._collect_actual_output 純邏輯測試（4 筆）."""

import unittest.mock
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def mock_step_store():
    """mock StepStore."""
    store = MagicMock()
    store.get_steps_by_unit.return_value = []
    store.get_step.return_value = None
    store.save_step.return_value = None
    store.clear_unit_steps.return_value = None
    return store


@pytest.fixture
def mock_unit_store():
    """mock UnitStore."""
    store = MagicMock()
    store.get_unit.return_value = None
    return store


@pytest.fixture
def mock_executor():
    """mock Executor."""
    executor = MagicMock()
    executor.execute = unittest.mock.AsyncMock()
    return executor


@pytest.fixture
def mock_verifier():
    """mock Verifier."""
    verifier = MagicMock()
    verifier.verify = unittest.mock.AsyncMock()
    return verifier


@pytest.fixture
def mock_tool_manager():
    """mock ToolManager."""
    tm = MagicMock()
    tm.tool_environments = {}
    return tm


def _make_runner(**kwargs):
    """建立 UnitRunner 實例."""
    from core.unit_runner import UnitRunner
    return UnitRunner(
        executor=kwargs.get("executor", MagicMock()),
        verifier=kwargs.get("verifier", MagicMock()),
        tool_manager=kwargs.get("tool_manager", MagicMock()),
        step_store=kwargs.get("step_store", MagicMock()),
        unit_store=kwargs.get("unit_store", MagicMock()),
        session_id=kwargs.get("session_id", "test_session"),
    )


class TestCollectActualOutput:
    """測試 UnitRunner._collect_actual_output 方法."""

    def test_collect_output_global_steps(self, mock_step_store):
        """等價類：有 GLOBAL step 輸出 → 收集並連接."""
        runner = _make_runner(step_store=mock_step_store, session_id="s1")

        # 模擬 StepResult
        sr1 = MagicMock()
        sr1.output_type = "GLOBAL"
        sr1.output = "output 1"
        sr2 = MagicMock()
        sr2.output_type = "GLOBAL"
        sr2.output = "output 2"
        sr3 = MagicMock()
        sr3.output_type = "INTERNAL"
        sr3.output = "internal output"

        mock_step_store.get_steps_by_unit.return_value = [sr1, sr2, sr3]

        result = runner._collect_actual_output("u1")
        assert result == "output 1\noutput 2"

    def test_collect_output_no_global(self, mock_step_store):
        """等價類：沒有 GLOBAL step → 空字串."""
        runner = _make_runner(step_store=mock_step_store, session_id="s1")

        sr = MagicMock()
        sr.output_type = "INTERNAL"
        sr.output = "internal"

        mock_step_store.get_steps_by_unit.return_value = [sr]

        result = runner._collect_actual_output("u1")
        assert result == ""

    def test_collect_output_empty_steps(self, mock_step_store):
        """邊界：沒有 steps → 空字串."""
        runner = _make_runner(step_store=mock_step_store, session_id="s1")
        mock_step_store.get_steps_by_unit.return_value = []

        result = runner._collect_actual_output("u1")
        assert result == ""

    def test_collect_output_global_empty_output(self, mock_step_store):
        """邊界：GLOBAL step 但 output 為空字串 → 跳過."""
        runner = _make_runner(step_store=mock_step_store, session_id="s1")

        sr1 = MagicMock()
        sr1.output_type = "GLOBAL"
        sr1.output = ""  # 空輸出
        sr2 = MagicMock()
        sr2.output_type = "GLOBAL"
        sr2.output = "valid output"

        mock_step_store.get_steps_by_unit.return_value = [sr1, sr2]

        result = runner._collect_actual_output("u1")
        assert result == "valid output"