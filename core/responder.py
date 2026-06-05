"""v2 responder — 回覆生成與最終整合.

依據 §3.8 (Responder) 定義：
- reply_simple: 簡單意圖直接回覆
- reply_tool: tool intent 回覆
- integrate: 整合所有 Unit 結果生成最終回覆
- 只整合 output_type 為 CONTENT 或 ACTION 的 Unit 結果
- 符合 v2 logging 規範
"""

import asyncio
import json
import logging
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

import config
from clients.message_builder import MessageBuilder
from core.health import log_action
from core.prompts import INTEGRATION_PROMPT
from models.blueprints import Result, Unit, UnitResult, UnitStatus

logger = logging.getLogger(__name__)


class Responder:
    """回覆生成器：整合所有 Unit 結果生成回覆"""

    def __init__(self, call_model_func: Optional[Callable[..., Awaitable[Result]]] = None) -> None:
        self.call_model_func = call_model_func

    async def reply_simple(
        self,
        system_prompt: str,
        user_input: str,
        buffer: str,
        summary: str,
        rag: str,
    ) -> Result:
        """生成 simple intent 的直接回覆.

        Args:
            system_prompt: 系統提示
            user_input: 用戶輸入
            buffer: 對話緩衝區內容
            summary: 摘要內容
            rag: RAG 檢索內容

        Returns:
            Result(data=str)
        """
        try:
            messages = MessageBuilder.build_dialog(
                system_prompt, user_input, summary, buffer, rag
            )
            result_obj = await asyncio.wait_for(
                self.call_model_func(
                    config.MODEL_MEDIUM, messages,
                    config.TEMPERATURE, config.MAX_TOKENS, config.THINK,
                    caller="responder"
                ),
                timeout=config.LLM_TIMEOUT,
            )
            if not result_obj.success:
                return Result(success=False, error=f"reply_simple LLM 失敗: {result_obj.error}")
            reply = result_obj.data if isinstance(result_obj.data, str) else str(result_obj.data)
            log_action("responder", "reply_simple_complete", "OK")
            return Result(success=True, data=reply)
        except asyncio.TimeoutError:
            logger.error("[Responder] reply_simple 逾時 (%ds)", config.LLM_TIMEOUT)
            log_action("responder", "reply_simple_failed", "FAILED", f"timeout={config.LLM_TIMEOUT}s", "簡單回覆逾時")
            return Result(success=False, error=f"reply_simple 逾時 ({config.LLM_TIMEOUT}s)")
        except Exception as e:
            logger.error("[Responder] reply_simple 失敗: %s", e, exc_info=True)
            log_action("responder", "reply_simple_failed", "FAILED", str(e), "簡單回覆失敗")
            return Result(success=False, error=f"reply_simple 失敗: {e}")

    async def reply_tool(
        self,
        agentic_loop_output: str,
        user_input: str,
    ) -> Result:
        """生成 tool intent 的回覆.

        Args:
            agentic_loop_output: Agentic Loop 輸出
            user_input: 用戶輸入

        Returns:
            Result(data=str)
        """
        try:
            messages = [
                {"role": "user", "content": f"[USER_INPUT]{user_input}[/USER_INPUT]\n[AGENTIC_OUTPUT]{agentic_loop_output}[/AGENTIC_OUTPUT]"},
                {"role": "system", "content": "請根據 Agentic Loop 的輸出，生成一份自然、完整的回覆給用戶。"},
            ]
            result_obj = await asyncio.wait_for(
                self.call_model_func(
                    config.MODEL_MEDIUM, messages,
                    config.TEMPERATURE, config.MAX_TOKENS, config.THINK,
                    caller="responder_tool"
                ),
                timeout=config.LLM_TIMEOUT,
            )
            if not result_obj.success:
                return Result(success=False, error=f"reply_tool LLM 失敗: {result_obj.error}")
            reply = result_obj.data if isinstance(result_obj.data, str) else str(result_obj.data)
            log_action("responder", "reply_tool_complete", "OK")
            return Result(success=True, data=reply)
        except asyncio.TimeoutError:
            logger.error("[Responder] reply_tool 逾時 (%ds)", config.LLM_TIMEOUT)
            log_action("responder", "reply_tool_failed", "FAILED", f"timeout={config.LLM_TIMEOUT}s", "工具回覆逾時")
            return Result(success=False, error=f"reply_tool 逾時 ({config.LLM_TIMEOUT}s)")
        except Exception as e:
            logger.error("[Responder] reply_tool 失敗: %s", e, exc_info=True)
            log_action("responder", "reply_tool_failed", "FAILED", str(e), "工具回覆失敗")
            return Result(success=False, error=f"reply_tool 失敗: {e}")

    async def integrate(
        self,
        original_task: Dict[str, Any],
        results: Dict[str, UnitResult],
        units: List[Unit],
    ) -> Result:
        """整合所有 Unit 結果生成最終回覆.

        輸入分為兩個層次：
        1. 實質內容：leaf CONTENT unit（無同類型下游依賴）的 actual_output
        2. 執行概況：所有 unit 的 goal + status + output_type

        Args:
            original_task: 原始任務描述 dict
            results: Unit 執行結果 Dict[unit_id, UnitResult]
            units: Unit 列表

        Returns:
            Result(data=str)
        """
        if not units:
            return Result(success=True, data="任務已執行完成。")

        success_results, failed_results, skipped_results = self._classify_results(results)
        unit_map = {u.unit_id: u for u in units}

        # 建構反向依賴映射，找出 leaf CONTENT units
        dependents = self._build_reverse_deps(units)

        # 區分兩種輸入
        substantive_units = self._collect_substantive_units(results, unit_map, dependents)
        execution_summary = self._build_execution_summary(units, results)

        # 邊界條件：沒有任何 CONTENT 或 ACTION unit
        has_content_or_action = any(u.output_type in ("CONTENT", "ACTION") for u in units)
        if not has_content_or_action:
            if failed_results:
                return Result(success=False, error="任務執行時發生錯誤。")
            return Result(success=True, data="任務已執行完成。")

        task_desc = original_task.get("goal", "") if isinstance(original_task, dict) else str(original_task)

        try:
            outputs_dict = {
                "task": task_desc,
                "substantive_content": substantive_units,
                "execution_summary": execution_summary,
            }
            outputs_json = json.dumps(outputs_dict, ensure_ascii=False, indent=2)
            messages = MessageBuilder.build_task(INTEGRATION_PROMPT, outputs_json)
        except Exception as e:
            logger.error("[Responder] integrate 格式化失敗: %s", e, exc_info=True)
            return Result(success=False, error=f"整合時發生錯誤：{e}")

        if self.call_model_func:
            try:
                result_obj = await self.call_model_func(
                    config.MODEL_MEDIUM, messages,
                    config.INTEGRATION_TEMPERATURE, config.INTEGRATION_MAX_TOKENS,
                    config.INTEGRATION_THINK,
                    caller="integrator",
                )
                if not result_obj.success:
                    logger.error("[Responder] 整合 LLM 失敗: %s", result_obj.error)
                    return Result(success=False, error=f"整合失敗: {result_obj.error}")
                content = result_obj.data if isinstance(result_obj.data, str) else str(result_obj.data)
                log_action("responder", "integrate_complete", "OK")
                return Result(success=True, data=content)
            except Exception as e:
                logger.error("[Responder] 整合時發生異常: %s", e, exc_info=True)
                log_action("responder", "integrate_failed", "FAILED", str(e), "整合結果失敗")
                return Result(success=False, error=f"整合時發生異常: {e}")

        log_action("responder", "integrate_complete", "OK")
        return Result(success=True, data=f"任務完成。\n\n{json.dumps(outputs_dict, ensure_ascii=False, indent=2)}")

    @staticmethod
    def _classify_results(
        results: Dict[str, UnitResult],
    ) -> Tuple[List[UnitResult], List[UnitResult], List[UnitResult]]:
        """將結果依狀態分類為 success / failed / skipped 三類"""
        success, failed, skipped = [], [], []
        for r in results.values():
            if r.status == UnitStatus.SUCCESS:
                success.append(r)
            elif r.status == UnitStatus.FAILED:
                failed.append(r)
            elif r.status == UnitStatus.SKIPPED:
                skipped.append(r)
        return success, failed, skipped

    @staticmethod
    def _build_reverse_deps(units: List[Unit]) -> Dict[str, List[str]]:
        """建構反向依賴映射：{unit_id: [下游 unit_id 列表]}"""
        dependents: Dict[str, List[str]] = {}
        for u in units:
            for dep_id in u.depends_on:
                dep_str = str(dep_id)
                dependents.setdefault(dep_str, []).append(u.unit_id)
        return dependents

    @staticmethod
    def _is_leaf_content(
        unit_id: str,
        unit_map: Dict[str, Unit],
        dependents: Dict[str, List[str]],
    ) -> bool:
        """判斷此 CONTENT unit 是否沒有同類型（CONTENT）的下游依賴。"""
        dep_unit = unit_map.get(unit_id)
        if not dep_unit or dep_unit.output_type != "CONTENT":
            return False
        # 檢查所有下游 unit 是否有 CONTENT 類型
        for dependent_id in dependents.get(unit_id, []):
            dependent_unit = unit_map.get(dependent_id)
            if dependent_unit and dependent_unit.output_type == "CONTENT":
                return False
        return True

    @staticmethod
    def _collect_substantive_units(
        results: Dict[str, UnitResult],
        unit_map: Dict[str, Unit],
        dependents: Dict[str, List[str]],
    ) -> List[Dict]:
        """收集 leaf CONTENT unit 的實質內容（含 actual_output）。

        只包含成功執行的 leaf CONTENT units。
        """
        substantive = []
        for unit_id, result in results.items():
            if Responder._is_leaf_content(unit_id, unit_map, dependents):
                unit = unit_map.get(unit_id)
                substantive.append({
                    "unit_id": unit_id,
                    "goal": unit.goal if unit else "",
                    "output": result.output if result.status == UnitStatus.SUCCESS else "",
                })
        return substantive

    @staticmethod
    def _build_execution_summary(
        units: List[Unit],
        results: Dict[str, UnitResult],
    ) -> List[Dict]:
        """建構所有 unit 的執行概況（不含 actual_output）。

        每個 unit 只包含 goal、status、output_type。
        """
        summary = []
        for unit in units:
            result = results.get(unit.unit_id)
            status_str = result.status.value if result else "UNKNOWN"
            summary.append({
                "unit_id": unit.unit_id,
                "goal": unit.goal,
                "output_type": unit.output_type,
                "status": status_str,
            })
        return summary