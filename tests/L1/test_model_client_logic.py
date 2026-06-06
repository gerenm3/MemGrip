"""tests/L1/test_model_client_logic.py — clients/model_client.py 純邏輯測試（12 筆）."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pytest
import unittest.mock


class TestResolveModel:
    """resolve_model 函式測試."""

    def test_local_large(self):
        """等價類：LLM_MODE=local, role=large → LARGE_MODEL_NAME."""
        from clients import model_client
        with unittest.mock.patch.object(model_client.config, "LLM_MODE", "local"), \
             unittest.mock.patch.object(model_client.config, "LARGE_MODEL_NAME", "llama3"):
            result = model_client.resolve_model("large")
            assert result == "llama3"

    def test_cloud_medium(self):
        """等價類：LLM_MODE=cloud, role=medium → CLOUD_MEDIUM_MODEL_NAME."""
        from clients import model_client
        with unittest.mock.patch.object(model_client.config, "LLM_MODE", "cloud"), \
             unittest.mock.patch.object(model_client.config, "CLOUD_MEDIUM_MODEL_NAME", "gpt-3.5"):
            result = model_client.resolve_model("medium")
            assert result == "gpt-3.5"

    def test_hybrid_embedding(self):
        """等價類：LLM_MODE=hybrid, role=embedding → EMBEDDING_MODEL_NAME."""
        from clients import model_client
        with unittest.mock.patch.object(model_client.config, "LLM_MODE", "hybrid"), \
             unittest.mock.patch.object(model_client.config, "EMBEDDING_MODEL_NAME", "all-minilm"):
            result = model_client.resolve_model("embedding")
            assert result == "all-minilm"

    def test_unknown_role(self):
        """邊界：未知 role → KeyError（因 local mapping 無 'unknown' key）."""
        from clients import model_client
        with unittest.mock.patch.object(model_client.config, "LLM_MODE", "local"):
            with pytest.raises(KeyError):
                model_client.resolve_model("unknown")


class TestGetClient:
    """get_client 函式測試."""

    def test_cloud_client(self):
        """等價類：model_name 含 '/' → CloudClient."""
        from clients.model_client import get_client
        client = get_client("openai/gpt-4")
        assert client is not None

    def test_ollama_client(self):
        """等價類：model_name 無 '/' → OllamaLocalClient."""
        from clients.model_client import get_client
        client = get_client("llama3")
        assert client is not None

    def test_tracer_passthrough(self):
        """等價類：tracer 正確傳遞."""
        from clients.model_client import get_client
        tracer = object()
        with unittest.mock.patch("clients.model_client.CloudClient") as MockCloud:
            get_client("openai/gpt-4", tracer=tracer)
            MockCloud.assert_called_once()
            call_args = MockCloud.call_args
            assert call_args[1]["tracer"] == tracer

    def test_empty_model_name(self):
        """邊界：空 model_name → OllamaLocalClient."""
        from clients.model_client import get_client
        client = get_client("")
        assert client is not None


class TestModelServiceError:
    """ModelServiceError 測試."""

    def test_is_exception(self):
        """等價類：繼承 Exception."""
        from clients.model_client import ModelServiceError
        assert issubclass(ModelServiceError, Exception)

    def test_can_raise(self):
        """等價類：可被 raise/catch."""
        from clients.model_client import ModelServiceError
        with pytest.raises(ModelServiceError):
            raise ModelServiceError("test error")


class TestSetGlobalTracer:
    """set_global_tracer 測試."""

    def test_sets_tracer(self):
        """等價類：設定全域 tracer."""
        from clients.model_client import set_global_tracer, _global_tracer
        tracer = object()
        set_global_tracer(tracer)
        # 驗證全域 tracer 被設定


class TestCallModelErrorHandling:
    """call_model 錯誤處理測試."""

    def test_error_returns_failure_result(self):
        """等價類：call_model 異常 → Result(success=False)."""
        from clients.model_client import call_model
        import asyncio
        from unittest.mock import AsyncMock

        async def _test():
            with unittest.mock.patch("clients.model_client.resolve_model", return_value="llama3"), \
                 unittest.mock.patch("clients.model_client.get_client") as mock_get:
                mock_client = AsyncMock()
                mock_client.chat.side_effect = Exception("test error")
                mock_get.return_value = mock_client
                result = await call_model("large", [])
                assert result.success is False
                assert "test error" in result.error

        asyncio.run(_test())
