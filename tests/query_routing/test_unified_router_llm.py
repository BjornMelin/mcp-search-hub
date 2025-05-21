"""Tests for LLM integration in the unified router."""

import asyncio
from decimal import Decimal
from unittest import mock

import pytest

from mcp_search_hub.models.query import QueryFeatures, SearchQuery
from mcp_search_hub.models.router import (
    ProviderExecutionResult,
    RoutingDecision,
    SearchResponse,
    TimeoutConfig,
)
from mcp_search_hub.providers.base import SearchProvider
from mcp_search_hub.query_routing.llm_router import RoutingHintParser
from mcp_search_hub.query_routing.unified_router import (
    ExecutionStrategy,
    UnifiedRouter,
)


class MockProvider(SearchProvider):
    """Mock search provider for testing."""

    def __init__(self, name):
        """Initialize with a name."""
        self.name = name
        self.search_called = False
        self.delay = 0

    async def search(self, query):
        """Mock search method."""
        self.search_called = True
        if self.delay > 0:
            await asyncio.sleep(self.delay)
        return SearchResponse(results=[{"title": f"Result from {self.name}"}])

    async def initialize(self):
        """Mock initialize method."""

    async def cleanup(self):
        """Mock cleanup method."""


class TestUnifiedRouterLLM:
    """Test the unified router with LLM integration."""

    def setup_method(self):
        """Set up test environment."""
        # Create mock providers
        self.providers = {
            "tavily": MockProvider("tavily"),
            "perplexity": MockProvider("perplexity"),
            "linkup": MockProvider("linkup"),
            "firecrawl": MockProvider("firecrawl"),
            "exa": MockProvider("exa"),
        }

        # Create timeout config
        self.timeout_config = TimeoutConfig(
            base_timeout_ms=2000,
            min_timeout_ms=1000,
            max_timeout_ms=5000,
            complexity_factor=1.0,
        )

        # Create test features
        self.features = QueryFeatures(
            length=20,
            word_count=4,
            contains_question=True,
            content_type="web_search",
            time_sensitivity=0.3,
            complexity=0.7,
            factual_nature=0.8,
        )

    @mock.patch("mcp_search_hub.query_routing.unified_router.LLM_ROUTER_ENABLED", True)
    def test_init_with_llm_router(self):
        """Test initialization with LLM router."""
        with mock.patch(
            "mcp_search_hub.query_routing.unified_router.LLMQueryRouter"
        ) as mock_llm_router:
            # Setup mock
            mock_llm_router.return_value = mock.MagicMock()

            # Create router
            router = UnifiedRouter(
                providers=self.providers,
                timeout_config=self.timeout_config,
            )

            # Verify LLM router was initialized
            mock_llm_router.assert_called_once()
            assert router.llm_router is not None
            assert router.llm_router in router._scorers

    @pytest.mark.asyncio
    async def test_route_and_execute_with_routing_hints(self):
        """Test routing with routing hints."""
        # Mock the hint parser
        hint_parser = mock.MagicMock(spec=RoutingHintParser)
        hint_parser.parse_hints.return_value = {
            "preferred_providers": ["tavily", "linkup"],
            "strategy": "parallel",
        }

        # Create router and replace hint parser
        router = UnifiedRouter(
            providers=self.providers,
            timeout_config=self.timeout_config,
        )

        # Mock select_providers to return a fixed decision
        router.select_providers = mock.MagicMock()
        router.select_providers.return_value = RoutingDecision(
            query_id="test",
            selected_providers=["perplexity", "exa"],  # Different from hints
            provider_scores=[],
            score_mode="avg",
            confidence=0.8,
            explanation="Test",
            metadata={},
        )

        # Create query with routing hints
        query = SearchQuery(
            query="test query",
            routing_hints="prioritize recent news",
        )

        # Execute with patched hint parser
        with mock.patch(
            "mcp_search_hub.query_routing.unified_router.RoutingHintParser",
            return_value=hint_parser,
        ):
            results = await router.route_and_execute(query, self.features)

        # Verify hint parser was called
        hint_parser.parse_hints.assert_called_once_with("prioritize recent news")

        # Verify providers were selected from hints
        assert "tavily" in results
        assert "linkup" in results

    @pytest.mark.asyncio
    async def test_route_and_execute_with_routing_strategy(self):
        """Test routing with explicit routing strategy."""
        # Create router
        router = UnifiedRouter(
            providers=self.providers,
            timeout_config=self.timeout_config,
        )

        # Mock the execution strategies
        parallel_strategy = mock.MagicMock(spec=ExecutionStrategy)
        parallel_results = {
            "tavily": mock.MagicMock(spec=ProviderExecutionResult),
            "perplexity": mock.MagicMock(spec=ProviderExecutionResult),
        }
        parallel_strategy.execute.return_value = parallel_results

        cascade_strategy = mock.MagicMock(spec=ExecutionStrategy)
        cascade_results = {
            "firecrawl": mock.MagicMock(spec=ProviderExecutionResult),
        }
        cascade_strategy.execute.return_value = cascade_results

        router._strategies = {
            "parallel": parallel_strategy,
            "cascade": cascade_strategy,
        }

        # Create query with routing strategy
        query = SearchQuery(
            query="test query",
            routing_strategy="cascade",
        )

        # Execute
        results = await router.route_and_execute(query, self.features)

        # Verify cascade strategy was used
        cascade_strategy.execute.assert_called_once()
        parallel_strategy.execute.assert_not_called()
        assert results == cascade_results

    @pytest.mark.asyncio
    async def test_route_and_execute_with_explicit_providers(self):
        """Test routing with explicit providers."""
        # Create router
        router = UnifiedRouter(
            providers=self.providers,
            timeout_config=self.timeout_config,
        )

        # Mock select_providers to return a fixed decision with different providers
        router.select_providers = mock.MagicMock()
        router.select_providers.return_value = RoutingDecision(
            query_id="test",
            selected_providers=["perplexity", "exa", "tavily"],
            provider_scores=[],
            score_mode="avg",
            confidence=0.8,
            explanation="Test",
            metadata={},
        )

        # Mock the execution strategy
        parallel_strategy = mock.MagicMock(spec=ExecutionStrategy)
        parallel_strategy.execute.return_value = {}
        router._strategies["parallel"] = parallel_strategy

        # Create query with explicit providers
        query = SearchQuery(
            query="test query",
            providers=["firecrawl", "linkup"],
        )

        # Execute
        await router.route_and_execute(query, self.features)

        # Verify the correct providers were used
        _, kwargs = parallel_strategy.execute.call_args
        assert kwargs["selected_providers"] == ["firecrawl", "linkup"]

    @pytest.mark.asyncio
    async def test_route_and_execute_with_budget(self):
        """Test routing with budget from query."""
        # Create router
        router = UnifiedRouter(
            providers=self.providers,
            timeout_config=self.timeout_config,
        )

        # Mock select_providers
        router.select_providers = mock.MagicMock()

        # Create query with budget
        budget = Decimal("0.05")
        query = SearchQuery(
            query="test query",
            budget=float(budget),
        )

        # Execute
        await router.route_and_execute(query, self.features)

        # Verify budget was passed to select_providers
        router.select_providers.assert_called_once()
        _, kwargs = router.select_providers.call_args
        assert kwargs["budget"] == float(budget)

    @pytest.mark.asyncio
    async def test_combined_parameters(self):
        """Test routing with combined parameters."""
        # Create router
        router = UnifiedRouter(
            providers=self.providers,
            timeout_config=self.timeout_config,
        )

        # Mock hint parser
        hint_parser = mock.MagicMock(spec=RoutingHintParser)
        hint_parser.parse_hints.return_value = {
            "preferred_providers": ["tavily", "linkup"],
            "strategy": "cascade",
        }

        # Create query with multiple routing parameters
        query = SearchQuery(
            query="test query",
            providers=["perplexity", "exa"],  # Should override hints
            routing_strategy="parallel",  # Should override hints
            routing_hints="prioritize recent news",
            budget=0.05,
        )

        # Mock select_providers
        router.select_providers = mock.MagicMock()
        router.select_providers.return_value = RoutingDecision(
            query_id="test",
            selected_providers=[],
            provider_scores=[],
            score_mode="avg",
            confidence=0.8,
            explanation="Test",
            metadata={},
        )

        # Mock strategy
        parallel_strategy = mock.MagicMock(spec=ExecutionStrategy)
        parallel_strategy.execute.return_value = {}
        router._strategies["parallel"] = parallel_strategy

        # Execute with patched hint parser
        with mock.patch(
            "mcp_search_hub.query_routing.unified_router.RoutingHintParser",
            return_value=hint_parser,
        ):
            await router.route_and_execute(query, self.features)

        # Verify hint parser was called
        hint_parser.parse_hints.assert_called_once()

        # Verify explicit parameters were used (overriding hints)
        _, kwargs = parallel_strategy.execute.call_args
        assert kwargs["selected_providers"] == ["perplexity", "exa"]
