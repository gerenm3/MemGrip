"""tests/L1/test_skill_manager_logic — SkillManager 純邏輯測試（10 筆）."""

import json
import os
import tempfile
import unittest.mock
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def skill_manager():
    """SkillManager instance fixture."""
    from skills.skill_manager import SkillManager
    return SkillManager()


@pytest.fixture
def temp_skill_dir():
    """建立臨時 skills 目錄."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


class TestSkillPathHelpers:
    """測試路徑輔助方法."""

    def test_level_path(self, skill_manager):
        """等價類：_level_path 回傳 skills/{level}/."""
        result = skill_manager._level_path("l1")
        assert "l1" in result

    def test_skill_path(self, skill_manager):
        """等價類：_skill_path 回傳 skills/{level}/{task_type}/."""
        result = skill_manager._skill_path("software_dev", "l1")
        assert "l1" in result
        assert "software_dev" in result

    def test_current_skill_file(self, skill_manager):
        """等價類：_current_skill_file 回傳 current.json 路徑."""
        result = skill_manager._current_skill_file("software_dev", "l1")
        assert "current.json" in result

    def test_history_dir(self, skill_manager):
        """等價類：_history_dir 回傳 history 目錄路徑."""
        result = skill_manager._history_dir("software_dev", "l1")
        assert "history" in result


class TestInitSkillDirs:
    """測試 init_skill_dirs 方法."""

    def test_init_skill_dirs_creates_directory(self, skill_manager, temp_skill_dir):
        """等價類：init_skill_dirs 建立目錄."""
        skill_manager.init_skill_dirs("software_dev", "l1")
        # 目錄存在
        assert os.path.exists(temp_skill_dir)


class TestSaveLoadSkill:
    """測試 save_skill / load_skill 方法."""

    def test_save_and_load_skill(self, skill_manager, temp_skill_dir):
        """等價類：儲存後載入 → 回傳相同資料."""
        skill_data = {
            "skill_version": 1,
            "core_concept": "test concept",
        }
        with patch("skills.skill_manager.SKILL_BASE_PATH", temp_skill_dir):
            skill_manager.init_skill_dirs("software_dev", "l1")
            skill_manager.save_skill("software_dev", skill_data, "l1")
            loaded = skill_manager.load_skill("software_dev", "l1")
            assert loaded["skill_version"] == 1
            assert loaded["core_concept"] == "test concept"

    def test_load_skill_not_exists_returns_empty(self, skill_manager, temp_skill_dir):
        """邊界：檔案不存在 → 回傳空 dict."""
        with patch("skills.skill_manager.SKILL_BASE_PATH", temp_skill_dir):
            result = skill_manager.load_skill("nonexistent", "l1")
            assert result == {}


class TestGetVersion:
    """測試 get_version 方法."""

    def test_get_version_exists(self, skill_manager, temp_skill_dir):
        """等價類：skill 存在 → 回傳 skill_version."""
        skill_data = {"skill_version": 3}
        with patch("skills.skill_manager.SKILL_BASE_PATH", temp_skill_dir):
            skill_manager.init_skill_dirs("software_dev", "l1")
            skill_manager.save_skill("software_dev", skill_data, "l1")
            result = skill_manager.get_version("software_dev", "l1")
            assert result == 3

    def test_get_version_not_exists(self, skill_manager, temp_skill_dir):
        """邊界：skill 不存在 → 回傳 0."""
        with patch("skills.skill_manager.SKILL_BASE_PATH", temp_skill_dir):
            result = skill_manager.get_version("nonexistent", "l1")
            assert result == 0


class TestApplyUpdate:
    """測試 apply_update 方法."""

    def test_apply_update_increments_version(self, skill_manager, temp_skill_dir):
        """等價類：apply_update 遞增 skill_version."""
        skill_data = {"skill_version": 1, "core_concept": "old"}
        with patch("skills.skill_manager.SKILL_BASE_PATH", temp_skill_dir):
            skill_manager.init_skill_dirs("software_dev", "l1")
            skill_manager.save_skill("software_dev", skill_data, "l1")

            updated = skill_manager.apply_update(
                "software_dev",
                {"core_concept": "new"},
                {"diagnosis": "test"},
                "l1",
            )
            assert updated["skill_version"] == 2
            assert updated["core_concept"] == "new"


class TestSkillGuideToPrompt:
    """測試 skill_guide_to_prompt 方法."""

    def test_skill_guide_to_prompt_with_data(self, skill_manager):
        """等價類：有 skill_guide → 轉換為 prompt 字串."""
        skill_guide = {
            "security": {
                "core_concept": "security first",
                "prompt_patterns": {"pattern1": "value1"},
                "design_principles": ["principle1"],
                "pitfalls": ["pitfall1"],
            }
        }
        result = skill_manager.skill_guide_to_prompt(skill_guide)
        assert "security" in result
        assert "security first" in result
        assert "pattern1" in result

    def test_skill_guide_to_prompt_empty(self, skill_manager):
        """邊界：空 skill_guide → 空字串."""
        result = skill_manager.skill_guide_to_prompt(None)
        assert result == ""

    def test_skill_guide_to_prompt_string(self, skill_manager):
        """等價類：skill_guide 是字串 → 直接回傳."""
        guide_str = "plain text guide"
        result = skill_manager.skill_guide_to_prompt(guide_str)
        assert result == guide_str