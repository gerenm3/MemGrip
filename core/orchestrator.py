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
from typing import Any, Awaitable, Callable, Dict, List, Optional

import config
import core.tracer as tracer
from core.health import get_user_warnings, log_action
from core.prompts import SYSTEM_PROMPT
from core.scheduler import validate_dag
from core.storage import StepStore, UnitStore
from core.unit_runner import UnitRunner
from core.clarification_manager import ClarificationManager, ClarificationResult
from models.blueprints import ClarificationState, Result, Step, StepResult, StepStatus, Unit, UnitResult, UnitStatus

logger = logging.getLogger(__name__)

# Module-level constants
MAX_DAG_RETRIES = 2
EXIT_KEYWORDS = frozenset(("exit", "quit"))

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
        self._unit_runner = None
        self.clarification_manager = None

        # 狀態
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
        # 啟動 idle watchdog
        asyncio.create_task(self.memory.start_idle_watchdog())
        while True:
            try:
                loop = asyncio.get_event_loop()
                user_input = await loop.run_in_executor(None, lambda: input("\nYou: ").strip())
                # 重置 idle 計時
                self.memory.on_activity()
                if not user_input:
                    continue

                # 檢查退出關鍵字
                if user_input.lower() in EXIT_KEYWORDS:
                    print("\n再見。")
                    break

                # 多輪澄清狀態機
                if self.clarification_manager and self.clarification_manager.clarification_state == ClarificationState.AWAITING_CLARIFICATION:
                    clar_result = await self.clarification_manager.handle_clarification_response(user_input)
                    if not clar_result.completed:
                        if clar_result.reply:
                            print(f"\nAssistant: {clar_result.reply}")
                        continue
                    # 澄清完成，根據 path 呼叫對應 pipeline
                    reply = await self._execute_clarified_result(clar_result)
                    warnings = get_user_warnings(self._session_id)
                    if warnings:
                        reply = reply + "\n\n⚠️ 系統警告：\n" + "\n".join(warnings)
                    print(f"\nAssistant: {reply}")
                    await self._summarize_if_needed()
                    continue

                # 新 session
                if not (self.clarification_manager and 
                        self.clarification_manager.clarification_state == ClarificationState.AWAITING_CLARIFICATION):
                    self._unit_store = UnitStore()
                    self._step_store = StepStore()
                    self._session_id = self._new_session()

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
    # 執行澄清後的結果
    # ------------------------------------------------------------------

    async def _execute_clarified_result(self, clar_result: ClarificationResult) -> str:
        """根據 ClarificationResult 的 path 呼叫對應 pipeline。"""
        if clar_result.path == "tool":
            return await self._run_tool_pipeline(clar_result.clarify_data, clar_result.clarify_data.get("goal", ""), clar_result.rag)
        elif clar_result.path == "complex":
            return await self._run_complex_pipeline(clar_result.clarify_data, clar_result.clarify_data.get("goal", ""), clar_result.domain)
        else:
            return "無法執行。"

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
        if not route_result.success:
            logger.warning("[Orchestrator] route_result.success=False, error=%s", route_result.error)
            return "路由失敗，無法處理您的請求。"

        route_data = route_result.data
        intent = route_data.get("intent", "simple")
        need_rag = route_data.get("need_rag", False)
        domain = route_data.get("domain", "general")
        log_action("orchestrator", "dispatch", "OK", intent)
        log_action("orchestrator", "pipeline_start", "OK", f"intent={intent} domain={domain}")

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
            self.clarification_manager.start_clarification(
                questions=questions,
                clarify_data=clarify_data,
                path="tool",
                buffer=buffer,
                summary=summary,
                rag=rag,
                domain="general",
                original_user_input=user_input,
            )
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
            environment=self.tool_manager.tool_environments.get(server_name, ""),
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
            self.clarification_manager.start_clarification(
                questions=questions,
                clarify_data=clarify_data,
                path="complex",
                buffer=buffer,
                summary=summary,
                rag=rag,
                domain=domain,
                original_user_input=user_input,
            )
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
        skill_guide = self.skill_manager.build_prompt(domain)

        # 取得可用 MCP Server 清單
        available_servers = list(self.tool_manager.server_schemas.keys())

        # L1: 任務拆解（含 DAG 驗證迴圈）
        dag_feedback = ""
        disasm_ok = False
        units: List[Unit] = []
        max_dag_retries = MAX_DAG_RETRIES

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

            unit_result = await self._unit_runner.execute(
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

        # 計算 unit 總數與成功數
        total_units = len(all_unit_results)
        success_units = sum(1 for r in all_unit_results if r.status == UnitStatus.SUCCESS)
        log_action("orchestrator", "pipeline_complete", "OK",
                   f"complex total={total_units} success={success_units}")

        return reply

    # ------------------------------------------------------------------
    # 輔助方法
    # ------------------------------------------------------------------

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
        """產生新 session ID，使用 tracer 統一管理.
        同時建立 UnitRunner 和 ClarificationManager 實例."""
        session_id = tracer.new_session()
        self._unit_runner = UnitRunner(
            executor=self.executor,
            verifier=self.verifier,
            tool_manager=self.tool_manager,
            step_store=self._step_store,
            unit_store=self._unit_store,
            session_id=session_id,
        )
        self.clarification_manager = ClarificationManager(
            router=self.router,
            clarifier=self.clarifier,
            memory=self.memory,
        )
        return session_id