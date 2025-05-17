"""Tests for Firecrawl MCP provider integration."""

import pytest

from mcp_search_hub.providers.firecrawl_mcp import FirecrawlMCPProvider

from .test_base_mcp import TestBaseMCPProvider, TestBaseMCPProviderRawContent


class TestFirecrawlMCPProvider(TestBaseMCPProvider, TestBaseMCPProviderRawContent):
    """Test Firecrawl MCP provider functionality."""

    provider_class = FirecrawlMCPProvider
    provider_name = "firecrawl"
    tool_name = "firecrawl_search"

    @pytest.fixture(autouse=True)
    def setup(self):
        """Pytest fixture setup."""

    def verify_raw_content_params(self, params):
        """Verify Firecrawl-specific raw content parameters."""
        # Firecrawl should include formats parameter when raw content is requested
        assert "formats" in params
        assert "markdown" in params["formats"]
        assert "links" in params["formats"]
