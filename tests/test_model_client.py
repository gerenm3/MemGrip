"""tests/test_model_client.py — OllamaClient 與 CloudClient 測試."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from clients.base import ChatResponse
from clients.ollama import OllamaLocalClient, ModelServiceError
from clients.cloud import CloudClient, CloudServiceError


# ============== 本地 Ollama 測試（實際呼叫） ==============


class TestOllamaLocalClient:
    """OllamaLocalClient 實際呼叫測試."""

    @pytest.mark.asyncio
    async def test_chat_returns_non_empty_content(self):
        """chat() 回傳非空 content."""
        client = OllamaLocalClient()
        messages = [{"role": "user", "content": "Hello"}]
        response = await client.chat(
            model="qwen3.5:9b",
            messages=messages,
            temperature=0.7,
            max_tokens=64,
        )
        assert isinstance(response, ChatResponse)
        assert isinstance(response.content, str)

    @pytest.mark.asyncio
    async def test_chat_think_false_executes_normally(self):
        """think=False 正常執行."""
        client = OllamaLocalClient()
        messages = [{"role": "user", "content": "Hi"}]
        response = await client.chat(
            model="qwen3.5:9b",
            messages=messages,
            think=False,
        )
        assert isinstance(response, ChatResponse)

    @pytest.mark.asyncio
    async def test_chat_returns_chatresponse_object(self):
        """回傳 ChatResponse 物件."""
        client = OllamaLocalClient()
        messages = [{"role": "user", "content": "Test"}]
        response = await client.chat(
            model="qwen3.5:9b",
            messages=messages,
            temperature=0.5,
            max_tokens=32,
        )
        assert isinstance(response, ChatResponse)
        assert hasattr(response, "content")
        assert hasattr(response, "tool_calls")
        assert hasattr(response, "reasoning_content")


# ===================== 雲端 client 測試（mock LiteLLM） =====================


class MockMessage:
    """模擬 litellm 回傳的 message."""
    def __init__(self, content="mocked response", tool_calls=None, reasoning_content=None):
        self.content = content
        self.tool_calls = tool_calls
        self.reasoning_content = reasoning_content


class MockChoice:
    """模擬 litellm 回傳的 choice."""
    def __init__(self, message):
        self.message = message


class MockResponse:
    """模擬 litellm 回傳的 response."""
    def __init__(self, content="mocked response", tool_calls=None, reasoning_content=None):
        self.choices = [MockChoice(MockMessage(content, tool_calls, reasoning_content))]


class TestCloudClient:
    """CloudClient mock 測試."""

    @patch("clients.cloud.litellm.acompletion")
    @pytest.mark.asyncio
    async def test_think_true_passes_reasoning_effort_high(self, mock_acompletion):
        """think=True 時 reasoning_effort='high' 正確傳遞."""
        mock_acompletion.return_value = MockResponse(content="reasoning response", reasoning_content="inner thoughts")

        client = CloudClient()
        messages = [{"role": "user", "content": "Think about this"}]
        response = await client.chat(model="gpt-4", messages=messages, think=True)

        # 確認 litellm.acompletion 被呼叫且 reasoning_effort="high"
        mock_acompletion.assert_awaited_once()
        call_kwargs = mock_acompletion.await_args.kwargs
        assert call_kwargs["reasoning_effort"] == "high"
        assert isinstance(response, ChatResponse)
        assert response.content == "reasoning response"
        assert response.reasoning_content == "inner thoughts"

    @patch("clients.cloud.litellm.acompletion")
    @pytest.mark.asyncio
    async def test_think_false_passes_reasoning_effort_none(self, mock_acompletion):
        """think=False 時 reasoning_effort='none' 正確傳遞."""
        mock_acompletion.return_value = MockResponse(content="normal response")

        client = CloudClient()
        messages = [{"role": "user", "content": "Normal query"}]
        response = await client.chat(model="gpt-4", messages=messages, think=False)

        mock_acompletion.assert_awaited_once()
        call_kwargs = mock_acompletion.await_args.kwargs
        assert call_kwargs["reasoning_effort"] == "none"
        assert isinstance(response, ChatResponse)
        assert response.content == "normal response"
        assert response.reasoning_content is None

    @patch("clients.cloud.litellm.acompletion")
    @pytest.mark.asyncio
    async def test_chat_response_parsed_correctly(self, mock_acompletion):
        """回傳值正確解析為 ChatResponse."""
        mock_tool_call = MagicMock()
        mock_tool_call.function.name = "search"
        mock_tool_call.function.arguments = {"query": "test"}

        mock_acompletion.return_value = MockResponse(
            content="Here is the answer",
            tool_calls=[mock_tool_call],
            reasoning_content=None,
        )

        client = CloudClient()
        messages = [{"role": "user", "content": "Search for test"}]
        response = await client.chat(model="gpt-4", messages=messages)

        assert isinstance(response, ChatResponse)
        assert response.content == "Here is the answer"
        assert len(response.tool_calls) == 1
        assert response.tool_calls[0].function.name == "search"
        assert response.reasoning_content is None

    @patch("clients.cloud.litellm.acompletion")
    @pytest.mark.asyncio
    async def test_empty_content_returns_empty_string(self, mock_acompletion):
        """content 為 None 時回傳空字串."""
        mock_acompletion.return_value = MockResponse(content=None)

        client = CloudClient()
        messages = [{"role": "user", "content": "Test"}]
        response = await client.chat(model="gpt-4", messages=messages)

        assert isinstance(response, ChatResponse)
        assert response.content == ""

    @patch("clients.cloud.litellm.acompletion")
    @pytest.mark.asyncio
    async def test_chat_uses_cloud_api_key(self, mock_acompletion):
        """確認呼叫時使用 CLOUD_API_KEY."""
        from config import CLOUD_API_KEY
        mock_acompletion.return_value = MockResponse(content="ok")

        client = CloudClient()
        messages = [{"role": "user", "content": "Test"}]
        await client.chat(model="gpt-4", messages=messages)

        call_kwargs = mock_acompletion.await_args.kwargs
        assert call_kwargs["api_key"] == CLOUD_API_KEY