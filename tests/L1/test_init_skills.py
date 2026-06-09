"""L1 test plan for init_skills (#18).

Test cases from docs/test_plan_l1/18_init_skills.md.
Only pure string formatting functions are in scope per l1_scope.md.

黑箱限制：無法注入 config.SKILL_DIMENSIONS，因此 TC-18-02（空維度）
無法黑箱驗證，改為測試無參數呼叫的回傳值。
"""
import pytest


class TestInitSkills:
    """Test init_skills per test plan #18 (L1 scope only)."""

    def test_TC_18_01_build_dimensions_text_normal(self):
        """TC-18-01: _build_dimensions_text - 正常生成."""
        from skills.init_skills import _build_dimensions_text
        result = _build_dimensions_text()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_TC_18_02_build_dimensions_text_empty(self, monkeypatch):
        """TC-18-02: _build_dimensions_text - 空維度.

        Note: Source code does not return empty string for empty SKILL_DIMENSIONS (DEF-009).
        This test remains failing to document the defect.
        """
        from skills import init_skills
        monkeypatch.setattr(init_skills.config, "SKILL_DIMENSIONS", {})
        result = init_skills._build_dimensions_text()
        # Source code returns header string for empty dimensions (DEF-009)
        assert result == ""

    def test_TC_18_03_build_l1_prompt_normal(self):
        """TC-18-03: _build_l1_prompt - 正常生成."""
        from skills.init_skills import _build_l1_prompt
        result = _build_l1_prompt("general")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_TC_18_04_build_l1_prompt_empty_domain(self):
        """TC-18-04: _build_l1_prompt - domain 為空."""
        from skills.init_skills import _build_l1_prompt
        result = _build_l1_prompt("")
        assert isinstance(result, str)

    def test_TC_18_05_build_l2_prompt_normal(self):
        """TC-18-05: _build_l2_prompt - 正常生成."""
        from skills.init_skills import _build_l2_prompt
        result = _build_l2_prompt("general")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_TC_18_06_build_l2_prompt_empty_domain(self):
        """TC-18-06: _build_l2_prompt - domain 為空."""
        from skills.init_skills import _build_l2_prompt
        result = _build_l2_prompt("")
        assert isinstance(result, str)