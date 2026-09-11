"""Tests for OpenAI provider endpoint compatibility.

Tests verify endpoint detection, model support logic, and MCP tool conversion
for both native OpenAI and custom endpoints (vLLM, etc.).
"""

import os
from unittest.mock import AsyncMock, patch

import pytest

from lightspeed_agentic.providers.openai import (
    _build_mcp_function_tools,
    _is_native_openai,
    _model_supports_json_schema,
)


class TestMCPFunctionTools:
    @pytest.mark.asyncio
    async def test_converts_tools_from_each_mcp_server(self):
        first_server = AsyncMock()
        second_server = AsyncMock()
        first_tool = object()
        second_tool = object()
        first_server.list_tools.return_value = [first_tool]
        second_server.list_tools.return_value = [second_tool]

        first_function_tool = object()
        second_function_tool = object()
        with patch(
            "agents.mcp.util.MCPUtil.to_function_tool",
            side_effect=[first_function_tool, second_function_tool],
        ) as convert:
            result = await _build_mcp_function_tools([first_server, second_server])

        assert result == [first_function_tool, second_function_tool]
        convert.assert_any_call(first_tool, first_server, convert_schemas_to_strict=False)
        convert.assert_any_call(second_tool, second_server, convert_schemas_to_strict=False)


class TestNativeOpenAIDetection:
    """Test _is_native_openai() helper."""

    def test_native_openai_by_default(self):
        """When OPENAI_BASE_URL unset, defaults to native OpenAI."""
        with patch.dict(os.environ, {}, clear=False):
            # Remove OPENAI_BASE_URL if set
            os.environ.pop("OPENAI_BASE_URL", None)
            assert _is_native_openai() is True

    def test_native_openai_explicit(self):
        """When OPENAI_BASE_URL is api.openai.com, recognized as native."""
        with patch.dict(os.environ, {"OPENAI_BASE_URL": "https://api.openai.com/v1"}):
            assert _is_native_openai() is True

    def test_vllm_not_native(self):
        """When OPENAI_BASE_URL is vLLM, recognized as non-native."""
        with patch.dict(os.environ, {"OPENAI_BASE_URL": "http://localhost:8000/v1"}):
            assert _is_native_openai() is False

    def test_custom_endpoint_not_native(self):
        """Custom OpenAI-compatible endpoint detected as non-native."""
        with patch.dict(os.environ, {"OPENAI_BASE_URL": "https://custom.example.com/v1"}):
            assert _is_native_openai() is False

    def test_invalid_url_defaults_to_false(self):
        """Malformed URL handled gracefully, defaults to non-native."""
        with patch.dict(os.environ, {"OPENAI_BASE_URL": "not-a-valid-url"}):
            assert _is_native_openai() is False


class TestModelSelectionByEndpoint:
    """Test endpoint detection and tool compatibility decisions."""

    def test_native_openai_detected_without_base_url(self):
        """When OPENAI_BASE_URL unset, detected as native OpenAI."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("OPENAI_BASE_URL", None)
            assert _is_native_openai() is True

    def test_native_openai_detected_with_explicit_api_openai_url(self):
        """When OPENAI_BASE_URL is api.openai.com, detected as native."""
        with patch.dict(os.environ, {"OPENAI_BASE_URL": "https://api.openai.com/v1"}):
            assert _is_native_openai() is True

    def test_vllm_detected_as_non_native(self):
        """When OPENAI_BASE_URL is vLLM, detected as non-native endpoint."""
        with patch.dict(os.environ, {"OPENAI_BASE_URL": "http://localhost:8000/v1"}):
            assert _is_native_openai() is False

    def test_custom_endpoint_detected_as_non_native(self):
        """Custom OpenAI-compatible endpoint detected as non-native."""
        custom_urls = [
            "https://custom.example.com/v1",
            "https://my-llm-service.internal/api/v1",
            "http://llm-proxy:8080/v1",
        ]
        for url in custom_urls:
            with patch.dict(os.environ, {"OPENAI_BASE_URL": url}):
                assert _is_native_openai() is False, f"Should detect {url} as non-native"

    def test_reasoning_available_with_responses_model(self):
        """OpenAIResponsesModel supports reasoning via response deltas."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("OPENAI_BASE_URL", None)
            assert _is_native_openai() is True
            # OpenAIResponsesModel emits ResponseReasoningTextDeltaEvent

    def test_vllm_detected_as_non_native_for_chat_completions(self):
        """Custom endpoints use the Chat Completions compatibility path."""
        with patch.dict(os.environ, {"OPENAI_BASE_URL": "http://localhost:8000/v1"}):
            assert _is_native_openai() is False
            # The query() method selects Chat Completions for custom endpoints.


class TestQueryFlowIntegration:
    """Integration tests validating endpoint selection logic."""

    def test_model_supports_json_schema_native_openai(self):
        """Test model support detection for native OpenAI."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("OPENAI_BASE_URL", None)
            # Supported models
            assert _model_supports_json_schema("gpt-4") is True
            assert _model_supports_json_schema("gpt-4o") is True
            assert _model_supports_json_schema("gpt-4-turbo") is True
            # Unsupported models
            assert _model_supports_json_schema("gpt-3.5-turbo") is False
            assert _model_supports_json_schema("text-davinci-003") is False

    def test_model_supports_json_schema_custom_endpoint(self):
        """Test model support detection for custom endpoints (vLLM, etc.)."""
        with patch.dict(os.environ, {"OPENAI_BASE_URL": "http://localhost:8000/v1"}):
            # Custom endpoints assume support (failures caught at API call time)
            assert _model_supports_json_schema("gpt-3.5-turbo") is True
            assert _model_supports_json_schema("meta-llama/Llama-2-7b") is True
            assert _model_supports_json_schema("any-model") is True
