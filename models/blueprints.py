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
    goal: str
    expected_input: str = ""
    expected_output: str = ""
    depends_on: List[str] = field(default_factory=list)
    mcp_server: Optional[str] = None
    output_type: str = "INTERNAL"


@dataclass
class Step:
    """L2 產出：步驟定義"""
    step_id: str
    goal: str
    tool: Optional[dict] = None
    depends_on: List[str] = field(default_factory=list)
    upstream_depends: List[str] = field(default_factory=list)
    output_type: str = "INTERNAL"


@dataclass
class UnitResult:
    """執行結果：Unit 層級"""
    unit_id: str
    status: UnitStatus
    output: str = ""
    error: str = ""
    replan_count: int = 0
    total_loop_count: int = 0
    step_loop_counts: list = field(default_factory=list)


@dataclass
class StepResult:
    """執行結果：Step 層級"""
    step_id: str
    status: StepStatus
    output: str = ""
    error: str = ""
    loop_count: int = 0
