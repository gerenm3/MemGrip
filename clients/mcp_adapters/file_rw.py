"""FileRWAdapter — 檔案讀寫 MCP Server Adapter"""

from clients.mcp_adapters.base import BaseMCPAdapter
import config
from mcp import StdioServerParameters


class FileRWAdapter(BaseMCPAdapter):
    """file_rw Server 的具體實作"""

    @property
    def name(self) -> str:
        return "file_rw"

    def get_server_params(self):
        return StdioServerParameters(
            command="npx",
            args=["@modelcontextprotocol/server-filesystem", config.FILE_RW_BASE_PATH],
        )

    def get_env_prompt(self) -> str:
        return f"請使用絕對路徑，允許目錄：{config.FILE_RW_BASE_PATH}"

    def get_description(self) -> str:
        return f"檔案讀寫，工作目錄：{config.FILE_RW_BASE_PATH}"
