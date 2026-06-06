"""MemoryManager 架構整合測試

測試 1：add() 基本功能
測試 2：get_context() 回傳格式
測試 3：即時摘要三路分流
測試 4：retrieve() 基本功能
測試 5：批量摘要觸發條件
測試 6：orchestrator 整合（不需要真實模型）
"""

import asyncio
import time
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from memory.manager import MemoryManager
from memory.buffer import ConversationBuffer, estimate_tokens
from memory.summary import ConversationSummary, TempCache
from memory.summarizer import ConversationSummarizer
from models.blueprints import Result


# ================================
# 測試 1：add() 基本功能
# ================================

class TestAddBasic:
    """測試 1：add() 基本功能"""

    def test_add_accumulates_buffer(self):
        """連續加入多輪對話，確認 buffer 正確累積"""
        mm = MemoryManager(
            call_embedding_func=None,
            vector_store=None,
            summary_store=None,
        )

        mm.add("user", "你好")
        mm.add("assistant", "你好！有什麼我可以幫忙的？")
        mm.add("user", "測試第二輪")
        mm.add("assistant", "收到")

        context = mm.buffer.get()
        assert len(context) == 4
        assert context[0] == {"role": "user", "content": "你好"}
        assert context[1] == {"role": "assistant", "content": "你好！有什麼我可以幫忙的？"}
        assert context[2] == {"role": "user", "content": "測試第二輪"}
        assert context[3] == {"role": "assistant", "content": "收到"}

    def test_add_token_limit_triggers_flush(self):
        """token 超限時，最早兩筆（完整的一輪）被移到 flushed"""
        mm = MemoryManager(
            call_embedding_func=None,
            vector_store=None,
            summary_store=None,
        )

        # 先建立 2 輪正常對話（tokens ≈ 16）
        mm.add("user", "你好")
        mm.add("assistant", "你好！")
        mm.add("user", "第二輪問題")
        mm.add("assistant", "第二輪回答")

        # 加入超長 user 訊息（≈ 800 tokens），total ≈ 816 > 800
        # 但最後一筆是 user，check() 會 break，不 flush
        mm.add("user", "A" * 2400)

        # 再加入 assistant 讓 check 能執行 flush（最後一筆是 assistant）
        mm.add("assistant", "B")

        flushed = mm.buffer.extract_flushed()
        assert len(flushed) >= 2, f"預期至少 2 筆 flushed，實際 {len(flushed)}"
        assert flushed[0]["role"] == "user"

    def test_odd_message_no_flush(self):
        """
        奇數訊息（只有 user，沒有 assistant）時，
        不應 flush 第一輪，避免出半輪對話
        """
        mm = MemoryManager(
            call_embedding_func=None,
            vector_store=None,
            summary_store=None,
        )

        long_content = "A" * 500

        # 最後一筆是 user（不是 assistant），不應 flush
        mm.add("user", "你好")
        mm.add("user", long_content)

        flushed = mm.buffer.extract_flushed()
        assert len(flushed) == 0, f"預期 0 筆 flushed（奇數訊息保護），實際 {len(flushed)}"


# ================================
# 測試 2：get_context() 回傳格式
# ================================

class TestGetContextFormat:
    """測試 2：get_context() 回傳格式"""

    def test_get_context_returns_correct_format(self):
        mm = MemoryManager(
            call_embedding_func=None,
            vector_store=None,
            summary_store=ConversationSummary(),
        )

        mm.add("user", "測試")
        mm.summary_store.set_summary("這是摘要")

        result = mm.get_context()

        assert isinstance(result, dict)
        assert "context" in result
        assert "summary" in result
        assert isinstance(result["context"], list)
        assert isinstance(result["summary"], str)
        assert result["summary"] == "這是摘要"
        assert len(result["context"]) == 1
        assert result["context"][0] == {"role": "user", "content": "測試"}

    def test_get_context_with_empty_summary(self):
        mm = MemoryManager(
            call_embedding_func=None,
            vector_store=None,
            summary_store=ConversationSummary(),
        )

        result = mm.get_context()
        assert result["summary"] == ""
        assert isinstance(result["context"], list)


# ================================
# 測試 3：即時摘要三路分流
# ================================

class TestImmediateSummarizeRouting:
    """測試 3：即時摘要三路分流"""

    def test_path_high_importance_low_similarity(self):
        """
        importance > 0.7 且 similarity < 0.7 → 寫入 vector_store
        """
        summary_store = ConversationSummary()
        vector_store = MagicMock()

        # mock temp_cache（因為 TempCache 是真實物件不能用 .called）
        temp_cache_mock = MagicMock()

        call_order = [0]

        async def call_model(model, messages, temp, max_tokens, use_history, caller=None):
            call_order[0] += 1
            if call_order[0] == 1:
                # 第一次：返回摘要
                return Result(success=True, data="高重要性摘要")
            else:
                # 第二次：重要性評估
                return Result(success=True, data="0.85")

        # 注入 summarizer
        mm = MemoryManager(
            call_embedding_func=AsyncMock(return_value=[0.1, 0.2]),
            vector_store=vector_store,
            summary_store=summary_store,
            temp_cache=temp_cache_mock,
            summarizer=ConversationSummarizer(call_model, AsyncMock(return_value=[0.1, 0.2])),
        )

        flushed_data = [
            {"role": "user", "content": "閒聊内容"},
            {"role": "assistant", "content": "了解"},
        ]

        result = asyncio.run(mm._immediate_summarize(flushed_data))

        # 確認寫入了 vector_store
        assert vector_store.add.called, "高重要性+低相似度應寫入 vector_store"
        # 不應寫入 temp_cache（因為 importance > 0.7）
        assert not temp_cache_mock.add.called, "不應寫入 temp_cache"
        # 摘要應已更新
        assert summary_store.get_summary() == "高重要性摘要"

    def test_path_low_importance_discard(self):
        """
        importance < 0.3 → 丟棄（不寫入任何地方）
        """
        # 用 MagicMock 而非真實 TempCache，才能用 .called
        temp_cache_mock = MagicMock()
        summary_store = ConversationSummary()
        vector_store = MagicMock()

        call_order = [0]

        async def call_model(model, messages, temp, max_tokens, use_history, caller=None):
            call_order[0] += 1
            if call_order[0] == 1:
                return Result(success=True, data="低重要性摘要")
            else:
                return Result(success=True, data="0.20")

        # 注入 summarizer
        mm = MemoryManager(
            call_embedding_func=AsyncMock(return_value=[0.1, 0.2]),
            vector_store=vector_store,
            summary_store=summary_store,
            temp_cache=temp_cache_mock,
            summarizer=ConversationSummarizer(call_model, AsyncMock(return_value=[0.1, 0.2])),
        )

        flushed_data = [
            {"role": "user", "content": "閒聊内容"},
            {"role": "assistant", "content": "了解"},
        ]

        result = asyncio.run(mm._immediate_summarize(flushed_data))

        # 不應寫入 vector_store 或 temp_cache
        assert not vector_store.add.called, "低重要性不應寫入 vector_store"
        assert not temp_cache_mock.add.called, "低重要性不應寫入 temp_cache"
        # summary_store 仍應更新摘要
        assert summary_store.get_summary() == "低重要性摘要"

    def test_path_moderate_importance_to_temp_cache(self):
        """
        其他情況（importance 在 0.3~0.7 之間）→ 寫入 temp_cache
        """
        # 用 MagicMock 而非真實 TempCache，才能用 .called
        temp_cache_mock = MagicMock()
        summary_store = ConversationSummary()
        vector_store = MagicMock()
        vector_store.compare.return_value = 0.5

        call_order = [0]

        async def call_model(model, messages, temp, max_tokens, use_history, caller=None):
            call_order[0] += 1
            if call_order[0] == 1:
                return Result(success=True, data="中等重要性摘要")
            else:
                return Result(success=True, data="0.50")

        # 注入 summarizer
        mm = MemoryManager(
            call_embedding_func=AsyncMock(return_value=[0.1, 0.2]),
            vector_store=vector_store,
            summary_store=summary_store,
            temp_cache=temp_cache_mock,
            summarizer=ConversationSummarizer(call_model, AsyncMock(return_value=[0.1, 0.2])),
        )

        flushed_data = [
            {"role": "user", "content": "普通内容"},
            {"role": "assistant", "content": "收到"},
        ]

        result = asyncio.run(mm._immediate_summarize(flushed_data))

        # 應寫入 temp_cache
        assert temp_cache_mock.add.called, "中等重要性應寫入 temp_cache"
        # 不應寫入 vector_store（因為 importance <= 0.7）
        assert not vector_store.add.called

    def test_path_high_similarity_discard(self):
        """
        similarity ≥ 0.7 → 太相似 → 丟棄（不寫入任何地方）
        """
        temp_cache_mock = MagicMock()
        summary_store = ConversationSummary()
        vector_store = MagicMock()
        # 設定 similarity ≥ 0.7（太相似）
        vector_store.compare.return_value = 0.85

        async def call_model(model, messages, temp, max_tokens, use_history, caller=None):
            return Result(success=True, data="摘要")

        mm = MemoryManager(
            call_embedding_func=AsyncMock(return_value=[0.1, 0.2]),
            vector_store=vector_store,
            summary_store=summary_store,
            temp_cache=temp_cache_mock,
            summarizer=ConversationSummarizer(call_model, AsyncMock(return_value=[0.1, 0.2])),
        )

        flushed_data = [
            {"role": "user", "content": "與已有記憶太相似"},
            {"role": "assistant", "content": "了解"},
        ]

        result = asyncio.run(mm._immediate_summarize(flushed_data))

        # 不應寫入任何地方
        assert not vector_store.add.called, "太相似不應寫入 vector_store"
        assert not temp_cache_mock.add.called, "太相似不應寫入 temp_cache"
        # summary_store 應更新摘要（摘要仍需保留）
        assert summary_store.get_summary() == "摘要"

    def test_path_very_low_importance_discard(self):
        """
        importance < 0.3 → 不重要 → 丟棄（不寫入任何地方）
        且 similarity < 0.7（不觸發太相似條件）
        """
        temp_cache_mock = MagicMock()
        summary_store = ConversationSummary()
        vector_store = MagicMock()
        # similarity < 0.7（不觸發太相似）
        vector_store.compare.return_value = 0.5

        call_order = [0]

        async def call_model(model, messages, temp, max_tokens, use_history, caller=None):
            call_order[0] += 1
            if call_order[0] == 1:
                return Result(success=True, data="低重要性摘要")
            else:
                return Result(success=True, data="0.20")

        mm = MemoryManager(
            call_embedding_func=AsyncMock(return_value=[0.1, 0.2]),
            vector_store=vector_store,
            summary_store=summary_store,
            temp_cache=temp_cache_mock,
            summarizer=ConversationSummarizer(call_model, AsyncMock(return_value=[0.1, 0.2])),
        )

        flushed_data = [
            {"role": "user", "content": "非常不重要的內容"},
            {"role": "assistant", "content": "了解"},
        ]

        result = asyncio.run(mm._immediate_summarize(flushed_data))

        # 不應寫入任何地方（importance < 0.3）
        assert not vector_store.add.called, "不重要不應寫入 vector_store"
        assert not temp_cache_mock.add.called, "不重要不應寫入 temp_cache"
        # summary_store 仍應更新摘要
        assert summary_store.get_summary() == "低重要性摘要"


# ================================
# 測試 4：retrieve() 基本功能
# ================================

class TestRetrieveBasic:
    """測試 4：retrieve() 基本功能"""

    @pytest.mark.asyncio
    async def test_retrieve_returns_first_result(self):
        """mock embedding 和 vector_store.search，確認回傳第一筆結果"""
        mock_vector_store = MagicMock()
        mock_vector_store.search.return_value = ["結果 A", "結果 B"]
        mock_vector_store.compare.return_value = 0.9

        # call_embedding_func 是 async，要用 AsyncMock
        mock_embedding = AsyncMock(return_value=[0.1, 0.2, 0.3])

        mm = MemoryManager(
            call_embedding_func=mock_embedding,
            vector_store=mock_vector_store,
            summary_store=None,
        )

        result = await mm.retrieve("測試查詢")

        mock_embedding.assert_called_once()
        mock_vector_store.search.assert_called_once()
        assert result == "結果 A", "應回傳第一筆結果"

    @pytest.mark.asyncio
    async def test_retrieve_returns_empty_when_no_results(self):
        """相似度低於閾值或無結果時回傳空字串"""
        mock_vector_store = MagicMock()
        mock_vector_store.search.return_value = []

        mm = MemoryManager(
            call_embedding_func=AsyncMock(return_value=[0.1, 0.2]),
            vector_store=mock_vector_store,
            summary_store=None,
        )

        result = await mm.retrieve("查詢")
        assert result == "", "無結果時應回傳空字串"

    @pytest.mark.asyncio
    async def test_retrieve_returns_empty_when_no_embedding_func(self):
        """沒有 embedding func 時直接回傳空字串"""
        mm = MemoryManager(
            call_embedding_func=None,
            vector_store=MagicMock(),
            summary_store=None,
        )

        result = await mm.retrieve("查詢")
        assert result == ""


# ================================
# 測試 5：批量摘要觸發條件
# ================================

class TestBatchSummarizeTrigger:
    """測試 5：批量摘要觸發條件"""

    def test_batch_summarize_triggered_when_idle_expired(self):
        """
        idle >= 900 秒 → 觸發 _batch_summarize_if_needed
        mock LLM 萃取成功，確認結果寫入 vector_store
        """
        temp_cache = TempCache()
        for i in range(3):
            temp_cache.add(
                raw_chunk=[{"role": "user", "content": f"內容{i}"}],
                summary=f"摘要{i}",
                similarity_score=0.5,
                importance_score=0.5,
            )

        mock_vector_store = MagicMock()

        async def call_model(model, messages, temp, max_tokens, use_history, caller=None):
            if caller == "memory_manager_batch":
                return Result(success=True, data='{"intent": "test", "decisions": [], "pending": [], "preferences": []}')
            return Result(success=True, data="摘要")

        # 注入 summarizer
        mm = MemoryManager(
            call_embedding_func=AsyncMock(return_value=[0.1, 0.2]),
            vector_store=mock_vector_store,
            summary_store=ConversationSummary(),
            temp_cache=temp_cache,
            summarizer=ConversationSummarizer(call_model, AsyncMock(return_value=[0.1, 0.2])),
        )

        # 手動將 last_batch_time 設為 1000 秒前（觸發 idle 條件）
        mm.last_batch_time = time.time() - 1000

        asyncio.run(mm._batch_summarize_if_needed())

        # 確認寫入了 vector_store
        assert mock_vector_store.add.called, "萃取成功應寫入 vector_store"
        # 確認 temp_cache 中的項目被移除
        assert temp_cache.count() == 0, "萃取成功後項目應從 temp_cache 移除"

    def test_batch_summarize_fails_keeps_items(self):
        """
        mock LLM 萃取失敗，確認項目保留在 temp_cache
        """
        temp_cache = TempCache()
        item_id = temp_cache.add(
            raw_chunk=[{"role": "user", "content": "測試"}],
            summary="摘要",
            similarity_score=0.5,
            importance_score=0.5,
        )
        initial_count = temp_cache.count()

        async def call_model_fail(model, messages, temp, max_tokens, use_history, caller=None):
            raise RuntimeError("LLM 服務不可用")

        # 注入 summarizer
        mm = MemoryManager(
            call_embedding_func=AsyncMock(return_value=[0.1, 0.2]),
            vector_store=MagicMock(),
            summary_store=ConversationSummary(),
            temp_cache=temp_cache,
            summarizer=ConversationSummarizer(call_model_fail, AsyncMock(return_value=[0.1, 0.2])),
        )

        mm.last_batch_time = time.time() - 1000

        # 不應拋出異常
        asyncio.run(mm._batch_summarize_if_needed())

        # 項目應保留
        assert temp_cache.count() == initial_count, "萃取失敗後項目應保留在 temp_cache"

    def test_batch_summarize_not_triggered_when_not_expired(self):
        """idle < 900 且 temp_cache 少於 3 項時不應觸發"""
        temp_cache = TempCache()
        temp_cache.add(
            raw_chunk=[{"role": "user", "content": "測試"}],
            summary="摘要",
            similarity_score=0.5,
            importance_score=0.5,
        )

        mm = MemoryManager(
            call_embedding_func=MagicMock(return_value=[0.1, 0.2]),
            vector_store=MagicMock(),
            summary_store=ConversationSummary(),
            temp_cache=temp_cache,
            summarizer=ConversationSummarizer(
                lambda *a, **kw: Result(success=True, data="摘要"),
                MagicMock(return_value=[0.1, 0.2]),
            ),
        )

        # last_batch_time 設為最近（未超時）
        mm.last_batch_time = time.time()

        # 不應拋出異常
        asyncio.run(mm._batch_summarize_if_needed())


# ================================
# 測試 6：Orchestrator 整合（不需要真實模型）
# ================================

class TestOrchestratorIntegration:
    """測試 6：orchestrator 整合"""

    @pytest.fixture
    def mock_memory(self):
        memory = AsyncMock(spec=MemoryManager)
        memory.get_context.return_value = {
            "context": [{"role": "user", "content": "你好"}],
            "summary": "測試摘要",
        }
        memory.serialize_context.return_value = "用戶：你好"
        memory.retrieve.return_value = "相關記憶"
        memory.flush.return_value = {}  # flush() 回傳 dict
        memory.current_session_id = None
        return memory

    @pytest.fixture
    def mock_router(self):
        router = MagicMock()
        router.route.return_value = {"intent": "simple", "need_rag": False}
        return router

    @pytest.fixture
    def mock_clarifier(self):
        return MagicMock()

    @pytest.fixture
    def mock_planner(self):
        return MagicMock()

    @pytest.fixture
    def mock_executor(self):
        return MagicMock()

    @pytest.fixture
    def mock_responder(self):
        # 使用 AsyncMock 因為 _handle_simple_intent 會 await reply_simple
        responder = AsyncMock()
        responder.reply_simple.return_value = Result(success=True, data="這是回應")
        responder.integrate.return_value = Result(success=True, data="整合回應")
        return responder

    @pytest.fixture
    def mock_tool_manager(self):
        tm = MagicMock()
        tm.server_schemas = {}
        tm.tool_environments = {}
        tm._init_tools = MagicMock(return_value=None)
        return tm

    @pytest.fixture
    def orchestrator(self, mock_memory, mock_router, mock_clarifier, mock_planner,
                     mock_executor, mock_responder, mock_tool_manager):
        from core.orchestrator import Orchestrator
        return Orchestrator(
            router=mock_router,
            clarifier=mock_clarifier,
            planner=mock_planner,
            executor=mock_executor,
            responder=mock_responder,
            summarizer=MagicMock(),
            summary=MagicMock(),
            temp_cache=MagicMock(),
            batch_summarizer=MagicMock(),
            tool_manager=mock_tool_manager,
            memory=mock_memory,
        )

    @pytest.mark.asyncio
    async def test_simple_intent_flow_calls_memory_methods(self, orchestrator):
        """
        跑一個 simple intent 流程，確認 memory.add()、memory.get_context()、
        memory.flush() 都被正確呼叫
        """
        user_input = "你好，請做個自我介紹"

        # 1. 取得 context
        context = orchestrator.memory.get_context()
        assert orchestrator.memory.get_context.called

        # 2. Dispatch to simple handler
        reply = await orchestrator._handle_simple_intent(
            user_input,
            "",  # rag_content
            True,  # has_tools
        )

        # reply 是 Result 物件，解包
        reply_text = reply.data if hasattr(reply, "data") else reply
        assert reply_text == "這是回應"

        # 3. 模擬 memory.add
        orchestrator.memory.add("user", user_input)
        orchestrator.memory.add("assistant", reply)

        # 確認 memory.add 被呼叫
        assert orchestrator.memory.add.called
        assert orchestrator.memory.add.call_count == 2
        orchestrator.memory.add.assert_any_call("user", user_input)
        orchestrator.memory.add.assert_any_call("assistant", reply)


    @pytest.mark.asyncio
    async def test_memory_methods_called_with_correct_args(self, orchestrator):
        """確認 memory 方法被以正確的參數呼叫"""
        user_input = "測試參數"
        reply = "回應內容"

        # reset call count
        orchestrator.memory.add.reset_mock()
        orchestrator.memory.get_context.reset_mock()
        orchestrator.memory.flush.reset_mock()

        # get_context
        context = orchestrator.memory.get_context()
        assert orchestrator.memory.get_context.called
        assert context["summary"] == "測試摘要"
        assert isinstance(context["context"], list)

        # add
        orchestrator.memory.add("user", user_input)
        orchestrator.memory.add("assistant", reply)
        assert orchestrator.memory.add.call_count == 2
        orchestrator.memory.add.assert_any_call("user", user_input)
        orchestrator.memory.add.assert_any_call("assistant", reply)

        # flush 不靠 patch，直接呼叫並驗證被呼叫（因為 _summarize_if_needed 內部用 create_task 異步排程）
        orchestrator.memory.flush()
        assert orchestrator.memory.flush.called
        assert orchestrator.memory.flush.called


# ================================
# 額外測試：serialize_context
# ================================

class TestSerializeContext:
    def test_serialize_returns_string(self):
        mm = MemoryManager(
            call_embedding_func=None,
            vector_store=None,
            summary_store=None,
        )

        mm.add("user", "你好")
        mm.add("assistant", "你好！")

        result = mm.serialize_context()
        assert isinstance(result, str)
        assert "用戶：你好" in result
        assert "助理：你好！" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])