"""v2 MCP Client — MCP Server 通訊封裝.

依據 §3.9 (Tool Manager) 定義：
- class MCPClient，供 ToolManager 透過 DI 注入
- call_tool(server_name, tool_name, tool_args) -> str
- 符合 v2 logging 規範
"""

import asyncio
import logging
import os

from mcp import ClientSession
from mcp.client.stdio import stdio_client
from typing import Any

import config
from models.blueprints import Result

logger = logging.getLogger(__name__)

_TIMEOUT_RAW = getattr(config, "MCP_TIMEOUT_SECONDS", 30)
TIMEOUT_SECONDS = max(1, int(_TIMEOUT_RAW))


def _get_content_text(content_item: Any) -> str:
    """安全取得 content item 的 text 屬性."""
    if hasattr(content_item, "text") and content_item.text is not None:
        return content_item.text
    if hasattr(content_item, "data") and hasattr(content_item, "mime_type"):
        return f"[image/{content_item.mime_type}]"
    return str(content_item)


class MCPClient:
    """MCP Server 通訊客戶端."""

    def __init__(self, adapter_map: dict[str, Any] | None = None) -> None:
        """初始化 MCPClient.

        Args:
            adapter_map: 可選的 adapter 映射表。若未提供則從 clients.mcp_adapters 載入。
        """
        if adapter_map is not None:
            self.adapter_map = adapter_map
            return
        
        # 從原模組載入 adapter 映射
        from clients.mcp_adapters import ADAPTER_MAP
        self.adapter_map = ADAPTER_MAP

    def _get_adapter(self, server_name: str) -> Any:
        """取得指定 server 的 adapter."""
        return self.adapter_map.get(server_name)

    async def get_tools(self, server_name: str) -> Result[Any]:
        """取得指定伺服器的工具列表.

        Args:
            server_name: MCP Server 名稱

        Returns:
            Result(data=list[tools])
        """
        adapter = self._get_adapter(server_name)
        if not adapter:
            logger.warning("[MCP] 未找到 Adapter：%s", server_name)
            return Result(success=False, error=f"未找到 Adapter: {server_name}")

        server_params = adapter.get_server_params()

        async def _fetch_tools():
            with open(os.devnull, 'w') as errlog:
                async with stdio_client(server_params, errlog=errlog) as (read, write):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        tools_response = await session.list_tools()
                        return tools_response.tools

        try:
            tools = await asyncio.wait_for(_fetch_tools(), timeout=TIMEOUT_SECONDS)
            return Result(success=True, data=tools)
        except asyncio.TimeoutError:
            logger.error("[MCP] get_tools() 逾時（%s 秒）：server=%s", TIMEOUT_SECONDS, server_name)
            return Result(success=False, error=f"get_tools 逾時 ({server_name})")
        except Exception as e:
            return Result(success=False, error=f"get_tools 異常: {e}")

    async def call_tool(self, server_name: str, tool_name: str, tool_args: dict[str, Any]) -> str:
        """執行 MCP 工具並回傳結果字串.

        Args:
            server_name: MCP Server 名稱
            tool_name: 工具名稱
            tool_args: 工具參數

        Returns:
            工具執行結果字串
        """
        adapter = self._get_adapter(server_name)
        if not adapter:
            return f"[Error] 未知的 server：{server_name}"

        server_params = adapter.get_server_params()

        async def _execute_tool():
            with open(os.devnull, 'w') as errlog:
                async with stdio_client(server_params, errlog=errlog) as (read, write):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        result = await session.call_tool(tool_name, tool_args)

                        logger.debug("[MCP call_tool] tool=%s, args=%s, result=%s", tool_name, tool_args, result)

                        if result.content:
                            text = _get_content_text(result.content[0])
                            if getattr(result, 'isError', False):
                                return f"[TOOL_ERROR] {text}"
                            return text

                        if getattr(result, 'isError', False):
                            return "[TOOL_ERROR] 工具執行失敗（isError=True 但無 content）"
                        logger.warning("[MCP call_tool] result.content is empty, returning empty string")
                        return ""

        try:
            return await asyncio.wait_for(_execute_tool(), timeout=TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            logger.error("[MCP] call_tool() 逾時（%s 秒）：server=%s, tool=%s", TIMEOUT_SECONDS, server_name, tool_name)
            return f"[TIMEOUT] 工具 {tool_name} 執行逾時（{TIMEOUT_SECONDS} 秒）"
        except Exception as e:
            return f"[Error] 執行工具 {tool_name} 時發生異常: {str(e)}"
