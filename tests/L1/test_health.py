"""tests/L1/test_health.py — core/health.py 純邏輯測試（10 筆）."""

import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pytest
import unittest.mock


class TestLogAction:
    """log_action 測試."""

    def test_creates_file(self, tmp_path):
        """等價類：首次寫入建立檔案."""
        log_file = tmp_path / "health.jsonl"
        with unittest.mock.patch.object(__import__("config"), "HEALTH_LOG_PATH", str(log_file)), \
             unittest.mock.patch("core.health.config.HEALTH_LOG_PATH", str(log_file)), \
             unittest.mock.patch("core.health.config.DEBUG_MODE", False):
            from core.health import log_action
            log_action("test", "test_action", "OK")
        assert log_file.exists()

    def test_appends(self, tmp_path):
        """等價類：多次寫入追加."""
        log_file = tmp_path / "health.jsonl"
        with unittest.mock.patch("core.health.config.HEALTH_LOG_PATH", str(log_file)), \
             unittest.mock.patch("core.health.config.DEBUG_MODE", False):
            from core.health import log_action
            log_action("test", "action1", "OK")
            log_action("test", "action2", "DEGRADED")
        lines = log_file.read_text().strip().split("\n")
        assert len(lines) == 2

    def test_json_format(self, tmp_path):
        """等價類：JSON 格式正確."""
        log_file = tmp_path / "health.jsonl"
        with unittest.mock.patch("core.health.config.HEALTH_LOG_PATH", str(log_file)), \
             unittest.mock.patch("core.health.config.DEBUG_MODE", False):
            from core.health import log_action
            log_action("test", "action", "OK", "detail", "user msg")
        line = log_file.read_text().strip().split("\n")[0]
        data = json.loads(line)
        assert "timestamp" in data
        assert data["module"] == "test"
        assert data["action"] == "action"
        assert data["status"] == "OK"
        assert data["detail"] == "detail"
        assert data["user_message"] == "user msg"

    def test_all_fields(self, tmp_path):
        """等價類：所有欄位正確寫入."""
        log_file = tmp_path / "health.jsonl"
        with unittest.mock.patch("core.health.config.HEALTH_LOG_PATH", str(log_file)), \
             unittest.mock.patch("core.health.config.DEBUG_MODE", False):
            from core.health import log_action
            log_action("mod", "act", "FAILED", "d", "u")
        line = log_file.read_text().strip().split("\n")[0]
        data = json.loads(line)
        assert data["module"] == "mod"
        assert data["action"] == "act"
        assert data["status"] == "FAILED"

    def test_empty_details(self, tmp_path):
        """邊界：空 details."""
        log_file = tmp_path / "health.jsonl"
        with unittest.mock.patch("core.health.config.HEALTH_LOG_PATH", str(log_file)), \
             unittest.mock.patch("core.health.config.DEBUG_MODE", False):
            from core.health import log_action
            log_action("test", "action", "OK")
        line = log_file.read_text().strip().split("\n")[0]
        data = json.loads(line)
        assert data["detail"] == ""

    def test_empty_session_id(self, tmp_path):
        """邊界：空 session_id → None."""
        log_file = tmp_path / "health.jsonl"
        with unittest.mock.patch("core.health.config.HEALTH_LOG_PATH", str(log_file)), \
             unittest.mock.patch("core.health.config.DEBUG_MODE", False):
            from core.health import log_action, set_session_id
            set_session_id(None)
            log_action("test", "action", "OK")
        line = log_file.read_text().strip().split("\n")[0]
        data = json.loads(line)
        assert data["session_id"] is None

    def test_multiple_actions(self, tmp_path):
        """等價類：多次 action 不覆蓋."""
        log_file = tmp_path / "health.jsonl"
        with unittest.mock.patch("core.health.config.HEALTH_LOG_PATH", str(log_file)), \
             unittest.mock.patch("core.health.config.DEBUG_MODE", False):
            from core.health import log_action
            for i in range(5):
                log_action("test", f"action{i}", "OK")
        lines = log_file.read_text().strip().split("\n")
        assert len(lines) == 5

    def test_unicode(self, tmp_path):
        """等價類：Unicode 內容正確."""
        log_file = tmp_path / "health.jsonl"
        with unittest.mock.patch("core.health.config.HEALTH_LOG_PATH", str(log_file)), \
             unittest.mock.patch("core.health.config.DEBUG_MODE", False):
            from core.health import log_action
            log_action("test", "測試", "OK", "詳細", "使用者")
        line = log_file.read_text().strip().split("\n")[0]
        data = json.loads(line)
        assert data["action"] == "測試"
        assert data["detail"] == "詳細"


class TestGetUserWarnings:
    """get_user_warnings 測試."""

    def test_no_warnings(self):
        """邊界：無警告 → []."""
        from core.health import get_user_warnings
        result = get_user_warnings(None)
        assert result == []

    def test_add_and_get_warnings(self):
        """等價類：DEGRADED/FAILED + user_message → 警告被記錄."""
        from core.health import log_action, get_user_warnings, set_session_id
        set_session_id("s1")
        log_action("test", "action", "DEGRADED", "d", "warning msg")
        warnings = get_user_warnings("s1")
        assert "warning msg" in warnings
        # 警告應被清除
        warnings2 = get_user_warnings("s1")
        assert warnings2 == []
