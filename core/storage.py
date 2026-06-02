"""v2 storage — 會話級 Unit 與 Step 的執行狀態持久化.

依據 §3.14 (Storage) 定義：
- 不直接供業務模組存取（原則 23）
- 會話級隔離
- 本地持久化（原則 6）
"""

import json
import logging
import threading
from pathlib import Path
from typing import Dict, List, Optional

from models.blueprints import UnitResult, StepResult

logger = logging.getLogger(__name__)

_STORAGE_DIR = Path("storage")


class UnitStore:
    """Unit 層級存放"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # session_id -> { unit_id -> UnitResult }
        self._store: Dict[str, Dict[str, UnitResult]] = {}

    def save_unit(self, session_id: str, unit_id: str, unit_result: UnitResult) -> None:
        with self._lock:
            self._store.setdefault(session_id, {})[unit_id] = unit_result
        self._flush_session(session_id)

    def get_unit(self, session_id: str, unit_id: str) -> Optional[UnitResult]:
        with self._lock:
            return self._store.get(session_id, {}).get(unit_id)

    def get_all_units(self, session_id: str) -> List[UnitResult]:
        with self._lock:
            units = self._store.get(session_id, {})
            return list(units.values())

    def _flush_session(self, session_id: str) -> None:
        """將 session 的 Unit 資料寫入本地檔案。"""
        try:
            _STORAGE_DIR.mkdir(parents=True, exist_ok=True)
            with self._lock:
                units = self._store.get(session_id, {})
            path = _STORAGE_DIR / f"units_{session_id}.json"
            serialized = {
                uid: {
                    "unit_id": u.unit_id,
                    "status": u.status.value,
                    "output": u.output,
                    "error": u.error,
                    "replan_count": u.replan_count,
                    "total_loop_count": u.total_loop_count,
                    "step_loop_counts": u.step_loop_counts,
                }
                for uid, u in units.items()
            }
            with open(path, "w", encoding="utf-8") as f:
                json.dump(serialized, f, ensure_ascii=False)
        except Exception as e:
            logger.error("[UnitStore] flush 失敗: %s", e, exc_info=True)


class StepStore:
    """Step 層級存放"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # session_id -> { step_id -> StepResult }
        self._store: Dict[str, Dict[str, StepResult]] = {}
        # session_id -> { unit_id -> [step_id, ...] }
        self._unit_steps: Dict[str, Dict[str, List[str]]] = {}

    def save_step(self, session_id: str, unit_id: str, step_id: str, step_result: StepResult) -> None:
        with self._lock:
            self._store.setdefault(session_id, {})[step_id] = step_result
            self._unit_steps.setdefault(session_id, {}).setdefault(unit_id, []).append(step_id)
        self._flush_session(session_id)

    def get_step(self, session_id: str, step_id: str) -> Optional[StepResult]:
        with self._lock:
            return self._store.get(session_id, {}).get(step_id)

    def get_steps_by_unit(self, session_id: str, unit_id: str) -> List[StepResult]:
        with self._lock:
            step_ids = self._unit_steps.get(session_id, {}).get(unit_id, [])
            steps_dict = self._store.get(session_id, {})
            return [steps_dict[sid] for sid in step_ids if sid in steps_dict]

    def clear_unit_steps(self, session_id: str, unit_id: str) -> None:
        """清空指定 unit 的所有 step 資料"""
        with self._lock:
            step_ids = self._unit_steps.get(session_id, {}).get(unit_id, [])
            store = self._store.get(session_id, {})
            for sid in step_ids:
                store.pop(sid, None)
            self._unit_steps.get(session_id, {}).pop(unit_id, None)

    def _flush_session(self, session_id: str) -> None:
        """將 session 的 Step 資料寫入本地檔案。"""
        try:
            _STORAGE_DIR.mkdir(parents=True, exist_ok=True)
            with self._lock:
                steps = self._store.get(session_id, {})
            path = _STORAGE_DIR / f"steps_{session_id}.json"
            serialized = {
                sid: {
                    "step_id": s.step_id,
                    "status": s.status.value,
                    "output": s.output,
                    "error": s.error,
                    "loop_count": s.loop_count,
                }
                for sid, s in steps.items()
            }
            with open(path, "w", encoding="utf-8") as f:
                json.dump(serialized, f, ensure_ascii=False)
        except Exception as e:
            logger.error("[StepStore] flush 失敗: %s", e, exc_info=True)
