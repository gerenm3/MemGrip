"""ToolManager — 工具管理（從 core/orchestrator.py 抽取工具相關方法）"""

import asyncio
import config
import json
import logging
from typing import Any, List, Optional
from clients.message_builder import MessageBuilder
from clients.mcp_adapters import SERVER_REGISTRY, ADAPTER_MAP
from core.health import log_action
from core.prompts import TOOL_EXECUTION_PROMPT
from models.blueprints import Result

logger = logging.getLogger(__name__)


class ToolManager:
    """ToolManager：工具初始化、轉換與執行"""

    def __init__(self, mcp_client: Any, call_model_func: Optional[Any] = None) -> None:
        self.mcp_client = mcp_client
        self.call_model_func = call_model_func
        self.tool_registry: dict[str, str] = {}
        self.server_schemas: dict[str, list] = {}
        self.tool_environments: dict[str, str] = {}

    async def initialize(self) -> None:
        """初始化工具清單（公開 API）"""
        await self._init_tools()

    async def _init_tools(self) -> None:
        """初始化工具清單 + 綁定執行層"""
        self.tool_registry = {}
        self.server_schemas = {}
        self.tool_environments = {}
        for server_name in SERVER_REGISTRY.keys():
            try:
                tools_result = await self.mcp_client.get_tools(server_name)
                if not tools_result.success:
                    raise RuntimeError(tools_result.error or "get_tools 失敗")
                tools = tools_result.data
                processed_schemas: list[dict] = []
                for tool in tools:
                    schema = self._mcp_tool_to_ollama(tool)
                    if tool.name == "write_file":
                        schema["function"]["description"] += " (警告：此操作為完全覆寫)"
                    processed_schemas.append(schema)
                    self.tool_registry[tool.name] = server_name
                self.server_schemas[server_name] = processed_schemas

                # 從 adapter 取得環境提示
                adapter = ADAPTER_MAP.get(server_name)
                if adapter:
                    env_desc = adapter.get_env_prompt()
                    self.tool_environments[server_name] = env_desc if env_desc else f"Server: {server_name}"
            except Exception as e:
                error_msg = f"伺服器 {server_name} 工具初始化失敗: {e}"
                logger.warning("[tool_manager] %s", error_msg)
                log_action("tool_manager", "server_init_failed", "DEGRADED", server_name + str(e), "部分工具服務不可用")

    def get_server_tools(self, server_name: str) -> list:
        """取得指定伺服器的所有工具清單（公開 API）"""
        return self.server_schemas.get(server_name, [])

    def _mcp_tool_to_ollama(self, mcp_tool: Any) -> dict:
        return {
            "type": "function",
            "function": {
                "name": mcp_tool.name,
                "description": mcp_tool.description,
                "parameters": mcp_tool.inputSchema
            }
        }

    @staticmethod
    def _format_tool_call(tc: Any) -> Optional[dict]:
        """將 tool_call 轉換為統一的 {name, arguments} 格式。"""
        if hasattr(tc, "function"):
            func = tc.function
            return {"name": func.name, "arguments": func.arguments}
        if isinstance(tc, dict):
            return {
                "name": tc.get("function", {}).get("name", ""),
                "arguments": tc.get("function", {}).get("arguments", {}),
            }
        return None

    @staticmethod
    def _parse_tool_arguments(raw: Any) -> dict:
        """解析 tool arguments：支援 str (JSON) 或 dict."""
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, str):
            try:
                return json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                return {}
        return {}

    async def execute_tool(self, server_name: str, tool_name: str, tool_args: dict) -> Result:
        """公開工具執行方法（供 Executor 呼叫）"""
        try:
            result = await self.mcp_client.call_tool(server_name, tool_name, tool_args)
            log_action("tool_manager", "tool_success", "OK", tool_name)
            return Result(success=True, data=result)
        except asyncio.TimeoutError as e:
            log_action("tool_manager", "tool_timeout", "DEGRADED", tool_name + str(e), "工具執行超時")
            return Result(success=False, error=f"工具執行超時: {e}")
        except Exception as e:
            logger.error("[tool_manager] 工具執行失敗: %s", e, exc_info=True)
            return Result(success=False, error=str(e))

    async def run_agentic_loop(self, goal: str, rag_content: str, all_tools: list, max_iterations: int = 15, environment: str = "") -> Result:
        """Agentic Loop：迭代呼叫模型直到沒有工具調用或達到上限"""
        try:
            system_prompt = TOOL_EXECUTION_PROMPT.format(
                tools=json.dumps(all_tools, ensure_ascii=False, indent=2),
                environment=environment or ""
            )
            context_parts = [f"[USER_INPUT]{goal}[/USER_INPUT]"]
            if rag_content:
                context_parts.append(f"[RAG]{rag_content}[/RAG]")
            context = "\n".join(context_parts)

            conversation: list[dict] = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": context}
            ]

            for i in range(max_iterations):
                content, tool_calls = await self._call_llm(
                    config.MEDIUM_MODEL_NAME, conversation, tools=all_tools, caller="tool_loop"
                )

                if tool_calls:
                    assistant_msg, valid_calls = self._build_assistant_msg(content, tool_calls)
                    conversation.append(assistant_msg)

                    for tc in valid_calls:
                        tool_result = await self._execute_single_tool(tc)
                        conversation.append({
                            "role": "tool",
                            "content": str(tool_result),
                            "tool_name": tc["name"],
                        })
                    continue

                final_reply = await self._generate_final_reply(goal, conversation)
                log_action("tool_manager", "agentic_loop_complete", "OK", goal)
                return Result(success=True, data=final_reply)

            log_action("tool_manager", "tool_call_limit", "DEGRADED", "max_iterations exceeded", "工具調用次數已達上限")
            return Result(success=False, data="工具調用次數已達上限。")
        except Exception as e:
            logger.error("[tool_manager] agentic loop 失敗: %s", e, exc_info=True)
            return Result(success=False, error=str(e))

    async def _call_llm(
        self,
        model: str,
        messages: list[dict],
        tools: Optional[List[dict]] = None,
        caller: str = "tool_loop"
    ) -> tuple[str, list]:
        """呼叫語言模型
        
        支援兩種回傳型別：
        - Result 物件（來自 call_model 公用函式）
        - tuple[str, list]（來自 OllamaClient.chat）
        """
        result = await self.call_model_func(
            model, messages,
            getattr(config, 'TOOL_EXECUTION_TEMPERATURE', 0.3),
            getattr(config, 'TOOL_EXECUTION_MAX_TOKENS', 8192),
            getattr(config, 'TOOL_EXECUTION_THINK', True),
            tools or None,
            caller=caller,
        )
        
        # 處理 Result 物件與 tuple 兩種型別
        if isinstance(result, Result):
            content = result.data or ""
            tool_calls = result.tool_calls or []
        else:
            content, tool_calls = result
        
        return content, tool_calls or []

    def _build_assistant_msg(
        self,
        content: str,
        tool_calls: list
    ) -> tuple[dict, list[dict]]:
        """建構 assistant 訊息並格式化 tool_calls"""
        assistant_msg: dict = {"role": "assistant", "content": content or ""}
        valid_calls = []
        for tc in tool_calls:
            if (formatted := self._format_tool_call(tc)) is not None:
                assistant_msg.setdefault("tool_calls", []).append({"function": formatted})
                valid_calls.append(formatted)
        return assistant_msg, valid_calls

    async def _execute_single_tool(self, parsed: dict) -> str:
        """執行單一工具呼叫"""
        t_name = parsed["name"]
        t_args = self._parse_tool_arguments(parsed["arguments"])
        server_name = self.tool_registry.get(t_name)
        if not server_name:
            return f"[Error] 找不到工具 {t_name} 對應的伺服器"
        return await self.mcp_client.call_tool(server_name, t_name, t_args)

    async def _generate_final_reply(self, goal: str, conversation: list[dict]) -> str:
        """生成最終回覆"""
        reply_conv = conversation + [{
            "role": "system",
            "content": f"[GOAL]{goal}[/GOAL]\n[EXECUTION_LOG]\n最後輸出結果給用戶。\n[/EXECUTION_LOG]\n請根據以上執行結果，生成一份自然、完整的回覆給用戶。回覆應清晰總結完成的工作，並直接回應用戶的需求。",
        }]
        final_reply, _ = await self._call_llm(
            config.MEDIUM_MODEL_NAME, reply_conv, caller="final_reply"
        )
        return final_reply
