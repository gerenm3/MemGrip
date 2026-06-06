"""tests/L1/test_summary -- 11 筆測試."""

import unittest

import pytest


class TestConversationSummary:
    """ConversationSummary 測試 (1-3)."""

    def test_get_summary_returns_empty_by_default(self):
        from memory.summary import ConversationSummary

        cs = ConversationSummary()
        assert cs.get_summary() == ""

    def test_set_summary_and_get_summary(self):
        from memory.summary import ConversationSummary

        cs = ConversationSummary()
        cs.set_summary("hello world")
        assert cs.get_summary() == "hello world"

    def test_set_summary_overwrites_previous(self):
        from memory.summary import ConversationSummary

        cs = ConversationSummary()
        cs.set_summary("first")
        cs.set_summary("second")
        assert cs.get_summary() == "second"


class TestTempCache:
    """TempCache 測試 (4-11)."""

    def test_add_returns_string_id(self, temp_cache_instance):
        item_id = temp_cache_instance.add(raw_chunk=["a"], summary="test", similarity_score=0.5, importance_score=0.5)
        assert isinstance(item_id, str)

    def test_remove_existing_returns_true(self, temp_cache_instance):
        item_id = temp_cache_instance.add(raw_chunk=["a"], summary="test", similarity_score=0.5, importance_score=0.5)
        assert temp_cache_instance.remove(item_id) is True

    def test_remove_nonexistent_returns_false(self, temp_cache_instance):
        assert temp_cache_instance.remove("nonexistent_id") is False

    def test_count_returns_number_of_items(self, temp_cache_instance):
        temp_cache_instance.add(raw_chunk=["a"], summary="test", similarity_score=0.5, importance_score=0.5)
        temp_cache_instance.add(raw_chunk=["b"], summary="test2", similarity_score=0.6, importance_score=0.6)
        assert temp_cache_instance.count() == 2

    def test_total_tokens_returns_sum(self, temp_cache_instance, mock_estimate_tokens):
        temp_cache_instance.add(raw_chunk=["a"], summary="test", similarity_score=0.5, importance_score=0.5)
        temp_cache_instance.add(raw_chunk=["b"], summary="test2", similarity_score=0.6, importance_score=0.6)
        assert temp_cache_instance.total_tokens() == 20

    def test_clear_removes_all_items(self, temp_cache_instance):
        temp_cache_instance.add(raw_chunk=["a"], summary="test", similarity_score=0.5, importance_score=0.5)
        temp_cache_instance.clear()
        assert temp_cache_instance.count() == 0

    def test_get_top_k_returns_sorted_by_effective_importance(self, temp_cache_instance):
        temp_cache_instance.add(raw_chunk=["a"], summary="test", similarity_score=0.9, importance_score=0.9)
        temp_cache_instance.add(raw_chunk=["b"], summary="test2", similarity_score=0.1, importance_score=0.1)
        top = temp_cache_instance.get_top_k(1)
        assert top[0]["similarity_score"] == 0.9

    def test_enforce_capacity_evicts_lowest_effective(self, mock_temp_cache_config):
        """驗證超過容量時淘汰最低 effective_importance 的項目。
        
        關鍵：需 mock _effective_importance=0 讓 effective_importance < threshold(0.1)
        才能觸發淘汰。若不 mock，預設 effective_importance=0.5 >= 0.1，
        淘汰條件 break 不會執行，items 會一直累加超過 100。
        """
        from memory.summary import TempCache

        cache = TempCache()
        # Mock _effective_importance to return 0 so items get evicted
        with unittest.mock.patch.object(cache, '_effective_importance', return_value=0):
            for i in range(110):
                cache.add(raw_chunk=["a"], summary="test", similarity_score=0.5, importance_score=0.5)
            assert cache.count() <= 100

    def test_enforce_capacity_with_time_decay(self, mock_temp_cache_config):
        """驗證超過容量時時間衰減導致 effective_importance 降低而觸發淘汰。
        
        使用 time.time() side_effect：
        - 前 110 次呼叫（add() 設定 timestamp）：回傳 real_time
        - 後續呼叫（_effective_importance 計算 age）：回傳 real_time + 1e7（約 115 天後）
        
        age_hours = (real_time + 1e7 - real_time) / 3600 ≈ 2778 小時
        effective_importance = confidence * exp(-0.01 * 2778) ≈ 0（遠低於 threshold=0.05）
        """
        import time
        from memory.summary import TempCache

        real_time = time.time()
        cache = TempCache()
        # 前 110 次 add() 各呼叫 time.time() 一次（設定 timestamp）
        # 之後 _effective_importance 呼叫 time.time() 回傳 real_time + 1e7
        with unittest.mock.patch("memory.summary.time.time", side_effect=[real_time] * 110 + [real_time + 1e7] * 10000):
            for i in range(110):
                cache.add(raw_chunk=["a"], summary="test", similarity_score=0.5, importance_score=0.5)
            assert cache.count() <= 100
