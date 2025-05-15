"""Test configuration for MCP Search Hub."""

import pytest

from mcp_search_hub.config import get_settings


@pytest.fixture
def mock_env(monkeypatch):
    """Mock environment variables for testing."""
    monkeypatch.setenv("LINKUP_API_KEY", "test_linkup_key")
    monkeypatch.setenv("EXA_API_KEY", "test_exa_key")
    monkeypatch.setenv("PERPLEXITY_API_KEY", "test_perplexity_key")
    monkeypatch.setenv("TAVILY_API_KEY", "test_tavily_key")
    monkeypatch.setenv("FIRECRAWL_API_KEY", "test_firecrawl_key")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("CACHE_TTL", "1800")

    # Clear lru_cache to ensure it picks up the new env vars
    get_settings.cache_clear()

    yield

    # Clean up
    get_settings.cache_clear()
