"""End-to-end integration tests for the MCP Search Hub.

These tests verify the full request flow from server through routing to providers and result processing.
All external APIs are mocked to ensure consistent test behavior.
"""

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from mcp_search_hub.models.query import SearchQuery
from mcp_search_hub.models.results import SearchResponse, SearchResult
from mcp_search_hub.server import SearchServer


class MockContext:
    """Mock Context object for testing."""

    def __init__(self):
        self.info_logs = []
        self.error_logs = []
        self.warning_logs = []

    def info(self, msg):
        self.info_logs.append(msg)

    def error(self, msg):
        self.error_logs.append(msg)

    def warning(self, msg):
        self.warning_logs.append(msg)


@pytest.fixture
def mock_context():
    """Fixture for MockContext."""
    return MockContext()


class MockProvider:
    """Mock search provider for testing."""

    def __init__(self, name, response=None, should_fail=False, delay=0.0):
        self.name = name
        self.initialized = True
        self.response = response or SearchResponse(
            results=[
                SearchResult(
                    title=f"{name} result",
                    url=f"https://{name}.com/result",
                    snippet=f"This is a result from {name}",
                    score=0.9,
                    source=name,
                )
            ],
            query="test query",
            total_results=1,
            provider=name,
        )
        self.should_fail = should_fail
        self.delay = delay
        self.search_called = False
        self.initialize_called = False
        self.close_called = False
        self.rate_limiter = MagicMock()
        self.rate_limiter.is_in_cooldown.return_value = False
        self.budget_tracker = MagicMock()
        self.budget_tracker.get_usage_report.return_value = {"daily_percent_used": 0}

    async def search(self, query):
        """Mock search method."""
        self.search_called = True
        if self.should_fail:
            raise Exception(f"{self.name} failed")
        if self.delay > 0:
            await asyncio.sleep(self.delay)
        return self.response

    async def initialize(self):
        """Mock initialize method."""
        self.initialize_called = True
        return True

    async def close(self):
        """Mock close method."""
        self.close_called = True
        return True

    async def list_tools(self):
        """Return mock tools."""
        return [{"name": "search", "description": "Search", "parameters": {}}]

    async def invoke_tool(self, tool_name, params):
        """Mock tool invocation."""
        return self.response

    async def check_status(self):
        """Return mock status."""
        from mcp_search_hub.models.base import HealthStatus

        return (HealthStatus.HEALTHY, "OK")

    def get_capabilities(self):
        """Return mock capabilities."""
        return {
            "content_types": ["general", "news"],
            "max_results": 10,
        }


@pytest.fixture
def mock_server():
    """Fixture for MockServer with patched providers."""
    # Create server
    server = SearchServer()

    # Setup mock providers
    providers = {
        "provider1": MockProvider("provider1"),
        "provider2": MockProvider("provider2"),
        "provider3": MockProvider("provider3", should_fail=True),
    }

    # Replace server's providers with our mocks
    server.providers = providers

    # Mark provider tools as registered to skip registration
    server._provider_tools_registered = True

    return server


@pytest.mark.asyncio
async def test_end_to_end_search_basic(mock_server, mock_context):
    """Test basic end-to-end search flow."""
    # Create a search query
    query = SearchQuery(query="test basic search", max_results=5)

    # Execute search
    response = await mock_server.search_with_routing(
        query, "test-request-id", mock_context
    )

    # Verify response structure
    assert response is not None
    assert len(response.results) > 0
    assert "providers_used" in response.metadata
    assert len(response.metadata["providers_used"]) > 0

    # Verify providers were called
    for _provider_name, provider in mock_server.providers.items():
        if not provider.should_fail:
            assert provider.search_called


@pytest.mark.asyncio
async def test_end_to_end_search_with_failures(mock_server, mock_context):
    """Test end-to-end search with provider failures."""
    # Create a search query
    query = SearchQuery(query="test with failures", max_results=5)

    # Execute search
    response = await mock_server.search_with_routing(
        query, "test-request-id", mock_context
    )

    # Verify response has results even with failures
    assert response is not None
    assert len(response.results) > 0

    # Verify failed provider was attempted but excluded from results
    failing_provider = mock_server.providers["provider3"]
    assert failing_provider.search_called
    assert "provider3" not in response.metadata["providers_used"]

    # Verify error was logged
    assert any("provider3 failed" in log for log in mock_context.error_logs)


@pytest.mark.asyncio
async def test_end_to_end_search_with_caching(mock_server, mock_context):
    """Test end-to-end search with caching."""
    # Create a search query
    query = SearchQuery(query="test caching search", max_results=5)

    # Execute search first time
    response1 = await mock_server.search_with_routing(
        query, "test-request-id-1", mock_context
    )

    # Reset provider call flags
    for provider in mock_server.providers.values():
        provider.search_called = False

    # Execute same search again (should be cached)
    response2 = await mock_server.search_with_routing(
        query, "test-request-id-2", mock_context
    )

    # Verify responses match
    assert response1.results == response2.results

    # Verify no providers were called the second time (cache hit)
    for provider in mock_server.providers.values():
        assert not provider.search_called

    # Verify cache hit was logged
    assert any("Cache hit" in log for log in mock_context.info_logs)


@pytest.mark.asyncio
async def test_end_to_end_different_content_types(mock_server, mock_context):
    """Test end-to-end search with different content types."""
    # Create queries with different content types
    queries = [
        ("test news search", "news"),
        ("test academic search", "academic"),
        ("test code search", "code"),
        ("what is the capital of France", "general"),  # Question
    ]

    for query_text, expected_content_type in queries:
        # Reset provider call flags
        for provider in mock_server.providers.values():
            provider.search_called = False

        # Execute search
        query = SearchQuery(query=query_text, max_results=5)
        response = await mock_server.search_with_routing(
            query, f"test-{expected_content_type}", mock_context
        )

        # Verify results
        assert response is not None
        assert len(response.results) > 0

        # Verify content type detection (logged in features)
        assert response.metadata["features"]["content_type"] is not None


@pytest.mark.asyncio
async def test_end_to_end_raw_content_flag(mock_server, mock_context):
    """Test end-to-end search with raw_content flag."""
    # Create a search query with raw_content=True
    query = SearchQuery(query="test raw content", max_results=5, raw_content=True)

    # Add raw content to provider responses
    for provider in mock_server.providers.values():
        provider.response.results[0].raw_content = f"Raw content from {provider.name}"

    # Execute search
    response = await mock_server.search_with_routing(
        query, "test-request-id", mock_context
    )

    # Verify raw content in response
    assert response is not None
    assert len(response.results) > 0
    for result in response.results:
        assert hasattr(result, "raw_content")
        assert result.raw_content is not None
        assert "Raw content from" in result.raw_content


@pytest.mark.asyncio
async def test_unified_router_strategy_selection(mock_server, mock_context):
    """Test that the router correctly selects strategies based on query characteristics."""
    # Test case with different strategy expectations
    test_cases = [
        # Simple query, expected parallel strategy
        {
            "query": "simple test query",
            "expected_strategy": "parallel",
            "complexity": 0.3,
        },
        # Complex query, expected cascade strategy
        {
            "query": "complex technical analysis of quantum computing implications on cryptography",
            "expected_strategy": "cascade",
            "complexity": 0.8,
        },
        # Single provider query, expected cascade strategy
        {
            "query": "single provider test",
            "expected_strategy": "cascade",
            "complexity": 0.3,
            "mock_selection": ["provider1"],  # Force single provider
        },
    ]

    # Test each case
    for case in test_cases:
        query = SearchQuery(query=case["query"], max_results=5)

        # Create a mock query features
        from mcp_search_hub.models.query import QueryFeatures

        QueryFeatures(
            length=len(case["query"]),
            word_count=len(case["query"].split()),
            content_type="general",
            complexity=case["complexity"],
            time_sensitivity=0.3,
            factual_nature=0.5,
            contains_question=False,
        )

        # Mock the select_providers and _determine_strategy to track what strategy was chosen
        with patch.object(mock_server.router, "select_providers") as mock_select:
            with patch.object(
                mock_server.router,
                "_determine_strategy",
                wraps=mock_server.router._determine_strategy,
            ) as mock_determine:
                # Configure select_providers mock
                if "mock_selection" in case:
                    from mcp_search_hub.models.router import RoutingDecision

                    mock_select.return_value = RoutingDecision(
                        query_id=query.query,
                        selected_providers=case["mock_selection"],
                        provider_scores=[],
                        score_mode="AVG",
                        confidence=0.8,
                        explanation="Mocked decision",
                        metadata={},
                    )

                # Execute search
                await mock_server.search_with_routing(
                    query, f"test-{case['expected_strategy']}", mock_context
                )

                # If we mocked the provider selection
                if "mock_selection" in case:
                    # Verify determine_strategy was called with our mocked selection
                    mock_determine.assert_called_once()
                    args, _ = mock_determine.call_args
                    # Check the selected providers match our mock
                    assert args[2] == case["mock_selection"]
                    # And check the strategy matches our expectation
                    assert mock_determine.return_value == case["expected_strategy"]
                else:
                    # Just verify it was called - harder to verify the result without mocking selection
                    assert mock_determine.called
