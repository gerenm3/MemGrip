"""v2 router — 意圖分類、server 選擇、澄清判斷.

依據 §3.1 (Router) 定義：
- 意圖分類：simple / tool / complex 三類
- Pattern match 優先 → 無匹配才調 LLM
- 單次 LLM 回傳 {intent, need_rag, domain}
- probe_server 僅在 tool 路徑，失敗回傳 Result(success=False)
- is_clarification 判斷用戶輸入是否為澄清回答
- 所有公開 API 回傳 Result
"""

import asyncio
import json
import logging
import os
import re
import threading
from typing import Any, List, Optional

import config as config
from clients.message_builder import MessageBuilder
from core.health import log_action
from core.json_utils import parse_first_json
from core.prompts import ROUTE_PROMPT, PROBE_ROUTER_PROMPT, IS_CLARIFICATION_PROMPT
from models.blueprints import Result

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
        self._last_mtime = 0.0
        self._patterns_list: list[dict] = self._load_patterns()
        self._lock = threading.Lock()

    @property
    def patterns(self) -> list[dict]:
        """讀取 patterns，若有 mtime 變化則重新載入"""
        try:
            current_mtime = os.path.getmtime(self.patterns_path)
        except OSError:
            return self._patterns_list

        if current_mtime != self._last_mtime:
            with self._lock:
                if current_mtime != self._last_mtime:
                    self._patterns_list = self._load_patterns()
                    self._last_mtime = current_mtime
        return self._patterns_list

    def _load_patterns(self) -> list[dict]:
        """載入 pattern 檔案，支援 domain 欄位（第 5 欄）"""
        try:
            with open(self.patterns_path, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("[Router._load_patterns] patterns 載入失敗：%s", e)
            return self._patterns_list

        patterns = []
        for i, item in enumerate(raw):
            if not isinstance(item, (list, tuple)) or len(item) < 3:
                logger.warning("[Router._load_patterns] pattern #%d 結構無效，已跳過", i)
                continue
            regex_str = item[0]
            if not isinstance(regex_str, str):
                logger.warning("[Router._load_patterns] pattern #%d regex 非字串，已跳過", i)
                continue
            try:
                re.compile(regex_str)
            except re.error as e:
                logger.warning("[Router._load_patterns] pattern #%d 無效 regex: %s", i, e)
                continue
            patterns.append({
                "regex": regex_str,
                "intent": item[1],
                "need_rag": item[2],
                "priority": item[3] if len(item) > 3 else 0,
                "domain": item[4] if len(item) > 4 else "general",
            })

        return sorted(patterns, key=lambda p: p["priority"], reverse=True)

    def _pattern_match(self, user_input: str) -> Optional[dict]:
        """比對 regex pattern（patterns 已按 priority 降序排列）"""
        matched = []
        for p in self.patterns:
            try:
                if re.search(p["regex"], user_input):
                    matched.append(p)
            except re.error as e:
                logger.warning("[Router._pattern_match] 無效 regex 已跳過: %s (%s)", p["regex"], e)
        if not matched:
            return None
        return {
            "intent": matched[0].get("intent", "simple"),
            "need_rag": matched[0].get("need_rag", False),
            "domain": matched[0].get("domain", "general"),
        }

    async def _call_llm(self, prompt: str, input_text: str, caller: str) -> Result:
        """呼叫 LLM 並解析 JSON"""
        messages = MessageBuilder.build_task(prompt, input_text)
        try:
            result = await self.call_model_func(
                config.MEDIUM_MODEL_NAME, messages,
                config.ROUTE_TEMPERATURE, config.ROUTE_MAX_TOKENS, False,
                caller=caller,
            )
        except Exception as e:
            logger.error("[Router._call_llm] LLM 呼叫失敗: %s", e, exc_info=True)
            return Result(success=False, error=str(e))

        content = result.data or ""
        parsed = parse_first_json(content)
        if parsed is None or not isinstance(parsed, dict):
            return Result(success=False, error="JSON parsing failed")
        return Result(success=True, data=parsed)

    def _validate_intent(self, intent: str) -> tuple[bool, str]:
        """驗證 intent 是否合法"""
        if intent in ("simple", "tool", "complex"):
            return True, intent
        return False, intent

    async def route(self, user_input: str, *, _max_attempts: int = 2) -> Result:
        """分流核心：pattern → LLM（可重試）"""
        if (matched := self._pattern_match(user_input)):
            data = dict(matched)
            data.setdefault("domain", "general")
            log_action("router", "route_success", "OK", data.get("intent", "simple"))
            return Result(success=True, data=data)

        for attempt in range(_max_attempts):
            try:
                result = await self._call_llm(ROUTE_PROMPT, user_input, caller="router")
            except Exception as e:
                result = Result(success=False, error=str(e))
            if result is None or not result.success:
                continue
            data = result.data
            valid, intent = self._validate_intent(data.get("intent", "simple"))
            if not valid:
                logger.warning("[Router.route] 驗證失敗，intent=%s，不進入重試", intent)
                return Result(success=False, error=f"invalid intent: {intent}")
            data["need_rag"] = data.get("need_rag", False)
            data["domain"] = data.get("domain", "general")
            log_action("router", "route_success", "OK", intent)
            return result

        log_action("router", "route_failed", "DEGRADED", "LLM routing failed after retries", "路由失敗")
        return Result(success=False, error="route 重試後仍失敗")

    async def probe_server(self, goal: str, server_names: list[str]) -> Result:
        """從 server_names 中挑選最適合的 MCP server"""
        if not server_names:
            logger.warning("[Router.probe_server] server_names 為空")
            return Result(success=False, error="server_names is empty")

        probe_messages = MessageBuilder.build_task(
            PROBE_ROUTER_PROMPT.format(
                server_list=json.dumps(server_names, ensure_ascii=False, indent=2)
            ),
            goal
        )
        try:
            probe_result = await self.call_model_func(
                config.MEDIUM_MODEL_NAME, probe_messages,
                config.ROUTE_TEMPERATURE, config.ROUTE_MAX_TOKENS, False,
                caller="tool_probe"
            )
            probe_content = probe_result.data or ""
        except Exception as e:
            log_action("router", "probe_server_llm", "DEGRADED", str(e), "無法自動偵測工具")
            return Result(success=False, error=str(e))

        extracted = self._extract_server_name(probe_content)
        if extracted:
            return Result(success=True, data={"server": extracted})
        return Result(success=False, error="LLM returned empty server name")

    async def is_clarification(self, user_input: str, pending_questions: List[str]) -> Result:
        """判斷用戶輸入是否為對澄清問題的回答。

        Args:
            user_input: 用戶當前的輸入
            pending_questions: 上一輪 Clarifier 提出的問題列表

        Returns:
            Result(data={"is_clarification": bool})
        """
        if not pending_questions:
            return Result(success=True, data={"is_clarification": False})

        questions_text = "\n".join(f"- {q}" for q in pending_questions)
        prompt = IS_CLARIFICATION_PROMPT.format(
            questions=questions_text,
            user_input=user_input
        )
        result = await self._call_llm(prompt, user_input, caller="is_clarification")
        if not result.success:
            log_action("router", "is_clarification_failed", "DEGRADED",
                       result.error, "無法判斷用戶意圖")
        return result

    @staticmethod
    def _extract_server_name(content: str) -> str:
        """提取 server 名稱（移除引號與空白）"""
        return content.strip().strip('"').strip()
