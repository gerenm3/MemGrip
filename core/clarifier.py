"""Clarifier — 結構化用戶輸入，輸出結構化欄位

依據 §3.2 (Clarifier) 定義：
- 公開 API clarify() 回傳 Result(data=ClarifyResult)
- buffer/summary/rag 由 Orchestrator 準備後作為參數傳入（原則 23）
- 內部最多 3 次 retry（含 JSON 解析失敗）
- 每次 LLM 呼叫包覆 timeout
- 失敗寫入 health.log_action(DEGRADED)
"""

import asyncio
import logging
import config
from typing import Any, Awaitable, Callable

from models.blueprints import Result

logger = logging.getLogger(__name__)

# Module-level constants
MAX_CLARIFY_ATTEMPTS = 3

from clients.message_builder import MessageBuilder
from core.json_utils import parse_first_json
from core.prompts import CLARIFY_PROMPT
from core.health import log_action

INPUT_TAGS: dict[str, str] = {
    "buffer": "[BUFFER]{text}[/BUFFER]",
    "summary": "[SUMMARY]{text}[/SUMMARY]",
    "user_input": "[USER_INPUT]{text}[/USER_INPUT]",
}


class Clarifier:
    """Clarifier：將用戶輸入轉為結構化欄位"""

    def __init__(
        self,
        call_model_func: Callable[..., Awaitable[Result]],
        buffer: Any,
        summary: Any,
    ) -> None:
        self.call_model_func = call_model_func
        self.buffer = buffer
        self.summary = summary

    async def clarify(self, user_input: str, buffer_text: str = "", summary_text: str = "", rag: str = "") -> Result:
        """Clarify（公開）：將 user_input 轉成結構化欄位（含 retry 機制）

        依據 §3.2：buffer/summary/rag 由 Orchestrator 準備後作為參數傳入。
        """
        try:
            parsed = await self._clarify(user_input, buffer_text, summary_text)
            log_action("clarifier", "clarify_done", "OK", f"goal={parsed.get('goal', '')}, constraints={len(parsed.get('constraints', []))}")
            return Result(success=True, data=parsed, error="")
        except Exception as e:
            log_action("clarifier", "clarify_retry_exhausted", "DEGRADED", str(e), "無法解析您的輸入")
            return Result(success=False, data=None, error=str(e))
    
    async def _clarify(self, user_input: str, buffer_text: str = "", summary_text: str = "") -> dict:
        """Clarify：將 user_input 轉成結構化欄位（含 retry 機制）"""
        input_text = self._format_input(buffer_text, summary_text, user_input)

        messages = MessageBuilder.build_task(CLARIFY_PROMPT, input_text)
        
        max_attempts = MAX_CLARIFY_ATTEMPTS
        for attempt in range(max_attempts):
            try:
                result = await asyncio.wait_for(
                    self.call_model_func(
                        config.MEDIUM_MODEL_NAME,
                        messages,
                        config.CLARIFY_TEMPERATURE,
                        config.CLARIFY_MAX_TOKENS,
                        False,
                        caller="clarifier",
                    ),
                    timeout=config.LLM_TIMEOUT,
                )
                if not result.success:
                    logger.error("Clarifier LLM call failed: %s", result.error)
                    log_action("clarifier", "llm_call_failed", "DEGRADED", result.error, "LLM 呼叫失敗")
                    continue
                content = result.data
            except asyncio.TimeoutError as e:
                logger.error("Clarifier LLM call timeout: %s", e)
                log_action("clarifier", "llm_call_timeout", "DEGRADED", str(e), "LLM 呼叫超時")
                continue
            except Exception as e:
                logger.error("Clarifier LLM call failed: %s", e)
                log_action("clarifier", "llm_call_failed", "DEGRADED", str(e), "LLM 呼叫失敗")
                continue

            parsed = self._parse_json_response(content)
            if parsed:
                log_action("clarifier", "clarify_success", "OK")
                return parsed
        
        # 3 次解析都失敗，回傳含 questions 的結構讓 orchestrator 向用戶提問
        log_action("clarifier", "clarify_retry_exhausted", "DEGRADED", "3 attempts failed", "無法解析您的輸入")
        return {
            "goal": "",
            "entities": [],
            "scope": "",
            "constraints": [],
            "rules": [],
            "success_criteria": [],
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
        """解析 JSON 回應（使用 parse_first_json）"""
        return parse_first_json(content)

    @staticmethod
    def _default_clarify(user_input: str) -> dict:
        """JSON 解析失敗時的預設值"""
        return {
            "goal": user_input,
            "entities": [],
            "scope": "",
            "constraints": [],
            "rules": [],
            "success_criteria": [],
            "questions": [],
        }
