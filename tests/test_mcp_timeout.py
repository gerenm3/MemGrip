"""測試 clients/mcp_client.py 的 timeout 保護機制"""

import asyncio
import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ============ Mock sys.modules ============
mock_config = types.ModuleType("config")
mock_config.MCP_TIMEOUT_SECONDS = 30
mock_config.SKILL_DIR_BASE = "/tmp"
mock_config.TASK_TYPES = []
mock_config.SKILL_DIMENSIONS = {}
mock_config.LVS_EVENT_SCORES = {
    "task_failed": 30,
    "unit_failed": 8,
    "replan": 10,
    "review_fail": 3,
    "loop_hit": 4,
}
mock_config.MODEL_BASE_URL = ""
mock_config.MAX_REPLAN_ATTEMPTS = 3
mock_config.MAX_REROLL_ATTEMPTS = 3
mock_config.MAX_RETRY_ATTEMPTS = 3
mock_config.CONTEXT_SAFETY_RATIO = 0.8
mock_config.APPROVAL_TIMEOUT = 1800
mock_config.EMBEDDING_THRESHOLD = 0.75
mock_config.EMBEDDING_MODEL = "bge-m3"
mock_config.EMBEDDING_MODEL_NAME = "bge-m3"
mock_config.RERANKER_MODEL_NAME = ""
mock_config.MAX_CLARIFY_ROUNDS = 3
mock_config.CLARIFY_TEMPERATURE = 0.1
mock_config.CLARIFY_MAX_TOKENS = 500
mock_config.ROUTER_MODEL_NAME = ""
mock_config.MEDIUM_MODEL_NAME = ""
mock_config.LARGE_MODEL_NAME = ""
mock_config.MICRO_MODEL_NAME = ""
mock_config.D_MODEL_NAME = ""
mock_config.LARGE_MODEL_MODE = "local"
mock_config.LARGE_MODEL_API_KEY = ""
mock_config.LARGE_MODEL_API_URL = ""
mock_config.MAX_RETRIES = 15
mock_config.TEMPERATURE = 0.7
mock_config.ROUTE_TEMPERATURE = 0.0
mock_config.SUMMARY_TEMPERATURE = 0.2
mock_config.DISASSEMBLY_TEMPERATURE = 0.0
mock_config.STEP_TEMPERATURE = 0.0
mock_config.STEP_EXECUTE_TEMPERATURE = 0.0
mock_config.INTEGRATION_TEMPERATURE = 0.3
mock_config.AGENTIC_TEMPERATURE = 0.0
mock_config.MAX_TOKENS = 8192
mock_config.ROUTE_MAX_TOKENS = 8192
mock_config.SUMMARY_MAX_TOKENS = 8192
mock_config.DISASSEMBLY_MAX_TOKENS = 32768
mock_config.STEP_MAX_TOKENS = 16384
mock_config.STEP_EXECUTE_MAX_TOKENS = 8192
mock_config.INTEGRATION_MAX_TOKENS = 8192
mock_config.TOOL_EXECUTION_MAX_TOKENS = 8192
mock_config.AGENTIC_MAX_TOKENS = 2048
mock_config.THINK = False
mock_config.DISASSEMBLY_THINK = True
mock_config.STEP_THINK = False
mock_config.STEP_EXECUTE_THINK = False
mock_config.INTEGRATION_THINK = False
mock_config.TOOL_EXECUTION_THINK = True
mock_config.AGENTIC_THINK = False
mock_config.IMPORTANCE_HIGH = 0.7
mock_config.IMPORTANCE_LOW = 0.3
mock_config.SIMILARITY_UPPER_BOUNDARY = 0.7
mock_config.BUFFER_MAX_TOKENS = 800
mock_config.CHROMA_DB_PATH = "./chroma_db"
mock_config.COLLECTION_SUMMARY_NAME = "SUMMARY"
mock_config.COLLECTION_RAW_NAME = "RAW"
mock_config.TEMP_CACHE_PATH = "./temp_cache"
mock_config.TEMP_CACHE_DECAY_LAMBDA = 0.01
mock_config.TEMP_CACHE_MAX_TOKENS = 50000
mock_config.TEMP_CACHE_MAX_ITEMS = 100
mock_config.TEMP_CACHE_IDLE_SECONDS = 900
mock_config.TEMP_CACHE_FORCE_TOKENS = 8000
mock_config.TEMP_CACHE_TOP_K = 10
mock_config.TEMP_CACHE_EVICTION_THRESHOLD = 0.05
mock_config.TRACE_LOG_PATH = "trace.jsonl"
mock_config.TASK_TRACE_PATH = "task_trace.jsonl"
mock_config.ENABLE_WEB_SEARCH = True
mock_config.ENABLE_FILE_RW = True
mock_config.ENABLE_TASK_MANAGER = True
mock_config.FILE_RW_BASE_PATH = "/home/kali/workspace"
mock_config.PATTERNS_PATH = "./patterns.json"
mock_config.BRAVE_SEARCH_API_KEY = ""
mock_config.GOOGLE_SEARCH_API_KEY = ""
mock_config.GOOGLE_SEARCH_ENGINE_ID = ""
mock_config.SYSTEM_PROMPT = ""
mock_config.SUMMARY_PROMPT = ""
mock_config.IMPORTANCE_PROMPT = ""
mock_config.ROUTE_INTENT_PROMPT = ""
mock_config.ROUTE_RAG_PROMPT = ""
mock_config.ROUTE_PROMPT = "ROUTE_PROMPT_PLACEHOLDER"
mock_config.CLARIFY_PROMPT = ""

mock_config.DISASSEMBLY_PROMPT = ""
mock_config.STEP_PLAN_PROMPT = ""
mock_config.STEP_EXECUTE_PROMPT = ""
mock_config.INTEGRATION_PROMPT = ""
mock_config.PROBE_ROUTER_PROMPT = ""
mock_config.TOOL_EXECUTION_PROMPT = ""

import sys
sys.modules["config"] = mock_config

mock_adapter_map = {}
mock_server_registry = {}

mock_adapters_module = types.ModuleType("clients.mcp_adapters")
mock_adapters_module.ADAPTER_MAP = mock_adapter_map
mock_adapters_module.SERVER_REGISTRY = mock_server_registry
sys.modules["clients.mcp_adapters"] = mock_adapters_module


class FakeTool:
    def __init__(self, name, description):
        self.name = name
        self.description = description
        self.input_schema = {}


@pytest.fixture(autouse=True)
def _reset_timeout():
    import clients.mcp_client
    clients.mcp_client.TIMEOUT_SECONDS = 30
    yield
    # 清理：移除 mcp_client 上的臨時屬性
    if hasattr(clients.mcp_client, "TIMEOUT_SECONDS"):
        delattr(clients.mcp_client, "TIMEOUT_SECONDS")


def _make_mock_session(**kwargs):
    """建立 mock session"""
    session = AsyncMock()
    session.initialize = AsyncMock()
    for k, v in kwargs.items():
        setattr(session, k, v)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    return session


def _make_mock_stdio_ctx(session):
    """
    建立一個 MagicMock 作為 stdio_client mock。
    MagicMock 被呼叫時（stdio_client(server_params, ...)），
    return_value 是一個 async context manager。
    """
    ctx_mock = MagicMock()
    ctx_mock.return_value.__aenter__ = AsyncMock(return_value=(session, session))
    ctx_mock.return_value.__aexit__ = AsyncMock(return_value=False)
    return ctx_mock


def _make_mock_session_cls(session):
    """建立 mock ClientSession class"""
    cls_mock = MagicMock()
    cls_mock.return_value.__aenter__ = AsyncMock(return_value=session)
    cls_mock.return_value.__aexit__ = AsyncMock(return_value=False)
    return cls_mock


# ============ Test: adapter not found ============
class TestMcpConfigTimeout:
    @pytest.mark.asyncio
    async def test_get_tools_returns_empty_when_adapter_not_found(self):
        import clients.mcp_client
        result = await clients.mcp_client.get_tools("nonexistent")
        assert result.success is False
        assert "未找到 Adapter" in result.error

    @pytest.mark.asyncio
    async def test_call_tool_returns_error_when_adapter_not_found(self):
        import clients.mcp_client
        result = await clients.mcp_client.call_tool("nonexistent", "test_tool", {})
        assert result == "[Error] 未知的 server：nonexistent"


# ============ Test: get_tools timeout (mock asyncio.wait_for) ============
class TestGetToolsTimeout:
    @pytest.mark.asyncio
    async def test_get_tools_timeout_returns_empty_list(self):
        """get_tools 超時時回傳 [] 且不拋 exception"""
        import clients.mcp_client
        clients.mcp_client.TIMEOUT_SECONDS = 0.05

        fake_adapter = MagicMock()
        fake_adapter.get_server_params.return_value = MagicMock(command="echo", args=[])

        original_wait_for = asyncio.wait_for

        async def _mock_wait_for(fut, timeout=None):
            if timeout == 0.05:
                raise asyncio.TimeoutError("mock timeout")
            return await original_wait_for(fut, timeout)

        with patch.object(clients.mcp_client, "ADAPTER_MAP", {"test_server": fake_adapter}):
            with patch.object(clients.mcp_client.asyncio, "wait_for", _mock_wait_for):
                result = await clients.mcp_client.get_tools("test_server")
                assert result.success is False
                assert "逾時" in result.error

    @pytest.mark.asyncio
    async def test_get_tools_success_returns_tools(self):
        """get_tools 成功時回傳 tools 列表"""
        import clients.mcp_client

        fake_adapter = MagicMock()
        fake_adapter.get_server_params.return_value = MagicMock(command="echo", args=[])

        fake_tool = FakeTool("search_files", "搜尋檔案")
        mock_session = _make_mock_session()
        mock_session.list_tools = AsyncMock(return_value=MagicMock(tools=[fake_tool]))

        stdio_mock = _make_mock_stdio_ctx(mock_session)

        # Mock ClientSession 以返回 mock session
        mock_session_cls = MagicMock()
        mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        async def _mock_wait_for(fut, timeout=None):
            return await fut

        with patch.object(clients.mcp_client, "ADAPTER_MAP", {"test_server": fake_adapter}):
            with patch.object(clients.mcp_client.asyncio, "wait_for", _mock_wait_for):
                with patch.object(clients.mcp_client, "stdio_client", stdio_mock):
                    with patch.object(clients.mcp_client, "ClientSession", mock_session_cls):
                        result = await clients.mcp_client.get_tools("test_server")
                        assert result.success is True
                        assert len(result.data) == 1
                        assert result.data[0].name == "search_files"


# ============ Test: call_tool timeout (mock asyncio.wait_for) ============
class TestCallToolTimeout:
    @pytest.mark.asyncio
    async def test_call_tool_timeout_returns_timeout_error(self):
        """call_tool 超時時回傳 [TIMEOUT] 錯誤訊息"""
        import clients.mcp_client
        clients.mcp_client.TIMEOUT_SECONDS = 0.05

        fake_adapter = MagicMock()
        fake_adapter.get_server_params.return_value = MagicMock(command="echo", args=[])

        original_wait_for = asyncio.wait_for

        async def _mock_wait_for(fut, timeout=None):
            if timeout == 0.05:
                raise asyncio.TimeoutError("mock timeout")
            return await original_wait_for(fut, timeout)

        with patch.object(clients.mcp_client, "ADAPTER_MAP", {"test_server": fake_adapter}):
            with patch.object(clients.mcp_client.asyncio, "wait_for", _mock_wait_for):
                result = await clients.mcp_client.call_tool("test_server", "slow_tool", {"arg": "val"})
                assert "[TIMEOUT]" in result
                assert "slow_tool" in result

    @pytest.mark.asyncio
    async def test_call_tool_timeout_does_not_raise_exception(self):
        """call_tool 超時時不拋出 exception，安全恢復"""
        import clients.mcp_client
        clients.mcp_client.TIMEOUT_SECONDS = 0.05

        fake_adapter = MagicMock()
        fake_adapter.get_server_params.return_value = MagicMock(command="echo", args=[])

        original_wait_for = asyncio.wait_for

        async def _mock_wait_for(fut, timeout=None):
            if timeout == 0.05:
                raise asyncio.TimeoutError("mock timeout")
            return await original_wait_for(fut, timeout)

        with patch.object(clients.mcp_client, "ADAPTER_MAP", {"test_server": fake_adapter}):
            with patch.object(clients.mcp_client.asyncio, "wait_for", _mock_wait_for):
                result = await clients.mcp_client.call_tool("test_server", "any_tool", {})
                assert isinstance(result, str)
                assert "[TIMEOUT]" in result

    @pytest.mark.asyncio
    async def test_call_tool_success_returns_text(self):
        """call_tool 成功時回傳工具結果的文字"""
        import clients.mcp_client

        fake_adapter = MagicMock()
        fake_adapter.get_server_params.return_value = MagicMock(command="echo", args=[])

        mock_session = _make_mock_session()
        mock_session.call_tool = AsyncMock(return_value=MagicMock(
            content=[MagicMock(text="result_text")],
            isError=False
        ))

        stdio_mock = _make_mock_stdio_ctx(mock_session)
        session_cls_mock = _make_mock_session_cls(mock_session)

        async def _mock_wait_for(fut, timeout=None):
            return await fut

        with patch.object(clients.mcp_client, "ADAPTER_MAP", {"test_server": fake_adapter}):
            with patch.object(clients.mcp_client.asyncio, "wait_for", _mock_wait_for):
                with patch.object(clients.mcp_client, "stdio_client", stdio_mock):
                    with patch.object(clients.mcp_client, "ClientSession", session_cls_mock):
                        result = await clients.mcp_client.call_tool("test_server", "search_tool", {"query": "test"})
                        assert result == "result_text"

    @pytest.mark.asyncio
    async def test_call_tool_error_flag(self):
        """call_tool isError=True 時回傳 [TOOL_ERROR]"""
        import clients.mcp_client

        fake_adapter = MagicMock()
        fake_adapter.get_server_params.return_value = MagicMock(command="echo", args=[])

        mock_session = _make_mock_session()
        mock_session.call_tool = AsyncMock(return_value=MagicMock(
            content=[MagicMock(text="error_msg")],
            isError=True
        ))

        stdio_mock = _make_mock_stdio_ctx(mock_session)
        session_cls_mock = _make_mock_session_cls(mock_session)

        async def _mock_wait_for(fut, timeout=None):
            return await fut

        with patch.object(clients.mcp_client, "ADAPTER_MAP", {"test_server": fake_adapter}):
            with patch.object(clients.mcp_client.asyncio, "wait_for", _mock_wait_for):
                with patch.object(clients.mcp_client, "stdio_client", stdio_mock):
                    with patch.object(clients.mcp_client, "ClientSession", session_cls_mock):
                        result = await clients.mcp_client.call_tool("test_server", "fail_tool", {})
                        assert "[TOOL_ERROR]" in result


# ============ Test: get_tools no timeout (normal speed) ============
class TestGetToolsNoTimeout:
    @pytest.mark.asyncio
    async def test_get_tools_normal_speed(self):
        """get_tools 在正常時間內完成（不觸發 timeout）"""
        import clients.mcp_client

        fake_adapter = MagicMock()
        fake_adapter.get_server_params.return_value = MagicMock(command="echo", args=[])

        fake_tool = FakeTool("read_file", "讀取檔案內容")
        mock_session = _make_mock_session()
        mock_session.list_tools = AsyncMock(return_value=MagicMock(tools=[fake_tool]))

        stdio_mock = _make_mock_stdio_ctx(mock_session)
        session_cls_mock = _make_mock_session_cls(mock_session)

        async def _mock_wait_for(fut, timeout=None):
            return await fut

        with patch.object(clients.mcp_client, "ADAPTER_MAP", {"test_server": fake_adapter}):
            with patch.object(clients.mcp_client.asyncio, "wait_for", _mock_wait_for):
                with patch.object(clients.mcp_client, "stdio_client", stdio_mock):
                    with patch.object(clients.mcp_client, "ClientSession", session_cls_mock):
                        result = await clients.mcp_client.get_tools("test_server")
                        assert result.success is True
                        assert len(result.data) == 1
                        assert result.data[0].name == "read_file"


# ============ Test: call_tool timeout message content ============
class TestCallToolTimeoutMessage:
    @pytest.mark.asyncio
    async def test_call_tool_timeout_message_contains_server_name(self):
        """timeout 訊息中包含 tool 名稱（非 server 名稱）"""
        import clients.mcp_client
        clients.mcp_client.TIMEOUT_SECONDS = 0.05

        fake_adapter = MagicMock()
        fake_adapter.get_server_params.return_value = MagicMock(command="echo", args=[])

        original_wait_for = asyncio.wait_for

        async def _mock_wait_for(fut, timeout=None):
            if timeout == 0.05:
                raise asyncio.TimeoutError("mock timeout")
            return await original_wait_for(fut, timeout)

        with patch.object(clients.mcp_client, "ADAPTER_MAP", {"brave_search": fake_adapter}):
            with patch.object(clients.mcp_client.asyncio, "wait_for", _mock_wait_for):
                result = await clients.mcp_client.call_tool("brave_search", "web_search", {"q": "test"})
                assert "[TIMEOUT]" in result
                assert "web_search" in result
                assert "0.05" in result

    @pytest.mark.asyncio
    async def test_call_tool_timeout_message_contains_tool_name(self):
        """timeout 訊息中包含 tool 名稱"""
        import clients.mcp_client
        clients.mcp_client.TIMEOUT_SECONDS = 0.05

        fake_adapter = MagicMock()
        fake_adapter.get_server_params.return_value = MagicMock(command="echo", args=[])

        original_wait_for = asyncio.wait_for

        async def _mock_wait_for(fut, timeout=None):
            if timeout == 0.05:
                raise asyncio.TimeoutError("mock timeout")
            return await original_wait_for(fut, timeout)

        with patch.object(clients.mcp_client, "ADAPTER_MAP", {"test_server": fake_adapter}):
            with patch.object(clients.mcp_client.asyncio, "wait_for", _mock_wait_for):
                result = await clients.mcp_client.call_tool("test_server", "my_custom_tool", {})
                assert "my_custom_tool" in result
