"""Test plan L1 - Disassembler (#11)

L1 scope (per l1_scope.md): _build_input, _parse_units
Also tests: __init__, disassemble (via mock)

Total: 24 test cases (TC-11-01 ~ TC-11-24)
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from core.disassembler import Disassembler
from models.blueprints import Unit, Result


# ── Disassembler.__init__ ────────────────────────────────────────────────

class TestDisassemblerInit:
    """TC-11-01 ~ TC-11-02"""

    def test_TC_11_01_init_normal(self):
        """TC-11-01: __init__ - 正常初始化"""
        mock_func = MagicMock()
        d = Disassembler(mock_func)
        assert d.call_model_func is mock_func

    def test_TC_11_02_init_not_callable(self):
        """TC-11-02: __init__ - call_model_func 不可呼叫"""
        with pytest.raises(TypeError):
            Disassembler("not_callable")


# ── Disassembler._build_input ────────────────────────────────────────────

class TestDisassemblerBuildInput:
    """TC-11-03 ~ TC-11-08, TC-11-24"""

    def test_TC_11_03_build_input_all_non_empty(self):
        """TC-11-03: _build_input - 全部非空"""
        result = Disassembler._build_input(
            "G", ["E1"], "S", ["C1"], ["SC1"]
        )
        assert "[GOAL]G[/GOAL]" in result
        assert "[ENTITIES]E1[/ENTITIES]" in result
        assert "[SCOPE]S[/SCOPE]" in result
        assert "[CONSTRAINTS]C1[/CONSTRAINTS]" in result
        assert "[SUCCESS_CRITERIA]SC1[/SUCCESS_CRITERIA]" in result

    def test_TC_11_04_build_input_entities_empty(self):
        """TC-11-04: _build_input - entities 為空"""
        result = Disassembler._build_input("G", [], "S", ["C1"], ["SC1"])
        assert "無" in result

    def test_TC_11_05_build_input_constraints_empty(self):
        """TC-11-05: _build_input - constraints 為空"""
        result = Disassembler._build_input("G", ["E1"], "S", [], ["SC1"])
        assert "無" in result

    def test_TC_11_06_build_input_success_criteria_empty(self):
        """TC-11-06: _build_input - success_criteria 為空"""
        result = Disassembler._build_input("G", ["E1"], "S", ["C1"], [])
        assert "無" in result

    def test_TC_11_07_build_input_success_criteria_str(self):
        """TC-11-07: _build_input - success_criteria 為 str"""
        result = Disassembler._build_input("G", ["E1"], "S", ["C1"], "SC1")
        assert "[SUCCESS_CRITERIA]SC1[/SUCCESS_CRITERIA]" in result

    def test_TC_11_08_build_input_all_empty(self):
        """TC-11-08: _build_input - goal 等皆為空字串"""
        result = Disassembler._build_input("", [], "", [], [])
        assert "無" in result

    def test_TC_11_24_build_input_success_criteria_multi_list(self):
        """TC-11-24: _build_input - success_criteria 為多元素 list"""
        result = Disassembler._build_input("G", ["E1"], "S", ["C1"], ["SC1", "SC2", "SC3"])
        assert "SC1, SC2, SC3" in result


# ── Disassembler._parse_units ────────────────────────────────────────────

class TestDisassemblerParseUnits:
    """TC-11-09 ~ TC-11-15"""

    def test_TC_11_09_parse_units_normal(self):
        """TC-11-09: _parse_units - 正常解析（key: content）"""
        content = '[{"id": 1, "content": "G1", "depends_on": [], "output_type": "INTERNAL"}]'
        result = Disassembler._parse_units(content)
        assert len(result) == 1
        assert isinstance(result[0], Unit)
        assert result[0].unit_id == "1"
        assert result[0].goal == "G1"
        assert result[0].depends_on == []
        assert result[0].output_type == "INTERNAL"

    def test_TC_11_10_parse_units_regex_no_match(self):
        """TC-11-10: _parse_units - regex 未匹配"""
        result = Disassembler._parse_units("no brackets here")
        assert result == []

    def test_TC_11_11_parse_units_parse_first_json_not_list(self):
        """TC-11-11: _parse_units - parse_first_json 回傳非 list"""
        result = Disassembler._parse_units('{"id": 1}')
        assert result == []

    def test_TC_11_12_parse_units_element_not_dict(self):
        """TC-11-12: _parse_units - element 非 dict 跳過"""
        content = '["string_element", {"id": 2, "content": "G2", "depends_on": []}]'
        result = Disassembler._parse_units(content)
        assert len(result) == 1
        assert result[0].unit_id == "2"
        assert result[0].goal == "G2"

    def test_TC_11_13_parse_units_depends_on_int(self):
        """TC-11-13: _parse_units - depends_on 元素為 int"""
        content = '[{"id": 2, "content": "G2", "depends_on": [1]}]'
        result = Disassembler._parse_units(content)
        assert result[0].depends_on == ["1"]

    def test_TC_11_14_parse_units_mcp_server_null(self):
        """TC-11-14: _parse_units - mcp_server 為 null"""
        content = '[{"id": 1, "content": "G1", "depends_on": [], "mcp_server": null}]'
        result = Disassembler._parse_units(content)
        assert result[0].mcp_server is None

    def test_TC_11_15_parse_units_id_none(self):
        """TC-11-15: _parse_units - u.get("id") 為 None"""
        content = '[{"content": "G1", "depends_on": []}]'
        result = Disassembler._parse_units(content)
        assert result[0].unit_id == ""


# ── Disassembler.disassemble ─────────────────────────────────────────────

class TestDisassemblerDisassemble:
    """TC-11-16 ~ TC-11-23"""

    @pytest.mark.asyncio
    async def test_TC_11_16_disassemble_normal(self):
        """TC-11-16: disassemble - 正常拆解"""
        mock_llm = AsyncMock()
        mock_llm.return_value = Result(
            success=True,
            data='[{"id": 1, "content": "G1", "depends_on": [], "output_type": "INTERNAL"}]'
        )
        d = Disassembler(mock_llm)
        clarify_result = {
            "goal": "G", "entities": [], "scope": "",
            "constraints": [], "success_criteria": ""
        }
        result = await d.disassemble(clarify_result)
        assert result.success is True
        assert len(result.data) == 1

    @pytest.mark.asyncio
    async def test_TC_11_17_disassemble_timeout(self):
        """TC-11-17: disassemble - LLM 逾時"""
        mock_llm = AsyncMock()
        mock_llm.side_effect = asyncio.TimeoutError("timeout")
        d = Disassembler(mock_llm)
        clarify_result = {"goal": "G", "entities": [], "scope": "", "constraints": [], "success_criteria": ""}
        result = await d.disassemble(clarify_result)
        assert result.success is False
        assert "逾時" in result.error

    @pytest.mark.asyncio
    async def test_TC_11_18_disassemble_llm_error(self):
        """TC-11-18: disassemble - LLM 失敗"""
        mock_llm = AsyncMock()
        mock_llm.side_effect = Exception("LLM error")
        d = Disassembler(mock_llm)
        clarify_result = {"goal": "G", "entities": [], "scope": "", "constraints": [], "success_criteria": ""}
        result = await d.disassemble(clarify_result)
        assert result.success is False
        assert result.error == "LLM error"

    @pytest.mark.asyncio
    async def test_TC_11_19_disassemble_empty_result(self):
        """TC-11-19: disassemble - 解析結果為空"""
        mock_llm = AsyncMock()
        mock_llm.return_value = Result(success=True, data="")
        d = Disassembler(mock_llm)
        clarify_result = {"goal": "G", "entities": [], "scope": "", "constraints": [], "success_criteria": ""}
        result = await d.disassemble(clarify_result)
        assert result.success is False
        assert "為空" in result.error

    @pytest.mark.asyncio
    async def test_TC_11_20_disassemble_feedback_not_empty(self):
        """TC-11-20: disassemble - feedback 非空"""
        mock_llm = AsyncMock()
        mock_llm.return_value = Result(success=True, data='[{"id": 1, "content": "G1", "depends_on": [], "output_type": "INTERNAL"}]')
        d = Disassembler(mock_llm)
        clarify_result = {"goal": "G", "entities": [], "scope": "", "constraints": [], "success_criteria": ""}
        result = await d.disassemble(clarify_result, feedback="Previous plan failed")
        assert result.success is True

    @pytest.mark.asyncio
    async def test_TC_11_21_disassemble_feedback_empty(self):
        """TC-11-21: disassemble - feedback 為空字串"""
        mock_llm = AsyncMock()
        mock_llm.return_value = Result(success=True, data='[{"id": 1, "content": "G1", "depends_on": [], "output_type": "INTERNAL"}]')
        d = Disassembler(mock_llm)
        clarify_result = {"goal": "G", "entities": [], "scope": "", "constraints": [], "success_criteria": ""}
        result = await d.disassemble(clarify_result, feedback="")
        assert result.success is True

    @pytest.mark.asyncio
    async def test_TC_11_22_disassemble_clarify_result_missing_goal(self):
        """TC-11-22: disassemble - clarify_result 缺 goal 欄位"""
        mock_llm = AsyncMock()
        mock_llm.return_value = Result(success=True, data='[{"id": 1, "content": "G1", "depends_on": [], "output_type": "INTERNAL"}]')
        d = Disassembler(mock_llm)
        clarify_result = {"entities": [], "scope": "", "constraints": [], "success_criteria": ""}
        result = await d.disassemble(clarify_result)
        assert result.success is True

    @pytest.mark.asyncio
    async def test_TC_11_23_disassemble_skill_guide_empty(self):
        """TC-11-23: disassemble - skill_guide 為空"""
        mock_llm = AsyncMock()
        mock_llm.return_value = Result(success=True, data='[{"id": 1, "content": "G1", "depends_on": [], "output_type": "INTERNAL"}]')
        d = Disassembler(mock_llm)
        clarify_result = {"goal": "G", "entities": [], "scope": "", "constraints": [], "success_criteria": ""}
        result = await d.disassemble(clarify_result, skill_guide="")
        assert result.success is True