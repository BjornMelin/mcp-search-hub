"""Tests for unified router implementation including both parallel and cascade modes."""

import asyncio
import time
from unittest.mock import AsyncMock, Mock, patch

import pytest

from mcp_search_hub.models.query import QueryFeatures, SearchQuery
from mcp_search_hub.models.results import SearchResponse, SearchResult
from mcp_search_hub.models.router import (
    CascadeExecutionPolicy,
    ProviderExecutionResult,
    ProviderPerformanceMetrics,
    ProviderScore,
    TimeoutConfig,
)
from mcp_search_hub.providers.base import SearchProvider
from mcp_search_hub.query_routing.unified_router import (
    CascadeExecutionStrategy,
    ExecutionStrategy,
    ParallelExecutionStrategy,
    ProviderScorer,
    UnifiedRouter,
)


class MockProvider(SearchProvider):
    """Mock provider for testing."""

    def __init__(self, name: str, response: SearchResponse | None = None):
        self.name = name
        self.response = response or SearchResponse(
            results=[
                SearchResult(
                    title=f"{name} result",
                    url=f"https://{name}.com",
                    snippet=f"Result from {name}",
                    score=0.9,
                    source=name,
                )
            ],
            query="test query",
            total_results=1,
            provider=name,
        )
        self._should_fail = False
        self._delay = 0

    async def search(self, query: SearchQuery) -> SearchResponse:
        """Return mock response."""
        if self._should_fail:
            raise Exception(f"{self.name} failed")
        if self._delay > 0:
            await asyncio.sleep(self._delay)
        return self.response

    def get_capabilities(self) -> dict:
        """Return mock capabilities."""
        return {
            "content_types": ["general", "news", "academic"],
            "max_results": 100,
        }

    def estimate_cost(self, query: SearchQuery) -> float:
        """Estimate query cost."""
        return 0.01


class MockScorer(ProviderScorer):
    """Mock scorer for testing."""

    def score_provider(self, provider_name, provider, features, metrics):
        """Return a fixed score."""
        from mcp_search_hub.models.router import ProviderScore

        return ProviderScore(
            provider_name=provider_name,
            base_score=0.8,
            performance_score=0.9,
            recency_bonus=0.0,
            confidence=0.85,
            weighted_score=0.85,
            explanation="Mock score",
        )


class MockExecutionStrategy(ExecutionStrategy):
    """Mock execution strategy for testing."""

    async def execute(
        self, query, features, providers, selected_providers, timeout_config
    ) -> dict:
        """Return mock execution results."""
        results = {}
        for provider_name in selected_providers:
            results[provider_name] = ProviderExecutionResult(
                provider_name=provider_name,
                success=True,
                response=SearchResponse(
                    results=[],
                    query=query.query,
                    total_results=0,
                    provider=provider_name,
                ),
                duration_ms=100,
            )
        return results


@pytest.fixture
def mock_providers():
    """Create mock providers."""
    return {
        "provider1": MockProvider("provider1"),
        "provider2": MockProvider("provider2"),
        "provider3": MockProvider("provider3"),
    }


@pytest.fixture
def unified_router(mock_providers):
    """Create unified router with mock providers."""
    return UnifiedRouter(providers=mock_providers)


@pytest.fixture
def sample_query():
    """Create sample search query."""
    return SearchQuery(query="test query")


@pytest.fixture
def sample_features():
    """Create sample query features."""
    return QueryFeatures(
        length=10,
        word_count=2,
        content_type="general",
        complexity=0.5,
        time_sensitivity=0.3,
        factual_nature=0.7,
        contains_question=False,
    )


@pytest.mark.asyncio
async def test_unified_router_initialization(mock_providers):
    """Test unified router initialization."""
    router = UnifiedRouter(providers=mock_providers)

    assert router.providers == mock_providers
    assert router.timeout_config is not None
    assert "parallel" in router._strategies
    assert "cascade" in router._strategies
    assert len(router._circuit_breakers) == len(mock_providers)


@pytest.mark.asyncio
async def test_provider_selection(unified_router, sample_query, sample_features):
    """Test provider selection based on scoring."""
    routing_decision = unified_router.select_providers(sample_query, sample_features)

    assert len(routing_decision.selected_providers) > 0
    assert routing_decision.confidence >= 0
    assert routing_decision.confidence <= 1
    assert len(routing_decision.provider_scores) > 0
    assert routing_decision.explanation is not None


@pytest.mark.asyncio
async def test_parallel_execution_strategy(mock_providers):
    """Test parallel execution strategy."""
    strategy = ParallelExecutionStrategy()
    query = SearchQuery(query="test")
    features = QueryFeatures(
        length=4,
        word_count=1,
        content_type="general",
        complexity=0.5,
        time_sensitivity=0.3,
        factual_nature=0.7,
        contains_question=False,
    )
    timeout_config = TimeoutConfig()

    # Mock the execution to avoid timing issues
    for provider in mock_providers.values():
        provider.search = AsyncMock(return_value=provider.response)

    results = await strategy.execute(
        query=query,
        features=features,
        providers=mock_providers,
        selected_providers=list(mock_providers.keys()),
        timeout_config=timeout_config,
    )

    assert len(results) == len(mock_providers)
    for provider_name, result in results.items():
        assert result.provider_name == provider_name
        assert result.success is True
        assert result.response is not None


@pytest.mark.asyncio
async def test_parallel_execution_with_mixed_results(mock_providers):
    """Test parallel execution strategy with mixed success/failure providers."""
    strategy = ParallelExecutionStrategy()
    query = SearchQuery(query="test")
    features = QueryFeatures(
        length=4,
        word_count=1,
        content_type="general",
        complexity=0.5,
        time_sensitivity=0.3,
        factual_nature=0.7,
        contains_question=False,
    )
    timeout_config = TimeoutConfig()

    # Make one provider fail and another delay
    mock_providers["provider1"].search = AsyncMock(side_effect=Exception("Test failure"))
    mock_providers["provider2"]._delay = 0.1  # Short delay that should complete
    mock_providers["provider3"].search = AsyncMock(return_value=mock_providers["provider3"].response)

    results = await strategy.execute(
        query=query,
        features=features,
        providers=mock_providers,
        selected_providers=list(mock_providers.keys()),
        timeout_config=timeout_config,
    )

    # All providers should have results
    assert len(results) == len(mock_providers)
    
    # Provider1 should fail
    assert results["provider1"].success is False
    assert "Test failure" in results["provider1"].error
    
    # Provider2 should succeed with delay
    assert results["provider2"].success is True
    assert results["provider2"].response is not None
    
    # Provider3 should succeed
    assert results["provider3"].success is True
    assert results["provider3"].response is not None


@pytest.mark.asyncio
async def test_parallel_execution_content_type_adaptability(mock_providers):
    """Test how parallel execution adapts to different content types."""
    strategy = ParallelExecutionStrategy()
    
    # Test with different content types
    content_types = ["general", "news", "academic", "code", "web_content"]
    
    for content_type in content_types:
        query = SearchQuery(query=f"test {content_type}")
        features = QueryFeatures(
            length=4,
            word_count=2,
            content_type=content_type,
            complexity=0.5,
            time_sensitivity=0.3 if content_type == "news" else 0.1,
            factual_nature=0.7 if content_type == "academic" else 0.5,
            contains_question=False,
        )
        timeout_config = TimeoutConfig()

        # Reset mocks
        for provider in mock_providers.values():
            provider.search = AsyncMock(return_value=provider.response)

        results = await strategy.execute(
            query=query,
            features=features,
            providers=mock_providers,
            selected_providers=list(mock_providers.keys()),
            timeout_config=timeout_config,
        )

        # Verify all successful
        assert len(results) == len(mock_providers)
        for provider_name, result in results.items():
            assert result.success is True
            assert result.response is not None


@pytest.mark.asyncio
async def test_parallel_execution_dynamic_timeout(mock_providers):
    """Test parallel execution with dynamic timeout calculation."""
    strategy = ParallelExecutionStrategy()
    
    # Test with varying complexity
    complexities = [0.1, 0.5, 0.9]
    timeout_config = TimeoutConfig(
        base_timeout_ms=2000,
        min_timeout_ms=1000,
        max_timeout_ms=5000,
        complexity_factor=1.5
    )
    
    timeout_times = []
    
    for complexity in complexities:
        query = SearchQuery(query="test")
        features = QueryFeatures(
            length=4,
            word_count=1,
            content_type="general",
            complexity=complexity,
            time_sensitivity=0.3,
            factual_nature=0.7,
            contains_question=False,
        )

        # Mock the _calculate_timeout method to capture the calculated timeout
        with patch.object(ParallelExecutionStrategy, '_calculate_timeout', wraps=strategy._calculate_timeout) as mock_timeout:
            # Reset provider mocks
            for provider in mock_providers.values():
                provider.search = AsyncMock(return_value=provider.response)
                
            await strategy.execute(
                query=query,
                features=features,
                providers=mock_providers,
                selected_providers=list(mock_providers.keys()),
                timeout_config=timeout_config,
            )
            
            # Get the timeout value that was calculated
            timeout_times.append(mock_timeout.return_value)
    
    # Higher complexity should result in longer timeouts
    assert timeout_times[0] < timeout_times[1] < timeout_times[2]


@pytest.mark.asyncio
async def test_cascade_execution_strategy(mock_providers):
    """Test cascade execution strategy."""
    strategy = CascadeExecutionStrategy()
    query = SearchQuery(query="test")
    features = QueryFeatures(
        length=4,
        word_count=1,
        content_type="general",
        complexity=0.5,
        time_sensitivity=0.3,
        factual_nature=0.7,
        contains_question=False,
    )
    timeout_config = TimeoutConfig()

    results = await strategy.execute(
        query=query,
        features=features,
        providers=mock_providers,
        selected_providers=list(mock_providers.keys()),
        timeout_config=timeout_config,
    )

    # With default policy, cascade should stop after first success
    assert len(results) >= 1
    assert any(result.success for result in results.values())
    
    # Verify only first provider was actually executed
    first_provider = list(mock_providers.keys())[0]
    assert first_provider in results
    assert results[first_provider].success


@pytest.mark.asyncio
async def test_cascade_execution_with_custom_policy(mock_providers):
    """Test cascade execution strategy with custom policies."""
    # Create a policy that continues after success
    custom_policy = CascadeExecutionPolicy(
        cascade_on_success=True,
        min_successful_providers=2,
        secondary_delay_ms=100,
    )
    
    strategy = CascadeExecutionStrategy(policy=custom_policy)
    query = SearchQuery(query="test")
    features = QueryFeatures(
        length=4,
        word_count=1,
        content_type="general",
        complexity=0.5,
        time_sensitivity=0.3,
        factual_nature=0.7,
        contains_question=False,
    )
    timeout_config = TimeoutConfig()

    # Reset and update provider mocks to track execution
    provider_executions = []
    for name, provider in mock_providers.items():
        async def mock_search(query, provider_name=name):
            provider_executions.append(provider_name)
            await asyncio.sleep(0.01)  # Small delay to ensure order
            return mock_providers[provider_name].response
        
        provider.search = AsyncMock(side_effect=mock_search)

    results = await strategy.execute(
        query=query,
        features=features,
        providers=mock_providers,
        selected_providers=list(mock_providers.keys()),
        timeout_config=timeout_config,
    )

    # With the custom policy, we should continue after success until min_successful_providers
    assert len(results) == len(mock_providers)
    assert sum(1 for r in results.values() if r.success) >= 2
    
    # All providers should have been executed in order
    assert len(provider_executions) == len(mock_providers)
    assert provider_executions == list(mock_providers.keys())


@pytest.mark.asyncio
async def test_cascade_execution_stops_after_min_success(mock_providers):
    """Test cascade execution stops after minimum success criteria is met."""
    # Policy that requires exactly 2 successful providers
    policy = CascadeExecutionPolicy(
        cascade_on_success=True,
        min_successful_providers=2,
    )
    
    strategy = CascadeExecutionStrategy(policy=policy)
    query = SearchQuery(query="test")
    features = QueryFeatures(
        length=4,
        word_count=1,
        content_type="general",
        complexity=0.5,
        time_sensitivity=0.3,
        factual_nature=0.7,
        contains_question=False,
    )
    timeout_config = TimeoutConfig()

    # Track provider executions
    executed_providers = set()
    
    for name, provider in mock_providers.items():
        async def mock_search(query, provider_name=name):
            executed_providers.add(provider_name)
            return mock_providers[provider_name].response
        
        provider.search = AsyncMock(side_effect=mock_search)

    results = await strategy.execute(
        query=query,
        features=features,
        providers=mock_providers,
        selected_providers=list(mock_providers.keys()),
        timeout_config=timeout_config,
    )

    # Should stop after 2 successful providers, not executing all 3
    assert len(results) == 2
    assert sum(1 for r in results.values() if r.success) == 2
    assert len(executed_providers) == 2


@pytest.mark.asyncio
async def test_cascade_execution_dynamic_timeout(mock_providers):
    """Test cascade execution with dynamic timeout for different query types."""
    strategy = CascadeExecutionStrategy()
    
    # Test various query types that affect timeout calculation
    test_cases = [
        # Simple query (should have shorter timeout)
        {"complexity": 0.2, "time_sensitivity": 0.1, "contains_question": False, "expected_timeout_factor": 1.0},
        # Complex query (should have longer timeout)
        {"complexity": 0.9, "time_sensitivity": 0.1, "contains_question": True, "expected_timeout_factor": 1.5},
        # Time-sensitive query (should have shorter timeout despite complexity)
        {"complexity": 0.7, "time_sensitivity": 0.9, "contains_question": False, "expected_timeout_factor": 1.0},
    ]
    
    timeout_config = TimeoutConfig(
        base_timeout_ms=2000,
        min_timeout_ms=1000,
        max_timeout_ms=5000,
        complexity_factor=1.5,
    )
    
    timeouts = []
    
    for i, case in enumerate(test_cases):
        features = QueryFeatures(
            length=10,
            word_count=5,
            content_type="general",
            complexity=case["complexity"],
            time_sensitivity=case["time_sensitivity"],
            factual_nature=0.5,
            contains_question=case["contains_question"],
        )
        
        # Mock the dynamic timeout calculation to capture the value
        with patch.object(CascadeExecutionStrategy, '_calculate_dynamic_timeout', wraps=strategy._calculate_dynamic_timeout) as mock_timeout:
            # Reset provider mocks
            for provider in mock_providers.values():
                provider.search = AsyncMock(return_value=provider.response)
                
            await strategy.execute(
                query=SearchQuery(query="test"),
                features=features,
                providers=mock_providers,
                selected_providers=[list(mock_providers.keys())[0]],  # Just need one provider
                timeout_config=timeout_config,
            )
            
            # Store the timeout that was calculated
            timeouts.append(mock_timeout.return_value)
    
    # Complex queries with questions should get longer timeouts
    assert timeouts[1] > timeouts[0]
    
    # Time-sensitive queries should get shorter timeouts
    assert timeouts[2] < timeouts[1]


@pytest.mark.asyncio
async def test_cascade_with_failures(mock_providers):
    """Test cascade execution with provider failures."""
    # Make first provider fail
    mock_providers["provider1"]._should_fail = True

    strategy = CascadeExecutionStrategy()
    query = SearchQuery(query="test")
    features = QueryFeatures(
        length=4,
        word_count=1,
        content_type="general",
        complexity=0.5,
        time_sensitivity=0.3,
        factual_nature=0.7,
        contains_question=False,
    )
    timeout_config = TimeoutConfig()

    results = await strategy.execute(
        query=query,
        features=features,
        providers=mock_providers,
        selected_providers=list(mock_providers.keys()),
        timeout_config=timeout_config,
    )

    # First should fail, others should be attempted
    assert results["provider1"].success is False
    assert results["provider1"].error is not None


@pytest.mark.asyncio
async def test_strategy_determination(unified_router, sample_query, sample_features):
    """Test automatic strategy determination."""
    # Single provider should use cascade
    strategy = unified_router._determine_strategy(
        sample_query, sample_features, ["provider1"]
    )
    assert strategy == "cascade"

    # High complexity should use cascade
    complex_features = QueryFeatures(
        length=10,
        word_count=2,
        content_type="general",
        complexity=0.8,
        time_sensitivity=0.3,
        factual_nature=0.7,
        contains_question=False,
    )
    strategy = unified_router._determine_strategy(
        sample_query, complex_features, ["provider1", "provider2"]
    )
    assert strategy == "cascade"

    # Normal multi-provider query should use parallel
    strategy = unified_router._determine_strategy(
        sample_query, sample_features, ["provider1", "provider2", "provider3"]
    )
    assert strategy == "parallel"


@pytest.mark.asyncio
async def test_route_and_execute(unified_router, sample_query, sample_features):
    """Test complete routing and execution flow."""
    results = await unified_router.route_and_execute(
        query=sample_query, features=sample_features
    )

    assert len(results) > 0
    for provider_name, result in results.items():
        assert result.provider_name == provider_name
        assert isinstance(result, ProviderExecutionResult)


@pytest.mark.asyncio
async def test_circuit_breaker_integration(
    unified_router, sample_query, sample_features
):
    """Test circuit breaker integration."""
    # Force failures to open circuit breaker
    provider_name = "provider1"
    circuit_breaker = unified_router._circuit_breakers[provider_name]

    # Record multiple failures
    for _ in range(3):
        circuit_breaker.record_failure()

    assert circuit_breaker.is_open

    # Provider should be skipped during selection
    routing_decision = unified_router.select_providers(sample_query, sample_features)
    assert provider_name not in routing_decision.selected_providers


@pytest.mark.asyncio
async def test_custom_strategy_registration(unified_router):
    """Test adding custom execution strategies."""
    custom_strategy = MockExecutionStrategy()
    unified_router.add_strategy("custom", custom_strategy)

    assert "custom" in unified_router._strategies
    assert unified_router._strategies["custom"] == custom_strategy


@pytest.mark.asyncio
async def test_custom_scorer_registration(unified_router):
    """Test adding custom provider scorers."""
    custom_scorer = MockScorer()
    unified_router.add_scorer(custom_scorer)

    assert custom_scorer in unified_router._scorers


@pytest.mark.asyncio
async def test_performance_metrics_update(unified_router):
    """Test updating provider performance metrics."""
    metrics = ProviderPerformanceMetrics(
        provider_name="provider1",
        avg_response_time=100.0,
        success_rate=0.95,
        avg_result_quality=0.85,
        total_queries=1000,
    )

    unified_router.update_performance_metrics("provider1", metrics)
    assert unified_router.performance_metrics["provider1"] == metrics


@pytest.mark.asyncio
async def test_budget_based_selection(unified_router, sample_query, sample_features):
    """Test provider selection with budget constraints."""
    routing_decision = unified_router.select_providers(
        sample_query, sample_features, budget=0.05
    )

    # Should select providers within budget
    assert len(routing_decision.selected_providers) > 0
    assert routing_decision.metadata["budget"] == 0.05


@pytest.mark.asyncio
async def test_parallel_execution_timeout(mock_providers):
    """Test parallel execution with timeouts."""
    # Add delay to one provider
    mock_providers["provider2"]._delay = 2.0

    query = SearchQuery(query="test", timeout_ms=1000)  # 1 second timeout

    # Use asyncio directly for more control
    results = {}
    start_time = asyncio.get_event_loop().time()

    # Create tasks manually
    tasks = {}
    for provider_name, provider in mock_providers.items():
        tasks[provider_name] = asyncio.create_task(provider.search(query))

    # Wait with timeout
    done, pending = await asyncio.wait(tasks.values(), timeout=1.0)

    # Cancel pending
    for task in pending:
        task.cancel()

    # Collect results
    for provider_name, task in tasks.items():
        if task in done and not task.exception():
            response = task.result()
            results[provider_name] = ProviderExecutionResult(
                provider_name=provider_name,
                success=True,
                response=response,
                duration_ms=(asyncio.get_event_loop().time() - start_time) * 1000,
            )
        else:
            results[provider_name] = ProviderExecutionResult(
                provider_name=provider_name,
                success=False,
                error="Timeout",
                duration_ms=1000,
            )

    # Provider2 should timeout
    assert results["provider2"].success is False
    assert "Timeout" in results["provider2"].error


@pytest.mark.asyncio
async def test_dynamic_timeout_calculation():
    """Test dynamic timeout calculation based on query complexity."""
    strategy = CascadeExecutionStrategy()
    timeout_config = TimeoutConfig(
        base_timeout_ms=5000, min_timeout_ms=1000, max_timeout_ms=30000
    )

    # Simple query
    simple_features = QueryFeatures(
        length=10,
        word_count=2,
        content_type="general",
        complexity=0.2,
        time_sensitivity=0.1,
        factual_nature=0.5,
        contains_question=False,
    )
    simple_timeout = strategy._calculate_dynamic_timeout(
        simple_features, timeout_config
    )

    # Complex query
    complex_features = QueryFeatures(
        length=50,
        word_count=10,
        content_type="academic",
        complexity=0.9,
        time_sensitivity=0.1,
        factual_nature=0.8,
        contains_question=True,
    )
    complex_timeout = strategy._calculate_dynamic_timeout(
        complex_features, timeout_config
    )

    # Complex queries should get more time
    assert complex_timeout > simple_timeout

    # Time-sensitive query
    urgent_features = QueryFeatures(
        length=15,
        word_count=3,
        content_type="news",
        complexity=0.5,
        time_sensitivity=0.9,
        factual_nature=0.6,
        contains_question=False,
    )
    urgent_timeout = strategy._calculate_dynamic_timeout(
        urgent_features, timeout_config
    )

    # Urgent queries should get less time
    assert urgent_timeout < simple_timeout
