"""L1 test plan for Tracer (#20).

Test cases from docs/test_plan_l1/20_tracer.md.
Only _mask_messages is in scope per l1_scope.md.
"""
import pytest
import hashlib


class TestTracer:
    """Test Tracer per test plan #20 (L1 scope only)."""

    def _get_masked(self, messages):
        """Call _mask_messages and return the modified messages."""
        from core.tracer import _mask_messages
        import copy
        return _mask_messages(copy.deepcopy(messages))

    def test_TC_20_01_no_system_role(self):
        """TC-20-01: _mask_messages - 無 system role."""
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi"}
        ]
        result = self._get_masked(messages)
        assert result[0]["content"] == "Hello"
        assert result[1]["content"] == "Hi"

    def test_TC_20_02_system_empty_content(self):
        """TC-20-02: _mask_messages - system role content 為空.
        
        測試計畫預期：空 content 脫敏為 "...{MD5}" 格式。
        """
        content = ""
        messages = [{"role": "system", "content": content}]
        result = self._get_masked(messages)
        expected_md5 = hashlib.md5(b"").hexdigest()
        expected = content[:100] + "..." + expected_md5
        assert result[0]["content"] == expected

    def test_TC_20_03_system_content_length_100(self):
        """TC-20-03: _mask_messages - system role content 長度 <= 100 (正好 100)."""
        content = "A" * 100
        messages = [{"role": "system", "content": content}]
        result = self._get_masked(messages)
        expected_md5 = hashlib.md5(content.encode()).hexdigest()
        expected = content[:100] + "..." + expected_md5
        assert result[0]["content"] == expected

    def test_TC_20_04_system_content_length_200(self):
        """TC-20-04: _mask_messages - system role content 長度 > 100."""
        content = "A" * 200
        messages = [{"role": "system", "content": content}]
        result = self._get_masked(messages)
        expected_md5 = hashlib.md5(content.encode()).hexdigest()
        expected = content[:100] + "..." + expected_md5
        assert result[0]["content"] == expected

    def test_TC_20_05_system_content_length_101(self):
        """TC-20-05: _mask_messages - system role content 長度 = 101."""
        content = "A" * 101
        messages = [{"role": "system", "content": content}]
        result = self._get_masked(messages)
        expected_md5 = hashlib.md5(content.encode()).hexdigest()
        expected = content[:100] + "..." + expected_md5
        assert result[0]["content"] == expected

    def test_TC_20_06_multiple_system_roles(self):
        """TC-20-06: _mask_messages - 多個 system role."""
        messages = [
            {"role": "system", "content": "S1"},
            {"role": "user", "content": "U"},
            {"role": "system", "content": "S2"}
        ]
        result = self._get_masked(messages)
        # Both system roles should be masked (content changed)
        assert result[0]["content"] != "S1"
        assert result[2]["content"] != "S2"
        assert "..." in result[0]["content"]
        assert "..." in result[2]["content"]
        # user not modified
        assert result[1]["content"] == "U"

    def test_TC_20_07_empty_messages(self):
        """TC-20-07: _mask_messages - messages 為空."""
        result = self._get_masked([])
        assert result == []

    def test_TC_20_08_none_messages(self):
        """TC-20-08: _mask_messages - messages 為 None (拋 TypeError)."""
        with pytest.raises(TypeError):
            self._get_masked(None)

    def test_TC_20_09_md5_correctness(self):
        """TC-20-09: _mask_messages - MD5 正確性."""
        content = "test system prompt"
        messages = [{"role": "system", "content": content}]
        result = self._get_masked(messages)
        expected_md5 = hashlib.md5(content.encode()).hexdigest()
        assert expected_md5 in result[0]["content"]
        assert "..." in result[0]["content"]

    def test_TC_20_10_non_string_content(self):
        """TC-20-10: _mask_messages - content 非字串 (拋 TypeError)."""
        messages = [{"role": "system", "content": 123}]
        with pytest.raises(TypeError):
            self._get_masked(messages)

    def test_TC_20_11_none_content(self):
        """TC-20-11: _mask_messages - content 為 None.
        
        測試計畫預期：None content 經 or "" 轉為空字串，脫敏為 "...{MD5}"。
        """
        messages = [{"role": "system", "content": None}]
        result = self._get_masked(messages)
        expected_md5 = hashlib.md5(b"").hexdigest()
        expected = ""[:100] + "..." + expected_md5
        assert result[0]["content"] == expected

    def test_TC_20_12_non_system_roles_unchanged(self):
        """TC-20-12: _mask_messages - 不修改非 system role."""
        messages = [
            {"role": "system", "content": "S"},
            {"role": "user", "content": "U"},
            {"role": "assistant", "content": "A"}
        ]
        result = self._get_masked(messages)
        assert result[1]["content"] == "U"
        assert result[2]["content"] == "A"