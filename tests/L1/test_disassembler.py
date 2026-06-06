"""tests/L1/test_disassembler.py — core/disassembler.py 純邏輯測試（12 筆）."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import unittest.mock

from models.blueprints import Unit


class TestBuildInput:
    """Disassembler._build_input 測試."""

    @unittest.mock.patch("config.PATTERNS_PATH", "/dev/null")
    def test_all_fields(self):
        """等價類：所有欄位有值."""
        from core.disassembler import Disassembler
        result = Disassembler._build_input(
            goal="test goal",
            entities=["e1"],
            scope="test scope",
            constraints=["c1"],
            success_criteria="sc"
        )
        assert "test goal" in result
        assert "e1" in result
        assert "test scope" in result
        assert "c1" in result
        assert "sc" in result

    def test_empty_entities(self):
        """邊界：entities 空 → '無'."""
        from core.disassembler import Disassembler
        result = Disassembler._build_input(
            goal="goal", entities=[], scope="scope", constraints=[], success_criteria="sc"
        )
        assert "無" in result

    def test_empty_constraints(self):
        """邊界：constraints 空 → '無'."""
        from core.disassembler import Disassembler
        result = Disassembler._build_input(
            goal="goal", entities=["e"], scope="scope", constraints=[], success_criteria="sc"
        )
        assert "無" in result

    def test_success_criteria_str(self):
        """等價類：success_criteria 為 str."""
        from core.disassembler import Disassembler
        result = Disassembler._build_input(
            goal="goal", entities=[], scope="scope", constraints=[], success_criteria="criteria"
        )
        assert "criteria" in result

    def test_success_criteria_list(self):
        """等價類：success_criteria 為 list."""
        from core.disassembler import Disassembler
        result = Disassembler._build_input(
            goal="goal", entities=[], scope="scope", constraints=[], success_criteria=["a", "b"]
        )
        assert "a" in result
        assert "b" in result

    def test_success_criteria_empty_list(self):
        """邊界：success_criteria 空 list → '無'."""
        from core.disassembler import Disassembler
        result = Disassembler._build_input(
            goal="goal", entities=[], scope="scope", constraints=[], success_criteria=[]
        )
        assert "無" in result


class TestParseUnits:
    """Disassembler._parse_units 測試."""

    def test_valid_json(self):
        """等價類：有效 JSON array → 解析為 Unit 列表."""
        from core.disassembler import Disassembler
        content = '[{"id": 1, "content": "test", "expected_output": "out", "expected_input": "in"}]'
        result = Disassembler._parse_units(content)
        assert len(result) == 1
        assert isinstance(result[0], Unit)
        assert result[0].goal == "test"

    def test_empty_array(self):
        """邊界：空 array → []."""
        from core.disassembler import Disassembler
        result = Disassembler._parse_units("[]")
        assert result == []

    def test_invalid_format(self):
        """等價類：無效格式 → []."""
        from core.disassembler import Disassembler
        result = Disassembler._parse_units("not json")
        assert result == []

    def test_missing_fields(self):
        """等價類：缺少 expected_input/expected_output → 預設空字串."""
        from core.disassembler import Disassembler
        content = '[{"id": 1, "goal": "test"}]'
        result = Disassembler._parse_units(content)
        assert len(result) == 1
        assert result[0].expected_output == ""
        assert result[0].expected_input == ""

    def test_depends_on_conversion(self):
        """等價類：depends_on 數字 → str 列表."""
        from core.disassembler import Disassembler
        content = '[{"id": 1, "goal": "test", "depends_on": [1, 2]}]'
        result = Disassembler._parse_units(content)
        assert result[0].depends_on == ["1", "2"]

    def test_mcp_server_null(self):
        """等價類：mcp_server null → None."""
        from core.disassembler import Disassembler
        content = '[{"id": 1, "goal": "test", "mcp_server": null}]'
        result = Disassembler._parse_units(content)
        assert result[0].mcp_server is None