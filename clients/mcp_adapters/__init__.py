"""Adapter registry — 集中管理所有 MCP Server Adapter"""

from clients.mcp_adapters.file_rw import FileRWAdapter
from clients.mcp_adapters.brave_search import BraveSearchAdapter

ADAPTERS = [
    FileRWAdapter(),
    BraveSearchAdapter(),
]

# 快速存取字典
ADAPTER_MAP = {adapter.name: adapter for adapter in ADAPTERS}
SERVER_REGISTRY = {adapter.name: adapter.get_server_params for adapter in ADAPTERS}

__all__ = ["ADAPTERS", "ADAPTER_MAP", "SERVER_REGISTRY"]