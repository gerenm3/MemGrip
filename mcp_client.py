import asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import config
import os

SERVER_REGISTRY = {
    "file_rw": {
        "params": StdioServerParameters(
            command="npx",
            args=["@modelcontextprotocol/server-filesystem", config.FILE_RW_BASE_PATH],
        ),
        # 定義此 Server 的「眼睛」：自動感知工具
        "probe": {
            "tool": "list_allowed_directories",
            "args": {} 
        }
    }
}

async def get_tools(server_name: str) -> list:
    # 1. 獲取註冊表中的配置字典
    config_entry = SERVER_REGISTRY.get(server_name)
    if not config_entry:
        return []
    
    # 2. 從字典中提取實際的 StdioServerParameters
    server_params = config_entry.get("params")
    if not server_params:
        return []

    # 3. 建立 MCP 連線並獲取工具清單
    # 注意：保持 errlog 的導向以維持 Console 清潔
    async with stdio_client(server_params, errlog=open(os.devnull, 'w')) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools_response = await session.list_tools()
            return tools_response.tools


async def call_tool(server_name: str, tool_name: str, tool_args: dict) -> str:
    # 1. 獲取註冊表配置
    config_entry = SERVER_REGISTRY.get(server_name)
    if not config_entry:
        return f"[Error] 未知的 server：{server_name}"
    
    # 2. 提取連線參數
    server_params = config_entry.get("params")
    if not server_params:
        return f"[Error] Server {server_name} 缺乏啟動參數"

    try:
        # 3. 建立連線並執行
        async with stdio_client(server_params, errlog=open(os.devnull, 'w')) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(tool_name, tool_args)
                
                # 確保回傳內容存在，避免 content[0] 導致 IndexError
                if not result.content:
                    return ""
                
                return result.content[0].text
                
    except Exception as e:
        # 這裡的回傳會被 ExecutionManager 捕獲並觸發閉環修正
        return f"[Error] 執行工具 {tool_name} 時發生異常: {str(e)}"

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