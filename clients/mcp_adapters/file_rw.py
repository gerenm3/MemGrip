"""FileRWAdapter — 檔案讀寫 MCP Server Adapter"""

import os
from clients.mcp_adapters.base import BaseMCPAdapter
from mcp import StdioServerParameters


class FileRWAdapter(BaseMCPAdapter):
    """file_rw Server 的具體實作"""

    @property
    def name(self) -> str:
        return "file_rw"

    def get_server_params(self):
        return StdioServerParameters(
            command="npx",
            args=["@modelcontextprotocol/server-filesystem", os.environ.get("MEMGRIP_FILE_RW_BASE_PATH", "/home/kali/workspace")],
        )

    def get_env_prompt(self) -> str:
        base_path = os.environ.get("MEMGRIP_FILE_RW_BASE_PATH", "/home/kali/workspace")
        return f"請使用絕對路徑，允許目錄：{base_path}"

    def get_description(self) -> str:
        base_path = os.environ.get("MEMGRIP_FILE_RW_BASE_PATH", "/home/kali/workspace")
        return f"檔案讀寫，工作目錄：{base_path}"
