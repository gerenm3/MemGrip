"""Clarifier — core/orchestrator.py _clarify"""

import json
import re
import config
from typing import Any
from clients.message_builder import MessageBuilder

INPUT_TAGS: dict[str, str] = {
    "buffer": "[BUFFER]{text}[/BUFFER]",
    "summary": "[SUMMARY]{text}[/SUMMARY]",
    "user_input": "[USER_INPUT]{text}[/USER_INPUT]",
}


class Clarifier:
    """Clarifier：將用戶輸入轉為結構化欄位"""

    def __init__(
        self,
        call_model_func: Any,
        buffer: Any,
        summary: Any,
    ) -> None:
        self.call_model_func = call_model_func
        self.buffer = buffer
        self.summary = summary

    async def _clarify(self, user_input: str) -> dict:
        """Clarify：將 user_input 轉成結構化欄位（含 retry 機制）"""
        buffer_text = self.buffer.serialize() or ""
        summary_text = self.summary.get_summary() or ""

        input_text = self._format_input(buffer_text, summary_text, user_input)

        messages = MessageBuilder.build_task(config.CLARIFY_PROMPT, input_text)
        
        max_attempts = 3
        for _ in range(max_attempts):
            content, _ = await self.call_model_func(
                config.MEDIUM_MODEL_NAME,
                messages,
                config.CLARIFY_TEMPERATURE,
                config.CLARIFY_MAX_TOKENS,
                False,
                caller="clarifier",
            )
            parsed = self._parse_json_response(content)
            if parsed:
                return parsed
        
        # 3 次解析都失敗，回傳含 questions 的結構讓 orchestrator 向用戶提問
        return {
            "goal": "",
            "entities": [],
            "scope": "",
            "constraints": [],
            "rules": [],
            "success_criteria": "",
            "questions": ["您的需求描述不够清楚，能否重新说明您想要完成的任务？"]
        }

    def _format_input(self, buffer_text: str, summary_text: str, user_input: str) -> str:
        """格式化輸入文字"""
        input_parts = [
            INPUT_TAGS["buffer"].format(text=buffer_text) if buffer_text else None,
            INPUT_TAGS["summary"].format(text=summary_text) if summary_text else None,
            INPUT_TAGS["user_input"].format(text=user_input),
        ]
        return "\n".join(part for part in input_parts if part)

    @staticmethod
    def _parse_json_response(content: str) -> dict | None:
        """解析 JSON 回應"""
        match = re.search(r"\{.*?\}", content, re.DOTALL)
        try:
            return json.loads(match.group()) if match else None
        except (json.JSONDecodeError, AttributeError):
            return None

    @staticmethod
    def _default_clarify(user_input: str) -> dict:
        """JSON 解析失敗時的預設值"""
        return {
            "goal": user_input,
            "entities": [],
            "scope": "",
            "constraints": [],
            "rules": [],
            "success_criteria": "",
            "questions": [],
        }
