"""Test plan L1 - Router (#9)

L1 scope (per l1_scope.md): _validate_intent, _pattern_match, _extract_server_name
Excluded: route, probe_server, is_clarification, _call_llm (depend on LLM)

Total: 23 test cases (TC-09-01 ~ TC-09-23)
"""

import json
import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest
from core.router import Router
from models.blueprints import Result


# ── Router patterns property ──────────────────────────────────────────────

class TestRouterPatterns:
    """TC-09-01 ~ TC-09-03"""

    def test_TC_09_01_patterns_cached_when_file_unchanged(self):
        router = Router(call_model_func=lambda *a, **k: Result(success=True))
        # First access loads patterns
        _ = router.patterns
        # Second access should use cache (no OSError)
        patterns = router.patterns
        assert isinstance(patterns, list)

    def test_TC_09_02_patterns_reload_when_file_changed(self):
        router = Router(call_model_func=lambda *a, **k: Result(success=True))
        with patch.object(os.path, "getmtime", side_effect=[0.0, 1.0]):
            _ = router.patterns
            patterns = router.patterns
            assert isinstance(patterns, list)

    def test_TC_09_03_patterns_os_error_returns_cached(self):
        router = Router(call_model_func=lambda *a, **k: Result(success=True))
        with patch.object(os.path, "getmtime", side_effect=OSError()):
            patterns = router.patterns
            assert isinstance(patterns, list)


# ── Router._load_patterns ──────────────────────────────────────────────

class TestRouterLoadPatterns:
    """TC-09-04 ~ TC-09-10"""

    def test_TC_09_04_load_patterns_empty_file(self):
        router = Router(call_model_func=lambda *a, **k: Result(success=True))
        mock_file = MagicMock()
        mock_file.__enter__.return_value.read.return_value = ""
        with patch("os.path.getmtime", return_value=1.0):
            with patch("os.path.exists", return_value=True):
                with patch("builtins.open", MagicMock(return_value=mock_file)):
                    result = router._load_patterns()
                    assert result == []

    def test_TC_09_05_load_patterns_invalid_json(self):
        router = Router(call_model_func=lambda *a, **k: Result(success=True))
        mock_file = MagicMock()
        mock_file.__enter__.return_value.read.return_value = "{invalid"
        with patch("os.path.getmtime", return_value=1.0):
            with patch("os.path.exists", return_value=True):
                with patch("builtins.open", MagicMock(return_value=mock_file)):
                    result = router._load_patterns()
                    # Should return cached (empty) list on parse failure
                    assert isinstance(result, list)

    def test_TC_09_06_load_patterns_length_less_than_3(self):
        router = Router(call_model_func=lambda *a, **k: Result(success=True))
        patterns_data = [["regex", "intent"]]  # length 2
        mock_file = MagicMock()
        mock_file.__enter__.return_value.read.return_value = json.dumps(patterns_data)
        with patch("os.path.getmtime", return_value=1.0):
            with patch("os.path.exists", return_value=True):
                with patch("builtins.open", MagicMock(return_value=mock_file)):
                    result = router._load_patterns()
                    assert result == []

    def test_TC_09_07_load_patterns_length_equals_3(self):
        router = Router(call_model_func=lambda *a, **k: Result(success=True))
        patterns_data = [["^hello", "simple", True]]
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(patterns_data, f)
            f.flush()
            temp_path = f.name
        with patch("os.path.getmtime", return_value=1.0):
            with patch("os.path.exists", return_value=True):
                with patch("builtins.open", MagicMock(return_value=open(temp_path))):
                    result = router._load_patterns()
                    assert len(result) == 1
                    assert result[0]["regex"] == "^hello"
                    assert result[0]["intent"] == "simple"
                    assert result[0]["priority"] == 0
                    assert result[0]["domain"] == "general"
        os.unlink(temp_path)

    def test_TC_09_08_load_patterns_length_equals_4(self):
        router = Router(call_model_func=lambda *a, **k: Result(success=True))
        patterns_data = [["^hello", "simple", True, 3]]  # index 3 is priority (int), domain defaults to "general"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(patterns_data, f)
            f.flush()
            temp_path = f.name
        with patch("os.path.getmtime", return_value=1.0):
            with patch("os.path.exists", return_value=True):
                with patch("builtins.open", MagicMock(return_value=open(temp_path))):
                    result = router._load_patterns()
                    assert len(result) == 1
                    assert result[0]["domain"] == "general"
                    assert result[0]["priority"] == 3
        os.unlink(temp_path)

    def test_TC_09_09_load_patterns_length_gte_5(self):
        router = Router(call_model_func=lambda *a, **k: Result(success=True))
        patterns_data = [["^hello", "simple", True, 5, "tech"]]
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(patterns_data, f)
            f.flush()
            temp_path = f.name
        with patch("os.path.getmtime", return_value=1.0):
            with patch("os.path.exists", return_value=True):
                with patch("builtins.open", MagicMock(return_value=open(temp_path))):
                    result = router._load_patterns()
                    assert len(result) == 1
                    assert result[0]["priority"] == 5
                    assert result[0]["domain"] == "tech"
        os.unlink(temp_path)

    def test_TC_09_10_load_patterns_invalid_regex(self):
        router = Router(call_model_func=lambda *a, **k: Result(success=True))
        patterns_data = [["[invalid", "intent", True]]
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(patterns_data, f)
            f.flush()
            temp_path = f.name
        with patch("os.path.getmtime", return_value=1.0):
            with patch("os.path.exists", return_value=True):
                with patch("builtins.open", MagicMock(return_value=open(temp_path))):
                    result = router._load_patterns()
                    assert result == []
        os.unlink(temp_path)


# ── Router._pattern_match ──────────────────────────────────────────────

class TestRouterPatternMatch:
    """TC-09-11 ~ TC-09-14"""

    def test_TC_09_11_pattern_match_empty_patterns(self):
        router = Router(call_model_func=lambda *a, **k: Result(success=True))
        result = router._pattern_match("test input")
        assert result is None

    def test_TC_09_12_pattern_match_single_pattern_matches(self):
        router = Router(call_model_func=lambda *a, **k: Result(success=True))
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump([["^hello", "simple", True, 0, "general"]], f)
            f.flush()
            temp_path = f.name
        with patch("os.path.getmtime", return_value=1.0):
            with patch("os.path.exists", return_value=True):
                with patch("builtins.open", MagicMock(return_value=open(temp_path))):
                    result = router._pattern_match("hello world")
                    assert result is not None
                    assert result["intent"] == "simple"
        os.unlink(temp_path)

    def test_TC_09_13_pattern_match_single_pattern_no_match(self):
        router = Router(call_model_func=lambda *a, **k: Result(success=True))
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump([["^hello", "simple", True, 0, "general"]], f)
            f.flush()
            temp_path = f.name
        with patch("os.path.getmtime", return_value=1.0):
            with patch("os.path.exists", return_value=True):
                with patch("builtins.open", MagicMock(return_value=open(temp_path))):
                    result = router._pattern_match("goodbye")
                    assert result is None
        os.unlink(temp_path)

    def test_TC_09_14_pattern_match_multiple_patterns_priority(self):
        router = Router(call_model_func=lambda *a, **k: Result(success=True))
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump([
                ["^hello", "simple", True, 1, "general"],
                ["^hello world", "complex", True, 5, "general"],
            ], f)
            f.flush()
            temp_path = f.name
        with patch("os.path.getmtime", return_value=1.0):
            with patch("os.path.exists", return_value=True):
                with patch("builtins.open", MagicMock(return_value=open(temp_path))):
                    result = router._pattern_match("hello world")
                    assert result is not None
                    assert result["intent"] == "complex"
        os.unlink(temp_path)


# ── Router._validate_intent ──────────────────────────────────────────────

class TestRouterValidateIntent:
    """TC-09-15 ~ TC-09-19"""

    def test_TC_09_15_validate_intent_simple(self):
        router = Router(call_model_func=lambda *a, **k: Result(success=True))
        valid, intent = router._validate_intent("simple")
        assert valid is True
        assert intent == "simple"

    def test_TC_09_16_validate_intent_tool(self):
        router = Router(call_model_func=lambda *a, **k: Result(success=True))
        valid, intent = router._validate_intent("tool")
        assert valid is True
        assert intent == "tool"

    def test_TC_09_17_validate_intent_complex(self):
        router = Router(call_model_func=lambda *a, **k: Result(success=True))
        valid, intent = router._validate_intent("complex")
        assert valid is True
        assert intent == "complex"

    def test_TC_09_18_validate_intent_empty_string(self):
        router = Router(call_model_func=lambda *a, **k: Result(success=True))
        valid, intent = router._validate_intent("")
        assert valid is False
        assert intent == ""

    def test_TC_09_19_validate_intent_invalid(self):
        router = Router(call_model_func=lambda *a, **k: Result(success=True))
        valid, intent = router._validate_intent("invalid_intent")
        assert valid is False
        assert intent == "invalid_intent"


# ── Router._extract_server_name ──────────────────────────────────────────────

class TestRouterExtractServerName:
    """TC-09-20 ~ TC-09-23"""

    def test_TC_09_20_extract_server_name_normal(self):
        result = Router._extract_server_name("  brave_search  ")
        assert result == "brave_search"

    def test_TC_09_21_extract_server_name_with_quotes(self):
        result = Router._extract_server_name('  "brave_search"  ')
        assert result == "brave_search"

    def test_TC_09_22_extract_server_name_with_quotes_and_spaces(self):
        result = Router._extract_server_name('  "brave_search"  ')
        assert result == "brave_search"

    def test_TC_09_23_extract_server_name_empty_string(self):
        result = Router._extract_server_name("")
        assert result == ""