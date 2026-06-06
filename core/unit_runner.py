"""v2 unit_runner — Unit 執行器。

將 Orchestrator._execute_unit() 和 _collect_actual_output() 的邏輯移入此模組。
"""

import logging
from typing import Any, Awaitable, Callable, Dict, List, Optional

from core.health import log_action
from core.scheduler import validate_steps
from models.blueprints import Result, Step, StepResult, StepStatus, Unit, UnitResult, UnitStatus

logger = logging.getLogger(__name__)

ReplanCallback = Callable[[dict, List[Step]], Awaitable[List[Step]]]


class UnitRunner:
    """執行單一 Unit，含 replan 邏輯。

    Args:
        executor: Step 執行器
        verifier: Unit 驗證器
        tool_manager: 工具管理器
        step_store: Step 儲存
        unit_store: Unit 儲存
        session_id: 工作階段 ID
    """

    def __init__(
        self,
        executor: Any,
        verifier: Any,
        tool_manager: Any,
        step_store: Any,
        unit_store: Any,
        session_id: str,
    ) -> None:
        self.executor = executor
        self.verifier = verifier
        self.tool_manager = tool_manager
        self._step_store = step_store
        self._unit_store = unit_store
        self._session_id = session_id

    async def execute(
        self,
        unit: Unit,
        steps: List[Step],
        max_replan: int,
        replan_callback: Optional[ReplanCallback] = None,
    ) -> UnitResult:
        """執行單一 Unit，含 replan 邏輯.

        Args:
            unit: Unit 物件
            steps: Step 列表
            max_replan: 最大 replan 次數
            replan_callback: replan callback 函式

        Returns:
            UnitResult
        """
        replan_count = 0
        upstream_outputs: Dict[str, str] = {}
        step_loop_counts: Dict[str, int] = {}  # {step_id: loop_count}

        while replan_count <= max_replan:
            if replan_count > 0:
                logger.info("[UnitRunner] replan unit=%s attempt=%d", unit.unit_id, replan_count)
                log_action("orchestrator", "replan_trigger", "DEGRADED",
                           f"{unit.unit_id} attempt={replan_count}", "單元需要重新規劃")
                log_action("orchestrator", "replan", "OK", f"{unit.unit_id} attempt={replan_count}")

            # 驗證 Steps 合法性
            vresult = validate_steps(steps)
            if not vresult.success:
                logger.warning(
                    "[UnitRunner] Steps 驗證失敗 unit=%s: %s",
                    unit.unit_id, vresult.error,
                )
                unit_failed = True
                failed_step_info = {
                    "step_id": "",
                    "goal": unit.goal,
                    "content": f"Steps 驗證失敗: {vresult.error}",
                }
            else:
                unit_failed = False
                failed_step_info: Optional[dict] = None

            step_results: Dict[str, Any] = {}

            # 逐 Step 執行
            for step in steps:
                # 檢查同 Unit 上游依賴
                step_deps_met = True
                for dep_step_id in step.depends_on:
                    dep_result = step_results.get(dep_step_id)
                    if dep_result and getattr(dep_result, 'status', None) == StepStatus.FAILED:
                        step_deps_met = False
                        break

                if not step_deps_met:
                    step_results[step.step_id] = Result(
                        success=False,
                        data=None,
                        error="上游 Step 失敗",
                    )
                    self._step_store.save_step(self._session_id, unit.unit_id, step.step_id, StepResult(
                        step_id=step.step_id,
                        status=StepStatus.FAILED,
                        error="上游 Step 失敗",
                    ))
                    continue

                # 準備 upstream_outputs
                step_upstream = dict(upstream_outputs)

                # 跨 Unit 依賴：從 unit_store 取得上游 unit 的輸出
                for udep in step.upstream_depends:
                    udep_str = str(udep) if not isinstance(udep, str) else udep
                    udep_result = self._unit_store.get_unit(self._session_id, udep_str)
                    if udep_result and udep_result.status == UnitStatus.SUCCESS and udep_result.output:
                        step_upstream[udep_str] = udep_result.output

                # 同 Unit 內依賴：確保 dep_step_id type 一致後查詢
                for dep_step_id in step.depends_on:
                    dep_step_key = str(dep_step_id) if not isinstance(dep_step_id, str) else dep_step_id
                    dep_sr = self._step_store.get_step(self._session_id, dep_step_key)
                    if dep_sr and dep_sr.status == StepStatus.SUCCESS and dep_sr.output:
                        step_upstream[dep_step_key] = dep_sr.output

                # 執行 Step
                environment = ""
                if unit.mcp_server:
                    environment = self.tool_manager.tool_environments.get(unit.mcp_server, "")
                exec_result = await self.executor.execute(
                    step=step,
                    upstream_outputs=step_upstream,
                    environment=environment,
                )

                step_ok = exec_result.success

                # 儲存 Step 結果（從 exec_result.data 提取 output 和 loop_count）
                output = ""
                loop_count = 0
                if hasattr(exec_result, 'data') and isinstance(exec_result.data, dict):
                    output = exec_result.data.get("output", "")
                    loop_count = exec_result.data.get("loop_count", 0)

                if step_ok:
                    step_results[step.step_id] = exec_result
                    step_loop_counts[step.step_id] = loop_count
                    self._step_store.save_step(self._session_id, unit.unit_id, step.step_id, StepResult(
                        step_id=step.step_id,
                        status=StepStatus.SUCCESS,
                        output=output,
                        output_type=step.output_type,
                        loop_count=loop_count,
                    ))
                    # 更新 upstream_outputs
                    if step.output_type == "GLOBAL" and output:
                        upstream_outputs[step.step_id] = output
                else:
                    # Step 失敗
                    self._step_store.save_step(self._session_id, unit.unit_id, step.step_id, StepResult(
                        step_id=step.step_id,
                        status=StepStatus.FAILED,
                        error=exec_result.error or "",
                    ))
                    failed_step_info = {
                        "step_id": step.step_id,
                        "goal": step.goal,
                        "content": exec_result.error or "執行失敗",
                    }
                    unit_failed = True
                    break

            if not unit_failed:
                # 所有 Steps 成功 → Verifier 驗證
                constraint_checks = []
                if unit.expected_output:
                    actual_output = self._collect_actual_output(unit.unit_id)
                    verify_result = await self.verifier.verify(
                        unit=unit,
                        actual_output=actual_output,
                    )
                    if verify_result.success and isinstance(verify_result.data, dict):
                        passed = verify_result.data.get("passed", False)
                        constraint_checks = verify_result.data.get("constraint_checks", [])
                        if not passed:
                            unit_failed = True
                            failed_step_info = {
                                "step_id": "",
                                "goal": unit.goal,
                                "content": f"Verifier 未通過: {verify_result.data.get('reason', '')}",
                                "gaps": verify_result.data.get("gaps", []),
                                "constraint_checks": verify_result.data.get("constraint_checks", []),
                            }

            if not unit_failed:
                # 成功：清空 step_store 後回傳
                output = self._collect_actual_output(unit.unit_id)
                self._step_store.clear_unit_steps(self._session_id, unit.unit_id)
                total_loop_count = sum(step_loop_counts.values())
                log_action("orchestrator", "unit_complete", "OK",
                           f"{unit.unit_id} status=SUCCESS output_type={unit.output_type}")
                return UnitResult(
                    unit_id=unit.unit_id,
                    status=UnitStatus.SUCCESS,
                    output=output,
                    replan_count=replan_count,
                    total_loop_count=total_loop_count,
                    step_loop_counts=list(step_loop_counts.values()),
                    constraint_checks=constraint_checks,
                )

            # 失敗 → replan
            replan_count += 1
            if replan_count > max_replan:
                logger.warning("[UnitRunner] unit=%s 超過 replan 上限", unit.unit_id)
                log_action("orchestrator", "replan_exhausted", "FAILED", unit.unit_id, "重規劃次數已達上限")
                log_action("orchestrator", "unit_complete", "OK",
                           f"{unit.unit_id} status=FAILED output_type={unit.output_type}")
                self._step_store.clear_unit_steps(self._session_id, unit.unit_id)
                total_loop_count = sum(step_loop_counts.values())
                return UnitResult(
                    unit_id=unit.unit_id,
                    status=UnitStatus.FAILED,
                    error=f"超過 replan 上限 ({max_replan} 次)",
                    replan_count=replan_count,
                    total_loop_count=total_loop_count,
                    step_loop_counts=list(step_loop_counts.values()),
                )

            # 取得已成功的 Steps（從 step_store 驗證狀態）
            successful_steps = []
            for step in steps:
                sr = self._step_store.get_step(self._session_id, step.step_id)
                if sr and sr.status == StepStatus.SUCCESS:
                    successful_steps.append(step)

            # 呼叫 replan callback
            if replan_callback:
                new_steps = await replan_callback(failed_step_info, successful_steps)
                # 合併邏輯：新 steps 優先，已成功的 steps 補充不存在的 id
                existing = {str(s.step_id): s for s in new_steps}
                for s in successful_steps:
                    sid = str(s.step_id)
                    if sid not in existing:
                        existing[sid] = s
                steps = list(existing.values())
            else:
                # 無 callback 且需要 replan，直接標記 FAILED
                logger.error("[UnitRunner] replan 需要但無 callback: unit=%s", unit.unit_id)
                self._step_store.clear_unit_steps(self._session_id, unit.unit_id)
                total_loop_count = sum(step_loop_counts.values())
                return UnitResult(
                    unit_id=unit.unit_id,
                    status=UnitStatus.FAILED,
                    error="replan 需要但無 callback",
                    replan_count=replan_count,
                    total_loop_count=total_loop_count,
                    step_loop_counts=list(step_loop_counts.values()),
                )

        # 循環結束仍未成功
        self._step_store.clear_unit_steps(self._session_id, unit.unit_id)
        total_loop_count = sum(step_loop_counts.values())
        return UnitResult(
            unit_id=unit.unit_id,
            status=UnitStatus.FAILED,
            error="replan 上限",
            replan_count=replan_count,
            total_loop_count=total_loop_count,
            step_loop_counts=list(step_loop_counts.values()),
        )

    def _collect_actual_output(self, unit_id: str) -> str:
        """收集 Unit 的實際輸出（只取 GLOBAL Steps）。"""
        steps = self._step_store.get_steps_by_unit(self._session_id, unit_id)
        outputs = []
        for sr in steps:
            if sr.output_type == "GLOBAL" and sr.output:
                outputs.append(sr.output)
        return "\n".join(outputs)