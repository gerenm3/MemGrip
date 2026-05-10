"""Blueprints — Unit、Step 等資料結構定義"""

from dataclasses import dataclass, field
from typing import List, Optional
from enum import Enum


class UnitStatus(Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class StepStatus(Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


@dataclass
class Unit:
    """L1 產出：執行單元定義"""
    unit_id: str
    goal: str                        # 語意描述
    expected_input: str = ""         # 語意描述
    expected_output: str = ""        # 語意描述
    depends_on: List[str] = field(default_factory=list)
    mcp_server: Optional[str] = None  # null 表示純推理
    output_type: str = "INTERNAL"    # "INTERNAL", "CONTENT", 或 "ACTION"


@dataclass
class Step:
    """L2 產出：步驟定義"""
    step_id: str
    goal: str
    tool: Optional[dict] = None      # null 表示純推理；完整工具定義 {"type": "function", "function": {"name": "...", "parameters": {...}}}
    depends_on: List[str] = field(default_factory=list)
    output_type: str = "INTERNAL"    # "INTERNAL" 或 "GLOBAL"


@dataclass
class UnitResult:
    """執行結果：Unit 層級"""
    unit_id: str
    status: UnitStatus
    output: str = ""
    error: str = ""


@dataclass
class StepResult:
    """執行結果：Step 層級"""
    step_id: str
    status: StepStatus
    output: str = ""
    error: str = ""