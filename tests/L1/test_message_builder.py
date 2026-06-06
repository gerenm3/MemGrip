"""tests/L1/test_message_builder.py — MessageBuilder 純邏輯測試（12 筆）."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from clients.message_builder import MessageBuilder


class TestBuildCore:
    """MessageBuilder.build_core 測試."""

    def test_build_core_returns_list(self):
        """等價類：正常輸入 → 回傳 list 格式正確."""
        result = MessageBuilder.build_core("sys prompt", "hello")
        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["role"] == "system"
        assert result[1]["role"] == "user"

    def test_build_core_user_content_wrapped(self):
        """等價類：user_content 應在 user role message 中."""
        result = MessageBuilder.build_core("sys", "user msg")
        assert result[1]["content"] == "user msg"

    def test_build_core_empty_user(self):
        """邊界：空 user_content."""
        result = MessageBuilder.build_core("sys", "")
        assert isinstance(result, list)
        assert result[1]["content"] == ""


class TestBuildTask:
    """MessageBuilder.build_task 測試."""

    def test_build_task_returns_list(self):
        """等價類：正常輸入 → 回傳 list 格式正確."""
        result = MessageBuilder.build_task("sys", "task")
        assert isinstance(result, list)
        assert len(result) == 2

    def test_build_task_system_in_system_role(self):
        """等價類：system prompt 應在 system role."""
        result = MessageBuilder.build_task("my system", "task")
        assert result[0]["role"] == "system"
        assert result[0]["content"] == "my system"


class TestBuildDialog:
    """MessageBuilder.build_dialog 測試."""

    def test_build_dialog_all_fields_populated(self):
        """等價類：5 個參數全部有值."""
        result = MessageBuilder.build_dialog(
            "sys", "user", "summary text", "buffer text", "rag text"
        )
        assert isinstance(result, list)
        full_content = " ".join(m["content"] for m in result)
        assert "summary text" in full_content
        assert "buffer text" in full_content
        assert "rag text" in full_content

    def test_build_dialog_empty_summary_buffer_rag(self):
        """邊界：summary/buffer/rag 全空."""
        result = MessageBuilder.build_dialog("sys", "user", "", "", "")
        assert isinstance(result, list)
        full_content = " ".join(m["content"] for m in result)
        assert "user" in full_content

    def test_build_dialog_summary_included(self):
        """等價類：summary 應包含在 message content."""
        result = MessageBuilder.build_dialog("sys", "user", "MY_SUMMARY", "", "")
        full_content = " ".join(m["content"] for m in result)
        assert "MY_SUMMARY" in full_content

    def test_build_dialog_buffer_included(self):
        """等價類：buffer 應包含在 message content."""
        result = MessageBuilder.build_dialog("sys", "user", "", "MY_BUFFER", "")
        full_content = " ".join(m["content"] for m in result)
        assert "MY_BUFFER" in full_content

    def test_build_dialog_rag_included(self):
        """等價類：rag 應包含在 message content."""
        result = MessageBuilder.build_dialog("sys", "user", "", "", "MY_RAG")
        full_content = " ".join(m["content"] for m in result)
        assert "MY_RAG" in full_content


class TestBuildMeta:
    """MessageBuilder.build_meta 測試."""

    def test_build_meta_returns_list(self):
        """等價類：正常輸入 → 回傳 list 格式正確."""
        result = MessageBuilder.build_meta("sys", {"data": "some content"})
        assert isinstance(result, list)
        assert len(result) == 2

    def test_build_meta_vs_build_core_difference(self):
        """等價類：meta 與 core 的 message 結構差異."""
        meta = MessageBuilder.build_meta("sys", {"data": "content"})
        core = MessageBuilder.build_core("sys", "user")
        # meta 和 core 的 role 順序應該一致（都是 system + user）
        assert meta[0]["role"] == core[0]["role"]
        assert meta[1]["role"] == core[1]["role"]