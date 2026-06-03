"""v2 skill_manager — Skill 管理.

依據 §3.12 (SkillManager) 定義：
- class SkillManager，供 Orchestrator 透過 DI 注入
- load_skill / save_skill / skill_guide_to_prompt 改為 instance method
- 保持現有邏輯
- 符合 v2 logging 規範
"""

import json
import logging
import os
import threading
from datetime import datetime
from typing import Any

import config

logger = logging.getLogger(__name__)

_SKILL_LOCK = threading.RLock()
SKILL_BASE_PATH = config.SKILL_DIR_BASE
TASK_TYPES = config.TASK_TYPES

# Prompt 常數
MAX_PITFALLS_IN_PROMPT = 2


class SkillManager:
    """Skill Guide 管理器."""

    def _level_path(self, level: str) -> str:
        """回傳 skills/{level}/ 路徑"""
        return os.path.join(SKILL_BASE_PATH, level)

    def _skill_path(self, task_type: str, level: str = "global") -> str:
        """回傳 skills/{level}/{task_type}/ 路徑"""
        return os.path.join(self._level_path(level), task_type)

    def _current_skill_file(self, task_type: str, level: str = "global") -> str:
        return os.path.join(self._skill_path(task_type, level), "current.json")

    def _history_dir(self, task_type: str, level: str = "global") -> str:
        return os.path.join(self._skill_path(task_type, level), "history")

    def init_skill_dirs(self, task_type: str = "global", level: str = "global") -> None:
        """初始化 skills/{level}/{task_type}/ 及 history 目錄."""
        if task_type == "global":
            base = self._level_path(level)
        else:
            base = self._skill_path(task_type, level)
        os.makedirs(base, exist_ok=True)
        os.makedirs(self._history_dir(task_type, level), exist_ok=True)

    def save_skill(self, task_type: str, skill_data: dict[str, Any], level: str = "l1") -> None:
        """儲存當前 skill 指導"""
        fpath = self._current_skill_file(task_type, level)
        os.makedirs(os.path.dirname(fpath), exist_ok=True)
        with _SKILL_LOCK:
            with open(fpath, "w", encoding="utf-8") as f:
                json.dump(skill_data, f, ensure_ascii=False, indent=2)

    def load_skill(self, task_type: str, level: str = "l1") -> dict[str, Any]:
        """載入當前 skill 指導."""
        current_file = self._current_skill_file(task_type, level)
        if not os.path.exists(current_file):
            global_file = self._current_skill_file("global", level)
            if os.path.exists(global_file):
                with _SKILL_LOCK:
                    with open(global_file, "r", encoding="utf-8") as gf:
                        content = gf.read()
                    with open(current_file, "w", encoding="utf-8") as cf:
                        json.dump(json.loads(content), cf, ensure_ascii=False, indent=2)
                return json.loads(content)
            return {}
        with _SKILL_LOCK:
            with open(current_file, "r", encoding="utf-8") as f:
                return json.load(f)

    def save_history(self, task_type: str, diagnosis: dict[str, Any], update: dict[str, Any], level: str = "l1") -> str:
        """儲存修改歷史。回傳 history 檔案路徑."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        history_file = os.path.join(self._history_dir(task_type, level), f"{timestamp}.json")
        record = {
            "timestamp": timestamp,
            "diagnosis": diagnosis,
            "update": update,
        }
        with open(history_file, "w", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False, indent=2)
        return history_file

    def get_version(self, task_type: str, level: str = "l1") -> int:
        """回傳當前 skill 的版本號，不存在時回傳 0."""
        current = self.load_skill(task_type, level)
        return current.get("skill_version", 0) if current else 0

    def apply_update(self, task_type: str, updated_skills: dict[str, Any], diagnosis: dict[str, Any], level: str = "l1") -> dict[str, Any]:
        """套用診斷結果到 skill 指導並儲存歷史。
        
        自動遞增 skill_version。
        """
        with _SKILL_LOCK:
            current = self.load_skill(task_type, level)
            for dimension, content in updated_skills.items():
                current[dimension] = content
            # 遞增版本號
            current["skill_version"] = current.get("skill_version", 0) + 1
            self.save_skill(task_type, current, level)
            self.save_history(task_type, diagnosis, updated_skills, level)
        return current

    def skill_guide_to_prompt(self, skill_guide: Any) -> str:
        """將 skill_guide 轉換為適合注入 prompt 的純文字字串."""
        if not skill_guide:
            return ""
        if isinstance(skill_guide, str):
            return skill_guide

        segments = []
        for dimension_name, dimension_data in skill_guide.items():
            if not dimension_data:
                continue
            core_concept = dimension_data.get("core_concept", "")
            if not core_concept:
                continue
            prompt_patterns = dimension_data.get("prompt_patterns", {})
            design_principles = dimension_data.get("design_principles", [])
            pitfalls = dimension_data.get("pitfalls", [])[:MAX_PITFALLS_IN_PROMPT]

            lines = [
                f"[{dimension_name}]",
                f"核心概念：{core_concept}",
                "可用方向：",
            ]
            for key, value in prompt_patterns.items():
                lines.append(f"- {key}：{value}")
            lines.append("設計原則：")
            for dp in design_principles:
                lines.append(f"- {dp}")
            lines.append("注意事項：")
            for p in pitfalls:
                lines.append(f"- {p}")
            segments.append("\n".join(lines))

        return "\n\n".join(segments)

    def build_prompt(self, domain: str, level: str = "l1") -> str:
        """建構 domain prompt：domain → Skill Guide → fallback global → 空字串."""
        try:
            skill_data = self.load_skill(domain, level)
            if skill_data:
                return self.skill_guide_to_prompt(skill_data)
        except Exception as e:
            logger.warning("[SkillManager] 無法載入 domain=%s skill: %s", domain, e)

        # Fallback 到 global
        try:
            skill_data = self.load_skill("global", level)
            if skill_data:
                return self.skill_guide_to_prompt(skill_data)
        except Exception as e:
            logger.warning("[SkillManager] 無法載入 global skill: %s", e)

        return ""
