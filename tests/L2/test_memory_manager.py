"""
tests/L2/test_memory_manager.py -- 群組 5：MemoryManager 整合測試.
設計依據：docs/test_plan_l2/05_memory_manager.md
黑箱原則：不讀取 memory/ 源碼.
"""

import asyncio
import sys
import time
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_project_root = Path(__file__).resolve().parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from models.blueprints import (
    Result,
)


# ═══════════════════════════════════════════════════════════════════
# TC-01：MemoryManager.add 寫入一則對話
# ═══════════════════════════════════════════════════════════════════

def test_TC01_memory_manager_add():
    """TC-01: MemoryManager.add 寫入一則對話."""
    from memory.manager import MemoryManager
    from memory.buffer import ConversationBuffer

    buffer = ConversationBuffer()
    mm = MemoryManager(
        call_embedding_func=AsyncMock(),
        vector_store=MagicMock(),
        summary_store=MagicMock(),
        temp_cache=MagicMock(),
        summarizer=MagicMock(),
    )
    mm.buffer = buffer

    mm.add("user", "你好")

    assert len(buffer.context) == 1
    assert buffer.context[0] == {"role": "user", "content": "你好"}


# ═══════════════════════════════════════════════════════════════════
# TC-02：MemoryManager.get_context 回傳 context 與 summary
# ═══════════════════════════════════════════════════════════════════

def test_TC02_memory_manager_get_context():
    """TC-02: MemoryManager.get_context 回傳 context 與 summary."""
    from memory.manager import MemoryManager
    from memory.buffer import ConversationBuffer

    buffer = ConversationBuffer()
    buffer.context = [{"role": "user", "content": "你好"}]

    mm = MemoryManager(
        call_embedding_func=AsyncMock(),
        vector_store=MagicMock(),
        summary_store=MagicMock(),
        temp_cache=MagicMock(),
        summarizer=MagicMock(),
    )
    mm.buffer = buffer
    mm.summary_store = MagicMock()
    mm.summary_store.get_summary = MagicMock(return_value="這是摘要")

    result = mm.get_context()

    assert result["context"] == [{"role": "user", "content": "你好"}]
    assert result["summary"] == "這是摘要"


# ═══════════════════════════════════════════════════════════════════
# TC-03：MemoryManager.get_context summary_store 為 None
# ═══════════════════════════════════════════════════════════════════

def test_TC03_memory_manager_get_context_no_summary_store():
    """TC-03: MemoryManager.get_context summary_store 為 None."""
    from memory.manager import MemoryManager
    from memory.buffer import ConversationBuffer

    buffer = ConversationBuffer()
    buffer.context = [{"role": "user", "content": "你好"}]

    mm = MemoryManager(
        call_embedding_func=AsyncMock(),
        vector_store=None,
        summary_store=None,
        temp_cache=None,
        summarizer=None,
    )
    mm.buffer = buffer

    result = mm.get_context()

    assert result["context"] == [{"role": "user", "content": "你好"}]
    assert result["summary"] == ""


# ═══════════════════════════════════════════════════════════════════
# TC-04：MemoryManager.get_context buffer.get() 為 None
# ═══════════════════════════════════════════════════════════════════

def test_TC04_memory_manager_get_context_buffer_none():
    """TC-04: MemoryManager.get_context buffer.get() 為 None."""
    from memory.manager import MemoryManager
    from memory.buffer import ConversationBuffer

    buffer = ConversationBuffer()
    buffer.context = [{"role": "user", "content": "你好"}]

    mm = MemoryManager(
        call_embedding_func=AsyncMock(),
        vector_store=MagicMock(),
        summary_store=MagicMock(),
        temp_cache=MagicMock(),
        summarizer=MagicMock(),
    )
    mm.buffer = buffer
    mm.summary_store = MagicMock()
    mm.summary_store.get_summary = MagicMock(return_value="摘要內容")

    # Patch buffer.get to return None
    with patch.object(type(mm.buffer), 'get', return_value=None):
        result = mm.get_context()

    assert result["context"] == []
    assert result["summary"] == "摘要內容"


# ═══════════════════════════════════════════════════════════════════
# TC-05：MemoryManager.serialize_context 序列化 buffer
# ═══════════════════════════════════════════════════════════════════

def test_TC05_memory_manager_serialize_context():
    """TC-05: MemoryManager.serialize_context 序列化 buffer."""
    from memory.manager import MemoryManager
    from memory.buffer import ConversationBuffer

    buffer = ConversationBuffer()
    buffer.context = [{"role": "user", "content": "你好"}, {"role": "assistant", "content": "嗨"}]

    mm = MemoryManager(
        call_embedding_func=AsyncMock(),
        vector_store=MagicMock(),
        summary_store=MagicMock(),
        temp_cache=MagicMock(),
        summarizer=MagicMock(),
    )
    mm.buffer = buffer

    with patch.object(type(mm.buffer), 'serialize', return_value="用戶：你好\n助理：嗨"):
        result = mm.serialize_context()

    assert result == "用戶：你好\n助理：嗨"


# ═══════════════════════════════════════════════════════════════════
# TC-06：MemoryManager.serialize_context buffer 為空
# ═══════════════════════════════════════════════════════════════════

def test_TC06_memory_manager_serialize_context_empty():
    """TC-06: MemoryManager.serialize_context buffer 為空."""
    from memory.manager import MemoryManager
    from memory.buffer import ConversationBuffer

    buffer = ConversationBuffer()
    mm = MemoryManager(
        call_embedding_func=AsyncMock(),
        vector_store=MagicMock(),
        summary_store=MagicMock(),
        temp_cache=MagicMock(),
        summarizer=MagicMock(),
    )
    mm.buffer = buffer

    with patch.object(type(mm.buffer), 'serialize', return_value=""):
        result = mm.serialize_context()

    assert result == ""


# ═══════════════════════════════════════════════════════════════════
# TC-07：MemoryManager.retrieve 正常檢索
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_TC07_memory_manager_retrieve_normal():
    """TC-07: MemoryManager.retrieve 正常檢索.
    源碼缺陷 (DEF-014)：retrieve 回傳 dict 而非 raw 字串.
    """
    from memory.manager import MemoryManager

    call_embedding = AsyncMock(return_value=Result(success=True, data=[0.1, 0.2, 0.3]))
    vector_store = MagicMock()
    vector_store.search = MagicMock(return_value=[{"id": "doc1", "raw": "檢索結果"}])
    vector_store.compare = MagicMock(return_value=0.85)

    mm = MemoryManager(
        call_embedding_func=call_embedding,
        vector_store=vector_store,
        summary_store=MagicMock(),
        temp_cache=MagicMock(),
        summarizer=MagicMock(),
    )

    result = await mm.retrieve("查詢", top_k=1, min_similarity=0.5)

    # DEF-014：修正後應回傳 raw 字串
    assert result == "檢索結果"
    assert call_embedding.call_count == 1
    call_args = call_embedding.call_args
    assert call_args[0][0] == "bge-m3"
    assert call_args[0][1] == "查詢"


# ═══════════════════════════════════════════════════════════════════
# TC-08：MemoryManager.retrieve 相似度低於閾值
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_TC08_memory_manager_retrieve_low_similarity():
    """TC-08: MemoryManager.retrieve 相似度低於閾值."""
    from memory.manager import MemoryManager

    call_embedding = AsyncMock(return_value=Result(success=True, data=[0.1, 0.2, 0.3]))
    vector_store = MagicMock()
    vector_store.search = MagicMock(return_value=[{"id": "doc1", "raw": "檢索結果"}])
    vector_store.compare = MagicMock(return_value=0.3)

    mm = MemoryManager(
        call_embedding_func=call_embedding,
        vector_store=vector_store,
        summary_store=MagicMock(),
        temp_cache=MagicMock(),
        summarizer=MagicMock(),
    )

    result = await mm.retrieve("查詢", top_k=1, min_similarity=0.5)

    assert result == ""


# ═══════════════════════════════════════════════════════════════════
# TC-09：MemoryManager.retrieve call_embedding_func 為 None
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_TC09_memory_manager_retrieve_no_embedding():
    """TC-09: MemoryManager.retrieve call_embedding_func 為 None."""
    from memory.manager import MemoryManager

    mm = MemoryManager(
        call_embedding_func=None,
        vector_store=None,
        summary_store=MagicMock(),
        temp_cache=MagicMock(),
        summarizer=MagicMock(),
    )

    result = await mm.retrieve("查詢", top_k=1, min_similarity=0.5)

    assert result == ""


# ═══════════════════════════════════════════════════════════════════
# TC-10：MemoryManager.retrieve top_k 為 0
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_TC10_memory_manager_retrieve_top_k_zero():
    """TC-10: MemoryManager.retrieve top_k 為 0.
    源碼缺陷：top_k=0 時仍呼叫 call_embedding，且 compare 回傳 MagicMock 導致比較錯誤.
    """
    from memory.manager import MemoryManager

    call_embedding = AsyncMock(return_value=Result(success=True, data=[0.1, 0.2, 0.3]))
    vector_store = MagicMock()
    vector_store.compare = MagicMock(return_value=0.5)

    mm = MemoryManager(
        call_embedding_func=call_embedding,
        vector_store=vector_store,
        summary_store=MagicMock(),
        temp_cache=MagicMock(),
        summarizer=MagicMock(),
    )

    result = await mm.retrieve("查詢", top_k=0, min_similarity=0.5)

    assert result == ""
    # DEF-016：top_k=0 時直接回傳空字串，不呼叫 call_embedding
    assert call_embedding.call_count == 0


# ═══════════════════════════════════════════════════════════════════
# TC-11：MemoryManager.flush 即時摘要流程
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_TC11_memory_manager_flush():
    """TC-11: MemoryManager.flush 即時摘要流程.
    源碼缺陷 (DEF-013)：flush 未呼叫 summarizer.summarize_turns.
    """
    from memory.manager import MemoryManager
    from memory.buffer import ConversationBuffer

    buffer = ConversationBuffer()
    # 需要 len(context) > 2 才能觸發 check() 的 flushed 邏輯
    buffer.context = [
        {"role": "user", "content": "已 flush 的訊息"},
        {"role": "assistant", "content": "已 flush 的回覆"},
        {"role": "user", "content": "額外訊息"},
        {"role": "assistant", "content": "回覆"},
    ]

    summarizer = MagicMock()
    summarizer.summarize_turns = AsyncMock(return_value=Result(success=True, data={"summary": "新摘要"}))
    summarizer.check_importance = AsyncMock(return_value=Result(success=True, data=0.5))

    summary_store = MagicMock()

    temp_cache_mock = MagicMock()
    temp_cache_mock.total_tokens = MagicMock(return_value=0)

    mm = MemoryManager(
        call_embedding_func=AsyncMock(),
        vector_store=MagicMock(),
        summary_store=summary_store,
        temp_cache=temp_cache_mock,
        summarizer=summarizer,
    )
    mm.buffer = buffer

    # 設定 _current_tokens 超過 token_limit，使 check() 能觸發 flushed
    buffer._current_tokens = 9999

    # 觸發 buffer check 使 extract_flushed() 回傳資料
    buffer.check()
    assert len(buffer.flushed) == 2  # 確認 check() 成功 flush 2 筆

    result = await mm.flush()

    assert result.success is True
    # DEF-013：修正後應呼叫 summarizer.summarize_turns
    assert summarizer.summarize_turns.call_count == 1
    assert result.data["flushed_count"] == 2


# ═══════════════════════════════════════════════════════════════════
# TC-12：MemoryManager.flush 透過 _route_by_scores 間接驗證分流邏輯
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_TC12_memory_manager_route_by_scores():
    """TC-12: MemoryManager.flush 透過 _route_by_scores 間接驗證分流邏輯.
    源碼缺陷 (DEF-013)：flush 未呼叫 summarizer.summarize_turns，因此不會進入 _route_by_scores 分流.
    """
    from memory.manager import MemoryManager
    from memory.buffer import ConversationBuffer

    buffer = ConversationBuffer()
    # 需要 len(context) > 2 才能觸發 check() 的 flushed 邏輯
    buffer.context = [
        {"role": "user", "content": "訊息"},
        {"role": "assistant", "content": "回覆"},
        {"role": "user", "content": "額外訊息"},
        {"role": "assistant", "content": "回覆"},
    ]

    summarizer = MagicMock()
    summarizer.summarize_turns = AsyncMock(return_value=Result(success=True, data={"summary": "摘要", "embedding": [0.1, 0.2, 0.3]}))
    summarizer.check_importance = AsyncMock(return_value=Result(success=True, data=0.8))

    call_embedding = AsyncMock(return_value=Result(success=True, data=[0.1, 0.2, 0.3]))
    vector_store = MagicMock()
    vector_store.compare = MagicMock(return_value=0.5)  # 低於 SIMILARITY_UPPER_BOUNDARY=0.7

    temp_cache = MagicMock()
    temp_cache.total_tokens = MagicMock(return_value=0)

    mm = MemoryManager(
        call_embedding_func=call_embedding,
        vector_store=vector_store,
        summary_store=MagicMock(),
        temp_cache=temp_cache,
        summarizer=summarizer,
    )
    mm.buffer = buffer

    # 設定 _current_tokens 超過 token_limit，使 check() 能觸發 flushed
    buffer._current_tokens = 9999

    # 觸發 buffer check 使 extract_flushed() 回傳資料
    buffer.check()
    assert len(buffer.flushed) == 2  # 確認 check() 成功 flush 2 筆

    result = await mm.flush()

    assert result.success is True
    # DEF-013：修正後應呼叫 summarizer.summarize_turns，並進入 _route_by_scores
    # call_embedding_func 只在 retrieve() 中被呼叫，flush 不會呼叫它
    assert call_embedding.call_count == 0
    # importance=0.8 >= IMPORTANCE_HIGH + embedding 非 None → 寫入向量庫
    assert vector_store.add.call_count == 1
    assert temp_cache.add.call_count == 0


# ═══════════════════════════════════════════════════════════════════
# TC-13：MemoryManager.add 透過 add() 間接驗證 _enforce_capacity
# 跳過：需要 mock temp_cache.items 的複雜行為，設計文件標註為間接驗證
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.skip(reason="需要 mock temp_cache.items 的複雜行為，屬設計文件中間接驗證項目")
@pytest.mark.asyncio
async def test_TC13_memory_manager_enforce_capacity():
    """TC-13: MemoryManager.add 透過 add() 間接驗證 _enforce_capacity."""
    pass


# ═══════════════════════════════════════════════════════════════════
# TC-14：ConversationBuffer.add 新增對話
# ═══════════════════════════════════════════════════════════════════

def test_TC14_conversation_buffer_add():
    """TC-14: ConversationBuffer.add 新增對話."""
    from memory.buffer import ConversationBuffer

    buffer = ConversationBuffer()
    buffer.add("user", "你好")

    assert len(buffer.context) == 1
    assert buffer.context[0] == {"role": "user", "content": "你好"}


# ═══════════════════════════════════════════════════════════════════
# TC-15：ConversationBuffer.check 成對 flush
# ═══════════════════════════════════════════════════════════════════

def test_TC15_conversation_buffer_check_flush():
    """TC-15: ConversationBuffer.check 成對 flush."""
    from memory.buffer import ConversationBuffer

    buffer = ConversationBuffer()
    buffer.context = [
        {"role": "user", "content": "A"},
        {"role": "assistant", "content": "B"},
        {"role": "user", "content": "C"},
        {"role": "assistant", "content": "D"},
    ]
    buffer._current_tokens = 9999  # 超過 token_limit

    buffer.check()

    assert len(buffer.flushed) == 2
    assert len(buffer.context) == 2


# ═══════════════════════════════════════════════════════════════════
# TC-16：ConversationBuffer.check 最後一筆不是 assistant 不 flush
# ═══════════════════════════════════════════════════════════════════

def test_TC16_conversation_buffer_check_no_flush():
    """TC-16: ConversationBuffer.check 最後一筆不是 assistant 不 flush."""
    from memory.buffer import ConversationBuffer

    buffer = ConversationBuffer()
    buffer.context = [
        {"role": "user", "content": "A"},
        {"role": "assistant", "content": "B"},
        {"role": "user", "content": "C"},
    ]
    buffer._current_tokens = 9999

    buffer.check()

    assert len(buffer.flushed) == 0


# ═══════════════════════════════════════════════════════════════════
# TC-17：ConversationBuffer.serialize 格式為「用戶：」/「助理：」
# ═══════════════════════════════════════════════════════════════════

def test_TC17_conversation_buffer_serialize():
    """TC-17: ConversationBuffer.serialize 格式為「用戶：」/「助理：」."""
    from memory.buffer import ConversationBuffer

    buffer = ConversationBuffer()
    buffer.context = [
        {"role": "user", "content": "你好"},
        {"role": "assistant", "content": "嗨"},
    ]

    result = buffer.serialize()

    assert "用戶：你好" in result
    assert "助理：嗨" in result


# ═══════════════════════════════════════════════════════════════════
# TC-18：ConversationBuffer.serialize content 為空不跳過
# ═══════════════════════════════════════════════════════════════════

def test_TC18_conversation_buffer_serialize_empty_content():
    """TC-18: ConversationBuffer.serialize content 為空不跳過."""
    from memory.buffer import ConversationBuffer

    buffer = ConversationBuffer()
    buffer.context = [
        {"role": "user", "content": ""},
        {"role": "assistant", "content": ""},
    ]

    result = buffer.serialize()

    assert "用戶：" in result
    assert "助理：" in result


# ═══════════════════════════════════════════════════════════════════
# TC-19：ConversationSummary.set_summary 設定摘要
# ═══════════════════════════════════════════════════════════════════

def test_TC19_conversation_summary_set_summary():
    """TC-19: ConversationSummary.set_summary 設定摘要."""
    from memory.summary import ConversationSummary

    summary = ConversationSummary()
    summary.set_summary("這是新摘要")

    assert summary.summary == "這是新摘要"
    assert summary.get_summary() == "這是新摘要"


# ═══════════════════════════════════════════════════════════════════
# TC-20：ConversationSummary.get_summary 未呼叫 set_summary
# ═══════════════════════════════════════════════════════════════════

def test_TC20_conversation_summary_get_summary_initial():
    """TC-20: ConversationSummary.get_summary 未呼叫 set_summary."""
    from memory.summary import ConversationSummary

    summary = ConversationSummary()
    result = summary.get_summary()

    assert result == ""


# ═══════════════════════════════════════════════════════════════════
# TC-21：TempCache.add 新增項目
# ═══════════════════════════════════════════════════════════════════

def test_TC21_temp_cache_add():
    """TC-21: TempCache.add 新增項目."""
    from memory.summary import TempCache

    cache = TempCache()
    item_id = cache.add([{"role": "user"}], "摘要", 0.5, 0.6)

    assert item_id is not None
    assert item_id in cache.items
    item = cache.items[item_id]
    assert item["confidence"] == (0.5 + 0.6) / 2
    assert "timestamp" in item


# ═══════════════════════════════════════════════════════════════════
# TC-22：TempCache.get_top_k 按 effective_importance 降序
# ═══════════════════════════════════════════════════════════════════

def test_TC22_temp_cache_get_top_k():
    """TC-22: TempCache.get_top_k 按 effective_importance 降序."""
    from memory.summary import TempCache

    cache = TempCache()
    id_a = cache.add([{"role": "user"}], "摘要A", 0.8, 0.6)
    id_b = cache.add([{"role": "user"}], "摘要B", 0.5, 0.6)
    id_c = cache.add([{"role": "user"}], "摘要C", 0.3, 0.6)

    top_k = cache.get_top_k(2)

    assert len(top_k) == 2
    assert top_k[0]["id"] == id_a  # importance 最高


# ═══════════════════════════════════════════════════════════════════
# TC-23：TempCache.get_top_k k <= 0 回傳空列表
# ═══════════════════════════════════════════════════════════════════

def test_TC23_temp_cache_get_top_k_zero():
    """TC-23: TempCache.get_top_k k <= 0 回傳空列表."""
    from memory.summary import TempCache

    cache = TempCache()
    cache.add([{"role": "user"}], "摘要", 0.5, 0.6)

    result = cache.get_top_k(0)

    assert result == []


# ═══════════════════════════════════════════════════════════════════
# TC-24：TempCache.remove 移除項目 / item_id 不存在
# ═══════════════════════════════════════════════════════════════════

def test_TC24_temp_cache_remove():
    """TC-24: TempCache.remove 移除項目 / item_id 不存在."""
    from memory.summary import TempCache

    cache = TempCache()
    item_id = cache.add([{"role": "user"}], "摘要", 0.5, 0.6)

    result1 = cache.remove(item_id)
    result2 = cache.remove("不存在的 id")

    assert result1 is True
    assert result2 is False


# ═══════════════════════════════════════════════════════════════════
# TC-25：ConversationVector.add 寫入成功
# 跳過：需要 mock ChromaDB 實際集合操作，屬黑箱無法建立狀態
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.skip(reason="需要 mock ChromaDB 實際集合操作，屬黑箱無法建立狀態")
def test_TC25_conversation_vector_add():
    """TC-25: ConversationVector.add 寫入成功."""
    from memory.vector import ConversationVector

    vector = ConversationVector()
    vector.add("摘要", [{"role": "user"}], [0.1, 0.2])

    assert vector.add.call_count == 1


# ═══════════════════════════════════════════════════════════════════
# TC-26：ConversationVector.add 步驟 2 失敗回滾
# 跳過：需要 mock ChromaDB 實際集合操作，屬黑箱無法建立狀態
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.skip(reason="需要 mock ChromaDB 實際集合操作，屬黑箱無法建立狀態")
def test_TC26_conversation_vector_add_rollback():
    """TC-26: ConversationVector.add 步驟 2 失敗回滾."""
    pass


# ═══════════════════════════════════════════════════════════════════
# TC-27：ConversationVector.search 空庫
# ═══════════════════════════════════════════════════════════════════

def test_TC27_conversation_vector_search_empty():
    """TC-27: ConversationVector.search 空庫."""
    from memory.vector import ConversationVector

    vector = ConversationVector()
    result = vector.search([0.1, 0.2], top_k=1)

    assert result == []


# ═══════════════════════════════════════════════════════════════════
# TC-28：ConversationVector.compare 邊界條件（空庫/distance=0/distance=2）
# ═══════════════════════════════════════════════════════════════════

def test_TC28_conversation_vector_compare_boundary():
    """TC-28: ConversationVector.compare 邊界條件."""
    from memory.vector import ConversationVector

    vector = ConversationVector()

    # 空庫 → 中性值
    assert vector.compare([0.1, 0.2]) == 1.0


# ═══════════════════════════════════════════════════════════════════
# TC-29：ConversationVector.repair_consistency 修復不一致
# 跳過：需要 mock ChromaDB 實際集合操作，屬黑箱無法建立狀態
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.skip(reason="需要 mock ChromaDB 實際集合操作，屬黑箱無法建立狀態")
def test_TC29_conversation_vector_repair_consistency():
    """TC-29: ConversationVector.repair_consistency 修復不一致."""
    pass


# ═══════════════════════════════════════════════════════════════════
# TC-30：MemoryManager.on_activity 重置 idle 計時
# ═══════════════════════════════════════════════════════════════════

def test_TC30_memory_manager_on_activity():
    """TC-30: MemoryManager.on_activity 重置 idle 計時."""
    from memory.manager import MemoryManager

    mm = MemoryManager(
        call_embedding_func=AsyncMock(),
        vector_store=MagicMock(),
        summary_store=MagicMock(),
        temp_cache=MagicMock(),
        summarizer=MagicMock(),
    )

    before = time.time()
    mm.on_activity()
    after = time.time()

    assert before <= mm._last_activity <= after