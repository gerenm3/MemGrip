"""Router — core/orchestrator.py"""

import json
import logging
import re
import config
from typing import Any, Optional
from clients.message_builder import MessageBuilder

logger = logging.getLogger(__name__)


class Router:
    """Router：負責 intent 分流與 pattern 匹配"""

    def __init__(
        self,
        call_model_func: Any,
        patterns_path: str = config.PATTERNS_PATH,
    ) -> None:
        self.call_model_func = call_model_func
        self.patterns_path = patterns_path
        self.patterns = self._load_patterns()

    def _load_patterns(self) -> list[dict]:
        """載入 pattern 檔案"""
        with open(self.patterns_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        return [
            {"regex": item[0], "intent": item[1], "need_rag": item[2]}
            for item in raw
        ]

    def _pattern_match(self, user_input: str) -> dict | None:
        """比對 regex pattern"""
        matched = [p for p in self.patterns if re.search(p["regex"], user_input)]
        return {"intent": matched[0]["intent"], "need_rag": matched[0]["need_rag"]} if len(matched) == 1 else None

    async def _call_llm(self, prompt: str, input_text: str) -> dict:
        """呼叫 LLM 並解析 JSON"""
        messages = MessageBuilder.build_task(prompt, input_text)
        content, _ = await self.call_model_func(
            config.ROUTER_MODEL_NAME, messages,
            config.ROUTE_TEMPERATURE, config.ROUTE_MAX_TOKENS, False,
            caller="router",
        )
        return self._parse_json_response(content)

    @staticmethod
    def _parse_json_response(content: str) -> dict | None:
        """解析 JSON 回應。解析失敗時回傳 None 並記錄 warning log。"""
        match = re.search(r"\{.*?\}", content, re.DOTALL)
        try:
            return json.loads(match.group()) if match else None
        except (json.JSONDecodeError, AttributeError):
            logger.warning("[Router._parse_json_response] JSON 解析失敗，原始內容：%s", content[:200])
            return None

    async def route(self, user_input: str) -> dict:
        """分流核心"""
        if (matched := self._pattern_match(user_input)):
            return matched

        intent = await self._call_intent(user_input)
        need_rag = await self._call_rag(user_input)
        return {"intent": intent, "need_rag": need_rag}

    async def _call_intent(self, user_input: str) -> str:
        """取得意圖分類"""
        result = await self._call_llm(config.ROUTE_INTENT_PROMPT, user_input)
        if result is None:
            logger.warning("[Router._call_intent] 意圖解析失敗，fallback 到 simple")
            return "simple"
        return result.get("intent", "simple")

    async def _call_rag(self, user_input: str) -> bool:
        """取得是否需要 RAG"""
        result = await self._call_llm(config.ROUTE_RAG_PROMPT, user_input)
        if result is None:
            logger.warning("[Router._call_rag] RAG 解析失敗，fallback 到 False（不需要 RAG）")
            return False
        raw = result.get("need_rag", False)
        return raw.lower() == "true" if isinstance(raw, str) else bool(raw)

    async def probe_server(self, goal: str, server_names: list[str]) -> str:
        """從 server_names 中挑選最適合的 MCP server"""
        probe_messages = MessageBuilder.build_task(
            config.PROBE_ROUTER_PROMPT.format(
                server_list=json.dumps(server_names, ensure_ascii=False, indent=2)
            ),
            goal
        )
        probe_content, _ = await self.call_model_func(
            config.ROUTER_MODEL_NAME, probe_messages,
            config.ROUTE_TEMPERATURE, config.ROUTE_MAX_TOKENS, False,
            caller="tool_probe"
        )
        return self._extract_server_name(probe_content)

    @staticmethod
    def _extract_server_name(content: str) -> str:
        """提取 server 名稱（移除引號與空白）"""
        return content.strip().strip('"').strip()
