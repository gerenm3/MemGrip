"""OllamaClient — 模型調用封裝"""

import ollama
from typing import List, Dict, Any, Optional


class OllamaClient:
    """Ollama 模型調用客戶端"""

    def __init__(self):
        self.client = ollama.AsyncClient()

    async def chat(
        self,
        model: str,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 8192,
        think: bool = False,
        tools: Optional[List[Dict]] = None,
    ) -> tuple:
        print(f"[OllamaClient.chat] === chat() 開始 ===")
        print(f"[OllamaClient.chat]   model={model}, messages_len={len(messages)}, temp={temperature}, max_tokens={max_tokens}, think={think}")
        if messages:
            print(f"[OllamaClient.chat]   first_msg role={messages[0].get('role')}, content={messages[0].get('content', '')[:200]!r}")
            print(f"[OllamaClient.chat]   last_msg role={messages[-1].get('role')}, content={messages[-1].get('content', '')[:200]!r}")
        if tools:
            print(f"[OllamaClient.chat]   tools={len(tools)} 個, tool_names={[t.get('function', {}).get('name', '') for t in tools]}")
        print(f"\n\nchat有正在跑-----------------------------------------------------------------------\n\n")
        response = await self.client.chat(
            model=model,
            messages=messages,
            tools=tools,
            think=think,
            options={"temperature": temperature, "num_predict": max_tokens},
        )
        message = response.get("message", {})
        content = message.get("content", "")
        tool_calls = message.get("tool_calls", [])
        
        print(f"[OllamaClient.chat]   模型返回: content_len={len(content) if content else 0}, tool_calls={len(tool_calls) if tool_calls else 0}")
        if content:
            print(f"[OllamaClient.chat]   content={content[:500]!r}")
        if tool_calls:
            for tc in tool_calls:
                t_name = tc.get("function", {}).get("name", "")
                t_args = tc.get("function", {}).get("arguments", "{}")
                print(f"[OllamaClient.chat]   tool_call: {t_name}({t_args})")
        print(f"[OllamaClient.chat] === chat() 完成 ===")
        return content, tool_calls

    async def embed(self, model: str, input: str) -> List[float]:
        response = await self.client.embed(model=model, input=input)
        return response.get("embeddings", [])
