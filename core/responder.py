"""Responder — 回覆生成與最終整合"""

import json
import config
from typing import Any, Dict, List, Optional
from models.blueprints import Unit, UnitResult, UnitStatus
from clients.message_builder import MessageBuilder


class Responder:
    """回覆生成器：整合所有 Unit 結果生成回覆 / 生成簡單回覆"""

    def __init__(self, call_model_func: Optional[Any] = None) -> None:
        self.call_model_func = call_model_func

    async def reply_simple(
        self,
        system_prompt: str,
        user_input: str,
        summary_content: str,
        buffer_content: str,
        rag_content: str,
    ) -> str:
        """生成 simple intent 的直接回覆"""
        messages = MessageBuilder.build_dialog(
            system_prompt, user_input,
            summary_content, buffer_content, rag_content
        )
        raw_reply = await self.call_model_func(
            config.MEDIUM_MODEL_NAME, messages,
            config.TEMPERATURE, config.MAX_TOKENS, config.THINK,
            caller="orchestrator"
        )
        return raw_reply[0] if isinstance(raw_reply, tuple) else raw_reply

    async def integrate(
        self,
        original_task: str,
        results: Dict[str, UnitResult],
        units: List[Unit],
    ) -> str:
        """整合所有 Unit 結果生成最終回覆"""
        success_results = [r for r in results.values() if r.status == UnitStatus.SUCCESS]
        failed_results = [r for r in results.values() if r.status == UnitStatus.FAILED]
        skipped_results = [r for r in results.values() if r.status == UnitStatus.SKIPPED]

        # 過濾：只保留 L1 指定的 GLOBAL units（output_type 為 CONTENT 或 ACTION）
        global_unit_ids = {u.unit_id for u in units if u.output_type in ("CONTENT", "ACTION")}
        success_results = [r for r in success_results if r.unit_id in global_unit_ids]

        # 全部失敗 → 仍回覆用戶（永不沉默）
        if not any([success_results, failed_results, skipped_results]):
            return "對不起，我無法完成您的請求。系統出現異常。"

        unit_outputs = self._format_all_results(success_results, failed_results, skipped_results, units)
        prompt = config.INTEGRATION_PROMPT
        outputs_dict = {"task": original_task, "outputs": unit_outputs}
        messages = MessageBuilder.build_task(prompt, json.dumps(outputs_dict, ensure_ascii=False, indent=2))

        if self.call_model_func:
            content, _ = await self.call_model_func(
                config.MEDIUM_MODEL_NAME, messages,
                config.INTEGRATION_TEMPERATURE, config.INTEGRATION_MAX_TOKENS,
                config.INTEGRATION_THINK,
                caller="integrator",
            )
            return content

        # 無模型時的 fallback
        return f"任務完成。\n\n{json.dumps(unit_outputs, ensure_ascii=False, indent=2)}"

    def _format_all_results(
        self,
        success_results: List[UnitResult],
        failed_results: List[UnitResult],
        skipped_results: List[UnitResult],
        units: List[Unit],
    ) -> dict[str, dict]:
        """格式化所有 Unit 結果"""
        unit_map: dict[str, Unit] = {u.unit_id: u for u in units}
        outputs: dict[str, dict] = {}
        outputs |= self._format_success(success_results, unit_map)
        outputs |= self._format_failed(failed_results)
        outputs |= self._format_skipped(skipped_results)
        return outputs

    def _format_success(self, results: List[UnitResult], unit_map: dict[str, Unit]) -> dict[str, dict]:
        """格式化成功的結果"""
        return {
            f"unit_{r.unit_id}": {
                "status": "SUCCESS",
                "goal": unit_obj.goal if (unit_obj := unit_map.get(r.unit_id)) else "",
                "output_type": unit_obj.output_type if unit_obj else "CONTENT",
                "output": r.output if unit_obj else r.output,
            } | (
                {"output_type": "ACTION"}
                if unit_obj and unit_obj.output_type == "ACTION"
                else {}
            )
            for r in results
        }

    def _format_failed(self, results: List[UnitResult]) -> dict[str, dict]:
        """格式化失敗的結果"""
        return {
            f"unit_{r.unit_id}": {"status": "FAILED", "error": r.error or ""}
            for r in results
        }

    def _format_skipped(self, results: List[UnitResult]) -> dict[str, dict]:
        """格式化跳過的结果"""
        return {
            f"unit_{r.unit_id}": {"status": "SKIPPED", "error": r.error or ""}
            for r in results
        }
