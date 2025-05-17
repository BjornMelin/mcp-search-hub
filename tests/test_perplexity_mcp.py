"""Tests for Perplexity MCP provider integration."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from mcp_search_hub.models.query import SearchQuery
from mcp_search_hub.providers.perplexity_mcp import PerplexityMCPProvider

from .test_base_mcp import TestBaseMCPProvider


class TestPerplexityMCPProvider(TestBaseMCPProvider):
    """Test Perplexity MCP provider functionality."""

    provider_class = PerplexityMCPProvider
    provider_name = "perplexity"
    tool_name = "perplexity_ask"

    @pytest.fixture(autouse=True)
    def setup(self):
        """Pytest fixture setup."""

    async def test_search_params_format(self):
        """Test that Perplexity formats search params correctly."""
        provider = self.get_provider()
        provider.initialized = True
        provider.session = MagicMock()

        # Mock tool invocation
        mock_result = AsyncMock()
        mock_result.content = [
            MagicMock(text={
                "results": []
            })
        ]
        provider.session.call_tool = AsyncMock(return_value=mock_result)

        query = SearchQuery(query="test query")
        await provider.search(query)

        # Verify the tool was called with messages format
        call_args = provider.session.call_tool.call_args
        params = call_args[1]["arguments"]
        assert "messages" in params
        assert params["messages"][0]["role"] == "user"
        assert params["messages"][0]["content"] == "test query"
