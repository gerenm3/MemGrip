"""Tests for core/json_utils — stack-based JSON extraction."""

import pytest
from core.json_utils import extract_first_json, extract_all_jsons, parse_first_json, parse_all_jsons


# ── extract_first_json ────────────────────────────────────────────


def test_simple_object():
    assert parse_first_json('{"a": 1}') == {"a": 1}


def test_simple_array():
    assert parse_first_json('["a", 1]') == ["a", 1]


def test_deeply_nested():
    deep = '{"l1": {"l2": {"l3": {"l4": {"l5": "deep"}}}}}'
    assert parse_first_json(deep) == {"l1": {"l2": {"l3": {"l4": {"l5": "deep"}}}}}


def test_nested_arrays():
    arr = '[{"items": [{"id": 1}, {"id": 2}]}, {"items": [{"id": 3}]}]'
    assert parse_first_json(arr) == [{"items": [{"id": 1}, {"id": 2}]}, {"items": [{"id": 3}]}]


def test_text_before_json():
    text = "Sure, here is the answer:\n\n{\"key\": \"value\"}"
    assert parse_first_json(text) == {"key": "value"}


def test_json_with_braces_in_strings():
    text = '{"msg": "use {foo} and [bar] in code"}'
    assert parse_first_json(text) == {"msg": "use {foo} and [bar] in code"}


def test_json_with_escaped_quotes():
    # Use raw string so backslashes are literal
    text = r'{"msg": "say \"hello {world}\""}'
    assert parse_first_json(text) == {"msg": 'say "hello {world}"'}


def test_raw_json_array():
    arr = '[{"x": 1}, {"x": 2}]'
    assert parse_first_json(arr) == [{"x": 1}, {"x": 2}]


def test_empty_string():
    assert extract_first_json('') is None


def test_none_input():
    assert extract_first_json(None) is None


def test_no_json_found():
    assert extract_first_json('just plain text') is None


def test_json_in_markdown():
    # LLM often wraps output in ``` blocks
    text = "```json\n{\"code\": true}\n```"
    result = extract_first_json(text)
    assert result == '{"code": true}'
    assert parse_first_json(text) == {"code": True}


# ── extract_all_jsons ─────────────────────────────────────────────


def test_multiple_jsons():
    text = '{"a": 1} some text {"b": 2}'
    assert extract_all_jsons(text) == ['{"a": 1}', '{"b": 2}']
    assert parse_all_jsons(text) == [{"a": 1}, {"b": 2}]


def test_no_jsons():
    assert extract_all_jsons('no json here') == []


def test_single_json():
    text = 'prefix {"key": "val"} suffix'
    assert extract_all_jsons(text) == ['{"key": "val"}']


def test_adjacent_jsons():
    text = '{"a":1}{"b":2}{"c":3}'
    assert extract_all_jsons(text) == ['{"a":1}', '{"b":2}', '{"c":3}']


# ── Edge cases that previously broke regex ─────────────────────────


def test_regex_broken_nested_json():
    """This is the original bug: r'\\{.*?\\}' stops at first }."""
    nested = '{"outer": {"inner": {"deep": 1}}, "end": 2}'
    result = parse_first_json(nested)
    assert result == {"outer": {"inner": {"deep": 1}}, "end": 2}


def test_complex_real_world():
    """Simulate a realistic LLM response with nested tool calls."""
    text = '''Here are the steps:

[
  {
    "id": "1",
    "content": "fetch data",
    "tools": {
      "name": "api_call",
      "params": {"url": "https://example.com", "query": {"nested": true}}
    }
  },
  {
    "id": "2",
    "content": "process results",
    "depends_on": ["1"]
  }
]'''
    result = extract_first_json(text)
    assert result is not None
    parsed = parse_first_json(text)
    assert isinstance(parsed, list)
    assert len(parsed) == 2
    assert parsed[0]["tools"]["params"]["query"]["nested"] is True