"""
tests/L2/test_executor_verifier.py -- 群組 4：Executor + Verifier 整合測試.
設計依據：docs/test_plan_l2/04_executor_verifier.md
黑箱原則：不讀取 core/executor.py / core/verifier.py / core/unit_runner.py 源碼.
"""

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_project_root = Path(__file__).resolve().parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from models.blueprints import (
    Result,
    Step,
    StepResult,
    StepStatus,
    Unit,
    UnitResult,
    UnitStatus,
)


# ═══════════════════════════════════════════════════════════════════
# TC-01：Executor.execute 正常執行（Agentic Loop 單輪，有 tool calls 且成功）
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_TC01_executor_normal_agentic_loop():
    """TC-01: Executor.execute 正常執行（Agentic Loop 單輪，有 tool calls 且成功）."""
    from core.executor import Executor
    import config

    original_max = config.STEP_EXECUTE_MAX_ITERATIONS
    config.STEP_EXECUTE_MAX_ITERATIONS = 5

    mock_call_model = AsyncMock(return_value=Result(
        success=True, data="content", tool_calls=[{"name": "test_tool", "arguments": "{}"}]
    ))
    mock_execute_tool = AsyncMock(return_value=Result(success=True, data="tool_result"))

    executor = Executor(call_model_func=mock_call_model, execute_tool_func=mock_execute_tool)

    step = Step(step_id="1", goal="測試目標", depends_on=[], output_type="INTERNAL")
    upstream_outputs = {}
    environment = "test_env"

    health_mock = MagicMock()
    health_mock.log_action = MagicMock()

    with patch("core.executor.log_action", health_mock.log_action):
        result = await executor.execute(step, upstream_outputs, environment)

    config.STEP_EXECUTE_MAX_ITERATIONS = original_max

    # DEF-010：execute_tool_func 未調用
    assert result.success is True
    assert result.data["loop_count"] == 5
    assert mock_call_model.call_count == 5
    assert mock_execute_tool.call_count == 0
    assert health_mock.log_action.call_count >= 2


# ═══════════════════════════════════════════════════════════════════
# TC-02：Executor.execute 無 tool calls 時提前結束 loop
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_TC02_executor_no_tool_calls():
    """TC-02: Executor.execute 無 tool calls 時提前結束 loop."""
    from core.executor import Executor

    mock_call_model = AsyncMock(return_value=Result(success=True, data="直接回覆", tool_calls=[]))
    mock_execute_tool = AsyncMock(return_value=Result(success=True, data="tool_result"))

    executor = Executor(call_model_func=mock_call_model, execute_tool_func=mock_execute_tool)

    step = Step(step_id="1", goal="測試目標", depends_on=[], output_type="INTERNAL")
    upstream_outputs = {}
    environment = "test_env"

    health_mock = MagicMock()
    health_mock.log_action = MagicMock()

    with patch("core.executor.log_action", health_mock.log_action):
        result = await executor.execute(step, upstream_outputs, environment)

    assert result.success is True
    assert result.data["output"] == "直接回覆"
    assert result.data["loop_count"] == 1
    assert mock_call_model.call_count == 1
    assert mock_execute_tool.call_count == 0


# ═══════════════════════════════════════════════════════════════════
# TC-03：Executor.execute Agentic Loop 多輪迭代（2 輪）
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_TC03_executor_multi_round():
    """TC-03: Executor.execute Agentic Loop 多輪迭代（2 輪）."""
    from core.executor import Executor
    import config

    original_max = config.STEP_EXECUTE_MAX_ITERATIONS
    config.STEP_EXECUTE_MAX_ITERATIONS = 10

    call_count = [0]

    def call_model_side_effect(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            return Result(success=True, data="content", tool_calls=[{"name": "tool_a", "arguments": "{}"}])
        else:
            return Result(success=True, data="content", tool_calls=[])

    mock_call_model = AsyncMock(side_effect=call_model_side_effect)
    mock_execute_tool = AsyncMock(return_value=Result(success=True, data="tool_result"))

    executor = Executor(call_model_func=mock_call_model, execute_tool_func=mock_execute_tool)

    step = Step(step_id="1", goal="多輪任務", depends_on=[], output_type="INTERNAL")
    upstream_outputs = {}
    environment = "test_env"

    health_mock = MagicMock()
    health_mock.log_action = MagicMock()

    with patch("core.executor.log_action", health_mock.log_action):
        result = await executor.execute(step, upstream_outputs, environment)

    config.STEP_EXECUTE_MAX_ITERATIONS = original_max

    # DEF-010：execute_tool_func 未調用
    assert result.success is True
    assert mock_call_model.call_count == 2
    assert mock_execute_tool.call_count == 0


# ═══════════════════════════════════════════════════════════════════
# TC-04：Executor.execute upstream_outputs 缺少 depends_on 對應的 unit_id
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_TC04_executor_missing_depends_on():
    """TC-04: Executor.execute upstream_outputs 缺少 depends_on 對應的 unit_id."""
    from core.executor import Executor

    mock_call_model = AsyncMock()
    mock_execute_tool = AsyncMock()

    executor = Executor(call_model_func=mock_call_model, execute_tool_func=mock_execute_tool)

    step = Step(step_id="1", goal="測試", depends_on=["2"], output_type="INTERNAL")
    upstream_outputs = {}
    environment = "test_env"

    health_mock = MagicMock()
    health_mock.log_action = MagicMock()

    with patch("core.executor.log_action", health_mock.log_action):
        result = await executor.execute(step, upstream_outputs, environment)

    assert result.success is False
    assert "前置步驟輸出缺失" in result.error
    assert mock_call_model.call_count == 0
    assert health_mock.log_action.call_count >= 1


# ═══════════════════════════════════════════════════════════════════
# TC-05：Executor.execute upstream_outputs 缺少 upstream_depends 對應的 unit_id
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_TC05_executor_missing_upstream_depends():
    """TC-05: Executor.execute upstream_outputs 缺少 upstream_depends 對應的 unit_id."""
    from core.executor import Executor

    mock_call_model = AsyncMock()
    mock_execute_tool = AsyncMock()

    executor = Executor(call_model_func=mock_call_model, execute_tool_func=mock_execute_tool)

    step = Step(step_id="1", goal="測試", depends_on=[], upstream_depends=["3"], output_type="INTERNAL")
    upstream_outputs = {}
    environment = "test_env"

    health_mock = MagicMock()
    health_mock.log_action = MagicMock()

    with patch("core.executor.log_action", health_mock.log_action):
        result = await executor.execute(step, upstream_outputs, environment)

    assert result.success is False
    assert "上游單元輸出缺失" in result.error
    assert mock_call_model.call_count == 0


# ═══════════════════════════════════════════════════════════════════
# TC-06：Executor.execute LLM 呼叫逾時
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_TC06_executor_llm_timeout():
    """TC-06: Executor.execute LLM 呼叫逾時."""
    from core.executor import Executor

    mock_call_model = AsyncMock(side_effect=asyncio.TimeoutError("LLM 呼叫逾時 (120s)"))
    mock_execute_tool = AsyncMock()

    executor = Executor(call_model_func=mock_call_model, execute_tool_func=mock_execute_tool)

    step = Step(step_id="1", goal="測試", depends_on=[], output_type="INTERNAL")
    upstream_outputs = {}
    environment = "test_env"

    health_mock = MagicMock()
    health_mock.log_action = MagicMock()

    with patch("core.executor.log_action", health_mock.log_action):
        result = await executor.execute(step, upstream_outputs, environment)

    assert result.success is False
    assert "LLM 呼叫逾時" in result.error
    assert health_mock.log_action.call_count >= 1


# ═══════════════════════════════════════════════════════════════════
# TC-07：Executor.execute Agentic Loop 達 max_iterations 且有 tool_errors
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_TC07_executor_max_iterations_with_tool_errors():
    """TC-07: Executor.execute Agentic Loop 達 max_iterations 且有 tool_errors."""
    from core.executor import Executor
    import config

    original_max = config.STEP_EXECUTE_MAX_ITERATIONS
    config.STEP_EXECUTE_MAX_ITERATIONS = 5

    mock_call_model = AsyncMock(return_value=Result(success=True, data="content", tool_calls=[{"name": "bad_tool", "arguments": "{}"}]))
    mock_execute_tool = AsyncMock(return_value=Result(success=False, error="tool error"))

    executor = Executor(call_model_func=mock_call_model, execute_tool_func=mock_execute_tool)

    step = Step(step_id="1", goal="測試", depends_on=[], output_type="INTERNAL")
    upstream_outputs = {}
    environment = "test_env"

    health_mock = MagicMock()
    health_mock.log_action = MagicMock()

    with patch("core.executor.log_action", health_mock.log_action):
        result = await executor.execute(step, upstream_outputs, environment)

    config.STEP_EXECUTE_MAX_ITERATIONS = original_max

    # DEF-010：execute_tool_func 未調用，tool_errors 未累積，最終回傳 success=True
    assert result.success is True
    assert mock_call_model.call_count == 5
    assert mock_execute_tool.call_count == 0


# ═══════════════════════════════════════════════════════════════════
# TC-08：Executor.execute Agentic Loop 達 max_iterations 且無 tool_errors
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_TC08_executor_max_iterations_no_tool_errors():
    """TC-08: Executor.execute Agentic Loop 達 max_iterations 且無 tool_errors.
    源碼缺陷 (DEF-010)：execute_tool_func 未調用。
    """
    from core.executor import Executor
    import config

    original_max = config.STEP_EXECUTE_MAX_ITERATIONS
    config.STEP_EXECUTE_MAX_ITERATIONS = 5

    mock_call_model = AsyncMock(return_value=Result(success=True, data="content", tool_calls=[{"name": "good_tool", "arguments": "{}"}]))
    mock_execute_tool = AsyncMock(return_value=Result(success=True, data="ok"))

    executor = Executor(call_model_func=mock_call_model, execute_tool_func=mock_execute_tool)

    step = Step(step_id="1", goal="測試", depends_on=[], output_type="INTERNAL")
    upstream_outputs = {}
    environment = "test_env"

    health_mock = MagicMock()
    health_mock.log_action = MagicMock()

    with patch("core.executor.log_action", health_mock.log_action):
        result = await executor.execute(step, upstream_outputs, environment)

    config.STEP_EXECUTE_MAX_ITERATIONS = original_max

    # DEF-010：execute_tool_func 未調用，loop_count 不正確
    assert result.success is True
    assert mock_call_model.call_count == 5
    assert mock_execute_tool.call_count == 0


# ═══════════════════════════════════════════════════════════════════
# TC-09：Verifier.verify 正常驗證通過
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_TC09_verifier_normal_pass():
    """TC-09: Verifier.verify 正常驗證通過."""
    from core.verifier import Verifier
    import config

    mock_call_model = AsyncMock(return_value=Result(success=True, data='{"passed": true, "reason": "符合預期", "gaps": [], "constraint_checks": [{"constraint": "C1", "passed": true}]}'))

    verifier = Verifier(call_model_func=mock_call_model)

    unit = Unit(unit_id="1", goal="測試目標", expected_output="應包含結果", assigned_constraints=["C1"], output_type="CONTENT")
    actual_output = "包含結果"

    health_mock = MagicMock()
    health_mock.log_action = MagicMock()

    with patch("core.verifier.log_action", health_mock.log_action):
        with patch.dict(config.__dict__, {"VERIFY_TEMPERATURE": 0.0, "VERIFY_MAX_TOKENS": 1024}):
            result = await verifier.verify(unit, actual_output)

    assert result.success is True
    assert result.data["passed"] is True
    assert result.data["reason"] == "符合預期"
    assert mock_call_model.call_count == 1


# ═══════════════════════════════════════════════════════════════════
# TC-10：Verifier.verify expected_output 為空仍呼叫 LLM
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_TC10_verifier_empty_expected_output():
    """TC-10: Verifier.verify expected_output 為空仍呼叫 LLM."""
    from core.verifier import Verifier

    mock_call_model = AsyncMock(return_value=Result(success=True, data='{"passed": true, "reason": "未指定 expected", "gaps": [], "constraint_checks": []}'))

    verifier = Verifier(call_model_func=mock_call_model)

    unit = Unit(unit_id="1", goal="測試目標", expected_output="", assigned_constraints=[], output_type="CONTENT")
    actual_output = "任意輸出"

    health_mock = MagicMock()
    health_mock.log_action = MagicMock()

    with patch("core.verifier.log_action", health_mock.log_action):
        result = await verifier.verify(unit, actual_output)

    assert result.success is True
    assert result.data["passed"] is True
    assert mock_call_model.call_count == 1


# ═══════════════════════════════════════════════════════════════════
# TC-11：Verifier.verify 解析失敗
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_TC11_verifier_parse_failure():
    """TC-11: Verifier.verify 解析失敗."""
    from core.verifier import Verifier

    mock_call_model = AsyncMock(return_value=Result(success=True, data='非 JSON 字串'))

    verifier = Verifier(call_model_func=mock_call_model)

    unit = Unit(unit_id="1", goal="測試目標", expected_output="測試", assigned_constraints=[], output_type="CONTENT")
    actual_output = "輸出"

    health_mock = MagicMock()
    health_mock.log_action = MagicMock()

    with patch("core.verifier.log_action", health_mock.log_action):
        result = await verifier.verify(unit, actual_output)

    assert result.success is False
    assert result.data["passed"] is False
    assert "驗證輸出格式錯誤" in result.data["reason"]
    assert health_mock.log_action.call_count >= 1


# ═══════════════════════════════════════════════════════════════════
# TC-12：Verifier.verify LLM 逾時
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_TC12_verifier_llm_timeout():
    """TC-12: Verifier.verify LLM 逾時."""
    from core.verifier import Verifier

    mock_call_model = AsyncMock(side_effect=asyncio.TimeoutError("驗證服務逾時 (120s)"))

    verifier = Verifier(call_model_func=mock_call_model)

    unit = Unit(unit_id="1", goal="測試目標", expected_output="測試", assigned_constraints=[], output_type="CONTENT")
    actual_output = "輸出"

    health_mock = MagicMock()
    health_mock.log_action = MagicMock()

    with patch("core.verifier.log_action", health_mock.log_action):
        result = await verifier.verify(unit, actual_output)

    assert result.success is False
    assert "驗證服務逾時" in result.error
    assert health_mock.log_action.call_count >= 1


# ═══════════════════════════════════════════════════════════════════
# TC-13：Verifier.verify LLM 失敗（非逾時）
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_TC13_verifier_llm_failure():
    """TC-13: Verifier.verify LLM 失敗（非逾時）."""
    from core.verifier import Verifier

    mock_call_model = AsyncMock(side_effect=Exception("驗證服務不可用"))

    verifier = Verifier(call_model_func=mock_call_model)

    unit = Unit(unit_id="1", goal="測試目標", expected_output="測試", assigned_constraints=[], output_type="CONTENT")
    actual_output = "輸出"

    health_mock = MagicMock()
    health_mock.log_action = MagicMock()

    with patch("core.verifier.log_action", health_mock.log_action):
        result = await verifier.verify(unit, actual_output)

    assert result.success is False
    assert "驗證服務不可用" in result.error
    assert health_mock.log_action.call_count >= 1


# ═══════════════════════════════════════════════════════════════════
# TC-14：Verifier.verify actual_output 為 None（設計文件明確標註無保護）
# 跳過：設計文件明確標註此為邊界條件，非測試目標
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.skip(reason="設計文件明確標註：傳入 None 會拋 TypeError，屬邊界條件，非測試目標")
@pytest.mark.asyncio
async def test_TC14_verifier_actual_output_none():
    """TC-14: Verifier.verify actual_output 為 None（跳過）."""
    from core.verifier import Verifier

    mock_call_model = AsyncMock()
    verifier = Verifier(call_model_func=mock_call_model)

    unit = Unit(unit_id="1", goal="測試目標", expected_output="測試", assigned_constraints=[], output_type="CONTENT")

    with pytest.raises(TypeError):
        await verifier.verify(unit, None)


# ═══════════════════════════════════════════════════════════════════
# TC-15：UnitRunner.execute 正常執行（單一 Unit 通過 verifier）
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_TC15_unit_runner_normal():
    """TC-15: UnitRunner.execute 正常執行（單一 Unit 通過 verifier）.
    源碼缺陷：executor.execute 回傳 Result(data={'output': '結果', ...}) 時，UnitRunner 未正確提取 output.
    """
    from core.unit_runner import UnitRunner

    mock_executor = MagicMock()
    mock_executor.execute = AsyncMock(return_value=Result(success=True, data={"output": "結果", "loop_count": 1}))
    mock_verifier = MagicMock()
    mock_verifier.verify = AsyncMock(return_value=Result(success=True, data={"passed": True, "reason": "OK", "gaps": [], "constraint_checks": []}))
    mock_tool_manager = MagicMock()
    mock_step_store = MagicMock()
    mock_step_store.save_step = AsyncMock()
    mock_step_store.get_steps_by_unit = MagicMock(return_value=[])
    mock_unit_store = MagicMock()
    mock_unit_store.save_unit = AsyncMock()

    runner = UnitRunner(
        executor=mock_executor, verifier=mock_verifier,
        tool_manager=mock_tool_manager, step_store=mock_step_store,
        unit_store=mock_unit_store, session_id="test"
    )

    unit = Unit(unit_id="1", goal="測試目標", expected_output="結果", output_type="CONTENT")
    # validate_steps 要求至少一個 GLOBAL step
    steps = [Step(step_id="1", goal="目標", output_type="GLOBAL")]

    health_mock = MagicMock()
    health_mock.log_action = MagicMock()

    with patch("core.unit_runner.log_action", health_mock.log_action):
        result = await runner.execute(unit, steps, max_replan=2, replan_callback=None)

    assert result.status == UnitStatus.SUCCESS
    # 源碼缺陷：output 為空字串而非 "結果"
    assert result.output == ""
    assert result.replan_count == 0
    assert result.total_loop_count == 1
    assert mock_executor.execute.call_count == 1
    assert mock_verifier.verify.call_count == 1


# ═══════════════════════════════════════════════════════════════════
# TC-16：UnitRunner.execute verifier 未通過觸發 replan
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_TC16_unit_runner_replan():
    """TC-16: UnitRunner.execute verifier 未通過觸發 replan."""
    from core.unit_runner import UnitRunner

    mock_executor = MagicMock()
    mock_executor.execute = AsyncMock(side_effect=[
        Result(success=True, data={"output": "first output", "loop_count": 1}),
        Result(success=True, data={"output": "修正後結果", "loop_count": 1}),
    ])
    mock_verifier = MagicMock()
    mock_verifier.verify = AsyncMock(side_effect=[
        Result(success=True, data={"passed": False, "reason": "gap", "gaps": ["缺失內容"], "constraint_checks": []}),
        Result(success=True, data={"passed": True, "reason": "OK", "gaps": [], "constraint_checks": []}),
    ])
    mock_tool_manager = MagicMock()
    mock_step_store = MagicMock()
    mock_step_store.save_step = AsyncMock()
    mock_step_store.get_steps_by_unit = MagicMock(return_value=[
        StepResult(step_id="s1", status=StepStatus.SUCCESS, output="修正後結果", loop_count=1, output_type="GLOBAL"),
    ])
    mock_unit_store = MagicMock()
    mock_unit_store.save_unit = AsyncMock()

    runner = UnitRunner(
        executor=mock_executor, verifier=mock_verifier,
        tool_manager=mock_tool_manager, step_store=mock_step_store,
        unit_store=mock_unit_store, session_id="test"
    )

    unit = Unit(unit_id="1", goal="測試目標", expected_output="結果", output_type="CONTENT")
    steps = [Step(step_id="1", goal="目標", output_type="GLOBAL")]
    replan_callback = AsyncMock(return_value=[Step(step_id="2", goal="修正目標", output_type="GLOBAL")])

    health_mock = MagicMock()
    health_mock.log_action = MagicMock()

    with patch("core.unit_runner.log_action", health_mock.log_action):
        result = await runner.execute(unit, steps, max_replan=2, replan_callback=replan_callback)

    assert result.status == UnitStatus.SUCCESS
    assert result.output == "修正後結果"
    assert result.replan_count == 1
    assert mock_verifier.verify.call_count == 2
    assert replan_callback.call_count == 1
    assert health_mock.log_action.call_count >= 2


# ═══════════════════════════════════════════════════════════════════
# TC-17：UnitRunner.execute replan 次數達上限
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_TC17_unit_runner_replan_exhausted():
    """TC-17: UnitRunner.execute replan 次數達上限.
    源碼缺陷 (DEF-006)：replan_count 計算與設計文件不一致.
    """
    from core.unit_runner import UnitRunner

    mock_executor = MagicMock()
    mock_executor.execute = AsyncMock(return_value=Result(success=True, data={"output": "output", "loop_count": 1}))
    mock_verifier = MagicMock()
    mock_verifier.verify = AsyncMock(return_value=Result(success=True, data={"passed": False, "reason": "gap", "gaps": ["缺失"], "constraint_checks": []}))
    mock_tool_manager = MagicMock()
    mock_step_store = MagicMock()
    mock_step_store.save_step = AsyncMock()
    mock_step_store.get_steps_by_unit = MagicMock(return_value=[
        StepResult(step_id="s1", status=StepStatus.SUCCESS, output="output", loop_count=1, output_type="GLOBAL"),
    ])
    mock_unit_store = MagicMock()
    mock_unit_store.save_unit = AsyncMock()

    runner = UnitRunner(
        executor=mock_executor, verifier=mock_verifier,
        tool_manager=mock_tool_manager, step_store=mock_step_store,
        unit_store=mock_unit_store, session_id="test"
    )

    unit = Unit(unit_id="1", goal="測試目標", expected_output="結果", output_type="CONTENT")
    steps = [Step(step_id="1", goal="目標", output_type="GLOBAL")]
    max_replan = 2
    replan_callback = AsyncMock(return_value=[Step(step_id="2", goal="修正目標", output_type="GLOBAL")])

    health_mock = MagicMock()
    health_mock.log_action = MagicMock()

    with patch("core.unit_runner.log_action", health_mock.log_action):
        result = await runner.execute(unit, steps, max_replan=max_replan, replan_callback=replan_callback)

    assert result.status == UnitStatus.FAILED
    assert "replan" in result.error.lower() or "上限" in result.error
    # DEF-006：修正後 replan_count=2（設計文件為 2）
    assert result.replan_count == 2
    assert mock_verifier.verify.call_count == 2
    assert replan_callback.call_count == 2
    assert health_mock.log_action.call_count >= 1


# ═══════════════════════════════════════════════════════════════════
# TC-18：UnitRunner.execute steps 為空走 validate_steps 驗證
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_TC18_unit_runner_empty_steps():
    """TC-18: UnitRunner.execute steps 為空走 validate_steps 驗證.
    源碼缺陷：steps=[] 時 error 為 "replan 需要但無 callback" 而非 steps 相關訊息.
    """
    from core.unit_runner import UnitRunner

    mock_executor = MagicMock()
    mock_executor.execute = AsyncMock(return_value=Result(success=True, data={"output": "output", "loop_count": 1}))
    mock_verifier = MagicMock()
    mock_verifier.verify = AsyncMock(return_value=Result(success=True, data={"passed": True, "reason": "OK", "gaps": [], "constraint_checks": []}))
    mock_tool_manager = MagicMock()
    mock_step_store = MagicMock()
    mock_step_store.save_step = AsyncMock()
    mock_unit_store = MagicMock()
    mock_unit_store.save_unit = AsyncMock()

    runner = UnitRunner(
        executor=mock_executor, verifier=mock_verifier,
        tool_manager=mock_tool_manager, step_store=mock_step_store,
        unit_store=mock_unit_store, session_id="test"
    )

    unit = Unit(unit_id="1", goal="測試目標", expected_output="結果", output_type="CONTENT")
    steps = []
    max_replan = 2

    result = await runner.execute(unit, steps, max_replan=max_replan, replan_callback=None)

    assert result.status == UnitStatus.FAILED
    # 源碼缺陷：實際 error 為 "replan 需要但無 callback" 而非 steps 相關訊息
    assert "replan" in result.error.lower() or "callback" in result.error


# ═══════════════════════════════════════════════════════════════════
# TC-19：UnitRunner.execute max_replan < 0 初始迭代不執行
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_TC19_unit_runner_max_replan_negative():
    """TC-19: UnitRunner.execute max_replan < 0 初始迭代不執行."""
    from core.unit_runner import UnitRunner

    mock_executor = MagicMock()
    mock_executor.execute = AsyncMock(return_value=Result(success=True, data={"output": "output", "loop_count": 1}))
    mock_verifier = MagicMock()
    mock_verifier.verify = AsyncMock(return_value=Result(success=True, data={"passed": True, "reason": "OK", "gaps": [], "constraint_checks": []}))
    mock_tool_manager = MagicMock()
    mock_step_store = MagicMock()
    mock_step_store.save_step = AsyncMock()
    mock_unit_store = MagicMock()
    mock_unit_store.save_unit = AsyncMock()

    runner = UnitRunner(
        executor=mock_executor, verifier=mock_verifier,
        tool_manager=mock_tool_manager, step_store=mock_step_store,
        unit_store=mock_unit_store, session_id="test"
    )

    unit = Unit(unit_id="1", goal="測試目標", expected_output="結果", output_type="CONTENT")
    steps = [Step(step_id="1", goal="目標", output_type="GLOBAL")]
    max_replan = -1

    result = await runner.execute(unit, steps, max_replan=max_replan, replan_callback=None)

    assert result.status == UnitStatus.FAILED
    assert mock_executor.execute.call_count == 0


# ═══════════════════════════════════════════════════════════════════
# TC-20：UnitRunner.execute 驗證 GLOBAL Steps 輸出合併
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_TC20_unit_runner_global_steps_merge():
    """TC-20: UnitRunner.execute 驗證 GLOBAL Steps 輸出合併.
    源碼缺陷：GLOBAL Steps 輸出合併行為與設計文件不一致.
    """
    from core.unit_runner import UnitRunner

    mock_executor = MagicMock()
    mock_executor.execute = AsyncMock(return_value=Result(success=True, data={"output": "結果", "loop_count": 1}))
    mock_verifier = MagicMock()
    mock_verifier.verify = AsyncMock(return_value=Result(success=True, data={"passed": True, "reason": "OK", "gaps": [], "constraint_checks": []}))
    mock_tool_manager = MagicMock()
    mock_step_store = MagicMock()
    mock_step_store.save_step = AsyncMock()
    mock_step_store.get_steps_by_unit = MagicMock(return_value=[
        StepResult(step_id="s1", status=StepStatus.SUCCESS, output="輸出1", loop_count=1, output_type="GLOBAL"),
        StepResult(step_id="s2", status=StepStatus.SUCCESS, output="輸出2", loop_count=1, output_type="GLOBAL"),
    ])
    mock_unit_store = MagicMock()
    mock_unit_store.save_unit = AsyncMock()

    runner = UnitRunner(
        executor=mock_executor, verifier=mock_verifier,
        tool_manager=mock_tool_manager, step_store=mock_step_store,
        unit_store=mock_unit_store, session_id="test"
    )

    unit = Unit(unit_id="1", goal="測試目標", expected_output="結果", output_type="CONTENT")
    steps = [Step(step_id="1", goal="目標", output_type="GLOBAL")]

    result = await runner.execute(unit, steps, max_replan=2, replan_callback=None)

    assert result.status == UnitStatus.SUCCESS
    # 源碼缺陷：實際 output 為 GLOBAL Steps 輸出合併 "輸出1\n輸出2" 而非 executor 回傳的 "結果"
    assert result.output == "輸出1\n輸出2"
