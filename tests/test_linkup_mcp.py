"""Tests for Linkup MCP provider integration."""

import pytest

from mcp_search_hub.providers.linkup_mcp import LinkupMCPProvider
from .test_base_mcp import TestBaseMCPProvider, TestBaseMCPProviderAdvancedQuery


class TestLinkupMCPProvider(TestBaseMCPProvider, TestBaseMCPProviderAdvancedQuery):
    """Test Linkup MCP provider functionality."""

    provider_class = LinkupMCPProvider
    provider_name = "linkup"
    tool_name = "search-web"

    @pytest.fixture(autouse=True)
    def setup(self):
        """Pytest fixture setup."""
        pass

    def get_advanced_options(self):
        """Get Linkup-specific advanced options."""
        return {
            "depth": "deep"
        }

    def verify_advanced_params(self, params):
        """Verify Linkup-specific advanced parameters."""
        # Linkup should have depth parameter
        assert "depth" in params
        assert params["depth"] == "deep"