"""clients/ollama.py — Ollama 模型調用客戶端（底層使用 Ollama SDK）."""

import logging
from typing import Any, Dict, List, Optional

import ollama
from core.health import log_action
from config import MODEL_BASE_URL
from clients.base import ChatResponse, serialize_tool_calls

logger = logging.getLogger(__name__)

# 預設參數
DEFAULT_TEMPERATURE = 0.7
DEFAULT_MAX_TOKENS = 8192


class ModelServiceError(Exception):
    """模型服務異常"""
    pass


class OllamaLocalClient:
    """Ollama 模型調用客戶端（底層使用 Ollama SDK）"""

    def __init__(self, tracer=None) -> None:
        """初始化 OllamaLocalClient。

        Args:
            tracer: 可選的 tracer 物件，用於記錄 trace。
        """
        self.tracer = tracer
        self._client = ollama.AsyncClient(host=MODEL_BASE_URL)

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
        """呼叫 LLM 進行對話（使用 Ollama SDK）。

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
            log_action("model_client", "model_call_start", "OK", f"model={model}, caller={caller}")

            options = {
                "temperature": temperature,
                "num_predict": max_tokens,
            }

            response = await self._client.chat(
                model=model,
                messages=messages,
                options=options,
                tools=tools or [],
                think=think,
            )

            message = response.message
            content = message.content or ""
            tool_calls = getattr(message, "tool_calls", None) or []
            reasoning_content = getattr(message, "reasoning", None)

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

            log_action("model_client", "model_call_end", "OK", f"model={model}, caller={caller}")
            return ChatResponse(
                content=content,
                tool_calls=tool_calls,
                reasoning_content=reasoning_content,
            )
        except Exception as e:
            log_action("model_client", "model_call_failed", "FAILED", str(e), "模型呼叫失敗")
            logger.error("[OllamaLocalClient] chat failed: %s", e, exc_info=True)
            raise ModelServiceError(f"{type(e).__name__}: {e}") from e

    async def embed(self, model: str, input_text: str) -> List[float]:
        """取得文字 embedding（使用 Ollama SDK）。

        Args:
            model: 模型名稱
            input_text: 輸入文字

        Returns:
            embedding 向量列表
        """
        try:
            response = await self._client.embed(
                model=model,
                input=input_text,
            )
            embeddings = response.get("embeddings")
            if not embeddings:
                logger.warning("[OllamaLocalClient] embed returned no embeddings for model=%s", model)
                return []
            return embeddings[0]
        except Exception as e:
            logger.error("[OllamaLocalClient] embed failed: %s", e, exc_info=True)
            raise ModelServiceError(f"{type(e).__name__}: {e}") from e