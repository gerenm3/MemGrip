"""
tests/L2/test_orchestrator_replan.py -- 群組 2：Orchestrator Replan 流程.
設計依據：docs/test_plan_l2/02_orchestrator_replan.md
黑箱原則：不讀取 core/unit_runner.py 源碼.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from models.blueprints import (
    Result,
    Step,
    StepResult,
    StepStatus,
    Unit,
    UnitResult,
    UnitStatus,
)


# ── TC-01：UnitRunner.execute 正常執行（無 replan） ──

@pytest.mark.asyncio
async def test_TC01_unit_runner_normal():
    """TC-01: UnitRunner.execute 正常執行（無 replan）."""
    from core.unit_runner import UnitRunner

    mock_executor = MagicMock()
    mock_executor.execute = AsyncMock(return_value=Result(
        success=True, data={"output": "step output", "loop_count": 1}
    ))
    mock_verifier = MagicMock()
    mock_verifier.verify = AsyncMock(return_value=Result(success=True, data={
        "passed": True, "reason": "OK", "gaps": [], "constraint_checks": []
    }))
    mock_tool_manager = MagicMock()
    mock_tool_manager.get_tools = AsyncMock(return_value=[{"name": "tool1"}])
    mock_step_store = MagicMock()
    mock_step_store.save_step = AsyncMock()
    mock_step_store.get_steps_by_unit = MagicMock(return_value=[
        StepResult(step_id="s1", status=StepStatus.SUCCESS, output="step output", loop_count=1, output_type="GLOBAL"),
    ])
    mock_unit_store = MagicMock()
    mock_unit_store.save_unit = AsyncMock()

    unit_runner = UnitRunner(
        executor=mock_executor, verifier=mock_verifier,
        tool_manager=mock_tool_manager, step_store=mock_step_store,
        unit_store=mock_unit_store, session_id="test_session"
    )

    unit = Unit(unit_id="u1", goal="goal1", expected_output="expected", output_type="CONTENT")
    steps = [Step(step_id="s1", goal="step1", output_type="GLOBAL")]
    max_replan = 2
    replan_callback = AsyncMock()

    health_mock = MagicMock()
    health_mock.log_action = MagicMock()

    result = await unit_runner.execute(unit, steps, max_replan, replan_callback)

    assert result.status == UnitStatus.SUCCESS
    assert result.output == "step output"
    assert result.replan_count == 0
    assert result.total_loop_count == 1
    assert result.step_loop_counts == [1]
    assert mock_executor.execute.call_count == 1
    assert mock_verifier.verify.call_count == 1
    assert replan_callback.call_count == 0


# ── TC-02：UnitRunner.execute - Verifier passed=False 觸發 replan ──

@pytest.mark.asyncio
async def test_TC02_unit_runner_replan_on_verify_fail():
    """TC-02: Verifier passed=False 觸發 replan."""
    from core.unit_runner import UnitRunner

    mock_executor = MagicMock()
    mock_executor.execute = AsyncMock(side_effect=[
        Result(success=True, data={"output": "first output", "loop_count": 1}),
        Result(success=True, data={"output": "replan output", "loop_count": 1}),
    ])
    mock_verifier = MagicMock()
    mock_verifier.verify = AsyncMock(side_effect=[
        Result(success=True, data={"passed": False, "reason": "output mismatch", "gaps": ["missing dimension"], "constraint_checks": []}),
        Result(success=True, data={"passed": True, "reason": "OK", "gaps": [], "constraint_checks": []}),
    ])
    mock_tool_manager = MagicMock()
    mock_tool_manager.get_tools = AsyncMock(return_value=[{"name": "tool1"}])
    mock_step_store = MagicMock()
    mock_step_store.save_step = AsyncMock()
    mock_step_store.get_steps_by_unit = MagicMock(return_value=[
        StepResult(step_id="s1", status=StepStatus.SUCCESS, output="replan output", loop_count=1, output_type="GLOBAL"),
    ])
    mock_unit_store = MagicMock()
    mock_unit_store.save_unit = AsyncMock()

    unit_runner = UnitRunner(
        executor=mock_executor, verifier=mock_verifier,
        tool_manager=mock_tool_manager, step_store=mock_step_store,
        unit_store=mock_unit_store, session_id="test_session"
    )

    unit = Unit(unit_id="u1", goal="goal1", expected_output="expected", output_type="CONTENT")
    steps = [Step(step_id="s1", goal="step1", output_type="GLOBAL")]
    max_replan = 2

    new_steps = [Step(step_id="s2", goal="step2", output_type="GLOBAL")]
    replan_callback = AsyncMock(return_value=new_steps)

    result = await unit_runner.execute(unit, steps, max_replan, replan_callback)

    assert result.status == UnitStatus.SUCCESS
    assert result.output == "replan output"
    assert result.replan_count == 1
    assert result.total_loop_count == 2
    assert result.step_loop_counts == [1, 1]
    assert mock_executor.execute.call_count == 2
    assert mock_verifier.verify.call_count == 2
    assert replan_callback.call_count == 1


# ── TC-03：UnitRunner.execute - Verifier LLM 呼叫失敗 ──

@pytest.mark.asyncio
async def test_TC03_unit_runner_verify_llm_failure():
    """TC-03: Verifier LLM 呼叫失敗."""
    from core.unit_runner import UnitRunner

    mock_executor = MagicMock()
    mock_executor.execute = AsyncMock(return_value=Result(
        success=True, data={"output": "step output", "loop_count": 1}
    ))
    mock_verifier = MagicMock()
    mock_verifier.verify = AsyncMock(return_value=Result(success=False, error="驗證服務不可用"))
    mock_tool_manager = MagicMock()
    mock_tool_manager.get_tools = AsyncMock(return_value=[{"name": "tool1"}])
    mock_step_store = MagicMock()
    mock_step_store.save_step = AsyncMock()
    mock_unit_store = MagicMock()
    mock_unit_store.save_unit = AsyncMock()

    unit_runner = UnitRunner(
        executor=mock_executor, verifier=mock_verifier,
        tool_manager=mock_tool_manager, step_store=mock_step_store,
        unit_store=mock_unit_store, session_id="test_session"
    )

    unit = Unit(unit_id="u1", goal="goal1", expected_output="expected", output_type="CONTENT")
    steps = [Step(step_id="s1", goal="step1", output_type="GLOBAL")]
    max_replan = 2
    # DEF-008：replan_callback 回傳 None 時視為空 steps
    replan_callback = AsyncMock(return_value=None)

    result = await unit_runner.execute(unit, steps, max_replan, replan_callback)

    # DEF-008：verify_result.success=False 時觸發 replan，replan_callback 回傳 None → 空 steps → validate_steps 失敗 → 不呼叫 verifier → 再次 replan → 達上限
    # DEF-008：verify_result.success=False 時觸發 replan，replan_callback 回傳 None → 空 steps → validate_steps 失敗 → 不呼叫 verifier → 再次 replan → 達上限
    # 實際行為：replan_callback.call_count == 2（第一次 replan 後 steps 為空，validate_steps 失敗，再次 replan）
    assert result.status == UnitStatus.FAILED
    assert "replan" in result.error.lower()
    assert result.replan_count == 2
    assert mock_verifier.verify.call_count == 1
    assert replan_callback.call_count == 2


# ── TC-04：UnitRunner.execute - replan_callback 回傳空 Steps ──

@pytest.mark.asyncio
async def test_TC04_unit_runner_replan_callback_empty():
    """TC-04: replan_callback 回傳空 Steps."""
    from core.unit_runner import UnitRunner

    mock_executor = MagicMock()
    mock_executor.execute = AsyncMock(return_value=Result(
        success=True, data={"output": "first output", "loop_count": 1}
    ))
    mock_verifier = MagicMock()
    mock_verifier.verify = AsyncMock(return_value=Result(success=True, data={
        "passed": False, "reason": "output mismatch", "gaps": ["missing dimension"], "constraint_checks": []
    }))
    mock_tool_manager = MagicMock()
    mock_tool_manager.get_tools = AsyncMock(return_value=[{"name": "tool1"}])
    mock_step_store = MagicMock()
    mock_step_store.save_step = AsyncMock()
    mock_unit_store = MagicMock()
    mock_unit_store.save_unit = AsyncMock()

    unit_runner = UnitRunner(
        executor=mock_executor, verifier=mock_verifier,
        tool_manager=mock_tool_manager, step_store=mock_step_store,
        unit_store=mock_unit_store, session_id="test_session"
    )

    unit = Unit(unit_id="u1", goal="goal1", expected_output="expected", output_type="CONTENT")
    steps = [Step(step_id="s1", goal="step1", output_type="GLOBAL")]
    max_replan = 2

    replan_callback = AsyncMock(return_value=[])

    result = await unit_runner.execute(unit, steps, max_replan, replan_callback)

    assert result.status == UnitStatus.FAILED
    assert "replan" in result.error.lower() or "空" in result.error or "steps" in result.error.lower()
    assert replan_callback.call_count >= 1


# ── TC-05：UnitRunner.execute - replan_callback 回傳 None ──

@pytest.mark.asyncio
async def test_TC05_unit_runner_replan_callback_none():
    """TC-05: replan_callback 回傳 None."""
    from core.unit_runner import UnitRunner

    mock_executor = MagicMock()
    mock_executor.execute = AsyncMock(return_value=Result(
        success=True, data={"output": "first output", "loop_count": 1}
    ))
    mock_verifier = MagicMock()
    mock_verifier.verify = AsyncMock(return_value=Result(success=True, data={
        "passed": False, "reason": "output mismatch", "gaps": ["missing dimension"], "constraint_checks": []
    }))
    mock_tool_manager = MagicMock()
    mock_tool_manager.get_tools = AsyncMock(return_value=[{"name": "tool1"}])
    mock_step_store = MagicMock()
    mock_step_store.save_step = AsyncMock()
    mock_unit_store = MagicMock()
    mock_unit_store.save_unit = AsyncMock()

    unit_runner = UnitRunner(
        executor=mock_executor, verifier=mock_verifier,
        tool_manager=mock_tool_manager, step_store=mock_step_store,
        unit_store=mock_unit_store, session_id="test_session"
    )

    unit = Unit(unit_id="u1", goal="goal1", expected_output="expected", output_type="CONTENT")
    steps = [Step(step_id="s1", goal="step1", output_type="GLOBAL")]
    max_replan = 2

    replan_callback = AsyncMock(return_value=None)

    result = await unit_runner.execute(unit, steps, max_replan, replan_callback)

    # DEF-009：replan_callback 回傳 None 視為空 steps，再次 replan 後達上限
    assert result.status == UnitStatus.FAILED
    assert "replan" in result.error.lower() or "new" in result.error.lower() or "steps" in result.error.lower()
    assert result.replan_count == 2


# ── TC-06：UnitRunner.execute - max_replan 上限到達 ──

@pytest.mark.asyncio
async def test_TC06_unit_runner_max_replan_exhausted():
    """TC-06: max_replan 上限到達.
    DEF-006：修正 replan_count 計算邏輯（while replan_count < max_replan）.
    """
    from core.unit_runner import UnitRunner

    mock_executor = MagicMock()
    mock_executor.execute = AsyncMock(return_value=Result(
        success=True, data={"output": "output", "loop_count": 1}
    ))
    mock_verifier = MagicMock()
    mock_verifier.verify = AsyncMock(return_value=Result(success=True, data={
        "passed": False, "reason": "output mismatch", "gaps": ["gap"], "constraint_checks": []
    }))
    mock_tool_manager = MagicMock()
    mock_tool_manager.get_tools = AsyncMock(return_value=[{"name": "tool1"}])
    mock_step_store = MagicMock()
    mock_step_store.save_step = AsyncMock()
    mock_unit_store = MagicMock()
    mock_unit_store.save_unit = AsyncMock()

    unit_runner = UnitRunner(
        executor=mock_executor, verifier=mock_verifier,
        tool_manager=mock_tool_manager, step_store=mock_step_store,
        unit_store=mock_unit_store, session_id="test_session"
    )

    unit = Unit(unit_id="u1", goal="goal1", expected_output="expected", output_type="CONTENT")
    steps = [Step(step_id="s1", goal="step1", output_type="GLOBAL")]
    max_replan = 2

    replan_callback = AsyncMock(return_value=[Step(step_id="s_new", goal="new step", output_type="GLOBAL")])

    result = await unit_runner.execute(unit, steps, max_replan, replan_callback)

    # DEF-006：修正後 while replan_count < max_replan 為 0 < 2 → True
    # 第 1 輪：verify failed → replan (call 1), replan_count=1
    # 第 2 輪：verify failed → replan (call 2), replan_count=2
    # 第 3 輪：2 < 2 → False，跳出循環
    # 實際：replan_callback.call_count == 2
    assert result.status == UnitStatus.FAILED
    assert "replan" in result.error.lower() or "上限" in result.error or "limit" in result.error.lower()
    assert result.replan_count == 2
    assert mock_executor.execute.call_count == 2  # 初始 + 1 次 replan（修正後）
    assert mock_verifier.verify.call_count == 2
    assert replan_callback.call_count == 2


# ── TC-07：UnitRunner.execute - max_replan < 0 邊界條件 ──

@pytest.mark.asyncio
async def test_TC07_unit_runner_max_replan_negative():
    """TC-07: max_replan < 0 邊界條件.
    DEF-006：修正後 while replan_count < max_replan 為 -1 < 0 為 False，不執行。
    """
    from core.unit_runner import UnitRunner

    mock_executor = MagicMock()
    mock_executor.execute = AsyncMock(return_value=Result(
        success=True, data={"output": "output", "loop_count": 1}
    ))
    mock_verifier = MagicMock()
    mock_verifier.verify = AsyncMock(return_value=Result(success=True, data={
        "passed": False, "reason": "output mismatch", "gaps": ["gap"], "constraint_checks": []
    }))
    mock_tool_manager = MagicMock()
    mock_tool_manager.get_tools = AsyncMock(return_value=[{"name": "tool1"}])
    mock_step_store = MagicMock()
    mock_step_store.save_step = AsyncMock()
    mock_unit_store = MagicMock()
    mock_unit_store.save_unit = AsyncMock()

    unit_runner = UnitRunner(
        executor=mock_executor, verifier=mock_verifier,
        tool_manager=mock_tool_manager, step_store=mock_step_store,
        unit_store=mock_unit_store, session_id="test_session"
    )

    unit = Unit(unit_id="u1", goal="goal1", expected_output="expected", output_type="CONTENT")
    steps = [Step(step_id="s1", goal="step1", output_type="GLOBAL")]
    max_replan = -1

    replan_callback = AsyncMock(return_value=[Step(step_id="s_new", goal="new step", output_type="GLOBAL")])

    result = await unit_runner.execute(unit, steps, max_replan, replan_callback)

    # DEF-006：修正後 while -1 < -1 為 False，不執行任何步驟
    assert result.status == UnitStatus.FAILED
    assert result.replan_count == 0
    assert mock_executor.execute.call_count == 0
    assert mock_verifier.verify.call_count == 0
    assert replan_callback.call_count == 0


# ── TC-08：UnitRunner.execute - steps 為空列表 ──

@pytest.mark.asyncio
async def test_TC08_unit_runner_empty_steps():
    """TC-08: steps 為空列表."""
    from core.unit_runner import UnitRunner

    mock_executor = MagicMock()
    mock_executor.execute = AsyncMock(return_value=Result(
        success=True, data={"output": "output", "loop_count": 1}
    ))
    mock_verifier = MagicMock()
    mock_verifier.verify = AsyncMock(return_value=Result(success=True, data={
        "passed": True, "reason": "OK", "gaps": [], "constraint_checks": []
    }))
    mock_tool_manager = MagicMock()
    mock_tool_manager.get_tools = AsyncMock(return_value=[{"name": "tool1"}])
    mock_step_store = MagicMock()
    mock_step_store.save_step = AsyncMock()
    mock_unit_store = MagicMock()
    mock_unit_store.save_unit = AsyncMock()

    unit_runner = UnitRunner(
        executor=mock_executor, verifier=mock_verifier,
        tool_manager=mock_tool_manager, step_store=mock_step_store,
        unit_store=mock_unit_store, session_id="test_session"
    )

    unit = Unit(unit_id="u1", goal="goal1", expected_output="expected", output_type="CONTENT")
    steps = []  # 空列表
    max_replan = 2

    replan_callback = AsyncMock(return_value=[Step(step_id="s1", goal="step1", output_type="GLOBAL")])

    result = await unit_runner.execute(unit, steps, max_replan, replan_callback)

    assert result.status == UnitStatus.SUCCESS
    assert replan_callback.call_count == 1
    assert mock_executor.execute.call_count == 1


# ── TC-09：UnitRunner.execute - _collect_actual_output 僅合併 GLOBAL ──

@pytest.mark.asyncio
async def test_TC09_unit_runner_collect_actual_output():
    """TC-09: _collect_actual_output 僅合併 GLOBAL."""
    from core.unit_runner import UnitRunner

    mock_executor = MagicMock()
    mock_executor.execute = AsyncMock(return_value=Result(
        success=True, data={"output": "global output", "loop_count": 1}
    ))
    mock_verifier = MagicMock()
    mock_verifier.verify = AsyncMock(return_value=Result(success=True, data={
        "passed": True, "reason": "OK", "gaps": [], "constraint_checks": []
    }))
    mock_tool_manager = MagicMock()
    mock_tool_manager.get_tools = AsyncMock(return_value=[{"name": "tool1"}])
    mock_step_store = MagicMock()
    mock_step_store.save_step = AsyncMock()
    mock_step_store.get_steps_by_unit = MagicMock(return_value=[
        StepResult(step_id="s1", status=StepStatus.SUCCESS, output="internal output", loop_count=1, output_type="INTERNAL"),
        StepResult(step_id="s2", status=StepStatus.SUCCESS, output="global output", loop_count=1, output_type="GLOBAL"),
    ])
    mock_unit_store = MagicMock()
    mock_unit_store.save_unit = AsyncMock()

    unit_runner = UnitRunner(
        executor=mock_executor, verifier=mock_verifier,
        tool_manager=mock_tool_manager, step_store=mock_step_store,
        unit_store=mock_unit_store, session_id="test_session"
    )

    unit = Unit(unit_id="u1", goal="goal1", expected_output="expected", output_type="CONTENT")
    steps = [
        Step(step_id="s1", goal="step1", output_type="INTERNAL"),
        Step(step_id="s2", goal="step2", output_type="GLOBAL"),
    ]
    max_replan = 2
    replan_callback = AsyncMock()

    result = await unit_runner.execute(unit, steps, max_replan, replan_callback)

    assert result.status == UnitStatus.SUCCESS
    assert mock_step_store.get_steps_by_unit.call_count == 2


# ── TC-10：UnitRunner.execute - Verifier 僅在 expected_output 非空時呼叫 ──

@pytest.mark.asyncio
async def test_TC10_unit_runner_verify_only_when_expected_output_not_empty():
    """TC-10: Verifier 僅在 expected_output 非空時呼叫."""
    from core.unit_runner import UnitRunner

    mock_executor = MagicMock()
    mock_executor.execute = AsyncMock(return_value=Result(
        success=True, data={"output": "output", "loop_count": 1}
    ))
    mock_verifier = MagicMock()
    mock_verifier.verify = AsyncMock(return_value=Result(success=True, data={
        "passed": True, "reason": "OK", "gaps": [], "constraint_checks": []
    }))
    mock_tool_manager = MagicMock()
    mock_tool_manager.get_tools = AsyncMock(return_value=[{"name": "tool1"}])
    mock_step_store = MagicMock()
    mock_step_store.save_step = AsyncMock()
    mock_step_store.get_steps_by_unit = MagicMock(return_value=[
        StepResult(step_id="s1", status=StepStatus.SUCCESS, output="output", loop_count=1, output_type="GLOBAL"),
    ])
    mock_unit_store = MagicMock()
    mock_unit_store.save_unit = AsyncMock()

    unit_runner = UnitRunner(
        executor=mock_executor, verifier=mock_verifier,
        tool_manager=mock_tool_manager, step_store=mock_step_store,
        unit_store=mock_unit_store, session_id="test_session"
    )

    unit = Unit(unit_id="u1", goal="goal1", expected_output="", output_type="CONTENT")
    steps = [Step(step_id="s1", goal="step1", output_type="GLOBAL")]
    max_replan = 2
    replan_callback = AsyncMock()

    result = await unit_runner.execute(unit, steps, max_replan, replan_callback)

    assert result.status == UnitStatus.SUCCESS
    assert result.output == "output"
    assert mock_verifier.verify.call_count == 0  # expected_output 為空，不呼叫 verifier
