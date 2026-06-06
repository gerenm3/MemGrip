"""Tests for route merge: intent + need_rag + domain in single LLM call."""

import asyncio
import os
from unittest.mock import AsyncMock, patch

import config
import pytest

from core.router import Router
from models.blueprints import Result


# --- Helpers ---

def _make_router(mock_call_model: AsyncMock) -> Router:
    return Router(call_model_func=mock_call_model)


def _route_with_mocked_patterns(router: Router, user_input: str):
    """設定 _patterns_list 並 mock getmtime 防止重新讀檔。"""
    with patch.object(os.path, 'getmtime', return_value=router._last_mtime):
        return asyncio.run(router.route(user_input))


# ── Test 1: simple_general (via pattern) ─────────────────────────
def test_01_simple_general_pattern():
    """測試 pattern 匹配：simple intent + general domain"""
    patterns = [
        {"regex": "今天.*天氣", "intent": "simple", "need_rag": False, "priority": 10, "domain": "general"},
    ]
    mock_call = AsyncMock(return_value=Result(success=True, data={}))
    router = _make_router(mock_call)
    router._patterns_list = patterns

    result = _route_with_mocked_patterns(router, "今天天氣如何")

    assert result.success is True
    assert result.data["intent"] == "simple"
    assert result.data["need_rag"] is False
    assert result.data["domain"] == "general"


# ── Test 2: simple_rag_true (via pattern) ──────────────────────
def test_02_simple_rag_true_pattern():
    """測試 pattern 匹配：need_rag=true"""
    patterns = [
        {"regex": "繼續|接著|再說", "intent": "simple", "need_rag": True, "priority": 10, "domain": "general"},
    ]
    mock_call = AsyncMock(return_value=Result(success=True, data={}))
    router = _make_router(mock_call)
    router._patterns_list = patterns

    result = _route_with_mocked_patterns(router, "繼續說下去")

    assert result.success is True
    assert result.data["intent"] == "simple"
    assert result.data["need_rag"] is True


# ── Test 3: simple_rag_false (via pattern) ───────────────────────
def test_03_simple_rag_false_pattern():
    """測試 pattern 匹配：need_rag=false"""
    patterns = [
        {"regex": "你是誰|你叫什麼", "intent": "simple", "need_rag": False, "priority": 10, "domain": "general"},
    ]
    mock_call = AsyncMock(return_value=Result(success=True, data={}))
    router = _make_router(mock_call)
    router._patterns_list = patterns

    result = _route_with_mocked_patterns(router, "你是誰")

    assert result.success is True
    assert result.data["intent"] == "simple"
    assert result.data["need_rag"] is False


# ── Test 4: tool_general (via pattern) ─────────────────────────
def test_04_tool_general_pattern():
    """測試 pattern 匹配：tool intent + general domain"""
    patterns = [
        {"regex": "搜尋|查.*資訊", "intent": "tool", "need_rag": False, "priority": 10, "domain": "general"},
    ]
    mock_call = AsyncMock(return_value=Result(success=True, data={}))
    router = _make_router(mock_call)
    router._patterns_list = patterns

    result = _route_with_mocked_patterns(router, "搜尋 Python 3.12 新功能")

    assert result.success is True
    assert result.data["intent"] == "tool"
    assert result.data["domain"] == "general"


# ── Test 5: tool_rag_true (via pattern) ───────────────────────
def test_05_tool_rag_true_pattern():
    """測試 pattern 匹配：tool + need_rag=true"""
    patterns = [
        {"regex": "上次的.*結果", "intent": "tool", "need_rag": True, "priority": 10, "domain": "general"},
    ]
    mock_call = AsyncMock(return_value=Result(success=True, data={}))
    router = _make_router(mock_call)
    router._patterns_list = patterns

    result = _route_with_mocked_patterns(router, "上次的結果呢")

    assert result.success is True
    assert result.data["intent"] == "tool"
    assert result.data["need_rag"] is True


# ── Test 6: tool_rag_false (via pattern) ───────────────────────
def test_06_tool_rag_false_pattern():
    """測試 pattern 匹配：tool + need_rag=false"""
    patterns = [
        {"regex": "搜尋.*台北.*天氣", "intent": "tool", "need_rag": False, "priority": 10, "domain": "general"},
    ]
    mock_call = AsyncMock(return_value=Result(success=True, data={}))
    router = _make_router(mock_call)
    router._patterns_list = patterns

    result = _route_with_mocked_patterns(router, "搜尋台北天氣")

    assert result.success is True
    assert result.data["need_rag"] is False


# ── Test 7-13: LLM 呼叫測試（patch _call_llm 繞過 parse）───

@pytest.mark.asyncio
async def test_07_complex_general_via_llm():
    """測試 LLM 呼叫：complex intent + general domain（走 _call_route）"""
    mock_call = AsyncMock(return_value=Result(success=True, data={}))
    router = _make_router(mock_call)
    router._patterns_list = []

    fake_result = Result(success=True, data={
        "intent": "complex", "need_rag": False, "domain": "general"
    })
    with patch.object(router, "_call_llm", new=AsyncMock(return_value=fake_result)):
        result = await router.route("幫我寫一篇關於歷史的報告")

    assert result.success is True
    assert result.data["intent"] == "complex"
    assert result.data["domain"] == "general"


@pytest.mark.asyncio
async def test_08_complex_software_dev_via_llm():
    """測試 LLM 呼叫：complex + software_dev"""
    mock_call = AsyncMock(return_value=Result(success=True, data={}))
    router = _make_router(mock_call)
    router._patterns_list = []

    fake_result = Result(success=True, data={
        "intent": "complex", "need_rag": False, "domain": "software_dev"
    })
    with patch.object(router, "_call_llm", new=AsyncMock(return_value=fake_result)):
        result = await router.route("幫我建立一個 Flask API")

    assert result.success is True
    assert result.data["domain"] == "software_dev"


@pytest.mark.asyncio
async def test_09_complex_it_security_via_llm():
    """測試 LLM 呼叫：complex + it_security"""
    mock_call = AsyncMock(return_value=Result(success=True, data={}))
    router = _make_router(mock_call)
    router._patterns_list = []

    fake_result = Result(success=True, data={
        "intent": "complex", "need_rag": False, "domain": "it_security"
    })
    with patch.object(router, "_call_llm", new=AsyncMock(return_value=fake_result)):
        result = await router.route("幫我掃描網路漏洞")

    assert result.success is True
    assert result.data["domain"] == "it_security"


@pytest.mark.asyncio
async def test_10_domain_software_dev():
    """測試 domain 分類：software_dev"""
    mock_call = AsyncMock(return_value=Result(success=True, data={}))
    router = _make_router(mock_call)
    router._patterns_list = []

    fake_result = Result(success=True, data={
        "intent": "tool", "need_rag": False, "domain": "software_dev"
    })
    with patch.object(router, "_call_llm", new=AsyncMock(return_value=fake_result)):
        result = await router.route("如何在 Docker 中部署 React 應用")

    assert result.success is True
    assert result.data["domain"] == "software_dev"


@pytest.mark.asyncio
async def test_11_domain_it_security():
    """測試 domain 分類：it_security"""
    mock_call = AsyncMock(return_value=Result(success=True, data={}))
    router = _make_router(mock_call)
    router._patterns_list = []

    fake_result = Result(success=True, data={
        "intent": "tool", "need_rag": False, "domain": "it_security"
    })
    with patch.object(router, "_call_llm", new=AsyncMock(return_value=fake_result)):
        result = await router.route("如何保護 SSH 不被暴力破解")

    assert result.success is True
    assert result.data["domain"] == "it_security"


@pytest.mark.asyncio
async def test_12_domain_general():
    """測試 domain 分類：general"""
    mock_call = AsyncMock(return_value=Result(success=True, data={}))
    router = _make_router(mock_call)
    router._patterns_list = []

    fake_result = Result(success=True, data={
        "intent": "simple", "need_rag": False, "domain": "general"
    })
    with patch.object(router, "_call_llm", new=AsyncMock(return_value=fake_result)):
        result = await router.route("推薦一本好的小說")

    assert result.success is True
    assert result.data["domain"] == "general"


@pytest.mark.asyncio
async def test_13_need_rag_boundary():
    """測試 need_rag 邊界：模糊指代應判為 true"""
    mock_call = AsyncMock(return_value=Result(success=True, data={}))
    router = _make_router(mock_call)
    router._patterns_list = []

    fake_result = Result(success=True, data={
        "intent": "simple", "need_rag": True, "domain": "general"
    })
    with patch.object(router, "_call_llm", new=AsyncMock(return_value=fake_result)):
        result = await router.route("那件事的結果呢")

    assert result.success is True
    assert result.data["need_rag"] is True


# ── Test 14: invalid intent → success=False ────────────────────
@pytest.mark.asyncio
async def test_14_invalid_intent_fallback():
    """測試無效 intent：LLM 返回 {"intent": "invalid"} → success=False"""
    mock_call = AsyncMock(return_value=Result(success=True, data={}))
    router = _make_router(mock_call)
    router._patterns_list = []

    fake_result = Result(success=True, data={
        "intent": "invalid", "need_rag": False, "domain": "general"
    })
    with patch.object(router, "_call_llm", new=AsyncMock(return_value=fake_result)):
        result = await router.route("隨便輸入")

    assert result.success is False


# ── Test 15: LLM failure retry → success=False ───────────────────
@pytest.mark.asyncio
async def test_15_llm_failure_retry():
    """測試 LLM 失敗重試：兩次都失敗 → success=False"""
    call_count = 0

    async def mock_fail(*_args, **_kwargs):
        nonlocal call_count
        call_count += 1
        return Result(success=False, error="mock LLM error")

    mock_call = AsyncMock(return_value=Result(success=True, data={}))
    router = _make_router(mock_call)
    router._patterns_list = []

    with patch.object(router, "_call_llm", new=AsyncMock(side_effect=mock_fail)):
        result = await router.route("some input")

    assert result.success is False
    assert call_count == 2  # 應重試一次
    assert "重試" in result.error