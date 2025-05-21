"""Tests for provider rate limiting and budget tracking."""

import time
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from mcp_search_hub.models.base import HealthStatus
from mcp_search_hub.models.query import SearchQuery
from mcp_search_hub.providers.base_mcp import BaseMCPProvider
from mcp_search_hub.providers.budget_tracker import (
    BudgetConfig,
    BudgetTrackerManager,
    ProviderBudgetTracker,
)
from mcp_search_hub.providers.rate_limiter import (
    ProviderRateLimiter,
    RateLimitConfig,
)


class MockProvider(BaseMCPProvider):
    """Mock provider for testing rate limiting and budget tracking."""

    def __init__(self, name="test_provider"):
        self.name = name
        self.calls = 0
        self.initialized = True
        self.session = MagicMock()

        # Create dedicated limiter and tracker instances to avoid test interference
        self.rate_limiter = ProviderRateLimiter(
            RateLimitConfig(
                requests_per_minute=3,
                requests_per_hour=10,
                requests_per_day=20,
                concurrent_requests=2,
                cooldown_period=1,
            )
        )

        self.budget_tracker = ProviderBudgetTracker(
            BudgetConfig(
                default_query_budget=Decimal("0.1"),
                daily_budget=Decimal("1.0"),
                monthly_budget=Decimal("10.0"),
                enforce_budget=True,
            )
        )

        self.base_cost = Decimal("0.05")

    async def search(self, query: SearchQuery):
        """Execute search and return results."""
        self.calls += 1

        # Use real rate limiting and budget tracking
        request_id = f"test-{time.time()}"
        rate_limited = not await self.rate_limiter.wait_if_limited(request_id)
        if rate_limited:
            return {"error": "Rate limited", "results": []}

        # Estimate cost
        estimated_cost = Decimal(str(self.estimate_cost(query)))

        # Check budget
        budget_exceeded = not await self.budget_tracker.check_budget(estimated_cost)
        if budget_exceeded:
            await self.rate_limiter.release(request_id)
            return {"error": "Budget exceeded", "results": []}

        # Record cost
        actual_cost = self._calculate_actual_cost(query, ["result1", "result2"])
        await self.budget_tracker.record_cost(actual_cost)

        # Release rate limit
        await self.rate_limiter.release(request_id)

        return {"results": ["result1", "result2"], "cost": float(actual_cost)}

    def estimate_cost(self, query: SearchQuery) -> float:
        """Estimate the cost of executing the query."""
        return float(self.base_cost)

    def _calculate_actual_cost(self, query, results) -> Decimal:
        """Calculate the actual cost of a search."""
        return Decimal("0.05")

    async def check_status(self):
        """Check provider status."""
        # Include rate limit and budget status in response
        is_rate_limited = self.rate_limiter.is_in_cooldown()
        budget_report = self.budget_tracker.get_usage_report()
        budget_exceeded = budget_report["daily_percent_used"] >= 100

        status = HealthStatus.HEALTHY
        message = "Provider operational"

        if is_rate_limited:
            status = HealthStatus.DEGRADED
            message = "Provider rate limited"

        if budget_exceeded:
            status = HealthStatus.DEGRADED
            message = "Provider budget exceeded"

        return (status, message)

    def get_capabilities(self):
        """Return provider capabilities."""
        return {
            "name": self.name,
            "rate_limit_info": self.rate_limiter.get_current_usage(),
            "budget_info": self.budget_tracker.get_usage_report(),
        }


@pytest.mark.asyncio
async def test_budget_tracker_basic_operation():
    """Test basic budget tracker operation."""
    # Create a dedicated tracker to avoid test interference
    tracker = ProviderBudgetTracker(
        BudgetConfig(
            default_query_budget=Decimal("0.1"),
            daily_budget=Decimal("0.5"),
            monthly_budget=Decimal("1.0"),
            enforce_budget=True,
        )
    )

    # Reset state for the test
    tracker.state.daily_cost = Decimal("0")
    tracker.state.monthly_cost = Decimal("0")

    # First request within budget should be allowed
    assert await tracker.check_budget(Decimal("0.1")) is True

    # Record the cost
    await tracker.record_cost(Decimal("0.1"))

    # Second request within budget should be allowed
    assert await tracker.check_budget(Decimal("0.1")) is True
    await tracker.record_cost(Decimal("0.1"))

    # Third request within budget should be allowed
    assert await tracker.check_budget(Decimal("0.1")) is True
    await tracker.record_cost(Decimal("0.1"))

    # Fourth request should be rejected (exceeds daily budget)
    assert await tracker.check_budget(Decimal("0.2")) is False

    # Get budget report
    report = tracker.get_usage_report()
    assert report["daily_cost"] == Decimal("0.3")
    assert report["daily_percent_used"] == Decimal("60")

    # Get remaining budget
    remaining = tracker.get_remaining_budget()
    assert remaining["daily_remaining"] == Decimal("0.2")


@pytest.mark.asyncio
async def test_budget_tracking_integration():
    """Test budget tracking with a mock manager."""
    # Create a manager
    manager = BudgetTrackerManager()

    # Get a tracker for a test provider
    tracker = manager.get_tracker(
        "test_provider",
        config=BudgetConfig(
            daily_budget=Decimal("1.0"),
            enforce_budget=True,
        ),
    )

    # Reset state
    tracker.state.daily_cost = Decimal("0")

    # Record some costs
    await tracker.record_cost(Decimal("0.3"))
    await tracker.record_cost(Decimal("0.4"))

    # Get usage reports
    usage = manager.get_all_usage()
    remaining = manager.get_all_remaining()

    # Verify tracking
    assert "test_provider" in usage
    assert "test_provider" in remaining
    assert usage["test_provider"]["daily_cost"] == Decimal("0.7")
    assert remaining["test_provider"]["daily_remaining"] == Decimal("0.3")


@pytest.mark.asyncio
async def test_usage_stats_integration():
    """Test usage statistics integration with provider."""
    # Import usage stats

    # Create a provider with controlled state
    provider = MockProvider("test_stats_provider")

    # Force budget to be close to limit
    provider.budget_tracker.state.daily_cost = Decimal("0.8")
    provider.budget_tracker.config.daily_budget = Decimal("1.0")

    # Get provider status
    status = await provider.check_status()

    # Should be healthy since budget not exceeded yet
    assert status[0] == HealthStatus.HEALTHY

    # Now exceed budget
    provider.budget_tracker.state.daily_cost = Decimal("1.0")

    # Status should now show degraded
    status = await provider.check_status()
    assert status[0] == HealthStatus.DEGRADED
