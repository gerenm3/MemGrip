"""tests/L1/test_buffer.py — memory/buffer.py 純邏輯測試（15 筆）."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pytest
import unittest.mock

from memory.buffer import estimate_tokens, ConversationBuffer


class TestEstimateTokens:
    """estimate_tokens 函式測試."""

    def test_empty_string(self):
        """邊界：空字串 → 0."""
        assert estimate_tokens("") == 0

    def test_ascii_only(self):
        """等價類：純 ASCII 'hello' → 5//3=1."""
        assert estimate_tokens("hello") == 1

    def test_cjk_only(self):
        """等價類：純 CJK '你好' → 2×2=4."""
        assert estimate_tokens("你好") == 4

    def test_mixed(self):
        """等價類：混合 'a你好' → 1//3+2×2=4."""
        assert estimate_tokens("a你好") == 4

    def test_cjk_extension_a(self):
        """等價類：擴展區 A (\\u3400-\\u4DBF)."""
        # \\u3400 是 CJK Extension A 的開始
        assert estimate_tokens("\u3400") == 2

    def test_non_cjk_ranges(self):
        """等價類：非 CJK 範圍（如 emoji）按一般字元."""
        # emoji 不屬於 CJK 範圍
        assert estimate_tokens("\U0001F600") == 0  # 😀

    def test_large_text(self):
        """邊界：大量文字 token 計算正確性."""
        text = "a" * 100 + "你" * 100
        expected = (100 // 3) + (100 * 2)
        assert estimate_tokens(text) == expected


class TestConversationBuffer:
    """ConversationBuffer 類別測試."""

    @pytest.fixture
    def mock_buffer_config(self):
        with unittest.mock.patch("config.BUFFER_MAX_TOKENS", 100):
            yield

    def test_init_default_state(self, mock_buffer_config):
        """等價類：初始化 context/flushed/_current_tokens."""
        buf = ConversationBuffer()
        assert buf.context == []
        assert buf.flushed == []
        assert buf._current_tokens == 0

    def test_add_user_message(self, mock_buffer_config):
        """等價類：add user role 訊息."""
        buf = ConversationBuffer()
        buf.add("user", "hello")
        assert len(buf.context) == 1
        assert buf.context[0]["role"] == "user"
        assert buf.context[0]["content"] == "hello"

    def test_add_assistant_message(self, mock_buffer_config):
        """等價類：add assistant role 訊息."""
        buf = ConversationBuffer()
        buf.add("assistant", "hi there")
        assert len(buf.context) == 1
        assert buf.context[0]["role"] == "assistant"

    def test_check_no_flush_below_limit(self, mock_buffer_config):
        """邊界：tokens 未超閾值不 flush."""
        buf = ConversationBuffer()
        # 10 tokens < 100
        for i in range(10):
            buf.add("user", f"msg{i}")
        # check() 回傳 None，檢查 context 沒被 flush
        buf.check()
        assert len(buf.context) == 10

    def test_check_flush_exceeds_limit(self, mock_buffer_config):
        """邊界：tokens 超過閾值觸發 flush."""
        buf = ConversationBuffer()
        # 寫入超過 100 tokens（交替 user/assistant 讓 check() 能 flush）
        # 每筆 ~10 tokens，25 對 = 500 tokens >> 100
        for i in range(25):
            buf.add("user", f"message number {i} with extra padding text")
            buf.add("assistant", f"reply number {i} with extra padding text")
        buf.check()
        assert len(buf.flushed) > 0

    def test_serialize_format(self, mock_buffer_config):
        """等價類：serialize 格式為『用戶：/助理：』."""
        buf = ConversationBuffer()
        buf.add("user", "你好")
        buf.add("assistant", "嗨")
        serialized = buf.serialize()
        assert "用戶：你好" in serialized
        assert "助理：嗨" in serialized

    def test_extract_flushed_clears(self, mock_buffer_config):
        """等價類：extract_flushed 後 flushed 清空."""
        buf = ConversationBuffer()
        buf.add("user", "test")
        buf.flushed = [{"role": "user", "content": "test"}]
        flushed = buf.extract_flushed()
        assert len(flushed) == 1
        assert buf.flushed == []

    def test_get_returns_copy(self, mock_buffer_config):
        """等價類：get() 回傳 context 的副本."""
        buf = ConversationBuffer()
        buf.add("user", "test")
        result = buf.get()
        assert result is not buf.context