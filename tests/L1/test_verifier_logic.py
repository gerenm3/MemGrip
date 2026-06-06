"""tests/L1/test_verifier_logic.py — core/verifier.py 純邏輯測試（12 筆）."""

import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pytest
import unittest.mock
from models.blueprints import Unit, Result


@pytest.fixture
def mock_call_model():
    return unittest.mock.AsyncMock()


@pytest.fixture
def mock_unit():
    def _make(
        unit_id="u1",
        expected_output="expected result",
        assigned_constraints=None,
        output_type="INTERNAL",
    ):
        return Unit(
            unit_id=unit_id,
            goal=f"goal_{unit_id}",
            expected_output=expected_output,
            assigned_constraints=assigned_constraints or [],
            output_type=output_type,
        )
    return _make


class TestInit:
    """Verifier.__init__ 測試."""

    def test_valid_callable(self):
        """等價類：有效 callable → 正常初始化."""
        from core.verifier import Verifier
        verifier = Verifier(call_model_func=lambda: None)
        assert verifier.call_model_func is not None

    def test_non_callable_raises(self):
        """邊界：非 callable → 拋 TypeError."""
        from core.verifier import Verifier
        with pytest.raises(TypeError):
            Verifier(call_model_func="not_callable")


class TestVerify:
    """Verifier.verify 測試."""

    @pytest.mark.asyncio
    async def test_verify_success(self, mock_call_model, mock_unit):
        """等價類：LLM 回傳 passed=True → success=True."""
        from core.verifier import Verifier
        verifier = Verifier(call_model_func=mock_call_model)
        mock_call_model.return_value = Result(
            success=True,
            data='{"passed": true, "reason": "matches"}'
        )
        unit = mock_unit()
        result = await verifier.verify(unit, "actual output")
        assert result.success is True
        assert result.data["passed"] is True

    @pytest.mark.asyncio
    async def test_verify_failed(self, mock_call_model, mock_unit):
        """等價類：LLM 回傳 passed=False → success=True, data.passed=False."""
        from core.verifier import Verifier
        verifier = Verifier(call_model_func=mock_call_model)
        mock_call_model.return_value = Result(
            success=True,
            data='{"passed": false, "reason": "does not match", "gaps": ["gap1"]}'
        )
        unit = mock_unit()
        result = await verifier.verify(unit, "actual output")
        assert result.success is True
        assert result.data["passed"] is False
        assert len(result.data["gaps"]) == 1

    @pytest.mark.asyncio
    async def test_verify_format_error(self, mock_call_model, mock_unit):
        """邊界：LLM 回傳非 JSON → success=False."""
        from core.verifier import Verifier
        verifier = Verifier(call_model_func=mock_call_model)
        mock_call_model.return_value = Result(success=True, data="not json")
        unit = mock_unit()
        result = await verifier.verify(unit, "actual output")
        assert result.success is False
        assert "格式錯誤" in result.data["reason"]

    @pytest.mark.asyncio
    async def test_verify_timeout(self, mock_call_model, mock_unit):
        """邊界：LLM 逾時 → success=False, error."""
        from core.verifier import Verifier
        mock_call_model.side_effect = asyncio.TimeoutError()
        verifier = Verifier(call_model_func=mock_call_model)
        unit = mock_unit()
        result = await verifier.verify(unit, "actual output")
        assert result.success is False
        assert "逾時" in result.error

    @pytest.mark.asyncio
    async def test_verify_llm_error(self, mock_call_model, mock_unit):
        """等價類：LLM 回傳 success=False → data=None → 解析失敗."""
        from core.verifier import Verifier
        mock_call_model.return_value = Result(success=False, error="service unavailable")
        verifier = Verifier(call_model_func=mock_call_model)
        unit = mock_unit()
        result = await verifier.verify(unit, "actual output")
        assert result.success is False
        assert "格式錯誤" in result.data["reason"]

    @pytest.mark.asyncio
    async def test_verify_no_expected_output(self, mock_call_model, mock_unit):
        """邊界：expected_output 為空 → 使用 '(未指定)'."""
        from core.verifier import Verifier
        verifier = Verifier(call_model_func=mock_call_model)
        mock_call_model.return_value = Result(success=True, data='{"passed": true, "reason": "ok"}')
        unit = mock_unit(expected_output="")
        result = await verifier.verify(unit, "actual output")
        assert result.success is True

    @pytest.mark.asyncio
    async def test_verify_no_constraints(self, mock_call_model, mock_unit):
        """邊界：無 assigned_constraints → 顯示 '（無 assigned constraints）'."""
        from core.verifier import Verifier
        verifier = Verifier(call_model_func=mock_call_model)
        mock_call_model.return_value = Result(success=True, data='{"passed": true, "reason": "ok"}')
        unit = mock_unit(assigned_constraints=[])
        result = await verifier.verify(unit, "actual output")
        assert result.success is True

    @pytest.mark.asyncio
    async def test_verify_with_constraints(self, mock_call_model, mock_unit):
        """等價類：有 assigned_constraints → 包含在 prompt 中."""
        from core.verifier import Verifier
        verifier = Verifier(call_model_func=mock_call_model)
        mock_call_model.return_value = Result(success=True, data='{"passed": true, "reason": "ok"}')
        unit = mock_unit(assigned_constraints=["constraint 1", "constraint 2"])
        result = await verifier.verify(unit, "actual output")
        assert result.success is True
        assert mock_call_model.called

    @pytest.mark.asyncio
    async def test_verify_empty_actual_output(self, mock_call_model, mock_unit):
        """邊界：actual_output 為空字串."""
        from core.verifier import Verifier
        verifier = Verifier(call_model_func=mock_call_model)
        mock_call_model.return_value = Result(success=True, data='{"passed": true, "reason": "ok"}')
        unit = mock_unit()
        result = await verifier.verify(unit, "")
        assert result.success is True

    @pytest.mark.asyncio
    async def test_verify_exception(self, mock_call_model, mock_unit):
        """等價類：LLM 拋異常 → success=False, error."""
        from core.verifier import Verifier
        mock_call_model.side_effect = ValueError("test error")
        verifier = Verifier(call_model_func=mock_call_model)
        unit = mock_unit()
        result = await verifier.verify(unit, "actual output")
        assert result.success is False
        assert "不可用" in result.error