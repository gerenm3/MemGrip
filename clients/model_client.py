"""OllamaClient — 模型調用封裝"""

import ollama
import json
import logging
from typing import Any, List, Dict, Optional, Tuple
from core.tracer import log_model_call


class ModelServiceError(Exception):
    """模型服務異常"""
    pass


class OllamaClient:
    """Ollama 模型調用客戶端"""

    def __init__(self) -> None:
        self.client = ollama.AsyncClient()

    @staticmethod
    def _serialize_tool_calls(tool_calls: List[Any]) -> List[Dict[str, Any]]:
        """將 tool_calls 轉換為可序列化的 dict"""
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
        print("\n==============================================================================")
        print(f"\nmessages:\n{json.dumps(messages, ensure_ascii=False, indent=2)}")

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

            if content:
                print(f"\ncontent:\n{content}")
            if tool_calls:
                print(f"\ntool_calls:\n{json.dumps(self._serialize_tool_calls(tool_calls), ensure_ascii=False, indent=2)}")
            print("\n==============================================================================\n")

            # 寫入 trace
            log_model_call(
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
            logging.error("Ollama API call failed: %s", e)
            raise ModelServiceError(f"Ollama 服務不可用：{e}") from e

    async def embed(self, model: str, input_text: str) -> List[float]:
        response = await self.client.embed(model=model, input=input_text)
        return response.get("embeddings", [])
