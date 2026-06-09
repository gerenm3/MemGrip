"""L1 test plan for BraveSearchAdapter (#16).

Test cases from docs/test_plan_l1/16_brave_search_adapter.md.
Per l1_scope.md: name, get_server_params, get_env_prompt, get_description are in scope.
get_server_params skipped: requires BRAVE_SEARCH_API_KEY to be set (external dependency).
"""
import pytest


class TestBraveSearchAdapter:
    """Test BraveSearchAdapter per test plan #16 (L1 scope)."""

    def _make_adapter(self):
        """Create a BraveSearchAdapter instance."""
        from clients.mcp_adapters.brave_search import BraveSearchAdapter
        return BraveSearchAdapter()

    def test_TC_16_01_name_property(self):
        """TC-16-01: name property - 正常回傳."""
        adapter = self._make_adapter()
        assert adapter.name is not None
        assert isinstance(adapter.name, str)

    def test_TC_16_02_get_server_params(self):
        """TC-16-02: get_server_params - API key 未設定時拋出 ValueError."""
        adapter = self._make_adapter()
        with pytest.raises(ValueError):
            adapter.get_server_params()

    def test_TC_16_03_get_env_prompt(self):
        """TC-16-03: get_env_prompt - 回傳非空字串."""
        adapter = self._make_adapter()
        prompt = adapter.get_env_prompt()
        assert isinstance(prompt, str)
        assert len(prompt) > 0

    def test_TC_16_04_get_description(self):
        """TC-16-04: get_description - 回傳非空字串."""
        adapter = self._make_adapter()
        desc = adapter.get_description()
        assert isinstance(desc, str)
        assert len(desc) > 0