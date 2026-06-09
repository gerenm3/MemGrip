"""Test plan L1 - blueprints (#3)

Covers: UnitStatus, StepStatus, ClarificationState enums;
        Unit, Step, UnitResult, StepResult, Result dataclasses.

Total: 20 test cases (TC-03-01 ~ TC-03-20)
"""

import pytest
from models.blueprints import (
    UnitStatus,
    StepStatus,
    ClarificationState,
    Unit,
    Step,
    UnitResult,
    StepResult,
    Result,
)


# ── UnitStatus ────────────────────────────────────────────────────────────

class TestUnitStatus:
    """TC-03-01 ~ TC-03-03"""

    def test_TC_03_01_success_value(self):
        assert UnitStatus.SUCCESS.value == "SUCCESS"

    def test_TC_03_02_failed_value(self):
        assert UnitStatus.FAILED.value == "FAILED"

    def test_TC_03_03_skipped_value(self):
        assert UnitStatus.SKIPPED.value == "SKIPPED"


# ── StepStatus ────────────────────────────────────────────────────────────

class TestStepStatus:
    """TC-03-04 ~ TC-03-05"""

    def test_TC_03_04_success_value(self):
        assert StepStatus.SUCCESS.value == "SUCCESS"

    def test_TC_03_05_failed_value(self):
        assert StepStatus.FAILED.value == "FAILED"


# ── ClarificationState ───────────────────────────────────────────────────

class TestClarificationState:
    """TC-03-06 ~ TC-03-07"""

    def test_TC_03_06_normal_value(self):
        assert ClarificationState.NORMAL.value == "NORMAL"

    def test_TC_03_07_awaiting_clarification_value(self):
        assert ClarificationState.AWAITING_CLARIFICATION.value == "AWAITING_CLARIFICATION"


# ── Unit ──────────────────────────────────────────────────────────────────

class TestUnit:
    """TC-03-08 ~ TC-03-11"""

    def test_TC_03_08_default_fields(self):
        u = Unit(unit_id="u0", goal="test")
        assert u.expected_input == ""
        assert u.expected_output == ""
        assert u.depends_on == []
        assert u.mcp_server is None
        assert u.output_type == "INTERNAL"
        assert u.assigned_constraints == []

    def test_TC_03_09_custom_output_type_content(self):
        u = Unit(unit_id="u0", goal="test", output_type="CONTENT")
        assert u.output_type == "CONTENT"

    def test_TC_03_10_custom_output_type_action(self):
        u = Unit(unit_id="u0", goal="test", output_type="ACTION")
        assert u.output_type == "ACTION"

    def test_TC_03_11_mcp_server_not_none(self):
        u = Unit(unit_id="u0", goal="test", mcp_server="brave_search")
        assert u.mcp_server == "brave_search"


# ── Step ──────────────────────────────────────────────────────────────────

class TestStep:
    """TC-03-12 ~ TC-03-14"""

    def test_TC_03_12_default_fields(self):
        s = Step(step_id="s0", goal="test")
        assert s.tool is None
        assert s.depends_on == []
        assert s.upstream_depends == []
        assert s.output_type == "INTERNAL"

    def test_TC_03_13_tool_not_none(self):
        s = Step(step_id="s0", goal="test", tool={"name": "read_file"})
        assert s.tool == {"name": "read_file"}

    def test_TC_03_14_output_type_global(self):
        s = Step(step_id="s0", goal="test", output_type="GLOBAL")
        assert s.output_type == "GLOBAL"


# ── UnitResult ────────────────────────────────────────────────────────────

class TestUnitResult:
    """TC-03-15"""

    def test_TC_03_15_default_fields(self):
        r = UnitResult(unit_id="u0", status=UnitStatus.SUCCESS)
        assert r.output == ""
        assert r.error == ""
        assert r.replan_count == 0
        assert r.total_loop_count == 0
        assert r.step_loop_counts == []
        assert r.constraint_checks == []


# ── StepResult ────────────────────────────────────────────────────────────

class TestStepResult:
    """TC-03-16"""

    def test_TC_03_16_default_fields(self):
        r = StepResult(step_id="s0", status=StepStatus.SUCCESS)
        assert r.output == ""
        assert r.error == ""
        assert r.loop_count == 0
        assert r.output_type == "INTERNAL"


# ── Result ────────────────────────────────────────────────────────────────

class TestResult:
    """TC-03-17 ~ TC-03-20"""

    def test_TC_03_17_success_construction(self):
        r = Result(success=True, data={"key": "value"})
        assert r.error == ""
        assert r.tool_calls == []

    def test_TC_03_18_failure_construction(self):
        r = Result(success=False, error="something went wrong")
        assert r.data is None
        assert r.tool_calls == []

    def test_TC_03_19_success_no_data(self):
        r = Result(success=True)
        assert r.data is None
        assert r.error == ""
        assert r.tool_calls == []

    def test_TC_03_20_tool_calls_not_empty(self):
        r = Result(success=True, data=None, tool_calls=[{"name": "test"}])
        assert r.tool_calls == [{"name": "test"}]