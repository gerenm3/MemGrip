"""MemGrip v2 Blueprints — 資料結構定義

依據 docs/v2/DESIGN.md §4.0 定義
符合 docs/v2/PRINCIPLES.md 所有原則
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, List, Optional


## ── Status 枚舉（§5.8）──

class UnitStatus(Enum):
    """Unit 執行結果狀態"""
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class StepStatus(Enum):
    """Step 執行結果狀態"""
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class ClarificationState(Enum):
    """多輪澄清狀態機"""
    NORMAL = "NORMAL"
    AWAITING_CLARIFICATION = "AWAITING_CLARIFICATION"


## ── 核心資料結構（§4.0）──

@dataclass
class Unit:
    """Unit — 由 Disassembler 產出，供 StepPlanner / Scheduler / Orchestrator 使用

    Attributes:
        unit_id: 唯一識別碼（如 `unit_0`）
        goal: 該 Unit 要完成的目標描述
        expected_input: 預期輸入描述（上游 Unit 輸出或初始條件）
        expected_output: 預期輸出描述（由 Disassembler 從 Clarifier 的 success_criteria 轉化）
        output_type: INTERNAL / CONTENT / ACTION（見 §5.7）
        depends_on: 依賴的其他 Unit ID 列表
        mcp_server: 若需 MCP 工具，指定 server 名稱；否則為 None
        assigned_constraints: 分配給此 Unit 的 constraints 清單（由 Disassembler 從 Clarifier 分配）
    """
    unit_id: str
    goal: str
    expected_input: str = ""
    expected_output: str = ""
    depends_on: List[str] = field(default_factory=list)
    mcp_server: Optional[str] = None
    output_type: str = "INTERNAL"
    assigned_constraints: List[str] = field(default_factory=list)


@dataclass
class Step:
    """Step — 由 StepPlanner 產出，供 Scheduler / Executor / Verifier 使用

    Attributes:
        step_id: 唯一識別碼（如 `step_0`）
        goal: 該 Step 要完成的目標描述
        tool: 要呼叫的工具描述（含 server_name, tool_name 等）；無工具時為 None
        depends_on: 同 Unit 內依賴的其他 Step ID 列表
        upstream_depends: 跨 Unit 依賴的上游 Unit ID 列表
        output_type: INTERNAL / GLOBAL（見 §5.7）
    """
    step_id: str
    goal: str
    tool: Optional[dict] = None
    depends_on: List[str] = field(default_factory=list)
    upstream_depends: List[str] = field(default_factory=list)
    output_type: str = "INTERNAL"


## ── 執行結果（§4.0 / §4.1）──

@dataclass
class UnitResult:
    """Unit 層級執行結果

    Attributes:
        unit_id: 唯一識別碼
        status: 執行狀態（SUCCESS/FAILED/SKIPPED）
        output: 執行結果輸出
        error: 錯誤訊息
        replan_count: 重新規劃次數
        total_loop_count: 該 unit 所有 step 的 loop_count 總和
        step_loop_counts: 每個 step 的 agentic loop 實際執行次數
        constraint_checks: Verifier 對每條 assigned constraint 的二元判斷結果 [{"constraint": str, "satisfied": bool}, ...]
    """
    unit_id: str
    status: UnitStatus
    output: str = ""
    error: str = ""
    replan_count: int = 0
    total_loop_count: int = 0
    step_loop_counts: List[int] = field(default_factory=list)
    constraint_checks: List[dict] = field(default_factory=list)


@dataclass
class StepResult:
    """Step 層級執行結果

    Attributes:
        step_id: 唯一識別碼
        status: 執行狀態（SUCCESS/FAILED）
        output: 執行結果輸出
        error: 錯誤訊息
        loop_count: 該 step 的 agentic loop 實際執行次數
        output_type: INTERNAL / GLOBAL（見 §5.7）
    """
    step_id: str
    status: StepStatus
    output: str = ""
    error: str = ""
    loop_count: int = 0
    output_type: str = "INTERNAL"


@dataclass
class Result:
    """統一成功/失敗結果包裝（§4.1）

    公開 API 統一回傳型別，涉及 I/O 或可能失敗的操作一律使用此包裝。
    例外：純邏輯計算、不涉及 I/O、不會失敗的公開 API 可直接回傳資料型別。

    Attributes:
        success: 操作成功與否
        data: 成功時的資料，失敗時為 None
        error: 失敗時的錯誤訊息，成功時為空字串
        tool_calls: 模型呼叫回傳的工具呼叫列表，非工具呼叫時為空列表
    """
    success: bool
    data: Any = None
    error: str = ""
    tool_calls: List[dict] = field(default_factory=list)
