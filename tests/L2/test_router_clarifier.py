"""
tests/L2/test_router_clarifier.py -- L2 mock integration tests for Router + Clarifier + ClarificationManager.
Group 7: 24 TCs (Router 12 + Clarifier 8 + ClarificationManager 4)
"""

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_project_root = Path(__file__).resolve().parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from models.blueprints import ClarificationState, Result
from core.clarification_manager import ClarificationManager, ClarificationResult


# ── Helpers ──

def _make_router(**kwargs):
    """Create a Router instance with mocked call_model_func."""
    from core.router import Router
    call_model_func = kwargs.get("call_model_func", AsyncMock(return_value=Result(success=True, data='{"intent": "simple", "need_rag": False, "domain": "general"}')))
    router = Router(call_model_func=call_model_func)
    return router


def _make_clarifier(**kwargs):
    """Create a Clarifier instance with mocked call_model_func."""
    from core.clarifier import Clarifier
    call_model_func = kwargs.get("call_model_func", AsyncMock(return_value=Result(success=True, data='{"goal": "test", "entities": [], "scope": "", "constraints": [], "rules": [], "success_criteria": "", "questions": []}') ))
    buffer = kwargs.get("buffer", MagicMock(get=MagicMock(return_value="") ))
    summary = kwargs.get("summary", MagicMock(get_summary=MagicMock(return_value="") ))
    clarifier = Clarifier(call_model_func=call_model_func, buffer=buffer, summary=summary)
    return clarifier


def _make_clarification_manager(**kwargs):
    """Create a ClarificationManager with mocked dependencies."""
    router = kwargs.get("router", MagicMock())
    clarifier = kwargs.get("clarifier", MagicMock())
    memory = kwargs.get("memory", MagicMock())
    cm = ClarificationManager(router=router, clarifier=clarifier, memory=memory)
    return cm


# ── Router Tests (TC-01 ~ TC-12) ──

class TestRouter:
    """Router tests: TC-01 ~ TC-12."""

    @pytest.mark.asyncio
    async def test_tc01_pattern_match_success(self):
        """TC-01: pattern match 成功 → 直接回傳 intent/domain/need_rag (LLM not called)."""
        mock_patterns = [{"regex": "^查詢.*", "intent": "simple", "need_rag": False, "priority": 0, "domain": "general"}]
        router = _make_router(call_model_func=AsyncMock())
        with patch.object(router, '_load_patterns', return_value=mock_patterns):
            result = await router.route("查詢今天的天气")

        assert result.success is True
        assert result.data["intent"] == "simple"
        assert result.data["need_rag"] is False
        assert result.data["domain"] == "general"
        router.call_model_func.assert_not_called()

    @pytest.mark.asyncio
    async def test_tc02_pattern_match_fail_llm_route_success(self):
        """TC-02: pattern match 失敗 → LLM route 成功 → intent validation 通過."""
        router = _make_router(call_model_func=AsyncMock(
            return_value=Result(success=True, data='{"intent": "tool", "need_rag": true, "domain": "software_dev"}')
        ))
        with patch.object(router, '_load_patterns', return_value=[]):
            result = await router.route("幫我寫一個 Python 函式")

        assert result.success is True
        assert result.data["intent"] == "tool"
        assert result.data["need_rag"] is True
        assert result.data["domain"] == "software_dev"
        router.call_model_func.assert_called_once()

    @pytest.mark.asyncio
    async def test_tc03_intent_validation_fail_retry_success(self):
        """TC-03: intent validation 失敗 → 重試（第 1 次 invalid_intent → 第 2 次 simple，最終成功）."""
        router = _make_router(call_model_func=AsyncMock(side_effect=[
            Result(success=True, data='{"intent": "invalid_intent", "need_rag": false, "domain": "general"}'),
            Result(success=True, data='{"intent": "simple", "need_rag": false, "domain": "general"}'),
        ]))
        with patch.object(router, '_load_patterns', return_value=[]):
            result = await router.route("幫我寫程式", _max_attempts=2)

        assert result.success is True
        assert result.data["intent"] == "simple"
        assert router.call_model_func.call_count == 2

    @pytest.mark.asyncio
    async def test_tc04_all_retries_fail(self):
        """TC-04: 所有重試失敗 → 設計文件預期 success=False（實際源碼未實作重試邏輯，測試失敗作為 DEF-018 標記）."""
        router = _make_router(call_model_func=AsyncMock(side_effect=[
            Result(success=True, data='{"intent": "invalid_intent", "need_rag": false, "domain": "general"}'),
            Result(success=True, data='{"intent": "invalid_intent", "need_rag": false, "domain": "general"}'),
        ]))
        with patch.object(router, '_load_patterns', return_value=[]):
            result = await router.route("執行複雜分析", _max_attempts=2)

        # 設計文件預期：所有重試失敗 → success=False
        assert result.success is False
        assert "重試" in result.error or "retry" in result.error.lower()

    @pytest.mark.asyncio
    async def test_tc05_probe_server_success(self):
        """TC-05: probe_server 成功 → Result(success=True, data={"server": str})."""
        router = _make_router(call_model_func=AsyncMock(
            return_value=Result(success=True, data='{"server": "brave_search"}')
        ))

        result = await router.probe_server("搜尋最新新聞", ["brave_search", "file_rw"])

        assert result.success is True
        assert result.data["server"] == "brave_search"
        router.call_model_func.assert_called_once()

    @pytest.mark.asyncio
    async def test_tc06_probe_server_empty_server_names(self):
        """TC-06: probe_server server_names 空 → Result(success=False, error="server_names is empty")."""
        router = _make_router()

        result = await router.probe_server("搜尋", [])

        assert result.success is False
        assert "server_names is empty" in result.error
        router.call_model_func.assert_not_called()

    @pytest.mark.asyncio
    async def test_tc07_probe_server_llm_fail(self):
        """TC-07: probe_server LLM 失敗 → Result(success=False, error=...)."""
        router = _make_router(call_model_func=AsyncMock(
            return_value=Result(success=False, error="LLM 呼叫逾時 (120s)")
        ))

        result = await router.probe_server("搜尋", ["brave_search"])

        assert result.success is False
        assert "LLM 呼叫逾時" in result.error
        router.call_model_func.assert_called_once()

    @pytest.mark.asyncio
    async def test_tc08_is_clarification_empty_pending(self):
        """TC-08: is_clarification pending_questions 空 → 直接回傳 False."""
        router = _make_router()

        result = await router.is_clarification("這是輸入", [])

        assert result.success is True
        assert result.data["is_clarification"] is False
        router.call_model_func.assert_not_called()

    @pytest.mark.asyncio
    async def test_tc09_is_clarification_true(self):
        """TC-09: is_clarification 判斷為澄清 → Result(success=True, data={"is_clarification": True})."""
        router = _make_router(call_model_func=AsyncMock(
            return_value=Result(success=True, data='{"is_clarification": true}')
        ))

        result = await router.is_clarification("我理解了，我想要部署", ["請說明你的需求"])

        assert result.success is True
        assert result.data["is_clarification"] is True
        router.call_model_func.assert_called_once()

    @pytest.mark.asyncio
    async def test_tc10_is_clarification_llm_fail(self):
        """TC-10: is_clarification LLM 失敗 → DEGRADED + 回傳 result."""
        router = _make_router(call_model_func=AsyncMock(
            return_value=Result(success=False, error="LLM 服務不可用")
        ))

        result = await router.is_clarification("回答", ["請說明你的需求"])

        assert result.success is False
        assert "LLM 服務不可用" in result.error
        router.call_model_func.assert_called_once()

    def test_tc11_extract_server_name(self):
        """TC-11: _extract_server_name 清理引號."""
        from core.router import Router
        result = Router._extract_server_name('  "brave_search"  ')
        assert result == "brave_search"

    @pytest.mark.asyncio
    async def test_tc12_probe_server_empty_response(self):
        """TC-12: probe_server LLM 回傳空 server → Result(success=False, error=...)."""
        router = _make_router(call_model_func=AsyncMock(
            return_value=Result(success=True, data='{"server": ""}')
        ))

        result = await router.probe_server("搜尋", ["brave_search"])

        assert result.success is False
        assert "server" in result.error.lower()


# ── Clarifier Tests (TC-13 ~ TC-20) ──
# All through public API clarify() — no direct private method calls.

class TestClarifier:
    """Clarifier tests: TC-13 ~ TC-20 (all via clarify() public API)."""

    @pytest.mark.asyncio
    async def test_tc13_clarify_llm_error(self):
        """TC-13: clarify 失敗（LLM 錯誤） → Result(success=False, data=None, error=str(e))."""
        clarifier = _make_clarifier(call_model_func=AsyncMock(side_effect=Exception("LLM 服務錯誤")))

        result = await clarifier.clarify("測試")

        assert result.success is False
        assert "LLM 服務錯誤" in result.error

    @pytest.mark.asyncio
    async def test_tc14_clarify_retry_fallback(self):
        """TC-14: clarify 內部 _clarify retry 3 次 → _default_clarify fallback (via public API)."""
        clarifier = _make_clarifier(call_model_func=AsyncMock(side_effect=[
            Result(success=True, data=''),
            Result(success=True, data=''),
            Result(success=True, data=''),
        ]))

        result = await clarifier.clarify("測試")

        assert result.success is True
        assert result.data["goal"] == "測試"

    @pytest.mark.asyncio
    async def test_tc15_clarify_format_input_with_tags(self):
        """TC-15: clarify 內部 _format_input 含 [BUFFER]/[SUMMARY]/[USER_INPUT] 標籤 (via public API)."""
        buffer = MagicMock(get=MagicMock(return_value="之前的對話內容"))
        summary = MagicMock(get_summary=MagicMock(return_value="摘要內容"))
        clarifier = _make_clarifier(
            call_model_func=AsyncMock(return_value=Result(success=True, data='{"goal": "測試", "questions": []}')),
            buffer=buffer,
            summary=summary,
        )

        result = await clarifier.clarify("新輸入")

        assert result.success is True
        call_args = clarifier.call_model_func.call_args
        assert call_args is not None
        # call_model_func is called with positional args: (messages_list,)
        messages = call_args[0][1] if call_args[0] else []
        all_content = " ".join(str(m) for m in messages)
        assert "[BUFFER]" in all_content
        assert "[SUMMARY]" in all_content
        assert "[USER_INPUT]" in all_content

    @pytest.mark.asyncio
    async def test_tc16_clarify_format_input_buffer_empty(self):
        """TC-16: clarify 內部 _format_input buffer 空 → 不含 buffer_text 內容 (via public API)."""
        buffer = MagicMock(get=MagicMock(return_value=""))
        summary = MagicMock(get_summary=MagicMock(return_value="摘要內容"))
        clarifier = _make_clarifier(
            call_model_func=AsyncMock(return_value=Result(success=True, data='{"goal": "測試", "questions": []}')),
            buffer=buffer,
            summary=summary,
        )

        result = await clarifier.clarify("新輸入")

        assert result.success is True
        call_args = clarifier.call_model_func.call_args
        assert call_args is not None
        messages = call_args[0][1] if call_args[0] else []
        all_content = " ".join(str(m) for m in messages)
        # buffer 為空時，messages 中不應包含 buffer_text 的實際內容
        assert "之前的對話內容" not in all_content
        assert "[SUMMARY]" in all_content

    @pytest.mark.asyncio
    async def test_tc17_clarify_parse_json_success(self):
        """TC-17: clarify 內部 _parse_json_response 成功 → dict (via public API)."""
        clarifier = _make_clarifier(call_model_func=AsyncMock(
            return_value=Result(success=True, data='{"goal": "測試", "entities": [], "scope": "", "constraints": [], "rules": [], "success_criteria": "", "questions": []}')
        ))

        result = await clarifier.clarify("測試")

        assert result.success is True
        assert result.data["goal"] == "測試"
        assert result.data["entities"] == []
        assert result.data["scope"] == ""

    @pytest.mark.asyncio
    async def test_tc18_clarify_parse_json_empty_fallback(self):
        """TC-18: clarify 內部 _parse_json_response 空字串 → None → fallback 到 _default_clarify (via public API)."""
        clarifier = _make_clarifier(call_model_func=AsyncMock(side_effect=[
            Result(success=True, data=''),
            Result(success=True, data=''),
            Result(success=True, data=''),
        ]))

        result = await clarifier.clarify("測試")

        assert result.success is True
        assert result.data["goal"] == "測試"

    @pytest.mark.asyncio
    async def test_tc19_clarify_default_clarify_values(self):
        """TC-19: clarify 內部 _default_clarify 預設值 (via public API)."""
        clarifier = _make_clarifier(call_model_func=AsyncMock(side_effect=[
            Result(success=True, data=''),
            Result(success=True, data=''),
            Result(success=True, data=''),
        ]))

        result = await clarifier.clarify("測試輸入")

        assert result.success is True
        assert result.data["goal"] == "測試輸入"
        assert result.data["entities"] == []
        assert result.data["scope"] == ""

    @pytest.mark.asyncio
    async def test_tc20_clarify_success(self):
        """TC-20: clarify 成功 → Result(success=True, data=parsed_dict)."""
        clarifier = _make_clarifier(call_model_func=AsyncMock(
            return_value=Result(success=True, data='{"goal": "部署應用程式", "entities": ["app"], "scope": "production", "constraints": [], "rules": [], "success_criteria": "部署成功", "questions": []}')
        ))

        result = await clarifier.clarify("幫我部署應用程式")

        assert result.success is True
        assert result.data["goal"] == "部署應用程式"
        assert result.data["entities"] == ["app"]
        assert result.data["scope"] == "production"


# ── ClarificationManager Tests (TC-21 ~ TC-24) ──

class TestClarificationManager:
    """ClarificationManager tests: TC-21 ~ TC-24."""

    @pytest.mark.asyncio
    async def test_tc21_start_clarification(self):
        """TC-21: start_clarification 初始化狀態（NORMAL → AWAITING）."""
        cm = _make_clarification_manager()
        cm._clarification_state = ClarificationState.NORMAL

        cm.start_clarification(
            questions=["請說明你的具體需求", "目標是什麼？"],
            clarify_data={"goal": None, "entities": [], "scope": "", "constraints": []},
            path="complex",
            buffer="buffer text",
            summary="summary text",
            rag="",
            domain="general",
        )

        assert cm._clarification_state == ClarificationState.AWAITING_CLARIFICATION
        assert cm._pending_questions == ["請說明你的具體需求", "目標是什麼？"]
        assert cm._pending_clarify_result == {"goal": None, "entities": [], "scope": "", "constraints": []}
        assert cm._pending_path == "complex"
        assert cm._pending_rag == ""
        assert cm._pending_buffer == "buffer text"
        assert cm._pending_summary == "summary text"
        assert cm._pending_domain == "general"
        assert cm._clarification_rounds == 1
        assert cm.clarification_state == ClarificationState.AWAITING_CLARIFICATION

    @pytest.mark.asyncio
    async def test_tc22_handle_clarification_response_is_clarification_true(self):
        """TC-22: handle_clarification_response → is_clarification=True → 繼續等待."""
        router = MagicMock()
        router.is_clarification = AsyncMock(return_value=Result(success=True, data={"is_clarification": True}))
        router.route = AsyncMock(return_value=Result(success=True, data={"intent": "complex", "need_rag": False, "domain": "software_dev"}))

        clarifier = MagicMock()
        clarifier.clarify = AsyncMock(return_value=Result(success=True, data={"questions": ["請再補充目標"], "goal": None, "entities": [], "scope": "", "constraints": []}))

        memory = MagicMock()
        memory.get_context = AsyncMock(return_value={"buffer": "buffer", "summary": "summary", "rag": ""})

        cm = ClarificationManager(router=router, clarifier=clarifier, memory=memory)
        cm._clarification_state = ClarificationState.AWAITING_CLARIFICATION
        cm._pending_questions = ["請說明你的具體需求"]
        cm._pending_clarify_result = {"goal": None, "entities": [], "scope": "", "constraints": []}
        cm._pending_path = "complex"
        cm._clarification_rounds = 1
        cm._clarification_history = []

        result = await cm.handle_clarification_response("我想要部署應用程式")

        assert result.completed is False
        assert result.path == "complex"
        assert cm._clarification_state == ClarificationState.AWAITING_CLARIFICATION
        assert cm._clarification_rounds == 2
        assert "請再補充目標" in cm._pending_questions
        router.is_clarification.assert_called_once()
        clarifier.clarify.assert_called_once()

    @pytest.mark.asyncio
    async def test_tc23_handle_clarification_response_is_clarification_false(self):
        """TC-23: handle_clarification_response → is_clarification=False → 清除 pending."""
        router = MagicMock()
        router.is_clarification = AsyncMock(return_value=Result(success=True, data={"is_clarification": False}))
        router.route = AsyncMock(return_value=Result(success=True, data={"intent": "simple", "need_rag": False, "domain": "general"}))

        clarifier = MagicMock()
        memory = MagicMock()
        memory.get_context = AsyncMock(return_value={"buffer": "buffer", "summary": "summary", "rag": ""})

        cm = ClarificationManager(router=router, clarifier=clarifier, memory=memory)
        cm._clarification_state = ClarificationState.AWAITING_CLARIFICATION
        cm._pending_questions = ["請說明你的具體需求"]
        cm._pending_clarify_result = {"goal": None, "entities": [], "scope": "", "constraints": []}
        cm._pending_path = "complex"
        cm._clarification_rounds = 1
        cm._clarification_history = []

        result = await cm.handle_clarification_response("這是另一個新問題")

        assert result.completed is True
        assert cm._clarification_state == ClarificationState.NORMAL
        assert cm._pending_questions == []
        assert cm._pending_clarify_result is None
        assert cm._pending_path is None

    @pytest.mark.asyncio
    async def test_tc24_clarification_rounds_exceeded(self):
        """TC-24: 輪數超限（MAX_CLARIFY_ROUNDS=2）→ 強制結束澄清."""
        router = MagicMock()
        router.is_clarification = AsyncMock(return_value=Result(success=True, data={"is_clarification": True}))
        router.route = AsyncMock(return_value=Result(success=True, data={"intent": "complex", "need_rag": False, "domain": "general"}))

        clarifier = MagicMock()
        clarifier.clarify = AsyncMock(return_value=Result(success=True, data={"questions": ["請再補充"], "goal": None, "entities": [], "scope": "", "constraints": []}))

        memory = MagicMock()
        memory.get_context = AsyncMock(return_value={"buffer": "buffer", "summary": "summary", "rag": ""})

        cm = ClarificationManager(router=router, clarifier=clarifier, memory=memory)
        cm._clarification_state = ClarificationState.AWAITING_CLARIFICATION
        cm._pending_questions = ["請補充"]
        cm._pending_clarify_result = {"goal": None, "entities": [], "scope": "", "constraints": []}
        cm._pending_path = "complex"
        cm._clarification_rounds = 2
        cm._clarification_history = ["Q: 請補充\nA: 已補充"]

        result = await cm.handle_clarification_response("我補充了資訊")

        assert result.completed is True
        assert cm._clarification_state == ClarificationState.NORMAL
        assert cm._pending_questions == []