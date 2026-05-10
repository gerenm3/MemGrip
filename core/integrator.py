"""Integrator — 最終整合回覆"""

import config
import json
from typing import Dict, List
from models.blueprints import Unit, UnitResult, UnitStatus
from clients.message_builder import MessageBuilder


class Integrator:
    """最終整合器：整合所有 Unit 結果生成回覆"""

    def __init__(self, call_model_func=None):
        self.call_model_func = call_model_func

    async def integrate(self, original_task: str,
                        results: Dict[str, UnitResult],
                        units: List[Unit]) -> str:
        """整合所有 Unit 結果生成最終回覆

        Args:
            original_task: 原始任務描述
            results: {unit_id: UnitResult}
            units: L1 產生的 Unit 列表（用於查找 goal / output_type）

        Returns:
            最終回覆字串
        """
        success_results = [r for r in results.values() if r.status == UnitStatus.SUCCESS]
        failed_results = [r for r in results.values() if r.status == UnitStatus.FAILED]
        skipped_results = [r for r in results.values() if r.status == UnitStatus.SKIPPED]

        # 全部失敗 → 仍回覆用戶（永不沉默）
        if not success_results and not failed_results and not skipped_results:
            return "對不起，我無法完成您的請求。系統出現異常。"

        # 建構輸出內容（JSON 格式，讓 LLM 清楚區分欄位邊界）
        unit_outputs = {}

        if success_results:
            for r in success_results:
                unit_obj = next((u for u in units if u.unit_id == r.unit_id), None)
                if unit_obj and unit_obj.output_type == 'ACTION':
                    clean_goal = unit_obj.goal
                    for dep_id in unit_obj.depends_on:
                        dep_unit = next((u for u in units if u.unit_id == str(dep_id)), None)
                        if dep_unit:
                            clean_goal = clean_goal.replace(f"<unit:{dep_id}>", dep_unit.expected_output)
                    unit_outputs[f"unit_{r.unit_id}"] = {
                        "status": "SUCCESS",
                        "goal": clean_goal,
                        "output_type": "ACTION"
                    }
                else:
                    unit_outputs[f"unit_{r.unit_id}"] = {
                        "status": "SUCCESS",
                        "goal": unit_obj.goal if unit_obj else "",
                        "output_type": unit_obj.output_type if unit_obj else "CONTENT",
                        "output": r.output or ""
                    }

        if failed_results:
            for r in failed_results:
                unit_outputs[f"unit_{r.unit_id}"] = {
                    "status": "FAILED",
                    "error": r.error or ""
                }

        if skipped_results:
            for r in skipped_results:
                unit_outputs[f"unit_{r.unit_id}"] = {
                    "status": "SKIPPED",
                    "error": r.error or ""
                }

        # 呼叫模型生成回覆
        prompt = config.INTEGRATION_PROMPT
        # 將 outputs 轉為 JSON 字串，讓 LLM 清楚區分每個單元輸出的欄位邊界
        outputs_dict = {
            "task": original_task,
            "outputs": unit_outputs
        }
        messages = MessageBuilder.build_task(prompt, json.dumps(outputs_dict, ensure_ascii=False, indent=2))

        if self.call_model_func:
            content, _ = await self.call_model_func(
                config.MEDIUM_MODEL_NAME, messages,
                config.INTEGRATION_TEMPERATURE, config.INTEGRATION_MAX_TOKENS,
                config.INTEGRATION_THINK
            )
            return content
        else:
            # 無模型時的 fallback
            return f"任務完成。\n\n{json.dumps(unit_outputs, ensure_ascii=False, indent=2)}"
