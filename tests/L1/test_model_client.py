"""tests/L1/test_model_client -- 10 筆測試."""

import unittest

import pytest


class TestResolveModel:
    """resolve_model 測試 (1-8)."""

    def test_resolve_model_local_large(self, mock_config_all_model_names):
        from clients import model_client

        result = model_client.resolve_model("large")
        assert result == "llama3"

    def test_resolve_model_local_medium(self, mock_config_all_model_names):
        from clients import model_client

        result = model_client.resolve_model("medium")
        assert result == "llama3-med"

    def test_resolve_model_local_embedding(self, mock_config_all_model_names):
        from clients import model_client

        result = model_client.resolve_model("embedding")
        assert result == "all-minilm"

    def test_resolve_model_cloud_large(self):
        from clients import model_client

        with unittest.mock.patch.object(model_client.config, "LLM_MODE", "cloud"):
            with unittest.mock.patch.object(model_client.config, "CLOUD_MODEL_NAME", "openai/gpt-4"):
                result = model_client.resolve_model("large")
                assert result == "openai/gpt-4"

    def test_resolve_model_cloud_medium(self):
        from clients import model_client

        with unittest.mock.patch.object(model_client.config, "LLM_MODE", "cloud"):
            with unittest.mock.patch.object(model_client.config, "CLOUD_MEDIUM_MODEL_NAME", "openai/gpt-3.5"):
                result = model_client.resolve_model("medium")
                assert result == "openai/gpt-3.5"

    def test_resolve_model_hybrid_large(self):
        from clients import model_client

        with unittest.mock.patch.object(model_client.config, "LLM_MODE", "hybrid"):
            with unittest.mock.patch.object(model_client.config, "CLOUD_MODEL_NAME", "openai/gpt-4"):
                result = model_client.resolve_model("large")
                assert result == "openai/gpt-4"

    def test_resolve_model_hybrid_medium(self):
        from clients import model_client

        with unittest.mock.patch.object(model_client.config, "LLM_MODE", "hybrid"):
            with unittest.mock.patch.object(model_client.config, "MEDIUM_MODEL_NAME", "llama3-med"):
                result = model_client.resolve_model("medium")
                assert result == "llama3-med"

    def test_resolve_model_unknown_mode_fallback_to_local(self):
        from clients import model_client

        with unittest.mock.patch.object(model_client.config, "LLM_MODE", "unknown_mode_xyz"):
            result = model_client.resolve_model("large")
            assert result == model_client.config.LARGE_MODEL_NAME


class TestGetClient:
    """get_client 測試 (9-10)."""

    def test_get_client_returns_cloud_when_name_contains_slash(self):
        from clients import model_client
        from clients.cloud import CloudClient

        client = model_client.get_client("openai/gpt-4")
        assert isinstance(client, CloudClient)

    def test_get_client_returns_ollama_when_no_slash(self):
        from clients import model_client
        from clients.ollama import OllamaLocalClient

        client = model_client.get_client("llama3")
        assert isinstance(client, OllamaLocalClient)
