"""L1 test plan for FileRWAdapter (#17).

Test cases from docs/test_plan_l1/17_file_rw_adapter.md.
Per l1_scope.md: name, get_server_params, get_env_prompt, get_description are in scope.
"""
import pytest


class TestFileRWAdapter:
    """Test FileRWAdapter per test plan #17 (L1 scope)."""

    def _make_adapter(self):
        """Create a FileRWAdapter instance."""
        from clients.mcp_adapters.file_rw import FileRWAdapter
        return FileRWAdapter()

    def test_TC_17_01_name_property(self):
        """TC-17-01: name property - 正常回傳."""
        adapter = self._make_adapter()
        assert adapter.name is not None
        assert isinstance(adapter.name, str)

    def test_TC_17_02_get_server_params(self):
        """TC-17-02: get_server_params - 回傳 StdioServerParameters."""
        from mcp import StdioServerParameters
        adapter = self._make_adapter()
        params = adapter.get_server_params()
        assert isinstance(params, StdioServerParameters)

    def test_TC_17_03_get_env_prompt(self):
        """TC-17-03: get_env_prompt - 回傳非空字串."""
        adapter = self._make_adapter()
        prompt = adapter.get_env_prompt()
        assert isinstance(prompt, str)
        assert len(prompt) > 0

    def test_TC_17_04_get_description(self):
        """TC-17-04: get_description - 回傳非空字串."""
        adapter = self._make_adapter()
        desc = adapter.get_description()
        assert isinstance(desc, str)
        assert len(desc) > 0