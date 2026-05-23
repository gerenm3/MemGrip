# MCP Adapter 重構設計文件

## 1. 設計目標

將目前硬編碼在 `SERVER_REGISTRY` 和 `TOOL_ENVIRONMENT` 中的 MCP Server 設定，抽象化為 Adapter 模式，使新增/移除 MCP Server 時不需要修改核心配置。

## 2. 新目錄結構

```
clients/
├── mcp_adapters/
│   ├── __init__.py
│   ├── base.py
│   ├── file_rw.py
│   └── brave_search.py
├── mcp_client.py
└── message_builder.py
```

## 3. `clients/mcp_adapters/base.py` — 抽象基底類別

```python
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
```

## 4. `clients/mcp_adapters/file_rw.py` — FileRW Adapter

```python
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
```

## 5. `clients/mcp_adapters/brave_search.py` — Brave Search Adapter

```python
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
```

## 6. `clients/mcp_adapters/__init__.py` — Adapter 註冊中心

```python
"""Adapter registry — 集中管理所有 MCP Server Adapter"""

from clients.mcp_adapters.file_rw import FileRWAdapter
from clients.mcp_adapters.brave_search import BraveSearchAdapter

ADAPTERS = [
    FileRWAdapter(),
    BraveSearchAdapter(),
]

# 快速存取字典
ADAPTER_MAP = {adapter.name: adapter for adapter in ADAPTERS}
```

## 7. 修改 `clients/mcp_client.py`

### 变更前（現有程式碼）

```python
SERVER_REGISTRY = {
    "file_rw": {
        "params": StdioServerParameters(...),
        "probe": {"tool": "list_allowed_directories", "args": {}},
    }
}

async def get_tools(server_name: str) -> list: ...
async def call_tool(server_name: str, tool_name: str, tool_args: dict) -> str: ...
```

### 變更後

```python
"""MCP Client — 透過 Adapter 動態管理 MCP Server"""

import logging
from clients.mcp_adapters import ADAPTER_MAP
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

logger = logging.getLogger(__name__)


def get_adapter_names() -> list[str]:
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
    async with stdio_client(server_params) as (read, write):
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
        async with stdio_client(server_params) as (read, write):
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
```

### 主要變更

| 項目 | 变更前 | 变更后 |
|------|--------|--------|
| Server 來源 | `SERVER_REGISTRY` 字典 | `ADAPTER_MAP` 字典 |
| Probe 功能 | 已死碼未使用 | **移除** |
| `get_tools()` | 直接從 `SERVER_REGISTRY` 取參數 | 從 `ADAPTER_MAP` 取得 adapter |
| `call_tool()` | 直接從 `SERVER_REGISTRY` 取參數 | 從 `ADAPTER_MAP` 取得 adapter |

## 8. 修改 `config.py`

### 变更前（現有程式碼）

```python
TOOL_ENVIRONMENT = {
    "file_rw": {
        "description": f"檔案讀寫，工作目錄：{FILE_RW_BASE_PATH}",
        "base_path": FILE_RW_BASE_PATH,
        "instruction": f"請使用絕對路徑，允許目錄：{FILE_RW_BASE_PATH}"
    }
}
AVAILABLE_TOOLS = [f"{k}:{v}" for k, v in TOOL_ENVIRONMENT.items()]
```

### 變更後

```python
# TOOL_ENVIRONMENT 與 AVAILABLE_TOOLS 已移除
# 改為從 clients/mcp_adapters 動態生成

# 保留 TOOL_ENVIRONMENT 的 backward compatibility 讀取
# 由 tool_manager.py 在 _init_tools() 時動態填充
```

### 影響範圍

- `config.py`：移除 `TOOL_ENVIRONMENT` 和 `AVAILABLE_TOOLS`
- `core/tool_manager.py`：`_init_tools()` 需改為從 `ADAPTER_MAP` 讀取 description
- `core/executor.py`：`_build_environment()` 需改為從 Adapter 讀取 env prompt
- `core/executor.py`：`_build_tool_instruction()` 需改為從 Adapter 讀取 description

## 9. 修改 `core/orchestrator.py`

### 变更前（第 129-130 行）

```python
if selected_server not in self.tool_manager.server_schemas:
    selected_server = "file_rw"  # ← 這裡的 fallback 移除
```

### 變更後

```python
if selected_server not in self.tool_manager.server_schemas:
    # 無法辨識的意圖，回傳錯誤訊息而非 fallback
    return "⚠️ 無法辨識的任務類型，請提供更多資訊。"
```

### 理由

- 原本的 `selected_server = "file_rw"` fallback 會導致意圖模糊的請求被錯誤地路由到檔案讀寫伺服器，造成工具調用失敗或意外行為。
- 改為明確回報錯誤，讓用戶知道需要提供更多資訊。

## 10. 修改 `core/tool_manager.py`

### `_init_tools()` 變更

```python
async def _init_tools(self) -> None:
    self.tool_registry = {}
    self.server_schemas = {}
    self.tool_environments = {}  # 新增：儲存環境提示

    for server_name in self.mcp_client.get_adapter_names():
        adapter = self.mcp_client.get_adapter(server_name)
        if not adapter:
            print(f"[Warning] 伺服器 {server_name} 沒有對應的 Adapter，跳過")
            continue

        try:
            tools = await self.mcp_client.get_tools(server_name)
            processed_schemas: list[dict] = []
            for tool in tools:
                schema = self._mcp_tool_to_ollama(tool)
                if tool.name == "write_file":
                    schema["function"]["description"] += " (警告：此操作為完全覆寫)"
                processed_schemas.append(schema)
                self.tool_registry[tool.name] = server_name
            self.server_schemas[server_name] = processed_schemas

            # 新增：儲存環境提示
            self.tool_environments[server_name] = {
                "description": adapter.get_description(),
                "instruction": adapter.get_env_prompt(),
            }
        except Exception as e:
            print(f"[Warning] 伺服器 {server_name} 工具初始化失敗: {e}")
```

### 主要變更

| 項目 | 变更前 | 变更后 |
|------|--------|--------|
| 來源 | `self.mcp_client.SERVER_REGISTRY.keys()` | `self.mcp_client.get_adapter_names()` |
| 環境提示 | `config.TOOL_ENVIRONMENT.get(server_name)` | `self.tool_environments[server_name]` |
| 描述 | `config.TOOL_ENVIRONMENT.get(server_name, {})` | `adapter.get_description()` |

## 11. 修改 `core/executor.py`

### `_build_environment()` 變更

```python
def _build_environment(self, server_name: Optional[str]) -> str:
    if not server_name:
        return ""
    env_info = self.tool_manager.tool_environments.get(server_name, {})
    instruction = env_info.get("instruction", "")
    return instruction if instruction else "\n".join(f"{k}：{v}" for k, v in env_info.items())
```

### 變更說明

- 從 `config.TOOL_ENVIRONMENT` 改為從 `self.tool_manager.tool_environments` 讀取
- 需要將 `tool_manager` 傳入 `Executor` 建構子（或作為引數）

## 12. 風險與對策

### 風險 1：Brave Search API key 未設定
- **對策**：`get_env_prompt()` 在 API key 為空時回傳警告訊息，用戶可一眼看出問題

### 風險 2：Adapter 初始化失敗
- **對策**：`_init_tools()` 中 `try/except` 包裹每組 Server，單一失敗不影響其他 Server

### 風險 3：backward compatibility
- **對策**：若有其他模組直接引用 `config.TOOL_ENVIRONMENT`，需一併修改。建議在 `config.py` 中保留一個 deprecated property。

## 13. 實作步驟建議

1. **建立 `clients/mcp_adapters/` 目錄與檔案**
   - `__init__.py`、`base.py`、`file_rw.py`、`brave_search.py`

2. **修改 `clients/mcp_client.py`**
   - 移除 `SERVER_REGISTRY` 和 `probe` 死碼
   - 改為從 `ADAPTER_MAP` 動態讀取

3. **修改 `core/tool_manager.py`**
   - `_init_tools()` 改為使用 adapter
   - 新增 `tool_environments` 屬性

4. **修改 `core/executor.py`**
   - `_build_environment()` 改為從 `tool_manager.tool_environments` 讀取

5. **修改 `config.py`**
   - 移除 `TOOL_ENVIRONMENT` 和 `AVAILABLE_TOOLS`
   - 保留 `FILE_RW_BASE_PATH` 和 `BRAVE_SEARCH_API_KEY` 等基礎配置

6. **修改 `core/orchestrator.py`**
   - 移除 `selected_server = "file_rw"` fallback
   - 改為回傳錯誤訊息

## 14. 未來擴展

新增一個 MCP Server 只需：

1. 建立 `clients/mcp_adapters/{server_name}.py`，繼承 `BaseMCPAdapter`
2. 在 `clients/mcp_adapters/__init__.py` 的 `ADAPTERS` 清單中註冊
3. 不需要修改任何其他核心檔案
