"""測試 Replan 資訊流：驗證 gaps 和 constraint_checks 正確注入 replan prompt。

測試設計：
1. 模擬 Verifier 第一次驗證失敗，返回 gaps 和 constraint_checks
2. 確認 replan 觸發
3. 確認 Step Planner 的 user prompt 包含 gaps 和 constraint_checks
"""
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from models.blueprints import Unit, Step, StepResult, StepStatus, UnitResult, UnitStatus, Result


class TestReplanInfoFlow:
    """測試 Replan 資訊流"""

    @pytest.mark.asyncio
    async def test_step_planner_build_input_includes_gaps_and_checks(self):
        """測試 StepPlanner._build_input() 正確注入 gaps 和 constraint_checks"""
        from core.step_planner import StepPlanner

        unit = Unit(
            unit_id="test-unit-1",
            goal="測試單元目標",
            expected_input="某輸入",
            expected_output="某輸出",
            output_type="CONTENT",
            assigned_constraints=["輸出必須包含統計數字", "輸出必須列出所有項目"],
        )

        successful_steps = [
            Step(step_id="1", goal="步驟一目標"),
        ]

        failed_step_info = {
            "step_id": "2",
            "goal": "步驟二目標",
            "content": "Verifier 未通過: 輸出缺少統計數字",
            "gaps": [
                "沒有列出完整的統計數字",
                "缺少項目的總數統計",
            ],
            "constraint_checks": [
                {"constraint": "輸出必須包含統計數字", "satisfied": False},
                {"constraint": "輸出必須列出所有項目", "satisfied": True},
            ],
        }

        input_text = StepPlanner._build_input(unit, successful_steps, failed_step_info)

        # 驗證 gaps 被注入
        assert "驗證差距：" in input_text
        assert "沒有列出完整的統計數字" in input_text
        assert "缺少項目的總數統計" in input_text

        # 驗證 constraint_checks 被注入
        assert "約束檢查結果：" in input_text
        assert "輸出必須包含統計數字" in input_text
        assert "輸出必須列出所有項目" in input_text

        # 驗證失敗步驟資訊被注入
        assert "前次失敗步驟：" in input_text
        assert "step_id=2" in input_text

        # 驗證已成功步驟被注入
        assert "已成功步驟：" in input_text
        assert "step_id=1" in input_text

    @pytest.mark.asyncio
    async def test_verifier_output_structure(self):
        """測試 Verifier 輸出包含 gaps 和 constraint_checks"""
        from core.verifier import Verifier
        from core.json_utils import parse_first_json

        # 模擬 call_model_func 返回包含 gaps 和 constraint_checks 的結果
        mock_verify_data = {
            "passed": False,
            "reason": "輸出缺少必要的統計資訊",
            "gaps": [
                "沒有列出所有項目的統計",
                "缺少時間線資訊",
            ],
            "constraint_checks": [
                {"constraint": "輸出必須包含統計數字", "satisfied": False},
                {"constraint": "輸出必須列出所有項目", "satisfied": False},
            ],
        }

        mock_call_model = AsyncMock()
        mock_call_model.return_value = Result(
            success=True,
            data=json.dumps(mock_verify_data, ensure_ascii=False),
        )

        verifier = Verifier(call_model_func=mock_call_model)

        unit = Unit(
            unit_id="test-unit-1",
            goal="測試目標",
            expected_output="包含統計數字的完整輸出",
            output_type="CONTENT",
            assigned_constraints=["輸出必須包含統計數字", "輸出必須列出所有項目"],
        )

        result = await verifier.verify(unit, "實際輸出內容")

        assert result.success is True
        assert isinstance(result.data, dict)
        assert result.data["passed"] is False
        assert len(result.data["gaps"]) == 2
        assert len(result.data["constraint_checks"]) == 2
        assert result.data["constraint_checks"][0]["satisfied"] is False

    @pytest.mark.asyncio
    async def test_orchestrator_replan_no_callback_returns_failed(self):
        """測試無 replan callback 時返回 FAILED"""
        from core.orchestrator import Orchestrator
        from core.scheduler import Scheduler
        from core.storage import StepStore, UnitStore

        mock_router = MagicMock()
        mock_clarifier = MagicMock()
        mock_disassembler = MagicMock()
        mock_executor = MagicMock()
        mock_verifier = MagicMock()
        mock_responder = MagicMock()
        mock_tool_manager = MagicMock()
        mock_scheduler = Scheduler()
        mock_memory = MagicMock()
        mock_lvs = MagicMock()
        mock_skill_manager = MagicMock()

        mock_step_planner = MagicMock()

        # Executor: step 1 成功, step 2 失敗
        mock_executor.execute = AsyncMock()
        mock_executor.execute.side_effect = [
            Result(success=True, data={"output": "檔案內容", "loop_count": 1}),
            Result(success=False, error="執行錯誤"),
        ]

        mock_verifier.verify = AsyncMock()
        mock_verifier.verify.return_value = Result(success=True, data={"passed": True})

        orchestrator = Orchestrator(
            router=mock_router,
            clarifier=mock_clarifier,
            disassembler=mock_disassembler,
            step_planner=mock_step_planner,
            executor=mock_executor,
            verifier=mock_verifier,
            responder=mock_responder,
            tool_manager=mock_tool_manager,
            scheduler=mock_scheduler,
            memory=mock_memory,
            lvs=mock_lvs,
            skill_manager=mock_skill_manager,
        )

        orchestrator._session_id = "test-session"
        orchestrator._unit_store = UnitStore()
        orchestrator._step_store = StepStore()

        unit = Unit(
            unit_id="test-unit-1",
            goal="測試單元",
            expected_input="輸入",
            expected_output="輸出",
            output_type="CONTENT",
            depends_on=[],
            mcp_server=None,
            assigned_constraints=["constraint1"],
        )

        steps = [
            Step(step_id="1", goal="讀取檔案", tool={"type": "function", "function": {"name": "read_file"}}),
            Step(step_id="2", goal="處理資料", tool=None),
        ]

        # 無 replan callback → 應該 FAILED
        result = await orchestrator._execute_unit(
            unit=unit,
            steps=steps,
            max_replan=2,
            replan_callback=None,
        )

        assert result.status == UnitStatus.FAILED


class TestReplanEndToEndMock:
    """端到端測試：使用 Mock 模擬完整 replan 流程"""

    @pytest.mark.asyncio
    async def test_full_replan_flow_with_verifier_failure(self):
        """模擬 Verifier 失敗 → replan → 成功 的完整流程"""
        from core.orchestrator import Orchestrator
        from core.scheduler import Scheduler
        from core.storage import StepStore, UnitStore

        mock_router = MagicMock()
        mock_clarifier = MagicMock()
        mock_disassembler = MagicMock()
        mock_executor = MagicMock()
        mock_verifier = MagicMock()
        mock_responder = MagicMock()
        mock_tool_manager = MagicMock()
        mock_scheduler = Scheduler()
        mock_memory = MagicMock()
        mock_lvs = MagicMock()
        mock_skill_manager = MagicMock()

        # 追蹤 step_planner 的 failed_step_info
        replan_prompts = []
        call_count = [0]

        mock_step_planner = MagicMock()

        async def mock_plan_unit(unit, available_tools=None, successful_steps=None, failed_step_info=None, **kwargs):
            call_count[0] += 1
            if failed_step_info:
                replan_prompts.append(failed_step_info)

            if call_count[0] == 1:
                return Result(success=True, data=[
                    Step(step_id="1", goal="讀取檔案", tool={"type": "function", "function": {"name": "read_file"}}, output_type="INTERNAL"),
                    Step(step_id="2", goal="處理資料", tool=None, output_type="GLOBAL"),
                ])
            else:
                return Result(success=True, data=[
                    Step(step_id="1", goal="讀取檔案", tool={"type": "function", "function": {"name": "read_file"}}, output_type="INTERNAL"),
                    Step(step_id="3", goal="修正後的處理", tool=None, output_type="GLOBAL"),
                ])

        mock_step_planner.plan_unit = mock_plan_unit

        # Executor 每次都成功
        mock_executor.execute = AsyncMock()
        mock_executor.execute.side_effect = [
            Result(success=True, data={"output": "檔案內容", "loop_count": 1}),  # step 1
            Result(success=True, data={"output": "處理結果", "loop_count": 1}),  # step 2
            Result(success=True, data={"output": "檔案內容", "loop_count": 1}),  # replan step 1
            Result(success=True, data={"output": "修正後結果", "loop_count": 1}),  # replan step 3
        ]

        # Verifier: 第一次失敗，第二次成功
        verify_call_count = [0]

        async def mock_verify(unit, actual_output):
            verify_call_count[0] += 1
            if verify_call_count[0] == 1:
                return Result(success=True, data={
                    "passed": False,
                    "reason": "輸出缺少必要資訊",
                    "gaps": ["缺少統計數字", "未列出所有項目"],
                    "constraint_checks": [
                        {"constraint": "必須包含統計數字", "satisfied": False},
                        {"constraint": "必須列出所有項目", "satisfied": False},
                    ],
                })
            else:
                return Result(success=True, data={
                    "passed": True,
                    "reason": "符合預期",
                    "gaps": [],
                    "constraint_checks": [],
                })

        mock_verifier.verify = mock_verify

        orchestrator = Orchestrator(
            router=mock_router,
            clarifier=mock_clarifier,
            disassembler=mock_disassembler,
            step_planner=mock_step_planner,
            executor=mock_executor,
            verifier=mock_verifier,
            responder=mock_responder,
            tool_manager=mock_tool_manager,
            scheduler=mock_scheduler,
            memory=mock_memory,
            lvs=mock_lvs,
            skill_manager=mock_skill_manager,
        )

        orchestrator._session_id = "test-session"
        orchestrator._unit_store = UnitStore()
        orchestrator._step_store = StepStore()

        unit = Unit(
            unit_id="test-unit-1",
            goal="測試任務",
            expected_input="輸入資料",
            expected_output="包含統計數字的完整輸出",
            output_type="CONTENT",
            depends_on=[],
            mcp_server=None,
            assigned_constraints=["必須包含統計數字", "必須列出所有項目"],
        )

        steps = [
            Step(step_id="1", goal="讀取檔案", tool={"type": "function", "function": {"name": "read_file"}}, output_type="INTERNAL"),
            Step(step_id="2", goal="處理資料", tool=None, output_type="GLOBAL"),
        ]

        async def replan_callback(failed_step_info, successful_steps):
            return await mock_step_planner.plan_unit(
                unit=unit,
                available_tools=[],
                successful_steps=successful_steps,
                failed_step_info=failed_step_info,
            )

        result = await orchestrator._execute_unit(
            unit=unit,
            steps=steps,
            max_replan=2,
            replan_callback=replan_callback,
        )

        # 驗證結果
        assert result.status == UnitStatus.SUCCESS
        assert result.replan_count == 1

        # 關鍵：驗證 replan 時的 failed_step_info 包含 gaps 和 constraint_checks
        assert len(replan_prompts) == 1
        failed_info = replan_prompts[0]
        assert "gaps" in failed_info
        assert "constraint_checks" in failed_info
        assert len(failed_info["gaps"]) == 2
        assert "缺少統計數字" in failed_info["gaps"][0]
        assert len(failed_info["constraint_checks"]) == 2
        assert failed_info["constraint_checks"][0]["constraint"] == "必須包含統計數字"
        assert failed_info["constraint_checks"][0]["satisfied"] is False

        assert verify_call_count[0] == 2
        assert call_count[0] == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])