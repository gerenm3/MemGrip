"""v2 verifier — 輸出驗證.

依據 §3.7 (Verifier) 定義：
- verify(unit, actual_output) -> Result(data={"passed": bool, "reason": str})
- actual_output 為 output_type=GLOBAL 的 Steps 輸出合併
- 使用 MEDIUM_MODEL_NAME
- 符合 v2 logging 規範
"""

import asyncio
import logging
from typing import Any, Awaitable, Callable

import config
from clients.message_builder import MessageBuilder
from core.health import log_action
from core.json_utils import parse_first_json
from core.prompts import VERIFY_PROMPT
from models.blueprints import Unit, Result

logger = logging.getLogger(__name__)


class Verifier:
    """輸出驗證器：檢查 Unit 輸出是否符合預期"""

    def __init__(self, call_model_func: Callable[..., Awaitable[Result]]) -> None:
        self.call_model_func = call_model_func
        if not callable(call_model_func):
            raise TypeError("call_model_func must be callable")

    async def verify(self, unit: Unit, actual_output: str) -> Result:
        """驗證 Unit 輸出是否符合 expected_output.

        Args:
            unit: 要驗證的 Unit
            actual_output: 實際輸出（GLOBAL Steps 合併）

        Returns:
            Result(data={"passed": bool, "reason": str})
        """
        expected = unit.expected_output or ""
        expected_str = expected if expected else "(未指定)"

        # 格式化 assigned constraints
        constraints = unit.assigned_constraints or []
        if constraints:
            constraints_str = "\n".join(f"- {c}" for c in constraints)
        else:
            constraints_str = "（無 assigned constraints）"

        log_action("verifier", "verify_start", "OK", unit.unit_id)

        prompt = VERIFY_PROMPT.format(
            output_type=unit.output_type,
            expected=expected_str,
            actual=actual_output,
            constraints=constraints_str,
        )
        messages = MessageBuilder.build_task(prompt, "")

        try:
            result = await asyncio.wait_for(
                self.call_model_func(
                    config.MEDIUM_MODEL_NAME,
                    messages,
                    0.0,
                    1024,
                    False,
                    caller="verifier",
                ),
                timeout=config.LLM_TIMEOUT,
            )
        except asyncio.TimeoutError:
            logger.error("[Verifier] LLM call timed out (%ds)", config.LLM_TIMEOUT)
            return Result(success=False, error=f"驗證服務逾時 ({config.LLM_TIMEOUT}s)")
        except Exception as e:
            logger.error("[Verifier] LLM call failed: %s", e, exc_info=True)
            return Result(success=False, error="驗證服務不可用")

        content = result.data or ""
        parsed = parse_first_json(content)
        if isinstance(parsed, dict):
            passed = parsed.get("passed", False)
            reason = parsed.get("reason", "")
            gaps = parsed.get("gaps", [])
            if passed:
                log_action("verifier", "verify_passed", "OK", unit.unit_id)
            else:
                log_action("verifier", "verify_failed", "DEGRADED",
                           f"{unit.unit_id}: gaps={len(gaps)}", "單元驗證未通過")
            return Result(success=True, data=parsed)
        return Result(success=False, data={"passed": False, "reason": "驗證輸出格式錯誤"})
