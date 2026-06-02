"""signal_collector — 收集任務執行指標並寫入 signal_log.jsonl.

符合 logging 規範
"""

import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

import config
from skills.skill_manager import SkillManager
from skills.trace_reader import build_execution_record

logger = logging.getLogger(__name__)

_signal_manager = SkillManager()


def collect(session_id: str, task_type: str, task_record: dict | None = None) -> dict | None:
    """從 task_record 收集指標，寫入 signal_log.jsonl.

    若提供 task_record（來自 LVS process），直接使用其指標，
    避免讀取尚未寫入的 task_trace.jsonl。

    Args:
        session_id: 任務 session ID
        task_type: 任務類型
        task_record: 可選的 task record dict（包含聚合指標）

    Returns:
        寫入的 signal dict，若無資料則回傳 None
    """
    # 優先使用傳入的 task_record；若無則從 trace_reader 讀取
    if task_record:
        execution_data = task_record
    else:
        execution_data = build_execution_record(session_id)
        if execution_data is None:
            logger.warning("[signal_collector] 找不到 session %s 的執行記錄", session_id)
            return None

    # 取得當前 skill_version
    skill_version = _signal_manager.get_version(task_type, "l1")

    signal = {
        "session_id": session_id,
        "task_type": task_type,
        "skill_version": skill_version,
        "ts": datetime.now(timezone(timedelta(hours=8))).isoformat(),
        # 聚合指標
        "unit_count": execution_data.get("unit_count", 0),
        "replan_count": execution_data.get("replan_count", 0),
        "failed_units": execution_data.get("failed_units", 0),
        "avg_loop_count": execution_data.get("avg_loop_count", 0),
        "constraint_satisfied_ratio": execution_data.get("constraint_satisfied_ratio", 1.0),
        "verifier_pass_ratio": execution_data.get("verifier_pass_ratio", 1.0),
    }

    signal_path = Path(config.SIGNAL_LOG_PATH)
    try:
        signal_path.parent.mkdir(parents=True, exist_ok=True)
        with open(signal_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(signal, ensure_ascii=False) + "\n")
        logger.info("[signal_collector] 寫入 signal_log: session=%s, version=%d", session_id, skill_version)
    except Exception as e:
        logger.error("[signal_collector] 寫入 signal_log.jsonl 失敗: %s", e, exc_info=True)

    return signal