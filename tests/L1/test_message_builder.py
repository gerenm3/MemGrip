"""Test plan L1 - MessageBuilder (#4)

Covers: build_core, build_task, build_dialog, build_meta (all static methods)

Total: 18 test cases (TC-04-01 ~ TC-04-18)
"""

import pytest
from clients.message_builder import MessageBuilder


# ── build_core ───────────────────────────────────────────────────────────

class TestBuildCore:
    """TC-04-01 ~ TC-04-04, TC-04-17"""

    def test_TC_04_01_normal_input(self):
        result = MessageBuilder.build_core("You are a helpful assistant", "Hello")
        assert result == [
            {"role": "system", "content": "You are a helpful assistant"},
            {"role": "user", "content": "Hello"},
        ]

    def test_TC_04_02_empty_system_prompt(self):
        result = MessageBuilder.build_core("", "Hello")
        assert result == [
            {"role": "system", "content": ""},
            {"role": "user", "content": "Hello"},
        ]

    def test_TC_04_03_empty_user_content(self):
        result = MessageBuilder.build_core("Hi", "")
        assert result == [
            {"role": "system", "content": "Hi"},
            {"role": "user", "content": ""},
        ]

    def test_TC_04_04_both_empty(self):
        result = MessageBuilder.build_core("", "")
        assert result == [
            {"role": "system", "content": ""},
            {"role": "user", "content": ""},
        ]

    def test_TC_04_17_special_characters(self):
        result = MessageBuilder.build_core("P", "Hello\nWorld\twith\\special")
        assert result[1]["content"] == "Hello\nWorld\twith\\special"


# ── build_task ───────────────────────────────────────────────────────────

class TestBuildTask:
    """TC-04-05 ~ TC-04-06"""

    def test_TC_04_05_normal_input(self):
        result = MessageBuilder.build_task("Task prompt", "Do this")
        assert result == [
            {"role": "system", "content": "Task prompt"},
            {"role": "user", "content": "Do this"},
        ]

    def test_TC_04_06_no_memory_tags(self):
        result = MessageBuilder.build_task("P", "U")
        content = result[1]["content"]
        assert "[SUMMARY]" not in content
        assert "[BUFFER]" not in content
        assert "[RAG]" not in content


# ── build_dialog ─────────────────────────────────────────────────────────

class TestBuildDialog:
    """TC-04-07 ~ TC-04-13, TC-04-18"""

    def test_TC_04_07_normal_with_all_memory(self):
        result = MessageBuilder.build_dialog(
            "P", "Hello", "Summary", "Buffer", "RAG"
        )
        content = result[0]["content"]
        assert "[SUMMARY]Summary[/SUMMARY]" in content
        assert "[BUFFER]Buffer[/BUFFER]" in content
        assert "[RAG]RAG[/RAG]" in content
        assert "[USER_INPUT]" in result[1]["content"]
        assert "Hello" in result[1]["content"]

    def test_TC_04_08_no_summary(self):
        result = MessageBuilder.build_dialog("P", "Hello", "", "Buffer", "RAG")
        content = result[0]["content"]
        assert "[SUMMARY]" not in content
        assert "[BUFFER]Buffer[/BUFFER]" in content

    def test_TC_04_09_no_buffer(self):
        result = MessageBuilder.build_dialog("P", "Hello", "Summary", "", "RAG")
        content = result[0]["content"]
        assert "[SUMMARY]Summary[/SUMMARY]" in content
        assert "[BUFFER]" not in content

    def test_TC_04_10_no_rag(self):
        result = MessageBuilder.build_dialog("P", "Hello", "Summary", "Buffer", "")
        content = result[0]["content"]
        assert "[RAG]" not in content
        assert "[SUMMARY]Summary[/SUMMARY]" in content
        assert "[BUFFER]Buffer[/BUFFER]" in content

    def test_TC_04_11_all_memory_empty(self):
        result = MessageBuilder.build_dialog("P", "Hello", "", "", "")
        content = result[0]["content"]
        assert "[SUMMARY]" not in content
        assert "[BUFFER]" not in content
        assert "[RAG]" not in content
        assert "[USER_INPUT]" in result[1]["content"]
        assert "Hello" in result[1]["content"]

    def test_TC_04_12_user_input_always_wrapped(self):
        result = MessageBuilder.build_dialog("P", "", "", "", "")
        content = result[0]["content"]
        assert "[USER_INPUT]" in result[1]["content"]

    def test_TC_04_13_memory_blocks_separated_by_newline(self):
        result = MessageBuilder.build_dialog("P", "U", "S", "B", "R")
        content = result[0]["content"]
        assert "\n\n" in content

    def test_TC_04_18_tag_order(self):
        result = MessageBuilder.build_dialog("P", "U", "S", "B", "R")
        content = result[0]["content"]
        summary_pos = content.find("[SUMMARY]")
        buffer_pos = content.find("[BUFFER]")
        rag_pos = content.find("[RAG]")
        assert summary_pos < buffer_pos < rag_pos
        assert "U" in result[1]["content"]
        assert "[USER_INPUT]" in result[1]["content"]