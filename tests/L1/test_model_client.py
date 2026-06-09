"""Test plan L1 - ModelClient (#8)

L1 scope (per l1_scope.md): set_global_tracer, resolve_model, get_client
Excluded: call_model, call_embedding (depend on LLM external service)

Total: 13 test cases (TC-08-01 ~ TC-08-13)
"""

import pytest
from unittest.mock import MagicMock, patch
import config
from clients.model_client import set_global_tracer, resolve_model, get_client, ModelServiceError


# ── set_global_tracer ──────────────────────────────────────────────

class TestSetGlobalTracer:
    """TC-08-01 ~ TC-08-02"""

    def test_TC_08_01_set_global_tracer_sets_tracer(self):
        tracer_obj = MagicMock()
        set_global_tracer(tracer_obj)
        from clients import model_client
        assert model_client._global_tracer is tracer_obj

    def test_TC_08_02_set_global_tracer_none(self):
        set_global_tracer(None)
        from clients import model_client
        assert model_client._global_tracer is None


# ── resolve_model ──────────────────────────────────────────────

class TestResolveModel:
    """TC-08-03 ~ TC-08-11"""

    def test_TC_08_03_resolve_local_large(self):
        with patch.object(config, "LLM_MODE", "local"):
            result = resolve_model("large")
            assert result == config.LARGE_MODEL_NAME

    def test_TC_08_04_resolve_local_medium(self):
        with patch.object(config, "LLM_MODE", "local"):
            result = resolve_model("medium")
            assert result == config.MEDIUM_MODEL_NAME

    def test_TC_08_05_resolve_local_embedding(self):
        with patch.object(config, "LLM_MODE", "local"):
            result = resolve_model("embedding")
            assert result == config.EMBEDDING_MODEL_NAME

    def test_TC_08_06_resolve_cloud_large(self):
        with patch.object(config, "LLM_MODE", "cloud"):
            result = resolve_model("large")
            assert result == config.CLOUD_MODEL_NAME

    def test_TC_08_07_resolve_cloud_medium(self):
        with patch.object(config, "LLM_MODE", "cloud"):
            result = resolve_model("medium")
            assert result == config.CLOUD_MEDIUM_MODEL_NAME

    def test_TC_08_08_resolve_hybrid_large(self):
        with patch.object(config, "LLM_MODE", "hybrid"):
            result = resolve_model("large")
            assert result == config.CLOUD_MODEL_NAME

    def test_TC_08_09_resolve_hybrid_medium(self):
        with patch.object(config, "LLM_MODE", "hybrid"):
            result = resolve_model("medium")
            assert result == config.MEDIUM_MODEL_NAME

    def test_TC_08_10_resolve_hybrid_embedding(self):
        with patch.object(config, "LLM_MODE", "hybrid"):
            result = resolve_model("embedding")
            assert result == config.EMBEDDING_MODEL_NAME

    def test_TC_08_11_resolve_unknown_mode_fallback(self):
        with patch.object(config, "LLM_MODE", "unknown_mode"):
            result = resolve_model("large")
            # Should fallback to local mapping
            assert result == config.LARGE_MODEL_NAME

    def test_TC_08_12_resolve_invalid_role_raises_key_error(self):
        with patch.object(config, "LLM_MODE", "local"):
            with pytest.raises(KeyError):
                resolve_model("unknown_role")


# ── get_client ──────────────────────────────────────────────

class TestGetClient:
    """TC-08-13 ~ TC-08-15 (L1 scope only)"""

    def test_TC_08_13_get_client_with_slash(self):
        tracer = MagicMock()
        with patch("clients.model_client.CloudClient") as MockCloud:
            MockCloud.return_value = MagicMock()
            client = get_client("openai/gpt-4", tracer)
            MockCloud.assert_called_once()
            call_kwargs = MockCloud.call_args.kwargs
            assert call_kwargs.get("tracer") is tracer

    def test_TC_08_14_get_client_without_slash(self):
        tracer = MagicMock()
        with patch("clients.model_client.OllamaLocalClient") as MockOllama:
            MockOllama.return_value = MagicMock()
            client = get_client("llama-3", tracer)
            MockOllama.assert_called_once()
            call_kwargs = MockOllama.call_args.kwargs
            assert call_kwargs.get("tracer") is tracer

    def test_TC_08_15_get_client_tracer_none(self):
        with patch("clients.model_client.OllamaLocalClient") as MockOllama:
            MockOllama.return_value = MagicMock()
            client = get_client("llama-3", None)
            MockOllama.assert_called_once()
            call_kwargs = MockOllama.call_args.kwargs
            assert call_kwargs.get("tracer") is None


# ── ModelServiceError ──────────────────────────────────────────────

class TestModelServiceError:
    """TC-08-16 (L1 scope: verify it's an Exception subclass)"""

    def test_TC_08_16_model_service_error_is_exception(self):
        e = ModelServiceError("test error")
        assert isinstance(e, Exception)