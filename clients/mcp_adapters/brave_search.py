"""BraveSearchAdapter — Brave 網頁搜尋 MCP Server Adapter"""

import os
from clients.mcp_adapters.base import BaseMCPAdapter
from mcp import StdioServerParameters


class BraveSearchAdapter(BaseMCPAdapter):
    """brave_search Server 的具體實作"""

    @property
    def name(self) -> str:
        return "brave_search"

    def get_server_params(self):
        return StdioServerParameters(
            command="npx",
            args=["@brave/brave-search-mcp-server"],
            env={
                "BRAVE_API_KEY": os.environ.get("BRAVE_API_KEY", ""),
            },
        )

    def get_env_prompt(self) -> str:
        api_key = os.environ.get("BRAVE_API_KEY", "")
        if not api_key:
            return "⚠️ 尚未設定 BRAVE_API_KEY 環境變數，Brave 搜尋將無法使用。請設定後重試。"
        return "使用 Brave 搜尋引擎查詢即時網頁資訊。"

    def get_description(self) -> str:
        api_key = os.environ.get("BRAVE_API_KEY", "")
        if not api_key:
            return "Brave 網頁搜尋（未設定 API key）"
        return "Brave 網頁搜尋"
