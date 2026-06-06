"""tests/L1/test_step_planner_logic.py — core/step_planner.py 純邏輯測試（15 筆）."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pytest
from models.blueprints import Step, Unit


@pytest.fixture
def make_unit():
    def _make(goal="test goal", expected_input="in", expected_output="out"):
        return Unit(
            unit_id="u1",
            goal=goal,
            expected_input=expected_input,
            expected_output=expected_output,
        )
    return _make


@pytest.fixture
def make_step():
    def _make(step_id="1", goal="test goal"):
        return Step(
            step_id=step_id,
            goal=goal,
        )
    return _make


class TestBuildInput:
    """StepPlanner._build_input 測試."""

    def test_basic_fields(self, make_unit):
        """等價類：unit.goal/expected_input/expected_output."""
        from core.step_planner import StepPlanner
        unit = make_unit(goal="test goal", expected_input="in", expected_output="out")
        result = StepPlanner._build_input(unit, [], None)
        assert "test goal" in result
        assert "in" in result
        assert "out" in result

    def test_with_successful_steps(self, make_unit):
        """等價類：包含 successful_steps."""
        from core.step_planner import StepPlanner
        unit = make_unit()
        steps = [Step(step_id="1", goal="done")]
        result = StepPlanner._build_input(unit, steps, None)
        assert "done" in result
        assert "step_id=1" in result

    def test_with_failed_step_info(self, make_unit):
        """等價類：包含 failed_step_info."""
        from core.step_planner import StepPlanner
        unit = make_unit()
        failed = {"step_id": "s1", "goal": "test goal", "content": "test content", "error": "err"}
        result = StepPlanner._build_input(unit, [], failed)
        assert "s1" in result
        assert "test content" in result

    def test_with_gaps(self, make_unit):
        """等價類：failed_step_info 含 gaps."""
        from core.step_planner import StepPlanner
        unit = make_unit()
        failed = {"gaps": ["gap1"]}
        result = StepPlanner._build_input(unit, [], failed)
        assert "gap1" in result

    def test_with_constraint_checks(self, make_unit):
        """等價類：failed_step_info 含 constraint_checks."""
        from core.step_planner import StepPlanner
        unit = make_unit()
        failed = {"constraint_checks": [{"constraint": "c1", "satisfied": False}]}
        result = StepPlanner._build_input(unit, [], failed)
        assert "c1" in result


class TestExtractFunctionTools:
    """StepPlanner._extract_function_tools 測試."""

    def test_normal(self):
        """等價類：function type tools."""
        from core.step_planner import StepPlanner
        tools = [
            {"type": "function", "function": {"name": "tool1", "description": "d1"}},
            {"type": "function", "function": {"name": "tool2", "description": "d2"}},
        ]
        slim_tools, tool_map = StepPlanner._extract_function_tools(tools)
        assert "tool1" in tool_map
        assert "tool2" in tool_map
        assert len(slim_tools) == 2

    def test_non_function_skipped(self):
        """等價類：非 function type 跳過."""
        from core.step_planner import StepPlanner
        tools = [
            {"type": "function", "function": {"name": "tool1", "description": "d1"}},
            {"type": "other"},
        ]
        slim_tools, tool_map = StepPlanner._extract_function_tools(tools)
        assert len(slim_tools) == 1

    def test_missing_name(self):
        """等價類：function 缺少 name → 跳過."""
        from core.step_planner import StepPlanner
        tools = [
            {"type": "function", "function": {"description": "d1"}},
        ]
        slim_tools, tool_map = StepPlanner._extract_function_tools(tools)
        assert len(slim_tools) == 0

    def test_duplicate_names(self):
        """等價類：重複 name → 警告 + tool_map 覆蓋."""
        from core.step_planner import StepPlanner
        tools = [
            {"type": "function", "function": {"name": "tool1", "description": "d1"}},
            {"type": "function", "function": {"name": "tool1", "description": "d2"}},
        ]
        slim_tools, tool_map = StepPlanner._extract_function_tools(tools)
        assert len(slim_tools) == 2
        assert tool_map["tool1"]["function"]["description"] == "d2"


class TestParseSteps:
    """StepPlanner._parse_steps 測試."""

    def test_valid(self, make_step):
        """等價類：有效 steps → Step 列表."""
        from core.step_planner import StepPlanner
        steps_data = [{"id": 1, "content": "test", "output_type": "INTERNAL"}]
        result = StepPlanner._parse_steps(steps_data, {})
        assert len(result) == 1
        assert isinstance(result[0], Step)

    def test_invalid_type_tools(self, make_step):
        """等價類：tools 為 list → 設為 None."""
        from core.step_planner import StepPlanner
        steps_data = [{"id": 1, "content": "test", "tools": ["a", "b"]}]
        result = StepPlanner._parse_steps(steps_data, {})
        assert result[0].tool is None

    def test_unknown_tool_warning(self, make_step):
        """等價類：未註冊 tool → warning."""
        from core.step_planner import StepPlanner
        steps_data = [{"id": 1, "content": "test", "tools": "unknown_tool"}]
        tool_map = {}
        result = StepPlanner._parse_steps(steps_data, tool_map)
        assert len(result) == 1

    def test_depends_on_conversion(self, make_step):
        """等價類：depends_on int → str."""
        from core.step_planner import StepPlanner
        steps_data = [{"id": 1, "content": "test", "depends_on": [1, 2]}]
        result = StepPlanner._parse_steps(steps_data, {})
        assert result[0].depends_on == ["1", "2"]

    def test_upstream_depends_strip_prefix(self, make_step):
        """等價類：'unit:1' → '1'."""
        from core.step_planner import StepPlanner
        steps_data = [{"id": 1, "content": "test", "upstream_depends": ["unit:1", "unit:2"]}]
        result = StepPlanner._parse_steps(steps_data, {})
        assert "1" in result[0].upstream_depends
        assert "2" in result[0].upstream_depends

    def test_output_type(self, make_step):
        """等價類：output_type INTERNAL/GLOBAL."""
        from core.step_planner import StepPlanner
        for ot in ["INTERNAL", "GLOBAL"]:
            steps_data = [{"id": 1, "content": "test", "output_type": ot}]
            result = StepPlanner._parse_steps(steps_data, {})
            assert result[0].output_type == ot