"""tests/L1/test_vector -- 10 筆測試."""

import unittest

import pytest


class TestCompare:
    """ConversationVector.compare 測試 (1-4)."""

    def test_compare_empty_collection_returns_1_0(self, vector_instance):
        vector_instance.summary_collection.count = unittest.mock.MagicMock(return_value=0)
        score = vector_instance.compare([0.1, 0.2, 0.3])
        assert score == 1.0

    def test_compare_distance_0_returns_1_0(self, vector_instance):
        vector_instance.summary_collection.count = unittest.mock.MagicMock(return_value=1)
        vector_instance.summary_collection.query = unittest.mock.MagicMock(
            return_value={"distances": [[0.0]]}
        )
        score = vector_instance.compare([0.1, 0.2, 0.3])
        assert score == 1.0

    def test_compare_distance_2_returns_0_0(self, vector_instance):
        vector_instance.summary_collection.count = unittest.mock.MagicMock(return_value=1)
        vector_instance.summary_collection.query = unittest.mock.MagicMock(
            return_value={"distances": [[2.0]]}
        )
        score = vector_instance.compare([0.1, 0.2, 0.3])
        assert score == 0.0

    def test_compare_distance_1_returns_0_5(self, vector_instance):
        vector_instance.summary_collection.count = unittest.mock.MagicMock(return_value=1)
        vector_instance.summary_collection.query = unittest.mock.MagicMock(
            return_value={"distances": [[1.0]]}
        )
        score = vector_instance.compare([0.1, 0.2, 0.3])
        assert score == 0.5

    def test_compare_cosine_distance_formula(self, vector_instance):
        """驗證 compare 公式為 score = 1.0 - distance / 2。
        
        源碼：memory/vector.py 第 158 行
        score = 1.0 - distance / COSINE_DISTANCE_DIVISOR  # COSINE_DISTANCE_DIVISOR = 2
        
        驗證多個距離值：
        - distance=0.0 → score = 1.0 - 0/2 = 1.0
        - distance=0.5 → score = 1.0 - 0.5/2 = 0.75
        - distance=1.0 → score = 1.0 - 1/2 = 0.5
        - distance=1.5 → score = 1.0 - 1.5/2 = 0.25
        - distance=2.0 → score = 1.0 - 2/2 = 0.0
        """
        vector_instance.summary_collection.count = unittest.mock.MagicMock(return_value=1)
        for distance, expected in [(0.0, 1.0), (0.5, 0.75), (1.0, 0.5), (1.5, 0.25), (2.0, 0.0)]:
            vector_instance.summary_collection.query = unittest.mock.MagicMock(
                return_value={"distances": [[distance]]}
            )
            score = vector_instance.compare([0.1, 0.2, 0.3])
            assert score == expected


class TestSearch:
    """ConversationVector.search 測試 (5-7)."""

    def test_search_empty_collection_returns_empty(self, vector_instance):
        vector_instance.summary_collection.count = unittest.mock.MagicMock(return_value=0)
        results = vector_instance.search([0.1, 0.2, 0.3], top_k=5)
        assert results == []

    def test_search_returns_parsed_json(self, vector_instance):
        vector_instance.summary_collection.count = unittest.mock.MagicMock(return_value=1)
        vector_instance.summary_collection.query = unittest.mock.MagicMock(
            return_value={"ids": [["id1"]], "distances": [[0.5]]}
        )
        vector_instance.raw_collection.get = unittest.mock.MagicMock(
            return_value={"ids": ["id1"], "documents": ['[{"key": "val"}]']}
        )
        results = vector_instance.search([0.1, 0.2, 0.3], top_k=5)
        assert len(results) == 1
        assert results[0] == [{"key": "val"}]

    def test_search_no_valid_ids_returns_empty(self, vector_instance):
        vector_instance.summary_collection.count = unittest.mock.MagicMock(return_value=1)
        vector_instance.summary_collection.query = unittest.mock.MagicMock(
            return_value={"ids": [["id1"]], "distances": [[0.5]]}
        )
        vector_instance.raw_collection.get = unittest.mock.MagicMock(
            return_value={"ids": [], "documents": []}
        )
        results = vector_instance.search([0.1, 0.2, 0.3], top_k=5)
        assert results == []


class TestRepairConsistency:
    """ConversationVector.repair_consistency 測試 (8-10)."""

    def test_repair_consistency_no_discrepancy(self, vector_instance):
        summary_mock = unittest.mock.MagicMock()
        summary_mock.count = unittest.mock.MagicMock(return_value=1)
        summary_mock.get = unittest.mock.MagicMock(return_value={"ids": ["id1"]})

        raw_mock = unittest.mock.MagicMock()
        raw_mock.count = unittest.mock.MagicMock(return_value=1)
        raw_mock.get = unittest.mock.MagicMock(return_value={"ids": ["id1"]})

        vector_instance.summary_collection = summary_mock
        vector_instance.raw_collection = raw_mock

        result = vector_instance.repair_consistency()
        assert result == {"summary_only": 0, "raw_only": 0, "cleaned": 0}

    def test_repair_consistency_summary_only_deleted(self, vector_instance):
        summary_mock = unittest.mock.MagicMock()
        summary_mock.count = unittest.mock.MagicMock(return_value=1)
        summary_mock.get = unittest.mock.MagicMock(return_value={"ids": ["id1"]})

        raw_mock = unittest.mock.MagicMock()
        raw_mock.count = unittest.mock.MagicMock(return_value=1)
        raw_mock.get = unittest.mock.MagicMock(return_value={"ids": []})

        vector_instance.summary_collection = summary_mock
        vector_instance.raw_collection = raw_mock

        result = vector_instance.repair_consistency()
        assert result["summary_only"] == 1
        assert result["cleaned"] == 1

    def test_repair_consistency_raw_only_deleted(self, vector_instance):
        summary_mock = unittest.mock.MagicMock()
        summary_mock.count = unittest.mock.MagicMock(return_value=1)
        summary_mock.get = unittest.mock.MagicMock(return_value={"ids": []})

        raw_mock = unittest.mock.MagicMock()
        raw_mock.count = unittest.mock.MagicMock(return_value=1)
        raw_mock.get = unittest.mock.MagicMock(return_value={"ids": ["id1"]})

        vector_instance.summary_collection = summary_mock
        vector_instance.raw_collection = raw_mock

        result = vector_instance.repair_consistency()
        assert result["raw_only"] == 1
        assert result["cleaned"] == 1
