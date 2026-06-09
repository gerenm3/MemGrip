"""L1 test for Verifier (module 27) - constants + verify() behavior.

Black-box testing: only read docs/test_plan_l1/27_verifier.md and api_signatures.md.
No source code reading of core/verifier.py.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock


class TestVerifierConstants:
    """TC-27-01 ~ TC-27-02: VERIFY_TEMPERATURE and VERIFY_MAX_TOKENS constants."""

    def test_TC27_01_verify_temperature_constant(self):
        """TC-27-01: VERIFY_TEMPERATURE 常數值 = 0.0。"""
        from core.verifier import VERIFY_TEMPERATURE
        assert VERIFY_TEMPERATURE == 0.0

    def test_TC27_02_verify_max_tokens_constant(self):
        """TC-27-02: VERIFY_MAX_TOKENS 常數值 = 1024。"""
        from core.verifier import VERIFY_MAX_TOKENS
        assert VERIFY_MAX_TOKENS == 1024


class TestVerifierInit:
    """TC-27-03 ~ TC-27-05: Verifier.__init__."""

    def test_TC27_03_init_valid_call_model_func(self):
        """TC-27-03: Verifier.__init__ - 有效 call_model_func 初始化成功。"""
        from core.verifier import Verifier

        mock_func = AsyncMock()
        verifier = Verifier(mock_func)
        assert verifier.call_model_func == mock_func

    def test_TC27_04_init_non_callable(self):
        """TC-27-04: Verifier.__init__ - 不可呼叫物件拋出 TypeError。"""
        from core.verifier import Verifier

        with pytest.raises(TypeError, match="call_model_func must be callable"):
            Verifier("not_callable")

    def test_TC27_05_init_none(self):
        """TC-27-05: Verifier.__init__ - None 作為 call_model_func 拋出 TypeError。"""
        from core.verifier import Verifier

        with pytest.raises(TypeError, match="call_model_func must be callable"):
            Verifier(None)


class TestVerifierVerify:
    """TC-27-06 ~ TC-27-16: Verifier.verify()."""

    def _make_verifier(self, mock_func=None):
        """Helper to create a Verifier with a mock call_model_func."""
        from core.verifier import Verifier
        from models.blueprints import Unit

        if mock_func is None:
            mock_func = AsyncMock()
        verifier = Verifier(mock_func)
        unit = Unit("u1", "G1", expected_output="expected text")
        return verifier, unit

    def test_TC27_06_expected_output_non_empty(self):
        """TC-27-06: verify - expected_output 非空，LLM 收到 expected_output。"""
        verifier, unit = self._make_verifier()
        mock_func = verifier.call_model_func
        mock_func.return_value = MagicMock(success=True, data='{"passed": true, "reason": "matches", "gaps": [], "constraint_checks": []}')

        import asyncio
        result = asyncio.get_event_loop().run_until_complete(verifier.verify(unit, "actual text"))

        # Verify that call_model_func was called with expected_output in messages
        assert mock_func.called
        call_args = mock_func.call_args
        # Check that expected_output was passed
        assert "expected text" in str(call_args)

    def test_TC27_07_expected_output_empty(self):
        """TC-27-07: verify - expected_output 為空，LLM 收到 (未指定)。"""
        from models.blueprints import Unit
        from core.verifier import Verifier

        mock_func = AsyncMock()
        mock_func.return_value = MagicMock(success=True, data='{"passed": true, "reason": "matches", "gaps": [], "constraint_checks": []}')
        verifier = Verifier(mock_func)
        unit = Unit("u1", "G1", expected_output="")

        import asyncio
        result = asyncio.get_event_loop().run_until_complete(verifier.verify(unit, "actual text"))

        assert mock_func.called
        call_args = mock_func.call_args
        assert "(未指定)" in str(call_args)

    def test_TC27_08_expected_output_none(self):
        """TC-27-08: verify - expected_output 為 None，LLM 收到 (未指定)。"""
        from models.blueprints import Unit
        from core.verifier import Verifier

        mock_func = AsyncMock()
        mock_func.return_value = MagicMock(success=True, data='{"passed": true, "reason": "matches", "gaps": [], "constraint_checks": []}')
        verifier = Verifier(mock_func)
        unit = Unit("u1", "G1", expected_output=None)

        import asyncio
        result = asyncio.get_event_loop().run_until_complete(verifier.verify(unit, "actual text"))

        assert mock_func.called
        call_args = mock_func.call_args
        assert "(未指定)" in str(call_args)

    def test_TC27_09_think_fixed_false(self):
        """TC-27-09: verify - think 參數固定 False。"""
        verifier, unit = self._make_verifier()
        mock_func = verifier.call_model_func
        mock_func.return_value = MagicMock(success=True, data='{"passed": true, "reason": "matches", "gaps": [], "constraint_checks": []}')

        import asyncio
        result = asyncio.get_event_loop().run_until_complete(verifier.verify(unit, "actual text"))

        # Verify think=False was passed as positional arg (5th position)
        call_args = mock_func.call_args[0]
        assert len(call_args) >= 5
        assert call_args[4] is False

    def test_TC27_10_temperature_uses_VERIFY_TEMPERATURE(self):
        """TC-27-10: verify - temperature 使用 VERIFY_TEMPERATURE (0.0)。"""
        verifier, unit = self._make_verifier()
        mock_func = verifier.call_model_func
        mock_func.return_value = MagicMock(success=True, data='{"passed": true, "reason": "matches", "gaps": [], "constraint_checks": []}')

        import asyncio
        result = asyncio.get_event_loop().run_until_complete(verifier.verify(unit, "actual text"))

        # Verify temperature=0.0 was passed as positional arg (3rd position)
        call_args = mock_func.call_args[0]
        assert len(call_args) >= 3
        assert call_args[2] == 0.0

    def test_TC27_11_max_tokens_uses_VERIFY_MAX_TOKENS(self):
        """TC-27-11: verify - max_tokens 使用 VERIFY_MAX_TOKENS (1024)。"""
        verifier, unit = self._make_verifier()
        mock_func = verifier.call_model_func
        mock_func.return_value = MagicMock(success=True, data='{"passed": true, "reason": "matches", "gaps": [], "constraint_checks": []}')

        import asyncio
        result = asyncio.get_event_loop().run_until_complete(verifier.verify(unit, "actual text"))

        # Verify max_tokens=1024 was passed as positional arg (4th position)
        call_args = mock_func.call_args[0]
        assert len(call_args) >= 4
        assert call_args[3] == 1024

    def test_TC27_12_llm_parse_success_passed_true(self):
        """TC-27-12: verify - LLM 解析成功 passed=True。"""
        verifier, unit = self._make_verifier()
        mock_func = verifier.call_model_func
        mock_func.return_value = MagicMock(success=True, data='{"passed": true, "reason": "matches", "gaps": [], "constraint_checks": []}')

        import asyncio
        result = asyncio.get_event_loop().run_until_complete(verifier.verify(unit, "actual text"))

        assert result.success is True
        assert result.data["passed"] is True
        assert result.data["reason"] == "matches"

    def test_TC27_13_llm_parse_success_passed_false(self):
        """TC-27-13: verify - LLM 解析成功 passed=False。"""
        verifier, unit = self._make_verifier()
        mock_func = verifier.call_model_func
        mock_func.return_value = MagicMock(success=True, data='{"passed": false, "reason": "mismatch", "gaps": ["gap1"], "constraint_checks": []}')

        import asyncio
        result = asyncio.get_event_loop().run_until_complete(verifier.verify(unit, "actual text"))

        assert result.success is True
        assert result.data["passed"] is False
        assert result.data["reason"] == "mismatch"
        assert result.data["gaps"] == ["gap1"]

    def test_TC27_14_llm_parse_failure(self):
        """TC-27-14: verify - LLM 解析失敗（無效 JSON）。"""
        verifier, unit = self._make_verifier()
        mock_func = verifier.call_model_func
        mock_func.return_value = MagicMock(success=True, data='not valid json{{{')

        import asyncio
        result = asyncio.get_event_loop().run_until_complete(verifier.verify(unit, "actual text"))

        assert result.success is False
        assert "驗證輸出格式錯誤" in result.data["reason"]

    def test_TC27_15_llm_timeout(self):
        """TC-27-15: verify - LLM 逾時。"""
        from core.verifier import Verifier
        import config
        import asyncio
        from models.blueprints import Unit

        mock_func = AsyncMock()
        mock_func.side_effect = asyncio.TimeoutError()
        verifier = Verifier(mock_func)
        unit = Unit("u1", "G1", expected_output="expected")

        import asyncio
        result = asyncio.get_event_loop().run_until_complete(verifier.verify(unit, "actual"))

        assert result.success is False
        assert "驗證服務逾時" in result.error
        assert f"({config.LLM_TIMEOUT}s)" in result.error

    def test_TC27_16_llm_failure(self):
        """TC-27-16: verify - LLM 失敗。"""
        from core.verifier import Verifier
        from models.blueprints import Unit

        mock_func = AsyncMock()
        mock_func.side_effect = Exception("service unavailable")
        verifier = Verifier(mock_func)
        unit = Unit("u1", "G1", expected_output="expected")

        import asyncio
        result = asyncio.get_event_loop().run_until_complete(verifier.verify(unit, "actual"))

        assert result.success is False
        assert "驗證服務不可用" in result.error