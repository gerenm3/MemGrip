"""tests/L1/test_trace_reader.py — skills/trace_reader.py 純邏輯測試（10 筆）."""

import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest


class TestLoadJsonl:
    """_load_jsonl 測試."""

    def test_load_jsonl_nonexistent_file(self, tmp_path):
        """等價類：檔案不存在 → 回傳空列表."""
        from skills.trace_reader import _load_jsonl
        result = _load_jsonl(str(tmp_path / "nonexistent.jsonl"))
        assert result == []

    def test_load_jsonl_empty_file(self, tmp_path):
        """等價類：空檔案 → 回傳空列表."""
        jsonl_file = tmp_path / "empty.jsonl"
        jsonl_file.write_text("")
        from skills.trace_reader import _load_jsonl
        result = _load_jsonl(str(jsonl_file))
        assert result == []

    def test_load_jsonl_valid_lines(self, tmp_path):
        """等價類：有效 JSONL → 回傳解析後的列表."""
        jsonl_file = tmp_path / "valid.jsonl"
        jsonl_file.write_text('{"a": 1}\n{"b": 2}\n')
        from skills.trace_reader import _load_jsonl
        result = _load_jsonl(str(jsonl_file))
        assert len(result) == 2
        assert result[0] == {"a": 1}
        assert result[1] == {"b": 2}

    def test_load_jsonl_skip_invalid_json(self, tmp_path):
        """等價類：無效 JSON 列被跳過."""
        jsonl_file = tmp_path / "mixed.jsonl"
        jsonl_file.write_text('{"a": 1}\nnot json\n{"b": 2}\n')
        from skills.trace_reader import _load_jsonl
        result = _load_jsonl(str(jsonl_file))
        assert len(result) == 2
        assert result[0] == {"a": 1}
        assert result[1] == {"b": 2}

    def test_load_jsonl_cache_hit(self, tmp_path):
        """等價類：快取命中 → 回傳快取結果."""
        jsonl_file = tmp_path / "cached.jsonl"
        jsonl_file.write_text('{"x": 1}\n')
        from skills.trace_reader import _load_jsonl
        result1 = _load_jsonl(str(jsonl_file))
        result2 = _load_jsonl(str(jsonl_file))
        assert result1 == result2
        assert result1[0] == {"x": 1}


class TestClearCache:
    """_clear_cache 測試."""

    def test_clear_cache_clears_all(self):
        """等價類：clear_cache 清除所有快取."""
        from skills import trace_reader
        trace_reader._cache["test"] = [1, 2, 3]
        trace_reader._clear_cache()
        assert trace_reader._cache == {}


class TestExtractToolCalls:
    """_extract_tool_calls_from_messages 測試."""

    def test_extract_tool_calls_normal(self):
        """等價類：正常 tool_calls → 正確提取."""
        from skills.trace_reader import _extract_tool_calls_from_messages
        arguments_json = '{"q": "test"}'
        messages = [
            {"role": "assistant", "tool_calls": [
                {"function": {"name": "search", "arguments": arguments_json}}
            ]},
        ]
        result = _extract_tool_calls_from_messages(messages)
        assert len(result) == 1
        assert result[0]["name"] == "search"
        assert result[0]["arguments"] == arguments_json

    def test_extract_tool_calls_no_tool_calls(self):
        """等價類：無 tool_calls → 空列表."""
        from skills.trace_reader import _extract_tool_calls_from_messages
        messages = [
            {"role": "user", "content": "hello"},
        ]
        result = _extract_tool_calls_from_messages(messages)
        assert result == []

    def test_extract_tool_calls_mixed_roles(self):
        """等價類：assistant + user role 混合 → 只取 assistant."""
        from skills.trace_reader import _extract_tool_calls_from_messages
        messages = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "tool_calls": [
                {"function": {"name": "call", "arguments": "{}"}}
            ]},
            {"role": "user", "content": "response"},
        ]
        result = _extract_tool_calls_from_messages(messages)
        assert len(result) == 1
        assert result[0]["name"] == "call"

    def test_extract_tool_calls_empty_messages(self):
        """邊界：空 list → 空列表."""
        from skills.trace_reader import _extract_tool_calls_from_messages
        result = _extract_tool_calls_from_messages([])
        assert result == []

    def test_extract_tool_calls_missing_function(self):
        """等價類：function 缺失 → 跳過."""
        from skills.trace_reader import _extract_tool_calls_from_messages
        messages = [
            {"role": "assistant", "tool_calls": [
                {"function": {"name": "call", "arguments": "{}"}},
                {"function": None},
            ]},
        ]
        result = _extract_tool_calls_from_messages(messages)
        assert len(result) == 1
        assert result[0]["name"] == "call"


class TestBuildExecutionRecord:
    """build_execution_record 測試."""

    def test_build_execution_record_no_task_record(self, tmp_path):
        """邊界：task_trace.jsonl 無對應 session → None."""
        task_trace = tmp_path / "task_trace.jsonl"
        task_trace.write_text('{"session_id": "other", "task_type": "test"}\n')
        trace_log = tmp_path / "trace.jsonl"
        trace_log.write_text('')
        from skills.trace_reader import build_execution_record
        from skills import trace_reader
        trace_reader._cache.clear()
        with patch("skills.trace_reader.config.TASK_TRACE_PATH", str(task_trace)), \
             patch("skills.trace_reader.config.TRACE_LOG_PATH", str(trace_log)):
            result = build_execution_record("nonexistent")
        assert result is None

    def test_build_execution_record_empty_units(self, tmp_path):
        """等價類：有 task_record 但 units 為空 → unit_count=0."""
        task_trace = tmp_path / "task_trace.jsonl"
        task_trace.write_text('{"session_id": "s1", "task_type": "test", "goal": "G1", "units": []}\n')
        trace_log = tmp_path / "trace.jsonl"
        trace_log.write_text('')
        from skills.trace_reader import build_execution_record
        from skills import trace_reader
        trace_reader._cache.clear()
        with patch("skills.trace_reader.config.TASK_TRACE_PATH", str(task_trace)), \
             patch("skills.trace_reader.config.TRACE_LOG_PATH", str(trace_log)):
            result = build_execution_record("s1")
        assert result is not None
        assert result["task_type"] == "test"
        assert result["goal"] == "G1"
        assert result["unit_count"] == 0
        assert result["failed_units"] == 0
        assert result["avg_loop_count"] == 0
        assert result["constraint_satisfied_ratio"] == 1.0
        assert result["verifier_pass_ratio"] == 1.0

    def test_build_execution_record_with_failed_units(self, tmp_path):
        """等價類：有 failed units → failed_units 正確."""
        task_trace = tmp_path / "task_trace.jsonl"
        task_trace.write_text(
            '{"session_id": "s1", "task_type": "test", "goal": "G1", '
            '"units": [{"unit_id": "u1", "status": "SUCCESS"}, '
            '{"unit_id": "u2", "status": "FAILED"}, '
            '{"unit_id": "u3", "status": "FAILED"}]}\n'
        )
        trace_log = tmp_path / "trace.jsonl"
        trace_log.write_text('')
        from skills.trace_reader import build_execution_record
        from skills import trace_reader
        trace_reader._cache.clear()
        with patch("skills.trace_reader.config.TASK_TRACE_PATH", str(task_trace)), \
             patch("skills.trace_reader.config.TRACE_LOG_PATH", str(trace_log)):
            result = build_execution_record("s1")
        assert result["failed_units"] == 2
        assert result["unit_count"] == 3

    def test_build_execution_record_with_constraint_checks(self, tmp_path):
        """等價類：有 constraint_checks → constraint_satisfied_ratio 正確."""
        task_trace = tmp_path / "task_trace.jsonl"
        task_trace.write_text(
            '{"session_id": "s1", "task_type": "test", "goal": "G1", '
            '"units": [{"unit_id": "u1", "status": "SUCCESS", '
            '"constraint_checks": [{"constraint": "c1", "satisfied": true}, '
            '{"constraint": "c2", "satisfied": false}]}]}\n'
        )
        trace_log = tmp_path / "trace.jsonl"
        trace_log.write_text('')
        from skills.trace_reader import build_execution_record
        from skills import trace_reader
        trace_reader._cache.clear()
        with patch("skills.trace_reader.config.TASK_TRACE_PATH", str(task_trace)), \
             patch("skills.trace_reader.config.TRACE_LOG_PATH", str(trace_log)):
            result = build_execution_record("s1")
        assert result["constraint_satisfied_ratio"] == 0.5

    def test_build_execution_record_with_verifier_pass(self, tmp_path):
        """等價類：有 executor_verify trace → verifier_pass_ratio 正確."""
        task_trace = tmp_path / "task_trace.jsonl"
        task_trace.write_text('{"session_id": "s1", "task_type": "test", "goal": "G1", "units": []}\n')
        trace_log = tmp_path / "trace.jsonl"
        with trace_log.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"session_id": "s1", "caller": "executor_verify",
                        "messages": [{"role": "user", "content": json.dumps({"passed": True})}]}) + "\n")
            f.write(json.dumps({"session_id": "s1", "caller": "executor_verify",
                        "messages": [{"role": "user", "content": json.dumps({"passed": False})}]}) + "\n")
        from skills.trace_reader import build_execution_record
        from skills import trace_reader
        trace_reader._cache.clear()
        with patch("skills.trace_reader.config.TASK_TRACE_PATH", str(task_trace)), \
             patch("skills.trace_reader.config.TRACE_LOG_PATH", str(trace_log)):
            result = build_execution_record("s1")
        assert result["verifier_pass_ratio"] == 0.5
