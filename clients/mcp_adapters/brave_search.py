"""BraveSearchAdapter — Brave 網頁搜尋 MCP Server Adapter"""

import os
from pathlib import Path
import config
from clients.mcp_adapters.base import BaseMCPAdapter
from mcp import StdioServerParameters

# 動態計算 server 路徑（不依賴絕對路徑）
ROOT_DIR = Path(__file__).parent.parent.parent
SERVER_PATH = ROOT_DIR / "vendors" / "brave-search-mcp-server" / "dist" / "index.js"


class BraveSearchAdapter(BaseMCPAdapter):
    """brave_search Server 的具體實作"""

    @property
    def name(self) -> str:
        return "brave_search"

    def get_server_params(self):
        api_key = config.BRAVE_SEARCH_API_KEY
        if not api_key:
            raise ValueError("BRAVE_SEARCH_API_KEY 未設定，請在 config.py 中配置。")
        return StdioServerParameters(
            command="node",
            args=[str(SERVER_PATH), "--brave-api-key", api_key],
        )

    def get_env_prompt(self) -> str:
        api_key = config.BRAVE_SEARCH_API_KEY
        if not api_key:
            return "⚠️ 尚未設定 BRAVE_SEARCH_API_KEY，Brave 搜尋將無法使用。"
        return "使用 Brave 搜尋引擎查詢即時網頁資訊。"

    def get_description(self) -> str:
        api_key = config.BRAVE_SEARCH_API_KEY
        if not api_key:
            return "Brave 網頁搜尋（未設定 API key）"
        return "Brave 網頁搜尋"
