"""MCP Client — 透過 Adapter 動態管理 MCP Server"""

import logging
import os
from mcp import ClientSession
from mcp.client.stdio import stdio_client
from clients.mcp_adapters import ADAPTER_MAP, SERVER_REGISTRY

logger = logging.getLogger(__name__)


def get_adapter_names() -> list:
    """回傳所有可用的 Adapter 名稱"""
    return list(ADAPTER_MAP.keys())


def get_adapter(name: str):
    """依名稱取得 Adapter"""
    return ADAPTER_MAP.get(name)


async def get_tools(server_name: str) -> list:
    adapter = ADAPTER_MAP.get(server_name)
    if not adapter:
        logger.warning("[MCP] 未找到 Adapter：%s", server_name)
        return []

    server_params = adapter.get_server_params()
    async with stdio_client(server_params, errlog=open(os.devnull, 'w')) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools_response = await session.list_tools()
            return tools_response.tools


async def call_tool(server_name: str, tool_name: str, tool_args: dict) -> str:
    adapter = ADAPTER_MAP.get(server_name)
    if not adapter:
        return f"[Error] 未知的 server：{server_name}"

    server_params = adapter.get_server_params()

    try:
        async with stdio_client(server_params, errlog=open(os.devnull, 'w')) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(tool_name, tool_args)

                if getattr(result, 'isError', False):
                    return f"[TOOL_ERROR] {result.content[0].text if result.content else '工具執行失敗'}"

                if not result.content:
                    return ""

                return result.content[0].text

    except Exception as e:
        return f"[Error] 執行工具 {tool_name} 時發生異常: {str(e)}"
