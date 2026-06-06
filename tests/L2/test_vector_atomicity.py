"""atomicity: add() 雙重保護 + repair_consistency + flush 計數

測試：
1. add() 成功時兩邊都寫入
2. add() 步驟 2 失敗時 rollback raw
3. repair_consistency() 無孤立資料
4. repair_consistency() 修復 summary-only
5. repair_consistency() 修復 raw-only
6. repair_consistency() 兩邊都有孤立
7. flush 計數器觸發 repair_consistency
"""

import asyncio
import time
import json
import pytest
from unittest.mock import MagicMock, patch, AsyncMock

chromadb = pytest.importorskip("chromadb")


class TestAddAtomicity:
    """測試 add() 的原子性寫入"""

    def test_add_success_writes_both_collections(self):
        """add() 成功時 summary + raw 都有資料"""
        # 建立 mock vector store（模擬真實 ConversationVector 的 behavior）
        mock_summary = MagicMock()
        mock_raw = MagicMock()

        from memory.vector import ConversationVector
        original_init = ConversationVector.__init__

        def fake_init(self):
            self.summary_collection = mock_summary
            self.raw_collection = mock_raw
            mock_summary.count.return_value = 0
            mock_raw.count.return_value = 0

        with patch.object(ConversationVector, '__init__', fake_init):
            store = ConversationVector()
            store.add(
                summary="這是摘要",
                raw=[{"role": "user", "content": "測試"}],
                embedding=[0.1, 0.2, 0.3]
            )

        # 確認兩邊都被呼叫了 add
        assert mock_raw.add.called, "raw_collection.add 應被呼叫"
        assert mock_summary.add.called, "summary_collection.add 應被呼叫"

        # 確認 raw 的 documents 是 JSON 字串
        # call_args[0] = args tuple, call_args[0][0] = ids list, call_args[1]["documents"][0] = doc
        raw_doc = json.loads(mock_raw.add.call_args[1]["documents"][0])
        assert raw_doc == [{"role": "user", "content": "測試"}]

    def test_add_step2_failure_triggers_rollback(self):
        """步驟 2（summary）失敗 → 刪除 raw 中對應 ID"""
        from memory.vector import ConversationVector

        mock_summary = MagicMock()
        mock_raw = MagicMock()
        recorded_ids = []

        # 模擬 raw 成功寫入，summary 拋出例外
        def raw_add_side_effect(*args, **kwargs):
            if args:
                recorded_ids.extend(args[0])
            else:
                recorded_ids.extend(kwargs.get("ids", []))

        def summary_add_side_effect(ids=None, **kwargs):
            raise RuntimeError("summary 寫入失敗")

        mock_raw.add.side_effect = raw_add_side_effect
        mock_summary.add.side_effect = summary_add_side_effect

        with patch.object(ConversationVector, '__init__', lambda self: None):
            store = ConversationVector()
            store.summary_collection = mock_summary
            store.raw_collection = mock_raw

            with pytest.raises(RuntimeError, match="summary 寫入失敗"):
                store.add(
                    summary="這是摘要",
                    raw=[{"role": "user", "content": "測試"}],
                    embedding=[0.1, 0.2]
                )

        # raw.add 被呼叫
        assert mock_raw.add.called

        # rollback：raw.delete 被呼叫且 IDs 匹配 raw.add 的 IDs
        assert mock_raw.delete.called, "rollback 時應刪除 raw 中的資料"
        raw_delete_ids = mock_raw.delete.call_args[1]["ids"]
        assert set(recorded_ids) == set(raw_delete_ids), "rollback 應刪除與 add 相同的 ID"


class TestRepairConsistency:
    """測試 repair_consistency()"""

    def test_repair_no_isolated_data(self):
        """兩邊 ID 完全一致 → 無清理"""
        from memory.vector import ConversationVector

        mock_summary = MagicMock()
        mock_raw = MagicMock()
        mock_summary.count.return_value = 3
        mock_raw.count.return_value = 3
        mock_summary.get.return_value = {"ids": ["a", "b", "c"]}
        mock_raw.get.return_value = {"ids": ["a", "b", "c"]}

        with patch.object(ConversationVector, '__init__', lambda self: None):
            store = ConversationVector()
            store.summary_collection = mock_summary
            store.raw_collection = mock_raw

            result = store.repair_consistency()

        assert result == {"summary_only": 0, "raw_only": 0, "cleaned": 0}
        assert not mock_summary.delete.called
        assert not mock_raw.delete.called

    def test_repair_summary_only_isolated(self):
        """summary 有 raw 沒有 → 刪除 summary-only"""
        from memory.vector import ConversationVector

        mock_summary = MagicMock()
        mock_raw = MagicMock()
        mock_summary.count.return_value = 3
        mock_raw.count.return_value = 2
        mock_summary.get.return_value = {"ids": ["a", "b", "c"]}
        mock_raw.get.return_value = {"ids": ["a", "b"]}

        with patch.object(ConversationVector, '__init__', lambda self: None):
            store = ConversationVector()
            store.summary_collection = mock_summary
            store.raw_collection = mock_raw

            result = store.repair_consistency()

        assert result["summary_only"] == 1
        assert result["raw_only"] == 0
        assert result["cleaned"] == 1
        assert mock_summary.delete.call_count == 1
        assert not mock_raw.delete.called

    def test_repair_raw_only_isolated(self):
        """raw 有 summary 沒有 → 刪除 raw-only"""
        from memory.vector import ConversationVector

        mock_summary = MagicMock()
        mock_raw = MagicMock()
        mock_summary.count.return_value = 2
        mock_raw.count.return_value = 3
        mock_summary.get.return_value = {"ids": ["a", "b"]}
        mock_raw.get.return_value = {"ids": ["a", "b", "c"]}

        with patch.object(ConversationVector, '__init__', lambda self: None):
            store = ConversationVector()
            store.summary_collection = mock_summary
            store.raw_collection = mock_raw

            result = store.repair_consistency()

        assert result["summary_only"] == 0
        assert result["raw_only"] == 1
        assert result["cleaned"] == 1
        assert mock_raw.delete.call_count == 1
        assert not mock_summary.delete.called

    def test_repair_both_sides_isolated(self):
        """兩邊都有孤立 → 都刪除"""
        from memory.vector import ConversationVector

        mock_summary = MagicMock()
        mock_raw = MagicMock()
        mock_summary.count.return_value = 4
        mock_raw.count.return_value = 4
        mock_summary.get.return_value = {"ids": ["a", "b", "c", "d"]}
        mock_raw.get.return_value = {"ids": ["a", "b", "e", "f"]}

        with patch.object(ConversationVector, '__init__', lambda self: None):
            store = ConversationVector()
            store.summary_collection = mock_summary
            store.raw_collection = mock_raw

            result = store.repair_consistency()

        assert result["summary_only"] == 2  # c, d
        assert result["raw_only"] == 2      # e, f
        assert result["cleaned"] == 4

    def test_repair_empty_collections(self):
        """兩邊都為空 → 無錯"""
        from memory.vector import ConversationVector

        mock_summary = MagicMock()
        mock_raw = MagicMock()
        mock_summary.count.return_value = 0
        mock_raw.count.return_value = 0

        with patch.object(ConversationVector, '__init__', lambda self: None):
            store = ConversationVector()
            store.summary_collection = mock_summary
            store.raw_collection = mock_raw

            result = store.repair_consistency()

        assert result == {"summary_only": 0, "raw_only": 0, "cleaned": 0}


class TestFlushRepairTrigger:
    """測試 flush() 計數器觸發 repair_consistency"""

    def test_flush_triggers_repair_every_n_times(self):
        """每 N 次 flush 觸發一次 repair_consistency"""
        import config

        mm_mock_vector = MagicMock()
        mm_mock_vector.repair_consistency.return_value = {"summary_only": 0, "raw_only": 0, "cleaned": 0}

        mock_buffer = MagicMock()
        mock_buffer.storage.return_value = [{"role": "user", "content": "測試"}]

        mock_summary_store = MagicMock()

        from memory.manager import MemoryManager
        mm = MemoryManager(
            call_embedding_func=None,
            vector_store=mm_mock_vector,
            summary_store=mock_summary_store,
            temp_cache=MagicMock(),
        )
        mm.buffer = mock_buffer

        # mock 掉 _immediate_summarize（它會調 vector_store.add）
        mm._immediate_summarize = AsyncMock(return_value=None)

        # 設定 temp_cache 的 total_tokens 回傳 0，避免觸發 batch
        mm.temp_cache.total_tokens.return_value = 0
        # 設定 last_batch_time 為近期，避免 idle 條件
        mm.last_batch_time = time.time()

        interval = getattr(config, 'VECTOR_REPAIR_INTERVAL', 50)

        # 先調 (interval - 1) 次，不應觸發
        for _ in range(interval - 1):
            asyncio.run(mm.flush())

        # repair_consistency 不應被呼叫
        assert not mm_mock_vector.repair_consistency.called, \
            f"調用 {interval - 1} 次不應觸發 repair"

        # 再調 1 次（總共 interval 次）→ 應觸發
        asyncio.run(mm.flush())
        assert mm_mock_vector.repair_consistency.called, \
            f"第 {interval} 次 flush 應觸發 repair_consistency"

    def test_flush_reset_counter_after_trigger(self):
        """觸發後計數器歸零，再 N 次才觸發"""
        import config

        mm_mock_vector = MagicMock()
        mm_mock_vector.repair_consistency.return_value = {"cleaned": 0}

        mock_buffer = MagicMock()
        mock_buffer.storage.return_value = [{"role": "user", "content": "測試"}]

        mock_summary_store = MagicMock()

        from memory.manager import MemoryManager
        mm = MemoryManager(
            call_embedding_func=None,
            vector_store=mm_mock_vector,
            summary_store=mock_summary_store,
            temp_cache=MagicMock(),
        )
        mm.buffer = mock_buffer

        # mock 掉 _immediate_summarize
        mm._immediate_summarize = AsyncMock(return_value=None)

        # 設定 temp_cache 的 total_tokens 回傳 0，避免觸發 batch
        mm.temp_cache.total_tokens.return_value = 0
        # 設定 last_batch_time 為近期，避免 idle 條件
        mm.last_batch_time = time.time()

        interval = getattr(config, 'VECTOR_REPAIR_INTERVAL', 50)

        # 調 interval 次 → 第一次觸發
        for _ in range(interval):
            asyncio.run(mm.flush())

        assert mm_mock_vector.repair_consistency.call_count == 1

        # 再調 interval 次 → 第二次觸發
        for _ in range(interval):
            asyncio.run(mm.flush())

        assert mm_mock_vector.repair_consistency.call_count == 2


class TestCompareSearchUnchanged:
    """確認 compare() / search() 輸入輸出介面不變"""

    def test_compare_empty_returns_1(self):
        """空向量庫 → compare 回傳 1.0"""
        from memory.vector import ConversationVector

        mock_summary = MagicMock()
        mock_summary.count.return_value = 0

        with patch.object(ConversationVector, '__init__', lambda self: None):
            store = ConversationVector()
            store.summary_collection = mock_summary

            result = store.compare([0.1, 0.2])

        assert result == 1.0

    def test_compare_returns_clamped_value(self):
        """非空向量庫 → 回傳正常計算結果"""
        from memory.vector import ConversationVector

        mock_summary = MagicMock()
        mock_summary.count.return_value = 1
        mock_summary.query.return_value = {"distances": [[0.5]]}

        with patch.object(ConversationVector, '__init__', lambda self: None):
            store = ConversationVector()
            store.summary_collection = mock_summary

            result = store.compare([0.1, 0.2])

        # (1 - 0.5) / 2 + 0.5 = 0.75
        assert result == 0.75

    def test_search_empty_returns_empty_list(self):
        """空向量庫 → search 回傳 []"""
        from memory.vector import ConversationVector

        mock_summary = MagicMock()
        mock_summary.count.return_value = 0

        with patch.object(ConversationVector, '__init__', lambda self: None):
            store = ConversationVector()
            store.summary_collection = mock_summary

            result = store.search([0.1, 0.2], top_k=3)

        assert result == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])