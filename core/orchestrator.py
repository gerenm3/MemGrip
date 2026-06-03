"""v2 orchestrator — 純協調器。

依據 §3.10 (Orchestrator) 定義：
- 純協調器，不直接呼叫模型、不直接執行工具、不直接處理資料
- 負責準備 buffer/summary/rag 後傳給各模組（原則 23）
- 負責 replan 決策（Step 層級，上限 MAX_REPLAN_ATTEMPTS 次）
- 三條執行路徑：simple / tool / complex
- 多輪澄清狀態機
- LVS + Optimizer 觸發
- Memory 管理（flush / add / get_context / retrieve）
- system_prompt 建構（domain → Skill Guide → fallback global → 空字串）
- replan 機制改為 callback 模式，由 _dispatch_complex 閉包捕獲上下文
"""

import asyncio
import logging
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, List, Optional

import config
import core.tracer as tracer
from core.health import get_user_warnings, log_action
from core.prompts import SYSTEM_PROMPT
from core.scheduler import validate_dag, validate_steps
from core.storage import StepStore, UnitStore
from models.blueprints import Result, Step, StepResult, StepStatus, Unit, UnitResult, UnitStatus

logger = logging.getLogger(__name__)


class ClarificationState(Enum):
    """多輪澄清狀態機"""
    NORMAL = "NORMAL"
    AWAITING_CLARIFICATION = "AWAITING_CLARIFICATION"


ReplanCallback = Callable[[dict, List[Step]], Awaitable[List[Step]]]


class Orchestrator:
    """純協調器：負責模組間協調、replan 決策、LVS 觸發.

    Args:
        router: 意圖路由
        clarifier: 輸入澄清
        disassembler: L1 任務拆解
        step_planner: L2 步驟規劃
        executor: Step 執行
        verifier: Unit 驗證
        responder: 回覆生成
        tool_manager: 工具管理
        scheduler: 依賴排序
        memory: 記憶管理
        lvs: 學習價值分數
        skill_manager: Skill Guide 管理
    """

    def __init__(
        self,
        router: Any,
        clarifier: Any,
        disassembler: Any,
        step_planner: Any,
        executor: Any,
        verifier: Any,
        responder: Any,
        tool_manager: Any,
        scheduler: Any,
        memory: Any,
        lvs: Any,
        skill_manager: Any,
    ) -> None:
        # 核心模組
        self.router = router
        self.clarifier = clarifier
        self.disassembler = disassembler
        self.step_planner = step_planner
        self.executor = executor
        self.verifier = verifier
        self.responder = responder
        self.tool_manager = tool_manager
        self.scheduler = scheduler
        self.memory = memory
        self.lvs = lvs
        self.skill_manager = skill_manager

        # 狀態
        self._clarification_state = ClarificationState.NORMAL
        self._pending_questions: List[str] = []
        self._pending_clarify_result: Optional[dict] = None
        self._pending_path: Optional[str] = None  # "tool" or "complex"
        self._pending_rag: str = ""
        self._pending_buffer: str = ""
        self._pending_summary: str = ""
        self._pending_domain: str = "general"
        self._pending_input: Optional[str] = None  # 非澄清回答時保留輸入
        self._clarification_rounds: int = 0  # 已澄清輪數
        self._clarification_history: List[str] = []  # 問答歷史
        self._original_user_input: str = ""  # 原始用戶輸入（含澄清上下文用）
        self._session_id: Optional[str] = None
        self._tools_initialized = False

        # Background task tracking
        self._background_tasks: set[asyncio.Task] = set()

        # Storage
        self._unit_store: Optional[UnitStore] = None
        self._step_store: Optional[StepStore] = None

    # ------------------------------------------------------------------
    # 主循環
    # ------------------------------------------------------------------

    async def run(self) -> None:
        """主循環：持续接收用戶輸入並_dispatch。"""
        while True:
            try:
                # 如果上一次澄清狀態處理產下了 _pending_input，優先處理
                if self._pending_input is not None:
                    user_input = self._pending_input
                    self._pending_input = None
                    logger.info("[Orchestrator] 處理保留的輸入: %s", user_input[:50])
                else:
                    user_input = input("\nYou: ").strip()
                    if not user_input:
                        continue

                    # 檢查退出關鍵字
                    if user_input.lower() in ("exit", "quit"):
                        print("\n再見。")
                        break

                # 多輪澄清狀態機
                if self._clarification_state == ClarificationState.AWAITING_CLARIFICATION:
                    clar_reply = await self._handle_clarification_response(user_input)
                    if clar_reply is not None:
                        # 澄清已完成，輸出回覆並繼續正常流程
                        warnings = get_user_warnings(self._session_id)
                        if warnings:
                            clar_reply = clar_reply + "\n\n⚠️ 系統警告：\n" + "\n".join(warnings)
                        print(f"\nAssistant: {clar_reply}")
                        await self._summarize_if_needed()
                        continue
                    # 仍處於澄清中，繼續等待用戶輸入
                    continue

                # 新 session
                self._session_id = self._new_session()
                self._unit_store = UnitStore()
                self._step_store = StepStore()

                # 路由
                route_result = await self.router.route(user_input)
                # 分流執行
                reply = await self._dispatch(route_result, user_input)
                # 輸出回覆
                if reply:
                    warnings = get_user_warnings(self._session_id)
                    if warnings:
                        reply = reply + "\n\n⚠️ 系統警告：\n" + "\n".join(warnings)
                    print(f"\nAssistant: {reply}")
                # 將對話寫入 memory
                self.memory.add("user", user_input)
                self.memory.add("assistant", reply)

                # 非同步 flush
                await self._summarize_if_needed()

            except KeyboardInterrupt:
                print("\n再見。")
                break
            except EOFError:
                break
            except Exception as e:
                logger.error("[Orchestrator] 主循環異常: %s", e, exc_info=True)
                print("系統出現異常。")

    # ------------------------------------------------------------------
    # 分流 dispatch
    # ------------------------------------------------------------------

    async def _dispatch(self, route_result, user_input):
        """根據路由結果分流到三條路徑.

        Args:
            route_result: Router.route() 回傳的 Result
            user_input: 原始用戶輸入

        Returns:
            回覆字串
        """
        route_data = route_result.data
        intent = route_data.get("intent", "simple")
        need_rag = route_data.get("need_rag", False)
        domain = route_data.get("domain", "general")
        log_action("orchestrator", "dispatch", "OK", intent)

        # 準備 RAG
        rag = ""
        if need_rag:
            rag = await self.memory.retrieve(user_input)

        # 準備 context
        buffer = self.memory.serialize_context()
        context = self.memory.get_context()
        summary = context.get("summary", "")

        if intent == "simple":
            return await self._dispatch_simple(user_input, buffer, summary, rag, domain)
        elif intent == "tool":
            return await self._dispatch_tool(user_input, buffer, summary, rag)
        elif intent == "complex":
            return await self._dispatch_complex(user_input, buffer, summary, rag, domain)
        else:
            return await self._dispatch_simple(user_input, buffer, summary, rag, domain)

    # ------------------------------------------------------------------
    # Simple 路徑
    # ------------------------------------------------------------------

    async def _dispatch_simple(
        self,
        user_input: str,
        buffer: str,
        summary: str,
        rag: str,
        domain: str,
    ) -> str:
        """Simple 路徑：Router → Responder.reply_simple"""
        log_action("orchestrator", "dispatch_simple_enter", "OK", "intent=simple")
        result = await self.responder.reply_simple(
            system_prompt=SYSTEM_PROMPT,
            user_input=user_input,
            buffer=buffer,
            summary=summary,
            rag=rag,
        )
        return result.data or "無法生成回覆。"

    # ------------------------------------------------------------------
    # Tool 路徑
    # ------------------------------------------------------------------

    async def _dispatch_tool(
        self,
        user_input: str,
        buffer: str,
        summary: str,
        rag: str,
    ) -> str:
        """Tool 路徑：Clarifier → _run_tool_pipeline"""
        # 澄清
        clarify_result = await self.clarifier.clarify(user_input, buffer, summary, rag)
        if not clarify_result.success:
            return "無法理解您的需求。"

        clarify_data = clarify_result.data
        questions = clarify_data.get("questions", [])

        # 澄清問題處理
        if questions:
            self._clarification_state = ClarificationState.AWAITING_CLARIFICATION
            self._clarification_rounds = 1
            self._clarification_history = []
            self._original_user_input = user_input
            self._pending_questions = questions
            self._pending_clarify_result = clarify_data
            self._pending_path = "tool"
            self._pending_rag = rag
            self._pending_buffer = buffer
            self._pending_summary = summary
            return "在您開始之前，我需要澄清一些問題：\n" + "\n".join(f"- {q}" for q in questions)

        return await self._run_tool_pipeline(clarify_data, user_input, rag)

    async def _run_tool_pipeline(
        self,
        clarify_data: dict,
        user_input: str,
        rag: str,
    ) -> str:
        """共用 Tool pipeline：probe_server → ToolManager → Responder.reply_tool"""
        goal = clarify_data.get("goal", user_input)

        # 探測 server
        probe_result = await self.router.probe_server(goal, list(self.tool_manager.server_schemas.keys()))
        if not probe_result.success:
            return "無法找到適合的工具。"

        server_name = probe_result.data.get("server", "")
        if not server_name:
            return "無法找到適合的工具。"

        # 取得工具清單
        all_tools = self.tool_manager.get_server_tools(server_name)

        # Agentic Loop
        loop_result = await self.tool_manager.run_agentic_loop(
            goal=goal,
            rag_content=rag,
            server_name=server_name,
            all_tools=all_tools,
        )

        # Responder 回覆
        reply_result = await self.responder.reply_tool(
            agentic_loop_output=loop_result.data or "",
            user_input=user_input,
        )
        return reply_result.data or "工具執行完成。"

    # ------------------------------------------------------------------
    # Complex 路徑
    # ------------------------------------------------------------------

    async def _dispatch_complex(
        self,
        user_input: str,
        buffer: str,
        summary: str,
        rag: str,
        domain: str,
    ) -> str:
        """Complex 路徑：Clarifier → _run_complex_pipeline"""
        # 澄清
        clarify_result = await self.clarifier.clarify(user_input, buffer, summary, rag)
        if not clarify_result.success:
            return "無法理解您的需求。"

        clarify_data = clarify_result.data
        questions = clarify_data.get("questions", [])

        if questions:
            self._clarification_state = ClarificationState.AWAITING_CLARIFICATION
            self._clarification_rounds = 1
            self._clarification_history = []
            self._original_user_input = user_input
            self._pending_questions = questions
            self._pending_clarify_result = clarify_data
            self._pending_path = "complex"
            self._pending_rag = rag
            self._pending_buffer = buffer
            self._pending_summary = summary
            self._pending_domain = domain
            return "在您開始之前，我需要澄清一些問題：\n" + "\n".join(f"- {q}" for q in questions)

        return await self._run_complex_pipeline(clarify_data, user_input, domain)

    async def _run_complex_pipeline(
        self,
        clarify_data: dict,
        user_input: str,
        domain: str,
    ) -> str:
        """共用 Complex pipeline：Disassembler → StepPlanner → Scheduler → Execute → Integrate → LVS → Optimizer"""
        # 取得 Skill Guide
        skill_guide = self._build_system_prompt(domain)

        # 取得可用 MCP Server 清單
        available_servers = list(self.tool_manager.server_schemas.keys())

        # L1: 任務拆解（含 DAG 驗證迴圈）
        dag_feedback = ""
        disasm_ok = False
        units: List[Unit] = []
        max_dag_retries = 2  # 驗證失敗後最多重試 2 次

        for attempt in range(1 + max_dag_retries):  # 1 次初始 + 最多 2 次重試
            disasm_result = await self.disassembler.disassemble(
                clarify_data,
                available_servers=available_servers,
                skill_guide=skill_guide,
                feedback=dag_feedback,
            )
            if not disasm_result.success:
                logger.error("[Orchestrator] Disassembler 失敗: %s", disasm_result.error)
                return "任務拆解失敗。"

            units = disasm_result.data or []
            if not units:
                return "無法拆解任務。"

            # DAG 驗證
            dag_result = validate_dag(units)
            if dag_result.success:
                disasm_ok = True
                break
            else:
                dag_feedback = dag_result.error or "DAG 驗證失敗"
                logger.warning(
                    "[Orchestrator] DAG 驗證失敗 (attempt %d/%d): %s",
                    attempt + 1, 1 + max_dag_retries, dag_feedback,
                )
                if attempt >= max_dag_retries:
                    logger.error("[Orchestrator] DAG 驗證達重試上限，仍無法通過")
                    return f"任務規劃多次驗證失敗：{dag_feedback}"

        if not disasm_ok:
            return "任務規劃驗證失敗。"

        # L2: 為每個 Unit 規劃 Steps
        unit_map = {u.unit_id: u for u in units}
        unit_steps: Dict[str, List[Step]] = {}
        for unit in units:
            available_tools = []
            if unit.mcp_server:
                available_tools = self.tool_manager.get_server_tools(unit.mcp_server)

            upstream_units_str = self._build_upstream_units_str(unit, unit_map)

            plan_result = await self.step_planner.plan_unit(
                unit=unit,
                available_tools=available_tools,
                skill_guide=skill_guide,
                upstream_units=upstream_units_str,
            )
            if plan_result.success:
                unit_steps[unit.unit_id] = plan_result.data or []

        # Scheduler: 拓撲排序
        schedule_result = self.scheduler.schedule(units, unit_steps)
        if not schedule_result.success:
            logger.error("[Orchestrator] Scheduler 失敗: %s", schedule_result.error)
            return "任務排程失敗。"

        schedule_data = schedule_result.data
        execution_order = schedule_data.get("execution_order", [])
        unit_step_orders = schedule_data.get("unit_step_orders", {})
        cyclic_units = schedule_data.get("cyclic_units", [])

        # 標記 cyclic units 為 FAILED
        for cu in cyclic_units:
            self._unit_store.save_unit(self._session_id, cu.unit_id, UnitResult(
                unit_id=cu.unit_id,
                status=UnitStatus.FAILED,
                error="循環依賴 detected",
            ))

        # 逐 Unit 執行（用 callback 閉包捕獲上下文）
        results: Dict[str, UnitResult] = {}
        max_replan = getattr(config, 'MAX_REPLAN_ATTEMPTS', 2)

        for unit in execution_order:
            # 檢查上游是否失敗
            upstream_failed = False
            for dep_id in unit.depends_on:
                dep_result = self._unit_store.get_unit(self._session_id, dep_id)
                if dep_result and dep_result.status == UnitStatus.FAILED:
                    upstream_failed = True
                    break

            if upstream_failed:
                self._unit_store.save_unit(self._session_id, unit.unit_id, UnitResult(
                    unit_id=unit.unit_id,
                    status=UnitStatus.SKIPPED,
                    error="上游 Unit 失敗",
                ))
                continue

            # 為每個 unit 定義 replan callback 閉包
            upstream_units_str = self._build_upstream_units_str(unit, unit_map)
            available_tools = self.tool_manager.get_server_tools(unit.mcp_server) if unit.mcp_server else []

            async def replan_callback(failed_step_info: dict, successful_steps: List[Step]) -> List[Step]:
                plan_result = await self.step_planner.plan_unit(
                    unit=unit,
                    available_tools=available_tools,
                    successful_steps=successful_steps,
                    failed_step_info=failed_step_info,
                    skill_guide=skill_guide,
                    upstream_units=upstream_units_str,
                )
                return plan_result.data if plan_result.success else []

            unit_result = await self._execute_unit(
                unit=unit,
                steps=unit_step_orders.get(unit.unit_id, []),
                max_replan=max_replan,
                replan_callback=replan_callback,
            )
            self._unit_store.save_unit(self._session_id, unit.unit_id, unit_result)
            results[unit.unit_id] = unit_result

        # Responder.integrate
        all_unit_results = self._unit_store.get_all_units(self._session_id)
        results_dict = {r.unit_id: r for r in all_unit_results}

        integrate_result = await self.responder.integrate(
            original_task=clarify_data,
            results=results_dict,
            units=units,
        )
        reply = integrate_result.data or "任務執行完成。"

        # 記錄任務 trace
        tracer.log_task(
            task_type=domain,
            user_input=user_input,
            goal=clarify_data.get("goal", ""),
            results=results_dict,
            units=units,
            clarifier_constraints=clarify_data.get("constraints", []),
        )

        # LVS 結算
        warning, triggered = await self.lvs.process(
            results=results_dict,
            session_id=self._session_id,
            task_type=domain,
        )

        if warning:
            reply = f"{reply}\n\n{warning}"

        if triggered:
            logger.info("[Orchestrator] LVS triggered, starting optimizer")
            def _on_optimizer_done(task: asyncio.Task) -> None:
                self._background_tasks.discard(task)
                if task.exception():
                    logger.error("[Orchestrator] optimizer task exception: %s", task.exception(), exc_info=True)

            for level in ("l1", "l2"):
                t = asyncio.create_task(
                    self._run_optimizer(self._session_id, domain, level)
                )
                t.add_done_callback(_on_optimizer_done)
                self._background_tasks.add(t)

        return reply

    # ------------------------------------------------------------------
    # Unit 執行（含 replan callback）
    # ------------------------------------------------------------------

    async def _execute_unit(
        self,
        unit: Unit,
        steps: List[Step],
        max_replan: int,
        replan_callback: Optional[ReplanCallback] = None,
    ) -> UnitResult:
        """執行單一 Unit，含 replan 邏輯（callback 模式）.

        Args:
            unit: Unit 物件
            steps: Step 列表
            max_replan: 最大 replan 次數
            replan_callback: replan callback 函式（由 _dispatch_complex 閉包提供上下文）

        Returns:
            UnitResult
        """
        replan_count = 0
        upstream_outputs: Dict[str, str] = {}
        step_loop_counts: Dict[str, int] = {}  # {step_id: loop_count}

        while replan_count <= max_replan:
            if replan_count > 0:
                logger.info("[Orchestrator] replan unit=%s attempt=%d", unit.unit_id, replan_count)
                log_action("orchestrator", "replan", "OK", f"{unit.unit_id} attempt={replan_count}")

            # 驗證 Steps 合法性
            vresult = validate_steps(steps)
            if not vresult.success:
                logger.warning(
                    "[Orchestrator] Steps 驗證失敗 unit=%s: %s",
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
                # 取得對應 server 的環境資訊
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
                logger.warning("[Orchestrator] unit=%s 超過 replan 上限", unit.unit_id)
                log_action("orchestrator", "replan_exhausted", "FAILED", unit.unit_id, "重規劃次數已達上限")
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
                logger.error("[Orchestrator] replan 需要但無 callback: unit=%s", unit.unit_id)
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

    # ------------------------------------------------------------------
    # 輔助方法
    # ------------------------------------------------------------------

    def _collect_actual_output(self, unit_id: str) -> str:
        """收集 Unit 的實際輸出（只取 GLOBAL Steps）。"""
        steps = self._step_store.get_steps_by_unit(self._session_id, unit_id)
        outputs = []
        for sr in steps:
            if sr.output_type == "GLOBAL" and sr.output:
                outputs.append(sr.output)
        return "\n".join(outputs)

    def _build_upstream_units_str(self, unit: Unit, unit_map: Dict[str, Unit]) -> str:
        """根據 Unit 的 depends_on 查詢上游單元的 expected_output.

        Args:
            unit: 當前 Unit
            unit_map: unit_id → Unit 的映射

        Returns:
            上游單元資訊字串（格式：unit:{id} → {expected_output}）
        """
        if not unit.depends_on:
            return "無"
        lines = []
        for dep_id in unit.depends_on:
            dep_unit = unit_map.get(dep_id)
            if dep_unit:
                lines.append(f"unit:{dep_id} → {dep_unit.expected_output}")
            else:
                lines.append(f"unit:{dep_id} → (未找到)")
        return "\n".join(lines)

    def _build_system_prompt(self, domain: str) -> str:
        """建構 system prompt：domain → Skill Guide → fallback global → 空字串.

        Args:
            domain: 任務領域

        Returns:
            Skill Guide 字串
        """
        try:
            skill_data = self.skill_manager.load_skill(domain, "l1")
            if skill_data:
                return self.skill_manager.skill_guide_to_prompt(skill_data)
        except Exception as e:
            logger.warning("[Orchestrator] 無法載入 domain=%s skill: %s", domain, e)

        # Fallback 到 global
        try:
            skill_data = self.skill_manager.load_skill("global", "l1")
            if skill_data:
                return self.skill_manager.skill_guide_to_prompt(skill_data)
        except Exception as e:
            logger.warning("[Orchestrator] 無法載入 global skill: %s", e)

        return ""

    async def _summarize_if_needed(self) -> None:
        """非同步 flush memory."""
        try:
            def _on_flush_done(task: asyncio.Task) -> None:
                self._background_tasks.discard(task)
                if task.exception():
                    logger.error("[Orchestrator] flush task exception: %s", task.exception(), exc_info=True)

            t = asyncio.create_task(self.memory.flush())
            t.add_done_callback(_on_flush_done)
            self._background_tasks.add(t)
        except Exception as e:
            logger.warning("[Orchestrator] flush 失敗: %s", e)

    async def _run_optimizer(self, session_id: str, task_type: str, level: str) -> None:
        """非同步執行 optimizer."""
        try:
            from skills.optimizer import Optimizer
            optimizer = Optimizer()
            await optimizer.run_optimizer(session_id, task_type, level)
        except Exception as e:
            logger.error("[Orchestrator] optimizer 異常: %s", e, exc_info=True)

    def _new_session(self) -> str:
        """產生新 session ID，使用 tracer 統一管理."""
        session_id = tracer.new_session()
        return session_id

    # ------------------------------------------------------------------
    # 多輪澄清
    # ------------------------------------------------------------------

    async def _resume_pending_dispatch(self, user_input: str) -> str:
        """澄清完成後恢復執行原本的 dispatch 流程.

        Args:
            user_input: 用戶輸入（用於重構 context）

        Returns:
            回覆字串
        """
        if not self._pending_clarify_result:
            return "澄清結果遺失，請重新輸入。"

        path = self._pending_path or "tool"
        buffer = self._pending_buffer
        summary = self._pending_summary
        rag = self._pending_rag
        domain = self._pending_domain

        if path == "complex":
            return await self._dispatch_complex_with_clarified(
                user_input, buffer, summary, rag, domain
            )
        else:
            # path == "tool"
            return await self._resume_tool(
                user_input, buffer, summary, rag
            )

    async def _resume_tool(
        self,
        user_input: str,
        buffer: str,
        summary: str,
        rag: str,
    ) -> str:
        """恢復 Tool 路徑執行"""
        clarify_data = self._pending_clarify_result
        return await self._run_tool_pipeline(clarify_data, user_input, rag)

    async def _dispatch_complex_with_clarified(
        self,
        user_input: str,
        buffer: str,
        summary: str,
        rag: str,
        domain: str,
    ) -> str:
        """使用已澄清的資料執行 Complex 路徑"""
        clarify_data = self._pending_clarify_result
        return await self._run_complex_pipeline(clarify_data, user_input, domain)

    async def _handle_clarification_response(self, user_input: str) -> Optional[str]:
        """處理用戶對澄清問題的回答.

        如果用戶回答的是澄清問題，重新呼叫 Clarifier。
        澄清完成後恢復執行原本的 dispatch 流程。
        否則清除 pending 狀態，將輸入保留供主循環處理。
        回傳 reply 字串（由呼叫端負責輸出），None 表示仍需澄清。
        """
        # 判斷是否為澄清回答
        clar_result = await self.router.is_clarification(
            user_input, self._pending_questions
        )

        is_clarification = False
        if clar_result.success and isinstance(clar_result.data, dict):
            is_clarification = clar_result.data.get("is_clarification", False)

        if is_clarification:
            # 記錄問答歷史
            for q in self._pending_questions:
                self._clarification_history.append(f"Q: {q}")
            self._clarification_history.append(f"A: {user_input}")

            # 增加澄清輪數
            self._clarification_rounds += 1

            # 檢查是否超過最大澄清輪數
            max_rounds = getattr(config, 'MAX_CLARIFY_ROUNDS', 2)
            if self._clarification_rounds > max_rounds:
                # 超出限制，強制結束澄清，用已有資料執行
                logger.warning(
                    "[Orchestrator] 澄清輪數超限 (%d > %d)，強制執行",
                    self._clarification_rounds, max_rounds,
                )
                self._clarification_state = ClarificationState.NORMAL
                reply = await self._resume_pending_dispatch(user_input)
                self.memory.add("user", user_input)
                self.memory.add("assistant", reply)
                warnings = get_user_warnings(self._session_id)
                if warnings:
                    reply = reply + "\n\n⚠️ 系統警告：\n" + "\n".join(warnings)
                await self._summarize_if_needed()
                self._clarification_rounds = 0
                self._clarification_history = []
                self._original_user_input = ""
                return reply

            # 建構含問答歷史的輸入：將原始輸入 + 問答歷史拼接到一起
            enriched_input = self._original_user_input
            if self._clarification_history:
                enriched_input += "\n\n[Clarification History]\n"
                enriched_input += "\n".join(self._clarification_history)

            # 重新澄清：使用含歷史的輸入
            clarify_result = await self.clarifier.clarify(
                enriched_input, self._pending_buffer, self._pending_summary, self._pending_rag
            )
            if clarify_result.success:
                new_data = clarify_result.data
                new_questions = new_data.get("questions", [])
                if new_questions:
                    self._pending_questions = new_questions
                    self._pending_clarify_result = new_data
                    logger.info("[Orchestrator] 仍有問題需要澄清: %s", new_questions)
                    return None
                else:
                    # 澄清完成，恢復執行原本的 dispatch 流程
                    self._clarification_state = ClarificationState.NORMAL
                    self._pending_clarify_result = new_data
                    self._pending_questions = []
                    self._clarification_rounds = 0
                    self._clarification_history = []
                    self._original_user_input = ""
                    reply = await self._resume_pending_dispatch(user_input)
                    self.memory.add("user", user_input)
                    self.memory.add("assistant", reply)
                    warnings = get_user_warnings(self._session_id)
                    if warnings:
                        reply = reply + "\n\n⚠️ 系統警告：\n" + "\n".join(warnings)
                    await self._summarize_if_needed()
                    return reply
            else:
                logger.error("[Orchestrator] 重新澄清失敗: %s", clarify_result.error)
                self._clarification_state = ClarificationState.NORMAL
                self._clarification_rounds = 0
                self._clarification_history = []
                self._original_user_input = ""
                return None
        else:
            # 用戶的回答不是針對澄清問題 → 視為「不要問了，直接執行」
            # 用已儲存的 clarify_data 恢復原本的 dispatch 流程
            logger.info(
                "[Orchestrator] 用戶輸入非澄清回答，視為直接執行指令: %s",
                user_input[:50],
            )
            self._clarification_state = ClarificationState.NORMAL
            self._pending_questions = []
            self._clarification_rounds = 0
            self._clarification_history = []
            self._original_user_input = ""
            reply = await self._resume_pending_dispatch(user_input)
            self.memory.add("user", user_input)
            self.memory.add("assistant", reply)
            warnings = get_user_warnings(self._session_id)
            if warnings:
                reply = reply + "\n\n⚠️ 系統警告：\n" + "\n".join(warnings)
            await self._summarize_if_needed()
            return reply
