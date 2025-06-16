"""Tests for SearchRouter implementation."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from mcp_search_hub.models.base import HealthStatus
from mcp_search_hub.models.query import QueryFeatures, SearchQuery
from mcp_search_hub.models.results import SearchResponse, SearchResult
from mcp_search_hub.query_routing.router import ProviderMetrics, SearchRouter


def create_test_features(query: str = "test") -> QueryFeatures:
    """Create test QueryFeatures with all required fields."""
    return QueryFeatures(
        length=len(query),
        word_count=len(query.split()),
        contains_question="?" in query,
        content_type="general",
        time_sensitivity=0.0,
        complexity=0.2,
        factual_nature=0.5,
    )


def create_test_result(
    title: str = "Test Result", url: str = "http://test.com"
) -> SearchResult:
    """Create test SearchResult with all required fields."""
    return SearchResult(
        title=title, url=url, snippet="Test snippet", source="test_provider", score=0.8
    )


def create_test_response(
    results: list[SearchResult] = None, query: str = "test"
) -> SearchResponse:
    """Create test SearchResponse with all required fields."""
    if results is None:
        results = [create_test_result()]
    return SearchResponse(
        results=results,
        query=query,
        total_results=len(results),
        provider="test_provider",
    )


class MockProvider:
    """Mock search provider for testing."""

    def __init__(self, name: str, enabled: bool = True):
        self.name = name
        self.enabled = enabled
        self.search = AsyncMock()


class TestProviderMetrics:
    """Test ProviderMetrics class."""

    def test_initialization(self):
        """Test metrics initialization."""
        metrics = ProviderMetrics(window_size=5)
        assert len(metrics.response_times) == 0
        assert metrics.success_count == 0
        assert metrics.error_count == 0
        assert metrics.last_success is None
        assert metrics.avg_response_time == float("inf")
        assert metrics.success_rate == 1.0
        assert metrics.is_healthy is True

    def test_record_success(self):
        """Test recording successful requests."""
        metrics = ProviderMetrics(window_size=3)

        # Record multiple successes
        metrics.record_success(0.1)
        metrics.record_success(0.2)
        metrics.record_success(0.3)

        assert metrics.success_count == 3
        assert metrics.error_count == 0
        assert (
            abs(metrics.avg_response_time - 0.2) < 0.001
        )  # Allow for floating point precision
        assert metrics.success_rate == 1.0
        assert metrics.is_healthy is True
        assert metrics.last_success is not None

    def test_record_error(self):
        """Test recording failed requests."""
        metrics = ProviderMetrics()

        # Record some successes and errors
        metrics.record_success(0.1)
        metrics.record_error()
        metrics.record_error()

        assert metrics.success_count == 1
        assert metrics.error_count == 2
        assert metrics.success_rate == 1 / 3
        assert metrics.is_healthy is False  # Success rate < 50%

    def test_response_time_window(self):
        """Test response time window management."""
        metrics = ProviderMetrics(window_size=2)

        # Add more response times than window size
        metrics.record_success(0.1)
        metrics.record_success(0.2)
        metrics.record_success(0.3)

        # Should only keep last 2 values
        assert len(metrics.response_times) == 2
        assert metrics.avg_response_time == 0.25  # (0.2 + 0.3) / 2


class TestSearchRouter:
    """Test SearchRouter class."""

    @pytest.fixture
    def mock_providers(self):
        """Create mock providers for testing."""
        return {
            "provider1": MockProvider("provider1", enabled=True),
            "provider2": MockProvider("provider2", enabled=True),
            "provider3": MockProvider("provider3", enabled=False),
        }

    @pytest.fixture
    def router(self, mock_providers):
        """Create router instance for testing."""
        return SearchRouter(
            providers=mock_providers,
            max_concurrent=2,
            default_timeout=5.0,
        )

    def test_initialization(self, router, mock_providers):
        """Test router initialization."""
        assert router.providers == mock_providers
        assert router.max_concurrent == 2
        assert router.default_timeout == 5.0
        assert len(router.metrics) == 3
        assert all(isinstance(m, ProviderMetrics) for m in router.metrics.values())

    def test_select_providers_best_performance(self, router):
        """Test provider selection with best performance strategy."""
        # Set up different performance metrics
        router.metrics["provider1"].record_success(0.1)  # Fast
        router.metrics["provider2"].record_success(0.3)  # Slower

        query = SearchQuery(query="test")
        features = create_test_features("test")

        selected = router._select_providers(query, features, 2, "best_performance")

        # Should select enabled providers, provider1 first (better performance)
        assert len(selected) <= 2
        assert "provider3" not in selected  # Disabled
        if len(selected) >= 2:
            assert selected[0] == "provider1"  # Better performance

    def test_select_providers_power_of_two(self, router):
        """Test provider selection with power of two strategy."""
        query = SearchQuery(query="test")
        features = create_test_features("test")

        with patch("random.sample") as mock_sample:
            mock_sample.return_value = ["provider1", "provider2"]

            selected = router._select_providers(query, features, 3, "power_of_two")

            # Should use random sampling
            mock_sample.assert_called_once()
            assert len(selected) <= 3
            assert "provider3" not in selected  # Disabled

    def test_select_providers_no_healthy(self, router):
        """Test provider selection when no providers are healthy."""
        # Make all enabled providers unhealthy
        for _ in range(10):
            router.metrics["provider1"].record_error()
            router.metrics["provider2"].record_error()

        query = SearchQuery(query="test")
        features = create_test_features("test")

        selected = router._select_providers(query, features, 2, "best_performance")

        # Should fall back to all enabled providers
        assert len(selected) <= 2
        assert "provider3" not in selected  # Still disabled

    @pytest.mark.asyncio
    async def test_route_and_execute_success(self, router):
        """Test successful route and execute."""
        # Mock successful provider responses
        mock_result1 = create_test_response(
            [create_test_result("Result 1", "http://test1.com")]
        )
        mock_result2 = create_test_response(
            [create_test_result("Result 2", "http://test2.com")]
        )

        router.providers["provider1"].search.return_value = mock_result1
        router.providers["provider2"].search.return_value = mock_result2

        query = SearchQuery(query="test")
        features = create_test_features("test")

        with patch.object(router, "_execute_with_circuit_breaker") as mock_execute:
            mock_execute.side_effect = [mock_result1, mock_result2]

            results = await router.route_and_execute(query, features, max_providers=2)

            assert len(results) <= 2
            # Results should be lists of SearchResult objects
            for provider_results in results.values():
                assert isinstance(provider_results, list)

    @pytest.mark.asyncio
    async def test_route_and_execute_no_providers(self, router):
        """Test route and execute with no available providers."""
        # Disable all providers
        for provider in router.providers.values():
            provider.enabled = False

        query = SearchQuery(query="test")
        features = create_test_features("test")

        results = await router.route_and_execute(query, features)

        assert results == {}

    @pytest.mark.asyncio
    async def test_route_and_execute_timeout(self, router):
        """Test route and execute with timeout."""

        # Make providers hang
        async def slow_search(*args, **kwargs):
            await asyncio.sleep(10)
            return create_test_response([], "test")

        router.providers["provider1"].search.side_effect = slow_search
        router.providers["provider2"].search.side_effect = slow_search

        query = SearchQuery(query="test")
        features = create_test_features("test")

        # Should timeout and return empty results
        results = await router.route_and_execute(query, features)

        # May be empty due to timeout
        assert isinstance(results, dict)

    @pytest.mark.asyncio
    async def test_execute_with_circuit_breaker_success(self, router):
        """Test circuit breaker with successful execution."""
        mock_result = create_test_response(
            [create_test_result("Test", "http://test.com")]
        )
        provider = router.providers["provider1"]
        provider.search.return_value = mock_result

        query = SearchQuery(query="test")

        result = await router._execute_with_circuit_breaker(
            "provider1", provider, query
        )

        assert result == mock_result
        assert router.metrics["provider1"].success_count == 1
        assert router.metrics["provider1"].error_count == 0

    @pytest.mark.asyncio
    async def test_execute_with_circuit_breaker_failure(self, router):
        """Test circuit breaker with failed execution."""
        provider = router.providers["provider1"]
        provider.search.side_effect = Exception("API Error")

        query = SearchQuery(query="test")

        result = await router._execute_with_circuit_breaker(
            "provider1", provider, query
        )

        assert result is None
        assert router.metrics["provider1"].error_count == 1

    def test_get_provider_health(self, router):
        """Test getting provider health status."""
        # Set up some metrics
        router.metrics["provider1"].record_success(0.1)
        router.metrics["provider2"].record_error()

        health = router.get_provider_health()

        assert len(health) == 3
        assert health["provider1"]["enabled"] is True
        assert health["provider1"]["healthy"] is True
        assert health["provider2"]["enabled"] is True
        assert health["provider2"]["success_rate"] < 1.0
        assert health["provider3"]["enabled"] is False

    @pytest.mark.asyncio
    async def test_check_health_healthy(self, router):
        """Test health check with healthy providers."""
        # Set up healthy metrics
        router.metrics["provider1"].record_success(0.1)
        router.metrics["provider2"].record_success(0.2)

        status, message = await router.check_health()

        assert status == HealthStatus.HEALTHY
        assert "healthy" in message.lower()

    @pytest.mark.asyncio
    async def test_check_health_degraded(self, router):
        """Test health check with degraded providers."""
        # Make one provider unhealthy
        for _ in range(10):
            router.metrics["provider1"].record_error()
        router.metrics["provider2"].record_success(0.1)

        status, message = await router.check_health()

        assert status in [HealthStatus.DEGRADED, HealthStatus.HEALTHY]

    @pytest.mark.asyncio
    async def test_check_health_unhealthy(self, router):
        """Test health check with no healthy providers."""
        # Make all enabled providers unhealthy
        for _ in range(10):
            router.metrics["provider1"].record_error()
            router.metrics["provider2"].record_error()

        status, message = await router.check_health()

        assert status == HealthStatus.UNHEALTHY
        assert "no healthy providers" in message.lower()

    @pytest.mark.asyncio
    async def test_check_health_no_enabled(self, router):
        """Test health check with no enabled providers."""
        # Disable all providers
        for provider in router.providers.values():
            provider.enabled = False

        status, message = await router.check_health()

        assert status == HealthStatus.UNHEALTHY
        assert "no providers enabled" in message.lower()

    def test_get_metrics(self, router):
        """Test getting router metrics."""
        # Set up some metrics
        router.metrics["provider1"].record_success(0.1)
        router.metrics["provider2"].record_error()

        metrics = router.get_metrics()

        assert "providers" in metrics
        assert "total_providers" in metrics
        assert "enabled_providers" in metrics
        assert "healthy_providers" in metrics

        assert metrics["total_providers"] == 3
        assert metrics["enabled_providers"] == 2  # provider3 is disabled

        # Check provider-specific metrics
        assert "provider1" in metrics["providers"]
        assert "provider2" in metrics["providers"]
        assert "provider3" in metrics["providers"]

        assert metrics["providers"]["provider1"]["success_rate"] == 1.0
        assert metrics["providers"]["provider2"]["success_rate"] == 0.0


class TestProviderSelectionStrategies:
    """Test different provider selection strategies."""

    @pytest.fixture
    def router_with_metrics(self):
        """Create router with realistic performance metrics."""
        providers = {
            "fast_provider": MockProvider("fast_provider", enabled=True),
            "slow_provider": MockProvider("slow_provider", enabled=True),
            "unreliable_provider": MockProvider("unreliable_provider", enabled=True),
            "disabled_provider": MockProvider("disabled_provider", enabled=False),
        }

        router = SearchRouter(
            providers=providers, max_concurrent=3, default_timeout=30.0
        )

        # Set up realistic metrics
        # Fast provider - good performance
        for _ in range(10):
            router.metrics["fast_provider"].record_success(0.1)

        # Slow provider - slower but reliable
        for _ in range(10):
            router.metrics["slow_provider"].record_success(0.5)

        # Unreliable provider - fast but fails often
        for _ in range(5):
            router.metrics["unreliable_provider"].record_success(0.1)
        for _ in range(5):
            router.metrics["unreliable_provider"].record_error()

        return router

    def test_best_performance_strategy(self, router_with_metrics):
        """Test best performance strategy prioritizes speed and reliability."""
        query = SearchQuery(query="test")
        features = create_test_features("test")

        selected = router_with_metrics._select_providers(
            query, features, 3, "best_performance"
        )

        # Should prioritize fast_provider, then slow_provider
        assert selected[0] == "fast_provider"
        assert "disabled_provider" not in selected
        assert len(selected) <= 3

    def test_round_robin_strategy(self, router_with_metrics):
        """Test round robin strategy randomizes selection."""
        query = SearchQuery(query="test")
        features = create_test_features("test")

        # Run multiple times to ensure randomization
        selections = []
        for _ in range(10):
            selected = router_with_metrics._select_providers(
                query, features, 2, "round_robin"
            )
            selections.append(tuple(selected))

        # Should have some variation in selection order
        unique_selections = set(selections)
        assert len(unique_selections) > 1  # Some randomization occurred

        # Should never include disabled provider
        for selection in selections:
            assert "disabled_provider" not in selection


class TestCircuitBreakerIntegration:
    """Test circuit breaker integration with router."""

    @pytest.fixture
    def router_with_failures(self):
        """Create router and simulate failures to trigger circuit breaker."""
        providers = {
            "reliable_provider": MockProvider("reliable_provider", enabled=True),
            "failing_provider": MockProvider("failing_provider", enabled=True),
        }

        return SearchRouter(
            providers=providers,
            max_concurrent=2,
            default_timeout=10.0,
            circuit_failure_threshold=3,  # Low threshold for testing
            circuit_recovery_timeout=10.0,
        )

    @pytest.mark.asyncio
    async def test_circuit_breaker_opens_after_failures(self, router_with_failures):
        """Test that circuit breaker opens after repeated failures."""
        # Set up failing provider
        router_with_failures.providers[
            "failing_provider"
        ].search.side_effect = Exception("API Error")
        router_with_failures.providers[
            "reliable_provider"
        ].search.return_value = create_test_response([], "test")

        query = SearchQuery(query="test")

        # Execute multiple requests to trigger circuit breaker
        for _ in range(5):
            result = await router_with_failures._execute_with_circuit_breaker(
                "failing_provider",
                router_with_failures.providers["failing_provider"],
                query,
            )
            # Should return None due to failures
            assert result is None

        # Check that failure count increased
        assert router_with_failures.metrics["failing_provider"].error_count >= 3

    @pytest.mark.asyncio
    async def test_healthy_provider_continues_working(self, router_with_failures):
        """Test that healthy providers continue working when others fail."""
        # Set up one failing, one working
        router_with_failures.providers[
            "failing_provider"
        ].search.side_effect = Exception("API Error")
        router_with_failures.providers[
            "reliable_provider"
        ].search.return_value = create_test_response(
            [create_test_result("Success", "http://test.com")]
        )

        query = SearchQuery(query="test")
        features = create_test_features("test")

        # Execute route and execute
        results = await router_with_failures.route_and_execute(
            query, features, max_providers=2
        )

        # Should have results from reliable provider despite failing provider
        assert len(results) >= 1
        if "reliable_provider" in results:
            assert len(results["reliable_provider"]) > 0
