"""v2 health — 系統健康狀態追蹤.

依據 §2.5 (HealthState) + §4.3 (Logging) 定義：
- 全局設施（原則 24），所有模組可直接呼叫
- 雙通道：log_action → append 檔案 + 記憶體 pending_warnings
- Status 三級：OK / DEGRADED / FAILED
- 本地 log 寫入不算 I/O（原則 6）
"""

import json
import logging
import time
from contextvars import ContextVar
from pathlib import Path
from typing import List, Optional

import config as config

logger = logging.getLogger(__name__)

_session_id_var: ContextVar[Optional[str]] = ContextVar('health_session_id', default=None)
_pending_warnings: dict[Optional[str], List[str]] = {}


def set_session_id(session_id: Optional[str]) -> None:
    """設定當前 session_id"""
    _session_id_var.set(session_id)


def log_action(module: str, action: str, status: str, detail: str = "", user_message: str = "") -> None:
    """記錄健康狀態到 health.jsonl（持久化）同時更新記憶體待通知清單。

    Args:
        module: 模組名稱
        action: 動作描述
        status: OK / DEGRADED / FAILED
        detail: 技術細節
        user_message: 使用者提示訊息
    """
    entry = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "session_id": _session_id_var.get(),
        "module": module,
        "action": action,
        "status": status,
        "detail": detail,
        "user_message": user_message,
    }

    log_path = Path(config.HEALTH_LOG_PATH)
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.error("[health] 寫入 health.jsonl 失敗: %s", e, exc_info=True)

    # Debug mode: print to stdout
    if config.DEBUG_MODE:
        print(f"[{module}] {action} | {status} | {detail or ''}")

    if status in ("DEGRADED", "FAILED") and user_message:
        _pending_warnings.setdefault(_session_id_var.get(), []).append(user_message)


def get_user_warnings(session_id: Optional[str]) -> List[str]:
    """取得並清除指定 session 的待通知警告。"""
    return _pending_warnings.pop(session_id, [])
