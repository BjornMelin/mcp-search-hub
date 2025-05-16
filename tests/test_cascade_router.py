"""Tests for cascade router functionality."""

import asyncio
import time

import pytest

from mcp_search_hub.models.query import QueryFeatures, SearchQuery
from mcp_search_hub.models.results import SearchResponse, SearchResult
from mcp_search_hub.models.router import (
    CascadeExecutionPolicy,
    TimeoutConfig,
)
from mcp_search_hub.providers.base import SearchProvider
from mcp_search_hub.query_routing.cascade_router import CascadeRouter, CircuitBreaker


class MockProvider(SearchProvider):
    """Mock provider for testing."""

    def __init__(
        self,
        name: str,
        response: SearchResponse = None,
        error: Exception = None,
        delay: float = 0,
    ):
        self.name = name
        self.response = response or SearchResponse(
            results=[
                SearchResult(
                    title=f"Result from {name}",
                    url=f"https://example.com/{name}",
                    snippet=f"Test result from {name}",
                    source=name,
                    score=0.9,
                )
            ],
            query="test query",
            total_results=1,
            provider=name,
        )
        self.error = error
        self.delay = delay
        self.call_count = 0

    async def search(self, query: SearchQuery) -> SearchResponse:
        """Mock search implementation."""
        self.call_count += 1

        if self.delay > 0:
            await asyncio.sleep(self.delay)

        if self.error:
            raise self.error

        return self.response

    async def check_status(self):
        """Mock status check."""
        return "ok", "Provider is operational"

    def register_tools(self, mcp):
        """Mock tool registration."""

    def estimate_cost(self, query: SearchQuery) -> float:
        """Mock cost estimation."""
        return 0.01

    def get_capabilities(self):
        """Mock capabilities."""
        return {
            "content_types": ["general"],
            "features": ["basic_search"],
        }


class TestCascadeRouter:
    """Test cascade router functionality."""

    @pytest.fixture
    def timeout_config(self):
        """Create timeout configuration."""
        return TimeoutConfig(
            base_timeout_ms=1000,
            min_timeout_ms=500,
            max_timeout_ms=5000,
        )

    @pytest.fixture
    def execution_policy(self):
        """Create execution policy."""
        return CascadeExecutionPolicy(
            cascade_on_success=False,
            min_successful_providers=1,
            secondary_delay_ms=100,
            circuit_breaker_max_failures=2,
            circuit_breaker_reset_timeout=10.0,
        )

    @pytest.fixture
    def providers(self):
        """Create mock providers."""
        return {
            "primary": MockProvider("primary"),
            "secondary": MockProvider("secondary"),
            "tertiary": MockProvider("tertiary"),
        }

    @pytest.mark.asyncio
    async def test_cascade_primary_success(
        self, providers, timeout_config, execution_policy
    ):
        """Test cascade stops after primary provider succeeds."""
        router = CascadeRouter(providers, timeout_config, execution_policy)

        query = SearchQuery(query="test query")
        features = QueryFeatures(
            content_type="general",
            length=10,
            word_count=2,
            contains_question=False,
            time_sensitivity=0.5,
            complexity=0.5,
            factual_nature=0.5,
        )

        results = await router.execute_cascade(
            query, features, ["primary", "secondary"]
        )

        # Primary should succeed
        assert results["primary"].success
        assert results["primary"].response is not None
        assert results["primary"].is_primary

        # Secondary should not be called
        assert "secondary" not in results or not results["secondary"].success
        assert providers["secondary"].call_count == 0

    @pytest.mark.asyncio
    async def test_cascade_primary_failure_secondary_success(
        self, timeout_config, execution_policy
    ):
        """Test cascade falls back to secondary when primary fails."""
        providers = {
            "primary": MockProvider("primary", error=Exception("Primary failed")),
            "secondary": MockProvider("secondary"),
        }

        router = CascadeRouter(providers, timeout_config, execution_policy)

        query = SearchQuery(query="test query")
        features = QueryFeatures(
            content_type="general",
            length=10,
            word_count=2,
            contains_question=False,
            time_sensitivity=0.5,
            complexity=0.5,
            factual_nature=0.5,
        )

        results = await router.execute_cascade(
            query, features, ["primary", "secondary"]
        )

        # Primary should fail
        assert not results["primary"].success
        assert results["primary"].error == "Primary failed"
        assert results["primary"].is_primary

        # Secondary should succeed
        assert results["secondary"].success
        assert results["secondary"].response is not None
        assert not results["secondary"].is_primary

    @pytest.mark.asyncio
    async def test_cascade_with_timeout(self, timeout_config, execution_policy):
        """Test cascade handles timeouts correctly."""
        providers = {
            "primary": MockProvider("primary", delay=2.0),  # Will timeout
            "secondary": MockProvider("secondary"),
        }

        # Set short timeout
        timeout_config.base_timeout_ms = 500
        router = CascadeRouter(providers, timeout_config, execution_policy)

        query = SearchQuery(query="test query")
        features = QueryFeatures(
            content_type="general",
            length=10,
            word_count=2,
            contains_question=False,
            time_sensitivity=0.5,
            complexity=0.5,
            factual_nature=0.5,
        )

        results = await router.execute_cascade(
            query, features, ["primary", "secondary"]
        )

        # Primary should timeout
        assert not results["primary"].success
        assert results["primary"].error == "Timeout"

        # Secondary should succeed
        assert results["secondary"].success
        assert results["secondary"].response is not None

    @pytest.mark.asyncio
    async def test_circuit_breaker_opens_after_failures(self, timeout_config):
        """Test circuit breaker opens after repeated failures."""
        execution_policy = CascadeExecutionPolicy(
            circuit_breaker_max_failures=2,
            circuit_breaker_reset_timeout=10.0,
        )

        providers = {
            "primary": MockProvider("primary", error=Exception("Always fails")),
            "secondary": MockProvider("secondary"),
        }

        router = CascadeRouter(providers, timeout_config, execution_policy)

        query = SearchQuery(query="test query")
        features = QueryFeatures(
            content_type="general",
            length=10,
            word_count=2,
            contains_question=False,
            time_sensitivity=0.5,
            complexity=0.5,
            factual_nature=0.5,
        )

        # First two calls should attempt primary
        for _ in range(2):
            results = await router.execute_cascade(
                query, features, ["primary", "secondary"]
            )
            assert not results["primary"].success
            assert results["secondary"].success

        # Third call should skip primary due to circuit breaker
        results = await router.execute_cascade(
            query, features, ["primary", "secondary"]
        )
        assert results["primary"].skipped
        assert results["primary"].error == "Circuit breaker open"
        assert providers["primary"].call_count == 2  # Only called twice

    @pytest.mark.asyncio
    async def test_dynamic_timeout_calculation(self, providers, execution_policy):
        """Test dynamic timeout adjusts based on query complexity."""
        timeout_config = TimeoutConfig(
            base_timeout_ms=1000,
            min_timeout_ms=500,
            max_timeout_ms=5000,
            complexity_factor=0.5,
        )

        router = CascadeRouter(providers, timeout_config, execution_policy)

        # Simple query
        simple_features = QueryFeatures(
            content_type="general",
            length=10,
            word_count=2,
            contains_question=False,
            time_sensitivity=0.1,
            complexity=0.2,
            factual_nature=0.5,
        )

        simple_timeout = router._calculate_dynamic_timeout(simple_features)

        # Complex query
        complex_features = QueryFeatures(
            content_type="academic",
            length=50,
            word_count=10,
            contains_question=True,
            time_sensitivity=0.1,
            complexity=0.9,
            factual_nature=0.9,
        )

        complex_timeout = router._calculate_dynamic_timeout(complex_features)

        # Complex queries should have longer timeouts
        assert complex_timeout > simple_timeout

        # Question queries should have longer timeouts
        question_features = simple_features.model_copy()
        question_features.contains_question = True
        question_timeout = router._calculate_dynamic_timeout(question_features)
        assert question_timeout > simple_timeout

        # Time-sensitive queries should have shorter timeouts
        time_sensitive_features = simple_features.model_copy()
        time_sensitive_features.time_sensitivity = 0.9
        time_sensitive_timeout = router._calculate_dynamic_timeout(
            time_sensitive_features
        )
        assert time_sensitive_timeout < simple_timeout

    @pytest.mark.asyncio
    async def test_cascade_on_success_policy(self, providers, timeout_config):
        """Test cascade continues even after success when policy is set."""
        execution_policy = CascadeExecutionPolicy(
            cascade_on_success=True,
            min_successful_providers=2,
        )

        router = CascadeRouter(providers, timeout_config, execution_policy)

        query = SearchQuery(query="test query")
        features = QueryFeatures(
            content_type="general",
            length=10,
            word_count=2,
            contains_question=False,
            time_sensitivity=0.5,
            complexity=0.5,
            factual_nature=0.5,
        )

        results = await router.execute_cascade(
            query, features, ["primary", "secondary", "tertiary"]
        )

        # All providers should be called despite primary success
        assert results["primary"].success
        assert results["secondary"].success
        assert providers["primary"].call_count == 1
        assert providers["secondary"].call_count == 1

        # Should stop after minimum successful providers reached
        assert providers["tertiary"].call_count == 0

    @pytest.mark.asyncio
    async def test_secondary_delay(self, timeout_config):
        """Test secondary providers have execution delay."""
        execution_policy = CascadeExecutionPolicy(
            secondary_delay_ms=200,
        )

        providers = {
            "primary": MockProvider("primary", error=Exception("Fails immediately")),
            "secondary": MockProvider("secondary"),
        }

        router = CascadeRouter(providers, timeout_config, execution_policy)

        query = SearchQuery(query="test query")
        features = QueryFeatures(
            content_type="general",
            length=10,
            word_count=2,
            contains_question=False,
            time_sensitivity=0.5,
            complexity=0.5,
            factual_nature=0.5,
        )

        start_time = asyncio.get_event_loop().time()
        results = await router.execute_cascade(
            query, features, ["primary", "secondary"]
        )
        end_time = asyncio.get_event_loop().time()

        # Total time should include secondary delay
        assert (end_time - start_time) >= 0.2
        assert results["secondary"].success

    @pytest.mark.asyncio
    async def test_all_providers_fail(self, timeout_config, execution_policy):
        """Test behavior when all providers fail."""
        providers = {
            "primary": MockProvider("primary", error=Exception("Primary failed")),
            "secondary": MockProvider("secondary", error=Exception("Secondary failed")),
        }

        router = CascadeRouter(providers, timeout_config, execution_policy)

        query = SearchQuery(query="test query")
        features = QueryFeatures(
            content_type="general",
            length=10,
            word_count=2,
            contains_question=False,
            time_sensitivity=0.5,
            complexity=0.5,
            factual_nature=0.5,
        )

        results = await router.execute_cascade(
            query, features, ["primary", "secondary"]
        )

        # All providers should fail
        assert not results["primary"].success
        assert not results["secondary"].success
        assert results["primary"].error == "Primary failed"
        assert results["secondary"].error == "Secondary failed"


class TestCircuitBreaker:
    """Test circuit breaker functionality."""

    def test_circuit_breaker_initial_state(self):
        """Test circuit breaker starts in closed state."""
        breaker = CircuitBreaker(max_failures=3, reset_timeout=10.0)

        assert not breaker.is_open
        assert breaker.state == "closed"
        assert breaker.failure_count == 0

    def test_circuit_breaker_opens_after_max_failures(self):
        """Test circuit breaker opens after max failures reached."""
        breaker = CircuitBreaker(max_failures=3, reset_timeout=10.0)

        # Record failures
        for _ in range(3):
            breaker.record_failure()

        assert breaker.is_open
        assert breaker.state == "open"
        assert breaker.failure_count == 3

    def test_circuit_breaker_half_open_after_timeout(self):
        """Test circuit breaker transitions to half-open after timeout."""
        breaker = CircuitBreaker(max_failures=1, reset_timeout=0.1)

        # Open the breaker
        breaker.record_failure()
        assert breaker.is_open

        # Wait for timeout
        time.sleep(0.2)

        # Should be half-open
        assert not breaker.is_open  # is_open property triggers state transition
        assert breaker.state == "half-open"

    def test_circuit_breaker_closes_on_success(self):
        """Test circuit breaker closes on success in half-open state."""
        breaker = CircuitBreaker(max_failures=1, reset_timeout=0.1)

        # Open the breaker
        breaker.record_failure()

        # Wait for timeout to transition to half-open
        time.sleep(0.2)
        _ = breaker.is_open  # Trigger state check

        # Record success
        breaker.record_success()

        assert breaker.state == "closed"
        assert breaker.failure_count == 0
