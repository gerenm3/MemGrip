"""
tests/L2/test_responder.py -- L2 mock integration tests for Responder.
Group 8: 20 TCs
"""

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_project_root = Path(__file__).resolve().parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from models.blueprints import Result, Unit, UnitResult, UnitStatus


# ── Helpers ──

def _make_responder(**kwargs):
    """Create a Responder instance with mocked call_model_func.
    
    黑箱原則：禁止直接賦值 MessageBuilder 屬性；需使用 patch() context manager。
    """
    from core.responder import Responder
    responder = Responder()
    responder.call_model_func = kwargs.get("call_model_func", AsyncMock(return_value=Result(success=True, data="reply")))
    return responder


def _make_mock_message_builder():
    """Create a mock MessageBuilder."""
    mb = MagicMock()
    mb.build_dialog = MagicMock(return_value=[{"role": "system", "content": "system"}, {"role": "user", "content": "user"}])
    mb.build_task = MagicMock(return_value=[{"role": "user", "content": "task"}])
    return mb


def _make_results_dict(results_list):
    """Convert list of UnitResult to Dict[str, UnitResult]."""
    return {r.unit_id: r for r in results_list}


# ── reply_simple Tests (TC-01 ~ TC-02) ──

class TestReplySimple:
    """reply_simple tests: TC-01 ~ TC-02."""

    @pytest.mark.asyncio
    async def test_tc01_reply_simple_success(self):
        """TC-01: reply_simple 成功 → Result(data=str)."""
        mb = _make_mock_message_builder()
        responder = _make_responder(
            call_model_func=AsyncMock(return_value=Result(success=True, data="這是簡單回覆")),
        )

        with patch('core.responder.MessageBuilder', mb):
            result = await responder.reply_simple(
                system_prompt="你是一個助手",
                user_input="你好",
                buffer="buffer text",
                summary="summary text",
                rag="rag content",
            )

        assert result.success is True
        assert result.data == "這是簡單回覆"
        mb.build_dialog.assert_called_once()
        responder.call_model_func.assert_called_once()

    @pytest.mark.asyncio
    async def test_tc02_reply_simple_fail(self):
        """TC-02: reply_simple 失敗（LLM 錯誤） → log_action(FAILED)."""
        mb = _make_mock_message_builder()
        responder = _make_responder(
            call_model_func=AsyncMock(side_effect=Exception("LLM 服務錯誤")),
        )

        with patch('core.responder.MessageBuilder', mb):
            result = await responder.reply_simple(
                system_prompt="你是一個助手",
                user_input="你好",
                buffer="",
                summary="",
                rag="",
            )

        assert result.success is False
        assert "LLM 服務錯誤" in result.error


# ── reply_tool Tests (TC-03 ~ TC-04) ──

class TestReplyTool:
    """reply_tool tests: TC-03 ~ TC-04."""

    @pytest.mark.asyncio
    async def test_tc03_reply_tool_success(self):
        """TC-03: reply_tool 成功 → Result(data=str)."""
        responder = _make_responder(
            call_model_func=AsyncMock(return_value=Result(success=True, data="這是工具回覆")),
        )

        result = await responder.reply_tool(
            agentic_loop_output="工具執行結果",
            user_input="搜尋資料",
        )

        assert result.success is True
        assert result.data == "這是工具回覆"
        responder.call_model_func.assert_called_once()

    @pytest.mark.asyncio
    async def test_tc04_reply_tool_fail(self):
        """TC-04: reply_tool 失敗 → log_action(FAILED)."""
        responder = _make_responder(
            call_model_func=AsyncMock(side_effect=Exception("LLM 服務錯誤")),
        )

        result = await responder.reply_tool(
            agentic_loop_output="輸出",
            user_input="輸入",
        )

        assert result.success is False
        assert "LLM 服務錯誤" in result.error


# ── integrate Tests (TC-05 ~ TC-20) ──
# All internal method tests (TC-08~TC-19) verified via public API integrate() only.
# integrate signature: integrate(task: str, results: Dict[str, UnitResult], units: List[Unit]) -> Result

class TestIntegrate:
    """integrate tests: TC-05 ~ TC-20 (internal methods verified via public API)."""

    @pytest.mark.asyncio
    async def test_tc05_integrate_no_units(self):
        """TC-05: integrate 無 units → 回傳 "任務已執行完成。"."""
        responder = _make_responder()

        result = await responder.integrate("測試任務", {}, [])

        assert result.success is True
        assert "任務已執行完成。" in result.data


    @pytest.mark.asyncio
    async def test_tc07_integrate_no_content_action_success(self):
        """TC-07: integrate 無 CONTENT/ACTION unit（全 success） → "任務已執行完成。"."""
        responder = _make_responder()
        results = _make_results_dict([
            UnitResult(unit_id="u1", status=UnitStatus.SUCCESS, output="輸出"),
        ])
        units = [Unit(unit_id="u1", goal="目標", output_type="INTERNAL")]

        result = await responder.integrate("測試任務", results, units)

        assert result.success is True
        assert "任務已執行完成。" in result.data

    @pytest.mark.asyncio
    async def test_tc08_integrate_classify_results_all_success(self):
        """TC-08: integrate 內部 _classify_results 全部 SUCCESS (via public API)."""
        mb = _make_mock_message_builder()
        responder = _make_responder(
            call_model_func=AsyncMock(return_value=Result(success=True, data="整合回覆")),
        )
        results = _make_results_dict([
            UnitResult(unit_id="u1", status=UnitStatus.SUCCESS, output="O1"),
            UnitResult(unit_id="u2", status=UnitStatus.SUCCESS, output="O2"),
        ])
        units = [
            Unit(unit_id="u1", goal="G1", output_type="CONTENT"),
            Unit(unit_id="u2", goal="G2", output_type="ACTION"),
        ]

        with patch('core.responder.MessageBuilder', mb):
            result = await responder.integrate("測試任務", results, units)

        assert result.success is True
        assert result.data == "整合回覆"
        responder.call_model_func.assert_called_once()

    @pytest.mark.asyncio
    async def test_tc09_integrate_classify_results_all_failed(self):
        """TC-09: integrate 內部 _classify_results 全部 FAILED (via public API)."""
        responder = _make_responder(call_model_func=None)
        results = _make_results_dict([
            UnitResult(unit_id="u1", status=UnitStatus.FAILED, error="E1"),
            UnitResult(unit_id="u2", status=UnitStatus.FAILED, error="E2"),
        ])
        units = [
            Unit(unit_id="u1", goal="G1", output_type="CONTENT"),
            Unit(unit_id="u2", goal="G2", output_type="ACTION"),
        ]

        result = await responder.integrate("測試任務", results, units)

        assert result.success is True
        assert "任務執行時發生錯誤。" in result.data

    @pytest.mark.asyncio
    async def test_tc10_integrate_classify_results_all_skipped(self):
        """TC-10: integrate 內部 _classify_results 全部 SKIPPED (via public API)."""
        responder = _make_responder()
        results = _make_results_dict([
            UnitResult(unit_id="u1", status=UnitStatus.SKIPPED),
            UnitResult(unit_id="u2", status=UnitStatus.SKIPPED),
        ])
        units = [
            Unit(unit_id="u1", goal="G1", output_type="CONTENT"),
            Unit(unit_id="u2", goal="G2", output_type="ACTION"),
        ]

        result = await responder.integrate("測試任務", results, units)

        assert result.success is True
        assert result.data is not None

    @pytest.mark.asyncio
    async def test_tc11_integrate_classify_results_mixed(self):
        """TC-11: integrate 內部 _classify_results 混合 (via public API)."""
        mb = _make_mock_message_builder()
        responder = _make_responder(
            call_model_func=AsyncMock(return_value=Result(success=True, data="整合回覆")),
        )
        results = _make_results_dict([
            UnitResult(unit_id="u1", status=UnitStatus.SUCCESS, output="O1"),
            UnitResult(unit_id="u2", status=UnitStatus.FAILED, error="E2"),
            UnitResult(unit_id="u3", status=UnitStatus.SKIPPED),
        ])
        units = [
            Unit(unit_id="u1", goal="G1", output_type="CONTENT"),
            Unit(unit_id="u2", goal="G2", output_type="ACTION"),
            Unit(unit_id="u3", goal="G3", output_type="INTERNAL"),
        ]

        with patch('core.responder.MessageBuilder', mb):
            result = await responder.integrate("測試任務", results, units)

        assert result.success is True
        assert result.data == "整合回覆"
        responder.call_model_func.assert_called_once()

    @pytest.mark.asyncio
    async def test_tc12_integrate_build_reverse_deps_normal(self):
        """TC-12: integrate 內部 _build_reverse_deps 正常 (via public API)."""
        mb = _make_mock_message_builder()
        responder = _make_responder(
            call_model_func=AsyncMock(return_value=Result(success=True, data="整合回覆")),
        )
        results = _make_results_dict([
            UnitResult(unit_id="u1", status=UnitStatus.SUCCESS, output="O1"),
        ])
        units = [
            Unit(unit_id="u1", goal="G1", output_type="CONTENT", depends_on=[]),
            Unit(unit_id="u2", goal="G2", output_type="ACTION", depends_on=["u1"]),
            Unit(unit_id="u3", goal="G3", output_type="INTERNAL", depends_on=["u1"]),
        ]

        with patch('core.responder.MessageBuilder', mb):
            result = await responder.integrate("測試任務", results, units)

        assert result.success is True
        assert result.data == "整合回覆"
        responder.call_model_func.assert_called_once()

    @pytest.mark.asyncio
    async def test_tc13_integrate_build_reverse_deps_empty(self):
        """TC-13: integrate 內部 _build_reverse_deps 空 (via public API)."""
        responder = _make_responder()
        results = {}
        units = []

        result = await responder.integrate("測試任務", results, units)

        assert result.success is True
        assert "任務已執行完成。" in result.data

    @pytest.mark.asyncio
    async def test_tc14_integrate_is_leaf_content_is_leaf(self):
        """TC-14: integrate 內部 _is_leaf_content 是 leaf (via public API)."""
        mb = _make_mock_message_builder()
        responder = _make_responder(
            call_model_func=AsyncMock(return_value=Result(success=True, data="整合回覆")),
        )
        results = _make_results_dict([
            UnitResult(unit_id="u1", status=UnitStatus.SUCCESS, output="實際輸出"),
        ])
        units = [Unit(unit_id="u1", goal="G1", output_type="CONTENT", depends_on=[])]

        with patch('core.responder.MessageBuilder', mb):
            result = await responder.integrate("測試任務", results, units)

        assert result.success is True
        assert result.data == "整合回覆"
        responder.call_model_func.assert_called_once()

    @pytest.mark.asyncio
    async def test_tc15_integrate_is_leaf_content_not_leaf(self):
        """TC-15: integrate 內部 _is_leaf_content 非 leaf (via public API)."""
        mb = _make_mock_message_builder()
        responder = _make_responder(
            call_model_func=AsyncMock(return_value=Result(success=True, data="整合回覆")),
        )
        results = _make_results_dict([
            UnitResult(unit_id="u1", status=UnitStatus.SUCCESS, output="O1"),
            UnitResult(unit_id="u2", status=UnitStatus.SUCCESS, output="O2"),
        ])
        units = [
            Unit(unit_id="u1", goal="G1", output_type="CONTENT", depends_on=[]),
            Unit(unit_id="u2", goal="G2", output_type="CONTENT", depends_on=["u1"]),
        ]

        with patch('core.responder.MessageBuilder', mb):
            result = await responder.integrate("測試任務", results, units)

        assert result.success is True
        assert result.data == "整合回覆"
        responder.call_model_func.assert_called_once()

    @pytest.mark.asyncio
    async def test_tc16_integrate_collect_substantive_units_normal(self):
        """TC-16: integrate 內部 _collect_substantive_units 正常 (via public API)."""
        mb = _make_mock_message_builder()
        responder = _make_responder(
            call_model_func=AsyncMock(return_value=Result(success=True, data="整合回覆")),
        )
        results = _make_results_dict([
            UnitResult(unit_id="u1", status=UnitStatus.SUCCESS, output="實際輸出"),
        ])
        units = [Unit(unit_id="u1", goal="目標", output_type="CONTENT", depends_on=[])]

        with patch('core.responder.MessageBuilder', mb):
            result = await responder.integrate("測試任務", results, units)

        assert result.success is True
        assert result.data == "整合回覆"
        responder.call_model_func.assert_called_once()

    @pytest.mark.asyncio
    async def test_tc17_integrate_collect_substantive_units_empty(self):
        """TC-17: integrate 內部 _collect_substantive_units 空（FAILED） (via public API)."""
        responder = _make_responder(call_model_func=None)
        results = _make_results_dict([
            UnitResult(unit_id="u1", status=UnitStatus.FAILED, error="錯誤"),
        ])
        units = [Unit(unit_id="u1", goal="目標", output_type="CONTENT", depends_on=[])]

        result = await responder.integrate("測試任務", results, units)

        assert result.success is True
        assert "任務執行時發生錯誤。" in result.data

    @pytest.mark.asyncio
    async def test_tc18_integrate_build_execution_summary_normal(self):
        """TC-18: integrate 內部 _build_execution_summary 正常 (via public API)."""
        mb = _make_mock_message_builder()
        responder = _make_responder(
            call_model_func=AsyncMock(return_value=Result(success=True, data="整合回覆")),
        )
        results = _make_results_dict([
            UnitResult(unit_id="u1", status=UnitStatus.SUCCESS, output="O1"),
            UnitResult(unit_id="u2", status=UnitStatus.FAILED, error="E2"),
            UnitResult(unit_id="u3", status=UnitStatus.SKIPPED),
        ])
        units = [
            Unit(unit_id="u1", goal="G1", output_type="CONTENT", depends_on=[]),
            Unit(unit_id="u2", goal="G2", output_type="ACTION", depends_on=["u1"]),
            Unit(unit_id="u3", goal="G3", output_type="INTERNAL", depends_on=["u1"]),
        ]

        with patch('core.responder.MessageBuilder', mb):
            result = await responder.integrate("測試任務", results, units)

        assert result.success is True
        assert result.data == "整合回覆"
        responder.call_model_func.assert_called_once()

    @pytest.mark.asyncio
    async def test_tc19_integrate_build_execution_summary_empty(self):
        """TC-19: integrate 內部 _build_execution_summary 空 (via public API)."""
        responder = _make_responder()
        results = {}
        units = []

        result = await responder.integrate("測試任務", results, units)

        assert result.success is True
        assert "任務已執行完成。" in result.data

    @pytest.mark.asyncio
    async def test_tc20_integrate_full_flow(self):
        """TC-20: integrate 完整流程（LLM 整合）."""
        mb = _make_mock_message_builder()
        responder = _make_responder(
            call_model_func=AsyncMock(return_value=Result(success=True, data="整合後的回覆")),
        )
        results = _make_results_dict([
            UnitResult(unit_id="u1", status=UnitStatus.SUCCESS, output="實際輸出"),
        ])
        units = [Unit(unit_id="u1", goal="目標", output_type="CONTENT", depends_on=[])]

        with patch('core.responder.MessageBuilder', mb):
            result = await responder.integrate("測試任務", results, units)

        assert result.success is True
        assert result.data == "整合後的回覆"
        mb.build_task.assert_called_once()
        responder.call_model_func.assert_called_once()
        # 從 call_args[0] 取 positional args（messages 在第一個 positional arg）
        call_args = responder.call_model_func.call_args
        messages = call_args[0][1] if call_args[0] else []
        assert len(messages) > 0
