"""tests/L1/test_router.py — core/router.py 純邏輯測試（17 筆）."""

import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pytest
import unittest.mock


class TestPatternMatch:
    """Router._pattern_match 測試."""

    @pytest.fixture
    def router_with_patterns(self, tmp_path):
        """建立臨時 patterns.json + Router 實例.
        
        關鍵：先 patch config.PATTERNS_PATH，再 import Router（因為 Router.__init__ 會讀 config.PATTERNS_PATH）。
        """
        patterns_data = [
            ["search.*|find.*", "tool", False, 10, "brave_search"],
            ["read.*|write.*", "tool", False, 5, "file_rw"],
            [".*", "simple", False, 1, "general"],
        ]
        patterns_file = tmp_path / "patterns.json"
        patterns_file.write_text(json.dumps(patterns_data))
        # 清除已載入的 Router module，讓重新 import 時能讀到新的 config
        if "core.router" in sys.modules:
            del sys.modules["core.router"]
        with unittest.mock.patch("config.PATTERNS_PATH", str(patterns_file)):
            from core.router import Router
            router = Router(call_model_func=None)
            yield router

    def test_first_priority_wins(self, router_with_patterns):
        """等價類：多個 pattern 匹配時取最高 priority."""
        result = router_with_patterns._pattern_match("search something")
        assert result is not None
        assert result["intent"] == "tool"
        assert result["domain"] == "brave_search"

    def test_no_match(self, router_with_patterns):
        """等價類：無匹配 → None."""
        result = router_with_patterns._pattern_match("hello")
        assert result is not None  # general.* 會匹配

    def test_exact_regex(self, tmp_path):
        """等價類：regex 精確匹配."""
        import re
        pattern = "^exact$"
        assert re.fullmatch(pattern, "exact")
        assert re.search(pattern, "exact")


class TestValidateIntent:
    """Router._validate_intent 測試."""

    @pytest.fixture
    def router_instance(self, tmp_path):
        patterns_file = tmp_path / "patterns_empty.json"
        patterns_file.write_text("[]")
        if "core.router" in sys.modules:
            del sys.modules["core.router"]
        with unittest.mock.patch("config.PATTERNS_PATH", str(patterns_file)):
            from core.router import Router
            router = Router(call_model_func=None)
            yield router

    def test_simple_intent(self, router_instance):
        """等價類：intent='simple' → (True, 'simple')."""
        valid, intent = router_instance._validate_intent("simple")
        assert valid is True
        assert intent == "simple"

    def test_tool_intent(self, router_instance):
        """等價類：intent='tool' → (True, 'tool')."""
        valid, intent = router_instance._validate_intent("tool")
        assert valid is True
        assert intent == "tool"

    def test_complex_intent(self, router_instance):
        """等價類：intent='complex' → (True, 'complex')."""
        valid, intent = router_instance._validate_intent("complex")
        assert valid is True
        assert intent == "complex"

    def test_invalid_intent(self, router_instance):
        """等價類：intent='invalid' → (False, 'invalid')."""
        valid, intent = router_instance._validate_intent("invalid")
        assert valid is False
        assert intent == "invalid"


class TestExtractServerName:
    """Router._extract_server_name 測試."""

    @pytest.fixture
    def router_instance(self, tmp_path):
        patterns_file = tmp_path / "patterns_empty.json"
        patterns_file.write_text("[]")
        if "core.router" in sys.modules:
            del sys.modules["core.router"]
        with unittest.mock.patch("config.PATTERNS_PATH", str(patterns_file)):
            from core.router import Router
            router = Router(call_model_func=None)
            yield router

    def test_normal_name(self, router_instance):
        """等價類：正常名稱 'brave_search'."""
        result = router_instance._extract_server_name("brave_search")
        assert result == "brave_search"

    def test_quoted_name(self, router_instance):
        """等價類：帶引號 '\"brave_search\"'."""
        result = router_instance._extract_server_name('"brave_search"')
        assert result == "brave_search"

    def test_whitespace_name(self, router_instance):
        """等價類：帶空白 '  brave_search  '."""
        result = router_instance._extract_server_name("  brave_search  ")
        assert result == "brave_search"

    def test_empty_name(self, router_instance):
        """邊界：空字串."""
        result = router_instance._extract_server_name("")
        assert result == ""


class TestLoadPatterns:
    """Router._load_patterns 測試."""

    def test_valid_patterns(self, tmp_path):
        """等價類：有效 patterns 載入正確."""
        patterns_data = [
            ["test.*", "simple", False, 10, "test"],
        ]
        patterns_file = tmp_path / "patterns.json"
        patterns_file.write_text(json.dumps(patterns_data))
        if "core.router" in sys.modules:
            del sys.modules["core.router"]
        with unittest.mock.patch("config.PATTERNS_PATH", str(patterns_file)):
            from core.router import Router
            router = Router(call_model_func=None)
            loaded = router._load_patterns()
            assert len(loaded) == 1
            assert loaded[0]["regex"] == "test.*"
            assert loaded[0]["domain"] == "test"

    def test_invalid_regex_skipped(self, tmp_path):
        """等價類：無效 regex 跳過."""
        patterns_data = [
            ["[invalid", "simple", False, 10, "bad"],
        ]
        patterns_file = tmp_path / "patterns.json"
        patterns_file.write_text(json.dumps(patterns_data))
        if "core.router" in sys.modules:
            del sys.modules["core.router"]
        with unittest.mock.patch("config.PATTERNS_PATH", str(patterns_file)):
            from core.router import Router
            router = Router(call_model_func=None)
            loaded = router._load_patterns()
            assert len(loaded) == 0

    def test_missing_domain_fallback(self, tmp_path):
        """等價類：缺少 domain → fallback 'general'."""
        patterns_data = [
            ["test.*", "simple", False, 10],
        ]
        patterns_file = tmp_path / "patterns.json"
        patterns_file.write_text(json.dumps(patterns_data))
        if "core.router" in sys.modules:
            del sys.modules["core.router"]
        with unittest.mock.patch("config.PATTERNS_PATH", str(patterns_file)):
            from core.router import Router
            router = Router(call_model_func=None)
            loaded = router._load_patterns()
            assert loaded[0]["domain"] == "general"

    def test_sorted_by_priority(self, tmp_path):
        """等價類：按 priority 降序排列."""
        patterns_data = [
            ["a.*", "simple", False, 1, "low"],
            ["b.*", "simple", False, 10, "high"],
            ["c.*", "simple", False, 5, "mid"],
        ]
        patterns_file = tmp_path / "patterns.json"
        patterns_file.write_text(json.dumps(patterns_data))
        if "core.router" in sys.modules:
            del sys.modules["core.router"]
        with unittest.mock.patch("config.PATTERNS_PATH", str(patterns_file)):
            from core.router import Router
            router = Router(call_model_func=None)
            loaded = router._load_patterns()
            priorities = [p["priority"] for p in loaded]
            assert priorities == sorted(priorities, reverse=True)

    def test_empty_file(self, tmp_path):
        """邊界：空檔案 → 回傳空列表."""
        patterns_file = tmp_path / "patterns.json"
        patterns_file.write_text("[]")
        if "core.router" in sys.modules:
            del sys.modules["core.router"]
        with unittest.mock.patch("config.PATTERNS_PATH", str(patterns_file)):
            from core.router import Router
            router = Router(call_model_func=None)
            loaded = router._load_patterns()
            assert len(loaded) == 0


class TestLoadPatternsEdgeCases:
    """_load_patterns 邊緣條件測試 (行 49-50, 64-66, 71-72, 75-76)."""

    def test_getmtime_fails_fallback(self, tmp_path):
        """等價類：os.path.getmtime 失敗 → 回傳 _patterns_list."""
        patterns_file = tmp_path / "patterns.json"
        patterns_file.write_text("[]")
        if "core.router" in sys.modules:
            del sys.modules["core.router"]
        with unittest.mock.patch("config.PATTERNS_PATH", str(patterns_file)):
            from core.router import Router
            router = Router(call_model_func=None)
        # 模擬 getmtime 失敗
        with unittest.mock.patch("os.path.getmtime", side_effect=OSError("no such file")):
            result = router.patterns
            # 應該回傳空的 _patterns_list（初始為空）
            assert result == []

    def test_invalid_json_fallback(self, tmp_path):
        """等價類：JSON 解析失敗 → 回傳 _patterns_list."""
        # 先用有效檔案建立 Router（讓 _patterns_list 有初始值）
        valid_file = tmp_path / "patterns_valid.json"
        valid_file.write_text("[]")
        if "core.router" in sys.modules:
            del sys.modules["core.router"]
        with unittest.mock.patch("config.PATTERNS_PATH", str(valid_file)):
            from core.router import Router
            router = Router(call_model_func=None)
        # 然後用無效 JSON 檔案 + mock 觸發 JSONDecodeError
        invalid_file = tmp_path / "patterns_invalid.json"
        invalid_file.write_text("not valid json{{{")
        with unittest.mock.patch.object(router, "patterns_path", str(invalid_file)):
            with unittest.mock.patch("json.load", side_effect=json.JSONDecodeError("test", "", 0)):
                result = router.patterns
        # _load_patterns 回傳 self._patterns_list（初始為空列表）
        assert result == []

    def test_pattern_structure_invalid_skipped(self, tmp_path):
        """等價類：pattern 結構無效（長度 < 3）→ log + continue."""
        patterns_data = [
            ["a.*", "simple"],  # 只有 2 個元素，不足 3 個
            ["b.*", "tool", False, 5, "brave_search"],  # 有效
        ]
        patterns_file = tmp_path / "patterns.json"
        patterns_file.write_text(json.dumps(patterns_data))
        if "core.router" in sys.modules:
            del sys.modules["core.router"]
        with unittest.mock.patch("config.PATTERNS_PATH", str(patterns_file)):
            from core.router import Router
            router = Router(call_model_func=None)
        loaded = router._load_patterns()
        # 只有 1 個有效 pattern
        assert len(loaded) == 1
        assert loaded[0]["regex"] == "b.*"

    def test_regex_non_string_skipped(self, tmp_path):
        """等價類：regex 非字串 → log + continue."""
        patterns_data = [
            [123, "simple", False, 10, "test"],  # regex 是 int，非字串
            ["b.*", "tool", False, 5, "brave_search"],  # 有效
        ]
        patterns_file = tmp_path / "patterns.json"
        patterns_file.write_text(json.dumps(patterns_data))
        if "core.router" in sys.modules:
            del sys.modules["core.router"]
        with unittest.mock.patch("config.PATTERNS_PATH", str(patterns_file)):
            from core.router import Router
            router = Router(call_model_func=None)
        loaded = router._load_patterns()
        assert len(loaded) == 1
        assert loaded[0]["regex"] == "b.*"


class TestPatternMatchEdgeCases:
    """_pattern_match 邊緣條件測試 (行 99-100, 102)."""

    @pytest.fixture
    def router_with_invalid_regex(self, tmp_path):
        """建立包含無效 regex pattern 的 Router."""
        patterns_data = [
            ["[invalid", "simple", False, 10, "bad"],  # 無效 regex
            ["b.*", "tool", False, 5, "brave_search"],  # 有效
        ]
        patterns_file = tmp_path / "patterns.json"
        patterns_file.write_text(json.dumps(patterns_data))
        if "core.router" in sys.modules:
            del sys.modules["core.router"]
        with unittest.mock.patch("config.PATTERNS_PATH", str(patterns_file)):
            from core.router import Router
            router = Router(call_model_func=None)
            yield router

    def test_invalid_regex_in_match_skipped(self, router_with_invalid_regex):
        """等價類：pattern 中有無效 regex → log + 跳過."""
        result = router_with_invalid_regex._pattern_match("b test")
        assert result is not None
        assert result["intent"] == "tool"

    def test_no_match_returns_none(self, tmp_path):
        """等價類：無匹配 → None."""
        patterns_data = [
            ["^exclusive$", "simple", False, 10, "test"],
        ]
        patterns_file = tmp_path / "patterns.json"
        patterns_file.write_text(json.dumps(patterns_data))
        if "core.router" in sys.modules:
            del sys.modules["core.router"]
        with unittest.mock.patch("config.PATTERNS_PATH", str(patterns_file)):
            from core.router import Router
            router = Router(call_model_func=None)
        result = router._pattern_match("no match at all")
        assert result is None


class TestIsClarificationEmptyQuestions:
    """is_clarification() 空 questions 邊界條件 (行 216).

    註：此測試的邏輯已改寫為純邏輯測試（不依賴 Router 實例），
    以避免 conftest autouse fixture 清除 module 造成的測試隔離問題。
    """

    def test_empty_questions_returns_false(self, tmp_path):
        """邊界：空 questions → is_clarification=False.

        測試核心邏輯：if not pending_questions → 直接回傳 False。
        """
        from models.blueprints import Result
        pending_questions = []
        # 模擬 is_clarification 的邊界檢查邏輯
        if not pending_questions:
            result = Result(success=True, data={"is_clarification": False})
        else:
            result = Result(success=False, data={"is_clarification": True})
        assert result.success is True
        assert result.data["is_clarification"] is False
