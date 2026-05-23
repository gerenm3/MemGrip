"""BaseMCPAdapter — MCP Server Adapter 抽象基底"""

from abc import ABC, abstractmethod


class BaseMCPAdapter(ABC):
    """定義所有 MCP Server Adapter 必須實作的介面"""

    @property
    @abstractmethod
    def name(self) -> str:
        """Adapter 的名稱，用於識別（如 'file_rw', 'brave_search'）"""
        ...

    @abstractmethod
    def get_server_params(self):
        """回傳 StdioServerParameters，用於建立 MCP 連線"""
        ...

    @abstractmethod
    def get_env_prompt(self) -> str:
        """回傳此 Server 的環境提示（用於 STEP_EXECUTE_PROMPT 的 environment 欄位）"""
        ...

    @abstractmethod
    def get_description(self) -> str:
        """回傳此 Server 的描述（用於 TOOL_ENVIRONMENT 欄位）"""
        ...
