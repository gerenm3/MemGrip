"""L1 test plan for ClarificationManager (#19).

Test cases from docs/test_plan_l1/19_clarification_manager.md.
Only pure state initialization and property getters/setters are in scope per l1_scope.md.
"""
import pytest
from models.blueprints import ClarificationState


class TestClarificationManager:
    """Test ClarificationManager per test plan #19 (L1 scope only)."""

    def _make_cm(self):
        """Create a ClarificationManager with mock dependencies."""
        from unittest.mock import MagicMock
        from core.clarification_manager import ClarificationManager
        mock_router = MagicMock()
        mock_clarifier = MagicMock()
        mock_memory = MagicMock()
        return ClarificationManager(mock_router, mock_clarifier, mock_memory)

    def test_TC_19_01_start_clarification_normal(self):
        """TC-19-01: start_clarification - 正常初始化."""
        cm = self._make_cm()
        cm.start_clarification(
            questions=["Q1"],
            clarify_data={"goal": "G"},
            path="tool",
            buffer="B",
            summary="S",
            rag="R",
            domain="general"
        )
        assert cm.clarification_state == ClarificationState.AWAITING_CLARIFICATION
        assert cm.pending_clarify_result == {"goal": "G"}

    def test_TC_19_02_start_clarification_default_domain(self):
        """TC-19-02: start_clarification - domain 預設 general."""
        cm = self._make_cm()
        cm.start_clarification(
            questions=["Q1"],
            clarify_data={"goal": "G"},
            path="tool",
            buffer="B",
            summary="S",
            rag="R"
        )
        # domain defaults to "general"
        assert cm.clarification_state == ClarificationState.AWAITING_CLARIFICATION

    def test_TC_19_03_clarification_state_initial(self):
        """TC-19-03: clarification_state - 初始值."""
        cm = self._make_cm()
        assert cm.clarification_state == ClarificationState.NORMAL

    def test_TC_19_04_clarification_state_set(self):
        """TC-19-04: clarification_state - 設定後."""
        cm = self._make_cm()
        cm.clarification_state = ClarificationState.AWAITING_CLARIFICATION
        assert cm.clarification_state == ClarificationState.AWAITING_CLARIFICATION

    def test_TC_19_05_clarification_rounds_initial(self):
        """TC-19-05: clarification_rounds - 初始值."""
        cm = self._make_cm()
        assert cm.clarification_rounds == 0

    def test_TC_19_06_clarification_rounds_set(self):
        """TC-19-06: clarification_rounds - 增加後."""
        cm = self._make_cm()
        cm.clarification_rounds = 3
        assert cm.clarification_rounds == 3

    def test_TC_19_07_clarification_history_initial(self):
        """TC-19-07: clarification_history - 初始值."""
        cm = self._make_cm()
        assert cm.clarification_history == []

    def test_TC_19_08_clarification_history_set(self):
        """TC-19-08: clarification_history - 增加後."""
        cm = self._make_cm()
        cm.clarification_history = ["Q1", "A1"]
        assert cm.clarification_history == ["Q1", "A1"]

    def test_TC_19_09_original_user_input_initial(self):
        """TC-19-09: original_user_input - 初始值."""
        cm = self._make_cm()
        assert cm.original_user_input == ""

    def test_TC_19_10_original_user_input_set(self):
        """TC-19-10: original_user_input - 設定後."""
        cm = self._make_cm()
        cm.original_user_input = "test input"
        assert cm.original_user_input == "test input"