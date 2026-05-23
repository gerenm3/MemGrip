"""Orchestrator — 純協調邏輯（不含模組實例化）"""

import asyncio
import config
import json
import logging
import time
from typing import Any, Dict, List
from models.blueprints import Unit, UnitStatus
from skills.skill_manager import load_skill, skill_guide_to_prompt
from core.tracer import new_session, log_task
from clients.model_client import ModelServiceError

logger = logging.getLogger(__name__)


class Orchestrator:
    """Orchestrator：純協調，不含任何模組實例化"""

    def __init__(
        self,
        router: Any,
        clarifier: Any,
        planner: Any,
        executor: Any,
        responder: Any,
        summarizer: Any,
        tool_manager: Any,
        buffer: Any,
        retriever: Any,
        summary: Any = None,
        temp_cache: Any = None,
        batch_summarizer: Any = None,
    ) -> None:
        self.router = router
        self.clarifier = clarifier
        self.planner = planner
        self.executor = executor
        self.responder = responder
        self.summarizer = summarizer
        self.tool_manager = tool_manager
        self.buffer = buffer
        self.retriever = retriever
        self.summary = summary
        self._summarize_tasks: set = set()
        self.temp_cache = temp_cache
        self.batch_summarizer = batch_summarizer
        self.last_batch_time: float = time.time()
        self._current_session_id: str | None = None

    async def run(self) -> None:
        """主循環"""
        try:
            await self.tool_manager._init_tools()
        except Exception as e:
            logger.warning("[Orchestrator] 工具初始化失敗：%s，仍可處理 simple 意圖", e)

        has_tools = bool(self.tool_manager.server_schemas)
        print("MemGrip — type 'exit' to quit\n")
        
        while True:
            user_input = self._get_user_input()
            if not user_input:
                continue

            # 新 session
            self._current_session_id = new_session()

            # 分流階段
            route_result = await self.router.route(user_input)
            intent = route_result['intent']
            need_rag = route_result['need_rag']

            # 上下文準備：透過 Retriever 取得 RAG 內容
            rag_content = await self.retriever.retrieve(user_input) if need_rag else ""

            # Intent 分流
            reply = await self._dispatch_by_intent(intent, user_input, rag_content, has_tools)

            self.buffer.add("user", user_input)
            self.buffer.add("assistant", reply)
            self._summarize_if_needed()
            print(f"MemGrip: {reply}\n")

    def _get_user_input(self) -> str:
        """獲取用戶輸入"""
        try:
            user_input = input("You: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nExiting.")
            raise SystemExit
        if user_input.lower() == "exit":
            print("\nGoodbye.")
            raise SystemExit
        return user_input

    async def _dispatch_by_intent(
        self, intent: str, user_input: str, rag_content: str, has_tools: bool
    ) -> str:
        """依意圖分流"""
        handlers = {
            "simple": self._handle_simple_intent,
            "tool": self._handle_tool_intent,
            "complex": self._handle_complex_intent,
        }
        handler = handlers.get(intent)
        if not handler:
            return f"未知意圖：{intent}"
        try:
            return await handler(user_input, rag_content, has_tools)
        except ModelServiceError:
            return "⚠️ AI 服務暫時不可用，請稍後再試。"

    async def _handle_simple_intent(self, user_input: str, rag_content: str, has_tools: bool) -> str:
        """處理簡單意圖"""
        return await self.responder.reply_simple(
            config.SYSTEM_PROMPT, user_input,
            self.summary.get_summary() if self.summary else "",
            self.buffer.serialize(), rag_content
        )

    async def _handle_tool_intent(self, user_input: str, rag_content: str, has_tools: bool) -> str:
        """處理工具意圖"""
        if not has_tools:
            return "⚠️ 目前無法使用工具（工具初始化失敗），請稍後再試。"

        clarify_result = await self._do_clarify(user_input)
        
        if (questions := clarify_result.get("questions")):
            return self._format_clarification_question(questions)

        clarify_goal = clarify_result.get("goal", user_input)
        server_names = list(self.tool_manager.server_schemas.keys())
        selected_server = await self.router.probe_server(clarify_goal, server_names)

        if selected_server not in self.tool_manager.server_schemas:
            return "⚠️ 無法判斷需要哪個工具，請更明確描述您的需求。"

        all_tools = self.tool_manager.server_schemas.get(selected_server, [])
        environment = self.tool_manager.tool_environments.get(selected_server, "")
        final_reply = await self.tool_manager.run_agentic_loop(
            clarify_goal, rag_content, all_tools, environment=environment
        )
        return final_reply

    async def _handle_complex_intent(self, user_input: str, rag_content: str, has_tools: bool) -> str:
        """處理複雜意圖"""
        if not has_tools:
            return "⚠️ 目前無法使用工具（工具初始化失敗），請稍後再試。"

        clarify_result = await self._do_clarify(user_input)

        if (questions := clarify_result.get("questions")):
            return self._format_clarification_question(questions)

        clarify_goal = clarify_result.get("goal", user_input)
        clarify_entities = clarify_result.get("entities", [])
        clarify_scope = clarify_result.get("scope", "")
        clarify_constraints = clarify_result.get("constraints", [])
        clarify_success_criteria = clarify_result.get("success_criteria", "")

        # L1 戰略拆解：將任務拆成 Units
        task_type = clarify_result.get("task_type", "general")
        skill_guide = load_skill(task_type)
        skill_guide_text = skill_guide_to_prompt(skill_guide)

        server_names = list(self.tool_manager.server_schemas.keys())
        units = await self.planner.disassemble(
            clarify_goal,
            clarify_entities,
            clarify_scope,
            clarify_constraints,
            clarify_success_criteria,
            tools=json.dumps(server_names, ensure_ascii=False, indent=2),
            skill_guide=skill_guide_text
        )

        if not units:
            return "未產生任何執行單元。"

        # L3 執行所有 Units
        results = await self.executor.execute_units(
            units, self.tool_manager.server_schemas
        )

        # === 新增：LVS 評估 ===
        from skills.lvs import (
            calculate_q,
            update_global_score,
            should_trigger,
            reset_after_trigger,
        )

        any_failed = any(r.status == UnitStatus.FAILED for r in results.values())
        task_record = {
            "session_id": self._current_session_id,
            "final_status": "failed" if any_failed else "success",
            "units": [
                {
                    "unit_id": uid,
                    "status": r.status.value,
                    "replan_count": r.replan_count,
                    "total_loop_count": r.total_loop_count,
                }
                for uid, r in results.items()
            ],
        }
        q = calculate_q(task_record)

        if should_trigger():
            g = update_global_score(q)
            last_run = reset_after_trigger()
            logger.info("[LVS] 觸發 optimizer (G=%.1f, Q=%.1f, last_run=%s)", g, q, last_run)

            # 觸發 optimizer（只更新 skill_guide，下次任務受益）
            try:
                import asyncio as _asyncio
                from skills.optimizer import run_optimizer as _run_optimizer
                _asyncio.create_task(_run_optimizer(str(self._current_session_id), task_type))
            except Exception as e:
                logger.error("[LVS] optimizer 呼叫失敗：%s", e)

            # 記錄原始結果（如實記錄本次任務問題）
            log_task(task_type, user_input, clarify_goal, results, units)

            # 正常整合回應
            reply = await self.responder.integrate(user_input, results, units)
            return f"⚠️ 本任務品質不佳（Q={q:.0f}），已觸發 optimizer 優化 skill guide。\n{reply}"
        else:
            g = update_global_score(q)
            logger.debug("[LVS] 未觸發 optimizer (G=%.1f, Q=%.1f)", g, q)
            # 記錄原始結果
            log_task(task_type, user_input, clarify_goal, results, units)
            # 正常整合回應
            reply = await self.responder.integrate(user_input, results, units)
            return reply

    async def _do_clarify(self, user_input: str) -> dict:
        """執行澄清"""
        clarify_result = await self.clarifier._clarify(user_input)
        return clarify_result

    def _format_clarification_question(self, questions: list[str]) -> str:
        """格式化澄清問題"""
        return "需要您進一步說明：\n" + "\n".join(f"- {q}" for q in questions)

    def _summarize_if_needed(self) -> None:
        """如果需要摘要則進行摘要"""
        flushed = self.buffer.storage()
        if flushed and self.summarizer:
            task = asyncio.create_task(self.summarizer.summarize(flushed))
            self._summarize_tasks.add(task)
            task.add_done_callback(self._summarize_tasks.discard)

        # 批次摘要：閒置 >= 900 秒 或 累積達 8000 tokens 時觸發
        if (
            self.temp_cache
            and self.batch_summarizer
            and self.temp_cache.count() > 0
        ):
            idle_seconds = time.time() - self.last_batch_time
            force_trigger = self.temp_cache.total_tokens() >= config.TEMP_CACHE_FORCE_TOKENS
            
            if idle_seconds >= config.TEMP_CACHE_IDLE_SECONDS or force_trigger:
                batch_task = asyncio.create_task(
                    self.batch_summarizer.flush(self.temp_cache)
                )
                self._summarize_tasks.add(batch_task)
                batch_task.add_done_callback(self._summarize_tasks.discard)
                self.last_batch_time = time.time()
