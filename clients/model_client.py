"""v2 OllamaClient — 模型調用封裝.

依據 §3.1 (ModelClient) 定義：
- class OllamaClient，提供 chat() 和 embed() 兩個介面
- __init__ 支援 client 注入（用於測試 mock）
- __init__ 支援 tracer 注入（用於 trace 記錄）
- 移除舊版 call_model_func() dead code
- 符合 v2 logging 規範（使用 logger 而非 print）
- 提供 _call_model() 公用函式供 Optimizer 等模組使用
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

import ollama
from models.blueprints import Result

logger = logging.getLogger(__name__)


async def _call_model(
    model: str,
    messages: List[Dict[str, str]],
    temperature: float = 0.7,
    max_tokens: int = 8192,
    think: bool = False,
    tools: Optional[List[Dict]] = None,
    caller: Optional[str] = None,
    unit_id: Optional[str] = None,
    step_id: Optional[str] = None,
) -> Result:
    """公用模型呼叫函式，供 Optimizer 等模組使用。

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
        Result(success=True, data=content, tool_calls=tool_calls)
    """
    client = OllamaClient()
    try:
        content, tool_calls = await client.chat(
            model, messages, temperature, max_tokens, think, tools,
            caller=caller, unit_id=unit_id, step_id=step_id,
        )
        return Result(success=True, data=content, tool_calls=tool_calls or [])
    except Exception as e:
        logger.error("[model_client] _call_model failed: %s", e, exc_info=True)
        return Result(success=False, error=str(e))


class ModelServiceError(Exception):
    """模型服務異常"""
    pass


class OllamaClient:
    """Ollama 模型調用客戶端"""

    def __init__(self, client=None, tracer=None) -> None:
        """初始化 OllamaClient。

        Args:
            client: 可選的 ollama.AsyncClient 實例。
                    若未提供則自動建立。支援測試時注入 mock client。
            tracer: 可選的 tracer 物件，用於記錄 trace。
        """
        self.client = client or ollama.AsyncClient()
        self.tracer = tracer

    @staticmethod
    def _serialize_tool_calls(tool_calls: List[Any]) -> List[Dict[str, Any]]:
        """將 tool_calls 轉換為可序列化的 dict。

        回傳的 arguments 欄位一律為 JSON 字串（str）。
        """
        return [
            {"name": tc.function.name, "arguments": tc.function.arguments}
            if hasattr(tc, "function")
            else dict(tc)
            for tc in tool_calls
        ]

    async def chat(
        self,
        model: str,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 8192,
        think: bool = False,
        tools: Optional[List[Dict]] = None,
        caller: Optional[str] = None,
        unit_id: Optional[str] = None,
        step_id: Optional[str] = None,
    ) -> Tuple[str, List[Any]]:
        """呼叫 LLM 進行對話.

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
            (content, tool_calls) 元組
        """
        try:
            response = await self.client.chat(
                model=model,
                messages=messages,
                tools=tools,
                think=think,
                options={"temperature": temperature, "num_predict": max_tokens},
            )
            message = response.message
            content = message.content or ""
            tool_calls = message.tool_calls or []

            # 寫入 trace（若 tracer 已注入）
            if self.tracer is not None:
                self.tracer.log_model_call(
                    caller=caller,
                    model=model,
                    messages=messages,
                    response=content,
                    tool_calls=self._serialize_tool_calls(tool_calls),
                    unit_id=unit_id,
                    step_id=step_id,
                )

            return content, tool_calls
        except Exception as e:
            logger.error("[OllamaClient] chat failed: %s", e, exc_info=True)
            raise ModelServiceError(f"{type(e).__name__}: {e}") from e

    async def embed(self, model: str, input_text: str) -> List[float]:
        """取得文字 embedding.

        Args:
            model: 模型名稱
            input_text: 輸入文字

        Returns:
            embedding 向量列表
        """
        try:
            response = await self.client.embed(model=model, input=input_text)
            embeddings = response.get("embeddings") or response.get("embedding")
            if embeddings is None:
                logger.warning("[OllamaClient] embed returned no embeddings for model=%s", model)
                return []
            return embeddings
        except Exception as e:
            logger.error("[OllamaClient] embed failed: %s", e, exc_info=True)
            raise ModelServiceError(f"{type(e).__name__}: {e}") from e
