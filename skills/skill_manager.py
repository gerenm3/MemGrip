# skill_manager.py

import json
import os
import shutil
from datetime import datetime

SKILL_BASE_PATH = "/home/kali/memgrip/skills"
TASK_TYPES = ["global", "general", "software_dev", "it_security"]

def _skill_path(task_type: str) -> str:
    return os.path.join(SKILL_BASE_PATH, task_type)

def _current_skill_file(task_type: str) -> str:
    return os.path.join(_skill_path(task_type), "current.json")

def _history_dir(task_type: str) -> str:
    return os.path.join(_skill_path(task_type), "history")

def init_skill_dirs():
    """初始化所有任務類型的目錄"""
    for task_type in TASK_TYPES:
        os.makedirs(_history_dir(task_type), exist_ok=True)

def save_skill(task_type: str, skill_data: dict):
    """儲存當前 skill 指導"""
    with open(_current_skill_file(task_type), "w", encoding="utf-8") as f:
        json.dump(skill_data, f, ensure_ascii=False, indent=2)

def load_skill(task_type: str) -> dict:
    """載入當前 skill 指導，不存在則從 global 複製"""
    current_file = _current_skill_file(task_type)
    
    if not os.path.exists(current_file):
        # 從 global 複製作為起點
        global_file = _current_skill_file("global")
        if os.path.exists(global_file):
            shutil.copy(global_file, current_file)
        else:
            return {}
    
    with open(current_file, "r", encoding="utf-8") as f:
        return json.load(f)

def save_history(task_type: str, diagnosis: dict, update: dict):
    """儲存修改歷史"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    history_file = os.path.join(
        _history_dir(task_type), 
        f"{timestamp}.json"
    )
    record = {
        "timestamp": timestamp,
        "diagnosis": diagnosis,
        "update": update
    }
    with open(history_file, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)

def apply_update(task_type: str, updated_skills: dict, diagnosis: dict):
    """套用診斷結果到 skill 指導並儲存歷史"""
    current = load_skill(task_type)
    
    # 只更新被修改的維度
    for dimension, content in updated_skills.items():
        current[dimension] = content
    
    save_skill(task_type, current)
    save_history(task_type, diagnosis, updated_skills)
    
    return current


def skill_guide_to_prompt(skill_guide) -> str:
    """將 skill_guide（五個維度）或字串轉換為適合注入 prompt 的純文字字串。

    每個維度輸出一個段落，格式：
    [維度名稱]
    核心概念：{core_concept}
    可用方向：
    - {key}：{prompt_patterns[key]}
    ...
    設計原則：
    - {design_principles[0]}
    - ...
    注意事項：
    - {pitfalls[0]}
    - {pitfalls[1]}

    不輸出 usage_guidelines 等結構性欄位。
    """
    if not skill_guide:
        return ""

    # 如果已經是字串，直接返回
    if isinstance(skill_guide, str):
        return skill_guide

    segments = []
    for dimension_name, dimension_data in skill_guide.items():
        if not dimension_data:
            continue

        # 核心概念
        core_concept = dimension_data.get("core_concept", "")
        if not core_concept:
            continue

        # 可用方向（prompt_patterns 的所有 key-value）
        prompt_patterns = dimension_data.get("prompt_patterns", {})

        # 設計原則（全部列舉）
        design_principles = dimension_data.get("design_principles", [])

        # 注意事項（僅前兩條）
        pitfalls = dimension_data.get("pitfalls", [])[:2]

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
