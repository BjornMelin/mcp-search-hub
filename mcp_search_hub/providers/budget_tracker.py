"""
Budget tracking and enforcement for provider API calls.

This module implements budget tracking and cost management for provider API calls,
allowing enforcement of per-query and cumulative budget limits.
"""

import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class BudgetConfig(BaseModel):
    """Configuration for provider budget tracking."""

    default_query_budget: Decimal = Decimal("0.05")
    daily_budget: Decimal = Decimal("10.00")
    monthly_budget: Decimal = Decimal("100.00")
    enforce_budget: bool = True


@dataclass
class BudgetState:
    """Tracks budget usage for a provider."""

    # Cost tracking
    daily_cost: Decimal = Decimal("0")
    monthly_cost: Decimal = Decimal("0")

    # Tracking for when to reset budgets
    last_daily_reset: float = field(default_factory=time.time)
    last_monthly_reset: float = field(default_factory=time.time)

    # List of recent costs for reporting
    recent_costs: list[tuple[float, Decimal]] = field(default_factory=list)

    # Lock for thread safety
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class ProviderBudgetTracker:
    """
    Budget tracker for provider API calls.

    Tracks costs, enforces budgets, and provides reporting on usage.
    """

    def __init__(self, config: BudgetConfig):
        """Initialize the budget tracker with the given configuration."""
        self.config = config
        self.state = BudgetState()

    async def check_budget(self, estimated_cost: Decimal) -> bool:
        """
        Check if a request is within budget.

        Args:
            estimated_cost: Estimated cost of the request

        Returns:
            bool: True if the request is within budget, False otherwise
        """
        if not self.config.enforce_budget:
            return True

        async with self.state.lock:
            # Reset budgets if needed
            self._check_budget_reset()

            # Check if this request would exceed any budget
            if estimated_cost > self.config.default_query_budget:
                return False

            if self.state.daily_cost + estimated_cost > self.config.daily_budget:
                return False

            # Budget is OK if monthly cost won't exceed limit
            return self.state.monthly_cost + estimated_cost <= self.config.monthly_budget

    async def record_cost(self, actual_cost: Decimal) -> None:
        """
        Record the actual cost of a completed request.

        Args:
            actual_cost: The actual cost of the request
        """
        async with self.state.lock:
            # Reset budgets if needed
            self._check_budget_reset()

            # Record the cost
            self.state.daily_cost += actual_cost
            self.state.monthly_cost += actual_cost

            # Keep track of recent costs (store up to 1000 entries)
            current_time = time.time()
            self.state.recent_costs.append((current_time, actual_cost))
            if len(self.state.recent_costs) > 1000:
                self.state.recent_costs.pop(0)

    def _check_budget_reset(self) -> None:
        """Check if daily or monthly budgets should be reset based on time."""
        current_time = time.time()

        # Reset daily budget if it's a new day
        day_seconds = 86400  # Seconds in a day
        if current_time - self.state.last_daily_reset >= day_seconds:
            self.state.daily_cost = Decimal("0")
            self.state.last_daily_reset = current_time

        # Reset monthly budget if it's a new month
        # Approximate month as 30 days
        month_seconds = 30 * day_seconds
        if current_time - self.state.last_monthly_reset >= month_seconds:
            self.state.monthly_cost = Decimal("0")
            self.state.last_monthly_reset = current_time

    def get_remaining_budget(self) -> dict[str, Decimal]:
        """
        Get the remaining budget for each time period.

        Returns:
            Dict with remaining budget for each time period
        """
        return {
            "query_budget": self.config.default_query_budget,
            "daily_remaining": max(
                Decimal("0"), self.config.daily_budget - self.state.daily_cost
            ),
            "monthly_remaining": max(
                Decimal("0"), self.config.monthly_budget - self.state.monthly_cost
            ),
        }

    def get_usage_report(self) -> dict[str, Decimal]:
        """
        Get a report of current budget usage.

        Returns:
            Dict with current usage statistics
        """
        return {
            "daily_cost": self.state.daily_cost,
            "monthly_cost": self.state.monthly_cost,
            "daily_budget": self.config.daily_budget,
            "monthly_budget": self.config.monthly_budget,
            "daily_percent_used": (
                self.state.daily_cost / self.config.daily_budget * 100
                if self.config.daily_budget > 0
                else Decimal("0")
            ),
            "monthly_percent_used": (
                self.state.monthly_cost / self.config.monthly_budget * 100
                if self.config.monthly_budget > 0
                else Decimal("0")
            ),
        }

    def get_recent_costs(
        self, hours: int = 24, limit: int = 100
    ) -> list[tuple[datetime, Decimal]]:
        """
        Get recent costs within the specified time window.

        Args:
            hours: Number of hours to look back
            limit: Maximum number of entries to return

        Returns:
            List of (timestamp, cost) tuples
        """
        current_time = time.time()
        cutoff_time = current_time - (hours * 3600)

        # Filter by time and convert timestamps to datetime
        recent = [
            (datetime.fromtimestamp(ts), cost)
            for ts, cost in self.state.recent_costs
            if ts >= cutoff_time
        ]

        # Sort by timestamp descending (newest first) and limit
        return sorted(recent, key=lambda x: x[0], reverse=True)[:limit]


class BudgetTrackerManager:
    """
    Manages budget trackers for all providers.

    Maintains a collection of budget trackers, one per provider,
    and provides access to them.
    """

    def __init__(self):
        """Initialize an empty budget tracker manager."""
        self.trackers: dict[str, ProviderBudgetTracker] = {}

    def get_tracker(
        self, provider_id: str, config: BudgetConfig | None = None
    ) -> ProviderBudgetTracker:
        """
        Get or create a budget tracker for the specified provider.

        Args:
            provider_id: Identifier of the provider
            config: Optional budget configuration; used only if creating a new tracker

        Returns:
            The budget tracker for the specified provider
        """
        if provider_id not in self.trackers:
            if config is None:
                config = BudgetConfig()
            self.trackers[provider_id] = ProviderBudgetTracker(config)
        return self.trackers[provider_id]

    def get_all_usage(self) -> dict[str, dict[str, Decimal]]:
        """
        Get usage reports for all providers.

        Returns:
            Dict mapping provider IDs to their usage reports
        """
        return {
            provider_id: tracker.get_usage_report()
            for provider_id, tracker in self.trackers.items()
        }

    def get_all_remaining(self) -> dict[str, dict[str, Decimal]]:
        """
        Get remaining budgets for all providers.

        Returns:
            Dict mapping provider IDs to their remaining budgets
        """
        return {
            provider_id: tracker.get_remaining_budget()
            for provider_id, tracker in self.trackers.items()
        }


# Global instance for application-wide use
budget_tracker_manager = BudgetTrackerManager()
