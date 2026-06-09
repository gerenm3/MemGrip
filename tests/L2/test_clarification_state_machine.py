"""
tests/L2/test_clarification_state_machine.py -- 群組 3：Clarification 狀態機.
設計依據：docs/test_plan_l2/03_clarification_state_machine.md
黑箱原則：不讀取 core/clarification_manager.py / core/clarifier.py / core/router.py 源碼.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from models.blueprints import (
    ClarificationState,
    Result,
)


# ── TC-01：NORMAL → AWAITING_CLARIFICATION 轉換 ──

@pytest.mark.asyncio
async def test_TC01_normal_to_awaiting():
    """TC-01: NORMAL → AWAITING_CLARIFICATION 轉換."""
    from core.clarification_manager import ClarificationManager

    mock_router = MagicMock()
    mock_router.is_clarification = AsyncMock(return_value=Result(success=True, data={"is_clarification": False}))
    mock_clarifier = MagicMock()
    mock_clarifier.clarify = AsyncMock(return_value=Result(success=True, data={
        "questions": ["請說明你的具體需求", "目標是什麼？"], "goal": None
    }))
    mock_memory = MagicMock()
    mock_memory.get_context = AsyncMock(return_value={
        "buffer": "buffer text", "summary": "summary text", "rag": ""
    })

    cm = ClarificationManager(router=mock_router, clarifier=mock_clarifier, memory=mock_memory)

    assert cm.clarification_state == ClarificationState.NORMAL

    result = cm.start_clarification(
        questions=["請說明你的具體需求", "目標是什麼？"],
        clarify_data={"goal": None},
        path="complex",
        buffer="buffer text",
        summary="summary text",
        rag="",
        domain="general"
    )

    assert cm.clarification_state == ClarificationState.AWAITING_CLARIFICATION


# ── TC-02：Clarifier 回傳 questions 非空但 goal 有值 ──

@pytest.mark.asyncio
async def test_TC02_questions_non_empty_goal_has_value():
    """TC-02: Clarifier 回傳 questions 非空但 goal 有值."""
    from core.clarification_manager import ClarificationManager

    mock_router = MagicMock()
    mock_clarifier = MagicMock()
    mock_clarifier.clarify = AsyncMock(return_value=Result(success=True, data={
        "questions": ["還請補充環境資訊"], "goal": "deploy"
    }))
    mock_memory = MagicMock()

    cm = ClarificationManager(router=mock_router, clarifier=mock_clarifier, memory=mock_memory)

    result = cm.start_clarification(
        questions=["還請補充環境資訊"],
        clarify_data={"goal": "deploy"},
        path="tool",
        buffer="",
        summary="",
        rag="",
        domain="general"
    )

    assert cm.clarification_state == ClarificationState.AWAITING_CLARIFICATION


# ── TC-03：AWAITING → is_clarification=True → 繼續等待 ──

@pytest.mark.asyncio
async def test_TC03_awaiting_is_clarification_true_continue():
    """TC-03: AWAITING → is_clarification=True → 繼續等待."""
    from core.clarification_manager import ClarificationManager

    mock_router = MagicMock()
    mock_router.is_clarification = AsyncMock(return_value=Result(success=True, data={"is_clarification": True}))
    mock_router.route = AsyncMock(return_value=Result(success=True, data={"intent": "complex", "need_rag": False, "domain": "general"}))
    mock_clarifier = MagicMock()
    mock_clarifier.clarify = AsyncMock(return_value=Result(success=True, data={
        "questions": ["請再補充目標"], "goal": None
    }))
    mock_memory = MagicMock()
    mock_memory.get_context = AsyncMock(return_value={
        "buffer": "", "summary": "", "rag": ""
    })

    cm = ClarificationManager(router=mock_router, clarifier=mock_clarifier, memory=mock_memory)

    # 先進入 AWAITING
    cm.start_clarification(
        questions=["請說明你的具體需求"],
        clarify_data={"goal": None},
        path="complex",
        buffer="", summary="", rag="", domain="general"
    )

    result = await cm.handle_clarification_response("我想要部署應用程式")

    assert cm.clarification_state == ClarificationState.AWAITING_CLARIFICATION
    assert result.completed is False


# ── TC-04：AWAITING → is_clarification=True → 澄清完成 → 重新路由 ──

@pytest.mark.asyncio
async def test_TC04_awaiting_clarification_complete_reroute():
    """TC-04: AWAITING → is_clarification=True → 澄清完成 → 重新路由."""
    from core.clarification_manager import ClarificationManager

    mock_router = MagicMock()
    mock_router.is_clarification = AsyncMock(return_value=Result(success=True, data={"is_clarification": True}))
    mock_router.route = AsyncMock(return_value=Result(success=True, data={
        "intent": "complex", "need_rag": False, "domain": "software_dev"
    }))
    mock_clarifier = MagicMock()
    mock_clarifier.clarify = AsyncMock(return_value=Result(success=True, data={
        "goal": "deploy", "entities": ["app"], "scope": "production", "constraints": [], "questions": []
    }))
    mock_memory = MagicMock()
    mock_memory.get_context = AsyncMock(return_value={
        "buffer": "", "summary": "", "rag": ""
    })

    cm = ClarificationManager(router=mock_router, clarifier=mock_clarifier, memory=mock_memory)

    cm.start_clarification(
        questions=["請說明你的具體需求"],
        clarify_data={"goal": None},
        path="complex",
        buffer="", summary="", rag="", domain="general"
    )

    result = await cm.handle_clarification_response("我想要部署到 production 環境")

    # DEF-007：completed=True 時 path 應為 "pending"
    assert cm.clarification_state == ClarificationState.NORMAL
    assert result.completed is True
    assert result.path == "pending"
    assert mock_router.route.call_count == 1


# ── TC-05：AWAITING → is_clarification=False → 清除 pending ──

@pytest.mark.asyncio
async def test_TC05_awaiting_is_clarification_false_clear_pending():
    """TC-05: AWAITING → is_clarification=False → 清除 pending."""
    from core.clarification_manager import ClarificationManager

    mock_router = MagicMock()
    mock_router.is_clarification = AsyncMock(return_value=Result(success=True, data={"is_clarification": False}))
    mock_router.route = AsyncMock(return_value=Result(success=True, data={"intent": "complex", "need_rag": False, "domain": "general"}))
    mock_clarifier = MagicMock()
    mock_memory = MagicMock()
    mock_memory.get_context = AsyncMock(return_value={
        "buffer": "", "summary": "", "rag": ""
    })

    cm = ClarificationManager(router=mock_router, clarifier=mock_clarifier, memory=mock_memory)

    cm.start_clarification(
        questions=["請說明你的具體需求"],
        clarify_data={"goal": None},
        path="complex",
        buffer="", summary="", rag="", domain="general"
    )

    result = await cm.handle_clarification_response("這是另一個新問題")

    assert cm.clarification_state == ClarificationState.NORMAL
    assert result.completed is True
    assert result.path == "pending"
    assert result.reply is None


# ── TC-06：輪數超限 → 強制結束澄清 ──

@pytest.mark.asyncio
async def test_TC06_rounds_exceeded_forced_end():
    """TC-06: 輪數超限 → 強制結束澄清."""
    from core.clarification_manager import ClarificationManager

    mock_router = MagicMock()
    mock_router.is_clarification = AsyncMock(return_value=Result(success=True, data={"is_clarification": True}))
    mock_router.route = AsyncMock(return_value=Result(success=True, data={"intent": "complex", "need_rag": False, "domain": "general"}))
    mock_clarifier = MagicMock()
    mock_clarifier.clarify = AsyncMock(return_value=Result(success=True, data={
        "questions": ["請再補充"], "goal": None
    }))
    mock_memory = MagicMock()
    mock_memory.get_context = AsyncMock(return_value={
        "buffer": "", "summary": "", "rag": ""
    })

    cm = ClarificationManager(router=mock_router, clarifier=mock_clarifier, memory=mock_memory)

    # 先進入 AWAITING
    cm.start_clarification(
        questions=["請補充"],
        clarify_data={"goal": None},
        path="complex",
        buffer="", summary="", rag="", domain="general"
    )

    # 手動設定 rounds 為 MAX_CLARIFY_ROUNDS（假設預設為 2）
    cm._clarification_rounds = 2

    result = await cm.handle_clarification_response("我補充了資訊")

    assert cm.clarification_state == ClarificationState.NORMAL
    assert result.completed is True


# ── TC-07：澄清完成 → simple 升級為 tool ──

@pytest.mark.asyncio
async def test_TC07_clarification_complete_simple_upgraded_to_tool():
    """TC-07: 澄清完成 → simple 升級為 tool."""
    from core.clarification_manager import ClarificationManager

    mock_router = MagicMock()
    mock_router.is_clarification = AsyncMock(return_value=Result(success=True, data={"is_clarification": True}))
    mock_router.route = AsyncMock(return_value=Result(success=True, data={
        "intent": "simple", "need_rag": False, "domain": "general"
    }))
    mock_clarifier = MagicMock()
    mock_clarifier.clarify = AsyncMock(return_value=Result(success=True, data={
        "goal": "simple query", "entities": [], "scope": "", "constraints": [], "questions": []
    }))
    mock_memory = MagicMock()
    mock_memory.get_context = AsyncMock(return_value={
        "buffer": "", "summary": "", "rag": ""
    })

    cm = ClarificationManager(router=mock_router, clarifier=mock_clarifier, memory=mock_memory)

    cm.start_clarification(
        questions=["請說明你的需求"],
        clarify_data={"goal": None},
        path="complex",
        buffer="", summary="", rag="", domain="general"
    )

    result = await cm.handle_clarification_response("我只想要簡單查詢")

    # DEF-007：completed=True 時 path 應為 "pending"
    assert cm.clarification_state == ClarificationState.NORMAL
    assert result.completed is True
    assert result.path == "pending"


# ── TC-08：ClarificationResult 結構驗證 ──

def test_TC08_clarification_result_structure():
    """TC-08: ClarificationResult 結構驗證."""
    from core.clarification_manager import ClarificationResult as CMClarificationResult

    result = CMClarificationResult(
        completed=True,
        path="pending",
        clarify_data={},
        domain="general",
        buffer="",
        summary="",
        rag="",
        reply=None
    )

    assert result.completed is True
    assert result.path == "pending"
    assert isinstance(result.clarify_data, dict)
    assert isinstance(result.domain, str)
    assert isinstance(result.buffer, str)
    assert isinstance(result.summary, str)
    assert isinstance(result.rag, str)
    assert result.reply is None


# ── TC-09：ClarificationManager 建構參數驗證 ──

def test_TC09_clarification_manager_constructor():
    """TC-09: ClarificationManager 建構參數驗證."""
    from core.clarification_manager import ClarificationManager

    mock_router = MagicMock()
    mock_clarifier = MagicMock()
    mock_memory = MagicMock()

    cm = ClarificationManager(router=mock_router, clarifier=mock_clarifier, memory=mock_memory)

    assert cm.clarification_state == ClarificationState.NORMAL
    assert cm.router is mock_router
    assert cm.clarifier is mock_clarifier
    assert cm.memory is mock_memory


# ── TC-10：ClarificationState 狀態枚舉驗證 ──

def test_TC10_clarification_state_enum():
    """TC-10: ClarificationState 狀態枚舉驗證."""
    assert ClarificationState.NORMAL.value == "NORMAL"
    assert ClarificationState.AWAITING_CLARIFICATION.value == "AWAITING_CLARIFICATION"
    assert ClarificationState.NORMAL != ClarificationState.AWAITING_CLARIFICATION
    assert ClarificationState.NORMAL == ClarificationState.NORMAL