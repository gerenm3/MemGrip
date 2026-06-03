"""v2 vector — 雙 collection 向量記憶體.

依據 §3.13 (Memory Layer) + §5.4 (摘要分流) 定義：
- ConversationVector：雙 collection 向量記憶體
- add() 原子寫入（summary 成功 → raw 失敗 → 回滾）（§3.13 保留）
- compare 公式 (1 - distance) / 2 + 0.5（§3.13 保留）
- repair_consistency 每 50 次成功 flush 觸發一次（§3.13 保留）
"""

import logging
import time
import uuid
from typing import Dict, List

import chromadb
import config

from core.health import log_action
from core.json_utils import parse_all_jsons, dump_json_str

logger = logging.getLogger(__name__)


class ConversationVector:
    """雙 collection 向量記憶體"""

    def __init__(self) -> None:
        self.client = chromadb.PersistentClient(path=config.CHROMA_DB_PATH)
        self.summary_collection = self.client.get_or_create_collection(
            name=config.COLLECTION_SUMMARY_NAME,
            metadata={"hnsw:space": "cosine"}
        )
        self.raw_collection = self.client.get_or_create_collection(
            name=config.COLLECTION_RAW_NAME,
            metadata={"hnsw:space": "cosine"}
        )

    def add(self, summary: str, raw: list, embedding: list) -> None:
        """原子性寫入：先 raw → 再 summary，失敗時回滾 raw。

        兩步都成功才算完成，任一失敗則拋出例外。
        """
        ids = str(uuid.uuid4())
        time_in = time.time_ns()

        # 步驟 1：寫入 raw_collection
        try:
            self.raw_collection.add(
                ids=[ids],
                documents=[dump_json_str(raw, ensure_ascii=False)],
                metadatas=[{"time": time_in}]
            )
        except Exception as e:
            logger.error("[ConversationVector] 步驟1寫入 raw_collection 失敗：%s", e, exc_info=True)
            raise

        try:
            # 步驟 2：寫入 summary_collection
            self.summary_collection.add(
                ids=[ids],
                documents=[summary],
                embeddings=embedding,
                metadatas=[{"time": time_in}]
            )
            log_action("vector", "write_success", "OK")
        except Exception as e:
            # 失敗 → 回滾步驟 1 已寫入的資料
            logger.warning("[ConversationVector] 步驟2寫入 summary_collection 失敗，執行回滾：%s", e)
            log_action("memory_vector", "summary_write_failed", "DEGRADED", str(e), "向量儲存失敗")
            try:
                self.raw_collection.delete(ids=[ids])
                logger.info("[ConversationVector] 回滾成功：已刪除 raw_collection 中 ID=%s 的資料", ids)
            except Exception as rollback_err:
                logger.error("[ConversationVector] 回滾失敗：%s", rollback_err, exc_info=True)
            raise

    def repair_consistency(self) -> Dict[str, int]:
        """檢查並修復兩組 collection 之間的不一致。

        回傳: {"summary_only": int, "raw_only": int, "cleaned": int}
        """
        result: Dict[str, int] = {"summary_only": 0, "raw_only": 0, "cleaned": 0}

        # 取 summary 所有 ID
        summary_ids = set()
        if self.summary_collection.count() > 0:
            try:
                summary_result = self.summary_collection.get(ids=None, include=[])
                summary_ids = set(summary_result["ids"])
            except Exception as e:
                logger.error("[ConversationVector] repair_consistency: 讀取 summary_collection ID 失敗：%s", e)
                log_action("memory_vector", "collection_read_failed", "DEGRADED",
                           "summary_collection read failed", "記憶體檢查失敗")
                return result

        # 取 raw 所有 ID
        raw_ids = set()
        if self.raw_collection.count() > 0:
            try:
                raw_result = self.raw_collection.get(ids=None, include=[])
                raw_ids = set(raw_result["ids"])
            except Exception as e:
                logger.error("[ConversationVector] repair_consistency: 讀取 raw_collection ID 失敗：%s", e)
                log_action("memory_vector", "collection_read_failed", "DEGRADED",
                           "raw_collection read failed", "記憶體檢查失敗")
                return result

        # 找出孤立資料
        summary_only = summary_ids - raw_ids
        raw_only = raw_ids - summary_ids

        result["summary_only"] = len(summary_only)
        result["raw_only"] = len(raw_only)

        # 刪除 summary_only 的孤立資料
        if summary_only:
            try:
                self.summary_collection.delete(ids=list(summary_only))
                result["cleaned"] += len(summary_only)
                logger.info("[ConversationVector] repair_consistency: 已刪除 %d 筆 summary-only 孤立資料", len(summary_only))
            except Exception as e:
                logger.error("[ConversationVector] repair_consistency: 刪除 summary_only 孤立資料失敗：%s", e)

        # 刪除 raw_only 的孤立資料
        if raw_only:
            try:
                self.raw_collection.delete(ids=list(raw_only))
                result["cleaned"] += len(raw_only)
                logger.info("[ConversationVector] repair_consistency: 已刪除 %d 筆 raw-only 孤立資料", len(raw_only))
            except Exception as e:
                logger.error("[ConversationVector] repair_consistency: 刪除 raw_only 孤立資料失敗：%s", e)

        if result["cleaned"] > 0:
            logger.info("[ConversationVector] repair_consistency: 本次共清理 %d 筆孤立資料", result["cleaned"])
            log_action("memory_vector", "repair_consistency", "DEGRADED",
                       f"cleaned={result['cleaned']}", "修復孤立資料")

        return result

    def compare(self, embedding: list) -> float:
        """計算 query embedding 與向量庫的相似度（0.0-1.0）。

        公式：將 chromadb cosine distance [0, 2] 映射回 [0, 1]。
        空庫回傳 1.0（中性，不拉低置信度）。
        """
        if self.summary_collection.count() == 0:
            return 1.0
        result = self.summary_collection.query(
            query_embeddings=embedding,
            n_results=1
        )
        distance = result['distances'][0][0]
        score = 1.0 - distance / 2
        return max(0.0, min(1.0, score))

    def search(self, embedding: list, top_k: int) -> list:
        """搜尋與 embedding 最相似的 top_k 筆 raw 資料。

        底層：先以 summary_collection 的 cosine distance 排序取得 top_k ID，
        再從 raw_collection 取出對應 documents，並透過 parse_all_jsons
        進行 JSON 反序列化。
        """
        if self.summary_collection.count() == 0:
            return []

        result = self.summary_collection.query(
            query_embeddings=embedding,
            n_results=top_k
        )
        ids = result['ids'][0]
        if not ids:
            return []

        # 過濾只取雙方 collection 都存在的 ID
        raw_result = self.raw_collection.get(ids=ids)
        fetched_ids = set(raw_result["ids"])
        valid_ids = [id for id in ids if id in fetched_ids]
        if not valid_ids:
            return []

        raw_result = self.raw_collection.get(ids=valid_ids)
        docs = raw_result["documents"]
        results: list = []

        for doc in docs:
            parsed = parse_all_jsons(doc)
            if parsed:
                results.extend(parsed)
            else:
                log_action("memory_vector", "search_json_parse_failed", "DEGRADED",
                           f"id={ids}", "JSON 解析失敗，該筆資料略過")
                logger.error("[ConversationVector] search: JSON 解析失敗 (id=%s): %s",
                             ids, doc[:100] if doc else "(empty)")

        return results
