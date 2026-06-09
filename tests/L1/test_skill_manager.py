"""Test plan L1 - SkillManager (#14)

L1 scope (per l1_scope.md): init_skill_dirs, save_skill, load_skill, get_version,
  apply_update, skill_guide_to_prompt, take_snapshot, rollback_to, build_prompt

Total: 29 test cases (TC-14-01 ~ TC-14-29)
"""

import json
import os
import shutil
import pytest
from unittest.mock import MagicMock, patch
from skills.skill_manager import SkillManager


# ── Fixtures ──────────────────────────────────────────────────────────

@pytest.fixture
def sm(tmp_path, monkeypatch):
    """Create SkillManager with tmp_path as base dir."""
    monkeypatch.setattr('skills.skill_manager.SKILL_BASE_PATH', str(tmp_path / "skills"))
    return SkillManager()


# ── SkillManager.init_skill_dirs ──────────────────────────────────────

class TestSkillManagerInitSkillDirs:
    """TC-14-01 ~ TC-14-02"""

    def test_TC_14_01_init_skill_dirs_normal(self, sm, tmp_path):
        """TC-14-01: init_skill_dirs - 正常初始化"""
        task_dir = tmp_path / "skills" / "l1" / "software_dev"
        sm.init_skill_dirs("software_dev", "l1")
        assert task_dir.exists()
        history_dir = task_dir / "history"
        assert history_dir.exists()

    def test_TC_14_02_init_skill_dirs_exists(self, sm, tmp_path):
        """TC-14-02: init_skill_dirs - 目錄已存在"""
        task_dir = tmp_path / "skills" / "l1" / "software_dev"
        task_dir.mkdir(parents=True)
        # Should not raise
        sm.init_skill_dirs("software_dev", "l1")
        assert task_dir.exists()


# ── SkillManager.save_skill ──────────────────────────────────────

class TestSkillManagerSaveSkill:
    """TC-14-03 ~ TC-14-05"""

    def test_TC_14_03_save_skill_normal(self, sm, tmp_path):
        """TC-14-03: save_skill - 正常儲存"""
        skill_data = {"reasoning_resolution": {"core_concept": "C"}}
        sm.save_skill("software_dev", skill_data, "l1")
        current_file = tmp_path / "skills" / "l1" / "software_dev" / "current.json"
        assert current_file.exists()
        with open(current_file) as f:
            saved = json.load(f)
        assert saved["reasoning_resolution"]["core_concept"] == "C"

    def test_TC_14_04_save_skill_dir_auto_create(self, sm, tmp_path):
        """TC-14-04: save_skill - 目錄不存在自動建立"""
        skill_data = {"reasoning_resolution": {"core_concept": "C"}}
        sm.save_skill("software_dev", skill_data, "l1")
        current_file = tmp_path / "skills" / "l1" / "software_dev" / "current.json"
        assert current_file.exists()

    def test_TC_14_05_save_skill_empty_dict(self, sm, tmp_path):
        """TC-14-05: save_skill - skill_data 為空 dict"""
        sm.save_skill("software_dev", {}, "l1")
        current_file = tmp_path / "skills" / "l1" / "software_dev" / "current.json"
        with open(current_file) as f:
            saved = json.load(f)
        assert saved == {}


# ── SkillManager.load_skill ──────────────────────────────────────

class TestSkillManagerLoadSkill:
    """TC-14-06 ~ TC-14-08, TC-14-26"""

    def test_TC_14_06_load_skill_normal(self, sm, tmp_path):
        """TC-14-06: load_skill - 正常載入"""
        current_file = tmp_path / "skills" / "l1" / "software_dev" / "current.json"
        current_file.parent.mkdir(parents=True)
        with open(current_file, "w") as f:
            json.dump({"reasoning_resolution": {"core_concept": "C"}}, f)
        result = sm.load_skill("software_dev", "l1")
        assert result["reasoning_resolution"]["core_concept"] == "C"

    def test_TC_14_07_load_skill_not_exists(self, sm, tmp_path):
        """TC-14-07: load_skill - current.json 不存在"""
        result = sm.load_skill("software_dev", "l1")
        assert result == {}

    def test_TC_14_08_load_skill_json_decode_error(self, sm, tmp_path):
        """TC-14-08: load_skill - JSON 解析失敗"""
        current_file = tmp_path / "skills" / "l1" / "software_dev" / "current.json"
        current_file.parent.mkdir(parents=True)
        with open(current_file, "w") as f:
            f.write("invalid json{{{")
        with pytest.raises(json.JSONDecodeError):
            sm.load_skill("software_dev", "l1")

    def test_TC_14_26_load_skill_fallback_global(self, sm, tmp_path):
        """TC-14-26: load_skill - fallback to global"""
        domain_file = tmp_path / "skills" / "l1" / "software_dev" / "current.json"
        domain_file.parent.mkdir(parents=True)
        global_file = tmp_path / "skills" / "l1" / "global" / "current.json"
        global_file.parent.mkdir(parents=True)
        with open(global_file, "w") as f:
            json.dump({"global_key": "global_val"}, f)
        # domain file does not exist
        result = sm.load_skill("software_dev", "l1")
        assert result["global_key"] == "global_val"
        # Should write to domain file
        assert domain_file.exists()


# ── SkillManager.get_version ──────────────────────────────────────

class TestSkillManagerGetVersion:
    """TC-14-09 ~ TC-14-11"""

    def test_TC_14_09_get_version_normal(self, sm, tmp_path):
        """TC-14-09: get_version - 正常取得版本號"""
        current_file = tmp_path / "skills" / "l1" / "software_dev" / "current.json"
        current_file.parent.mkdir(parents=True)
        with open(current_file, "w") as f:
            json.dump({"skill_version": 3}, f)
        result = sm.get_version("software_dev", "l1")
        assert result == 3

    def test_TC_14_10_get_version_no_skill_version(self, sm, tmp_path):
        """TC-14-10: get_version - skill_version 欄位不存在"""
        current_file = tmp_path / "skills" / "l1" / "software_dev" / "current.json"
        current_file.parent.mkdir(parents=True)
        with open(current_file, "w") as f:
            json.dump({"reasoning_resolution": {}}, f)
        result = sm.get_version("software_dev", "l1")
        assert result == 0

    def test_TC_14_11_get_version_skill_not_exists(self, sm, tmp_path):
        """TC-14-11: get_version - skill 不存在"""
        result = sm.get_version("software_dev", "l1")
        assert result == 0


# ── SkillManager.apply_update ──────────────────────────────────────

class TestSkillManagerApplyUpdate:
    """TC-14-12 ~ TC-14-13"""

    def test_TC_14_12_apply_update_normal(self, sm, tmp_path):
        """TC-14-12: apply_update - 正常更新"""
        sm.init_skill_dirs("software_dev", "l1")
        current_file = tmp_path / "skills" / "l1" / "software_dev" / "current.json"
        with open(current_file, "w") as f:
            json.dump({"skill_version": 1, "reasoning_resolution": {"core_concept": "Old"}}, f)
        updated_skills = {"reasoning_resolution": {"core_concept": "New"}}
        result = sm.apply_update("software_dev", updated_skills, {"diagnosis": "D"}, "l1")
        assert result["skill_version"] == 2
        assert result["reasoning_resolution"]["core_concept"] == "New"
        with open(current_file) as f:
            saved = json.load(f)
        assert saved["skill_version"] == 2

    def test_TC_14_13_apply_update_empty_updated(self, sm, tmp_path):
        """TC-14-13: apply_update - updated_skills 為空"""
        sm.init_skill_dirs("software_dev", "l1")
        current_file = tmp_path / "skills" / "l1" / "software_dev" / "current.json"
        with open(current_file, "w") as f:
            json.dump({"skill_version": 1}, f)
        result = sm.apply_update("software_dev", {}, {"diagnosis": "D"}, "l1")
        assert result["skill_version"] == 2


# ── SkillManager.skill_guide_to_prompt ──────────────────────────────────────

class TestSkillManagerSkillGuideToPrompt:
    """TC-14-14 ~ TC-14-21"""

    def test_TC_14_14_skill_guide_to_prompt_normal(self, sm):
        """TC-14-14: skill_guide_to_prompt - 正常轉換"""
        skill_guide = {
            "reasoning_resolution": {
                "core_concept": "C",
                "prompt_patterns": {"simple": "S"},
                "design_principles": ["DP1"],
                "pitfalls": ["P1"]
            }
        }
        result = sm.skill_guide_to_prompt(skill_guide)
        assert "reasoning_resolution" in result
        assert "核心概念：C" in result
        assert "可用方向" in result
        assert "設計原則" in result
        assert "注意事項" in result

    def test_TC_14_15_skill_guide_to_prompt_empty_dict(self, sm):
        """TC-14-15: skill_guide_to_prompt - skill_guide 為空 dict"""
        result = sm.skill_guide_to_prompt({})
        assert result == ""

    def test_TC_14_16_skill_guide_to_prompt_str(self, sm):
        """TC-14-16: skill_guide_to_prompt - skill_guide 為 str"""
        result = sm.skill_guide_to_prompt("custom text")
        assert result == "custom text"

    def test_TC_14_17_skill_guide_to_prompt_core_concept_missing(self, sm):
        """TC-14-17: skill_guide_to_prompt - core_concept 缺失"""
        skill_guide = {
            "reasoning_resolution": {
                "prompt_patterns": {},
                "design_principles": [],
                "pitfalls": []
            }
        }
        result = sm.skill_guide_to_prompt(skill_guide)
        # Should skip this dimension (no blocks produced)
        assert result == ""

    def test_TC_14_18_skill_guide_to_prompt_prompt_patterns_empty(self, sm):
        """TC-14-18: skill_guide_to_prompt - prompt_patterns 為空"""
        skill_guide = {
            "reasoning_resolution": {
                "core_concept": "C",
                "prompt_patterns": {},
                "design_principles": [],
                "pitfalls": []
            }
        }
        result = sm.skill_guide_to_prompt(skill_guide)
        assert "可用方向" in result

    def test_TC_14_19_skill_guide_to_prompt_design_principles_empty(self, sm):
        """TC-14-19: skill_guide_to_prompt - design_principles 為空"""
        skill_guide = {
            "reasoning_resolution": {
                "core_concept": "C",
                "design_principles": [],
                "prompt_patterns": {},
                "pitfalls": []
            }
        }
        result = sm.skill_guide_to_prompt(skill_guide)
        assert "設計原則" in result

    def test_TC_14_20_skill_guide_to_prompt_pitfalls_empty(self, sm):
        """TC-14-20: skill_guide_to_prompt - pitfalls 為空"""
        skill_guide = {
            "reasoning_resolution": {
                "core_concept": "C",
                "pitfalls": [],
                "prompt_patterns": {},
                "design_principles": []
            }
        }
        result = sm.skill_guide_to_prompt(skill_guide)
        assert "注意事項" in result

    def test_TC_14_21_skill_guide_to_prompt_pitfalls_exceed_max(self, sm):
        """TC-14-21: skill_guide_to_prompt - pitfalls 超過 MAX_PITFALLS_IN_PROMPT(2)"""
        skill_guide = {
            "reasoning_resolution": {
                "core_concept": "C",
                "pitfalls": ["P1", "P2", "P3", "P4"]
            }
        }
        result = sm.skill_guide_to_prompt(skill_guide)
        assert "P1" in result
        assert "P2" in result
        assert "P3" not in result
        assert "P4" not in result


# ── SkillManager.take_snapshot / rollback_to ──────────────────────────────────────

class TestSkillManagerSnapshotRollback:
    """TC-14-22 ~ TC-14-25"""

    def test_TC_14_22_take_snapshot_normal(self, sm, tmp_path):
        """TC-14-22: take_snapshot - 正常快照"""
        current_file = tmp_path / "skills" / "l1" / "software_dev" / "current.json"
        current_file.parent.mkdir(parents=True)
        with open(current_file, "w") as f:
            json.dump({"reasoning_resolution": {"core_concept": "C"}}, f)
        snapshot = sm.take_snapshot("software_dev", "l1")
        # Modify snapshot
        snapshot["reasoning_resolution"]["core_concept"] = "Modified"
        # Original should not change
        with open(current_file) as f:
            saved = json.load(f)
        assert saved["reasoning_resolution"]["core_concept"] == "C"

    def test_TC_14_23_take_snapshot_skill_not_exists(self, sm, tmp_path):
        """TC-14-23: take_snapshot - skill 不存在"""
        result = sm.take_snapshot("software_dev", "l1")
        assert result == {}

    def test_TC_14_24_rollback_to_normal(self, sm, tmp_path):
        """TC-14-24: rollback_to - 正常回滾"""
        sm.init_skill_dirs("software_dev", "l1")
        current_file = tmp_path / "skills" / "l1" / "software_dev" / "current.json"
        with open(current_file, "w") as f:
            json.dump({"reasoning_resolution": {"core_concept": "Current"}}, f)
        snapshot = {"reasoning_resolution": {"core_concept": "Original"}}
        sm.rollback_to("software_dev", "l1", snapshot)
        with open(current_file) as f:
            saved = json.load(f)
        assert saved["reasoning_resolution"]["core_concept"] == "Original"

    def test_TC_14_25_rollback_to_empty_snapshot(self, sm, tmp_path):
        """TC-14-25: rollback_to - snapshot 為空"""
        sm.init_skill_dirs("software_dev", "l1")
        current_file = tmp_path / "skills" / "l1" / "software_dev" / "current.json"
        with open(current_file, "w") as f:
            json.dump({"reasoning_resolution": {"core_concept": "C"}}, f)
        sm.rollback_to("software_dev", "l1", {})
        with open(current_file) as f:
            saved = json.load(f)
        assert saved == {}


# ── SkillManager.build_prompt ──────────────────────────────────────

class TestSkillManagerBuildPrompt:
    """TC-14-27 ~ TC-14-29"""

    def test_TC_14_27_build_prompt_domain_exists(self, sm, tmp_path):
        """TC-14-27: build_prompt - domain 存在"""
        current_file = tmp_path / "skills" / "l1" / "software_dev" / "current.json"
        current_file.parent.mkdir(parents=True)
        with open(current_file, "w") as f:
            json.dump({"reasoning_resolution": {"core_concept": "C"}}, f)
        result = sm.build_prompt("software_dev", "l1")
        assert "核心概念" in result

    def test_TC_14_28_build_prompt_domain_not_exists_fallback_global(self, sm, tmp_path):
        """TC-14-28: build_prompt - domain 不存在 fallback global"""
        global_file = tmp_path / "skills" / "l1" / "global" / "current.json"
        global_file.parent.mkdir(parents=True)
        with open(global_file, "w") as f:
            json.dump({"reasoning_resolution": {"core_concept": "GlobalC"}}, f)
        result = sm.build_prompt("software_dev", "l1")
        assert "GlobalC" in result

    def test_TC_14_29_build_prompt_all_not_exists(self, sm, tmp_path):
        """TC-14-29: build_prompt - 全部不存在"""
        result = sm.build_prompt("software_dev", "l1")
        assert result == ""