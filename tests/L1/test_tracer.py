"""tests/L1/test_tracer — tracer 模組層級函數純邏輯測試（4 筆）."""

import hashlib
import json
import unittest.mock
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestMaskMessages:
    """測試 tracer._mask_messages 模組層級函數."""

    def test_mask_messages_normal(self):
        """等價類：正常 messages 不脫敏（非 system role 保持原樣）."""
        from core.tracer import _mask_messages
        messages = [
            {"role": "user", "content": "hello world"},
            {"role": "assistant", "content": "hi there"},
        ]
        result = _mask_messages(messages)
        assert len(result) == 2
        assert result[0]["role"] == "user"
        assert result[0]["content"] == "hello world"
        assert result[1]["role"] == "assistant"
        assert result[1]["content"] == "hi there"

    def test_mask_messages_system_masked(self):
        """等價類：system role 的內容被脫敏（前 100 字 + ... + MD5）."""
        from core.tracer import _mask_messages
        long_content = "A" * 200
        messages = [
            {"role": "system", "content": long_content},
        ]
        result = _mask_messages(messages)
        masked = result[0]["content"]
        md5_hash = hashlib.md5(long_content.encode("utf-8", errors="ignore")).hexdigest()
        # 源碼: content[:100] + "..." + md5 → 總長 = 100 + 3 + 32 = 135
        assert len(masked) == 100 + 3 + len(md5_hash)
        assert long_content[:100] in masked
        assert md5_hash in masked

    def test_mask_messages_empty_list(self):
        """邊界：空 list → []."""
        from core.tracer import _mask_messages
        result = _mask_messages([])
        assert result == []

    def test_mask_messages_none_content(self):
        """邊界：content 為 None → 不拋異常，使用空字串."""
        from core.tracer import _mask_messages
        messages = [
            {"role": "system", "content": None},
            {"role": "user", "content": "test"},
        ]
        result = _mask_messages(messages)
        assert len(result) == 2
        # content=None → content="" → 脫敏為 ".."+md5("")
        assert ".." in result[0]["content"]
        assert result[1]["content"] == "test"


class TestNewSession:
    """測試 new_session 函數."""

    def test_new_session_returns_uuid_format(self):
        """等價類：new_session 回傳 UUID 格式字串."""
        from core.tracer import new_session
        result = new_session()
        assert isinstance(result, str)
        assert len(result) == 36  # UUID format
        parts = result.split("-")
        assert len(parts) == 5  # UUID has 5 parts

    def test_new_session_sets_context_var(self):
        """等價類：new_session 設定 _session_id_var."""
        from core.tracer import new_session, _session_id_var
        session_id = new_session()
        assert _session_id_var.get() == session_id


class TestLogModelCall:
    """測試 log_model_call 函數."""

    def test_log_model_call_creates_file(self, tmp_path):
        """等價類：log_model_call 寫入 trace 檔案."""
        from core.tracer import new_session, log_model_call

        session_id = new_session()
        trace_dir = tmp_path / "traces"
        trace_path = trace_dir / f"{session_id}.jsonl"

        with patch("core.tracer.config.LOGS_DIR", str(tmp_path)), \
             patch("core.tracer.time.time", return_value=1234567890.0):
            log_model_call(
                caller="test_caller",
                model="test_model",
                messages=[{"role": "user", "content": "hello"}],
                response="goodbye",
                tool_calls=[],
            )

        assert trace_path.exists()
        content = trace_path.read_text()
        assert "test_caller" in content
        assert "test_model" in content
        assert "hello" in content
        assert "goodbye" in content

    def test_log_model_call_handles_write_error(self, tmp_path):
        """邊界：寫入失敗 → 不拋異常，記錄 logger.error."""
        from core.tracer import new_session, log_model_call

        session_id = new_session()
        # 指向不存在的目錄
        with patch("core.tracer.config.LOGS_DIR", "/nonexistent/path"), \
             patch("core.tracer.logger") as mock_logger:
            # 不拋異常
            log_model_call(
                caller="test_caller",
                model="test_model",
                messages=[{"role": "user", "content": "hello"}],
                response="goodbye",
                tool_calls=[],
            )
            # 確認 logger.error 被呼叫
            assert mock_logger.error.called


class TestLogTask:
    """測試 log_task 函數."""

    def test_log_task_writes_task_trace(self, tmp_path):
        """等價類：log_task 寫入 task_trace.jsonl."""
        from core.tracer import new_session, log_task

        session_id = new_session()
        task_trace_path = tmp_path / "task_trace.jsonl"

        # 使用 MagicMock（log_task 用 unit.unit_id 存取屬性）
        mock_unit = MagicMock()
        mock_unit.unit_id = "u1"
        mock_unit.goal = "test goal"
        mock_unit.output_type = "ACTION"
        mock_unit.assigned_constraints = []

        import uuid as uuid_mod

        with patch("core.tracer.config.TASK_TRACE_PATH", str(task_trace_path)), \
             patch("core.tracer.datetime") as mock_dt, \
             patch("core.tracer.uuid.uuid4", return_value=uuid_mod.UUID("12345678-90ab-cdef-1234-567890abcdef")):
            mock_dt.now.return_value.isoformat.return_value = "2024-01-01T00:00:00+08:00"
            mock_dt.timezone = __import__("datetime").timezone
            mock_dt.timedelta = __import__("datetime").timedelta

            log_task(
                task_type="software_dev",
                user_input="test input",
                goal="test goal",
                results={},
                units=[mock_unit],
            )

        assert task_trace_path.exists()
        content = task_trace_path.read_text()
        assert "software_dev" in content
        assert "test input" in content
        assert "test goal" in content