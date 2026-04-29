import asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import config
import os

SERVER_REGISTRY = {
    "file_rw": StdioServerParameters(
        command="npx",
        args=["@modelcontextprotocol/server-filesystem", config.FILE_RW_BASE_PATH],
    ),

}

async def get_tools(server_name: str) -> list:
    server_params = SERVER_REGISTRY.get(server_name)
    if not server_params:
        return []
    async with stdio_client(server_params, errlog=open(os.devnull, 'w')) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            return tools.tools

async def call_tool(server_name: str, tool_name: str, tool_args: dict) -> str:
    server_params = SERVER_REGISTRY.get(server_name)
    if not server_params:
        return f"[Error] 未知的 server：{server_name}"
    async with stdio_client(server_params, errlog=open(os.devnull, 'w')) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, tool_args)
            return result.content[0].text



    """
    "web_fetch": StdioServerParameters(
        command="uvx",
        args=["mcp-server-fetch"],
    ),
    "web_search": StdioServerParameters(
        command="node",
        args=["/home/kali/brave-search-mcp-server/dist/index.js"],
        env={"BRAVE_API_KEY": config.BRAVE_SEARCH_API_KEY},
    ),
    """