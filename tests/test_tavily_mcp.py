"""Tests for Tavily MCP provider integration."""

import pytest

from mcp_search_hub.providers.tavily_mcp import TavilyMCPProvider
from .test_base_mcp import TestBaseMCPProvider, TestBaseMCPProviderAdvancedQuery, TestBaseMCPProviderRawContent


class TestTavilyMCPProvider(TestBaseMCPProvider, TestBaseMCPProviderAdvancedQuery, TestBaseMCPProviderRawContent):
    """Test Tavily MCP provider functionality."""

    provider_class = TavilyMCPProvider
    provider_name = "tavily"
    tool_name = "tavily_search"

    @pytest.fixture(autouse=True)
    def setup(self):
        """Pytest fixture setup."""
        pass

    def get_advanced_options(self):
        """Get Tavily-specific advanced options."""
        return {
            "deep_search": True
        }

    def verify_advanced_params(self, params):
        """Verify Tavily-specific advanced parameters."""
        # Tavily should have search_depth parameter
        assert "search_depth" in params
        assert params["search_depth"] == "advanced"

    def verify_raw_content_params(self, params):
        """Verify Tavily-specific raw content parameters."""
        # Tavily should include include_raw_content parameter
        assert "include_raw_content" in params
        assert params["include_raw_content"] is True