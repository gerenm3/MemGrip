"""clients/cloud.py — 雲端 LLM 呼叫客戶端（使用 LiteLLM）."""

import logging
from typing import Any, Dict, List, Optional

import litellm
from core.health import log_action
from config import CLOUD_API_KEY, LLM_TIMEOUT
from clients.base import ChatResponse, serialize_tool_calls

logger = logging.getLogger(__name__)

# 預設參數
DEFAULT_TEMPERATURE = 0.7
DEFAULT_MAX_TOKENS = 8192


class CloudServiceError(Exception):
    """雲端服務異常"""
    pass


class CloudClient:
    """雲端 LLM 呼叫客戶端（使用 LiteLLM）"""

    def __init__(self, tracer=None) -> None:
        """初始化 CloudClient。

        Args:
            tracer: 可選的 tracer 物件，用於記錄 trace。
        """
        self.tracer = tracer

    async def chat(
        self,
        model: str,
        messages: List[Dict[str, str]],
        temperature: float = DEFAULT_TEMPERATURE,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        think: bool = False,
        tools: Optional[List[Dict]] = None,
        caller: Optional[str] = None,
        unit_id: Optional[str] = None,
        step_id: Optional[str] = None,
    ) -> ChatResponse:
        """呼叫雲端 LLM 進行對話（使用 LiteLLM）。

        Args:
            model: 模型名稱
            messages: 對話訊息列表
            temperature: 溫度參數
            max_tokens: 最大 token 數
            think: 是否啟用思考模式
            tools: 可選的工具列表
            caller: 呼叫者標識，用於 trace
            unit_id: Unit ID，用於 trace
            step_id: Step ID，用於 trace

        Returns:
            ChatResponse 物件
        """
        try:
            log_action("cloud_client", "model_call_start", "OK", f"model={model}, caller={caller}")

            # 根據 think 模式選擇 reasoning_effort
            reasoning_effort = "high" if think else "none"

            response = await litellm.acompletion(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                tools=tools or None,
                reasoning_effort=reasoning_effort,
                api_key=CLOUD_API_KEY,
                timeout=LLM_TIMEOUT,
                drop_params=True,
            )

            content = response.choices[0].message.content or ""
            tool_calls = response.choices[0].message.tool_calls or []
            reasoning_content = getattr(response.choices[0].message, "reasoning_content", None)

            # 寫入 trace（若 tracer 已注入）
            if self.tracer is not None:
                self.tracer.log_model_call(
                    caller=caller,
                    model=model,
                    messages=messages,
                    response=content,
                    tool_calls=serialize_tool_calls(tool_calls),
                    unit_id=unit_id,
                    step_id=step_id,
                )

            log_action("cloud_client", "model_call_end", "OK", f"model={model}, caller={caller}")
            return ChatResponse(
                content=content,
                tool_calls=tool_calls,
                reasoning_content=reasoning_content,
            )
        except Exception as e:
            log_action("cloud_client", "model_call_failed", "FAILED", str(e), "雲端模型呼叫失敗")
            logger.error("[CloudClient] chat failed: %s", e, exc_info=True)
            raise CloudServiceError(f"{type(e).__name__}: {e}") from e

    async def embed(self, model: str, input_text: str) -> List[float]:
        """取得文字 embedding（使用 LiteLLM）。

        Args:
            model: 模型名稱
            input_text: 輸入文字

        Returns:
            embedding 向量列表
        """
        try:
            # 雲端模型通常不支援 embed，此方法保留作為擴充
            logger.warning("[CloudClient] embed not implemented for cloud API")
            return []
        except Exception as e:
            logger.error("[CloudClient] embed failed: %s", e, exc_info=True)
            raise CloudServiceError(f"{type(e).__name__}: {e}") from e