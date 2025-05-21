"""Usage statistics for providers."""

import logging
from decimal import Decimal

from ..providers.budget_tracker import budget_tracker_manager
from ..providers.rate_limiter import rate_limiter_manager

logger = logging.getLogger(__name__)


class UsageStats:
    """Static class for retrieving usage statistics for all providers."""

    @staticmethod
    def get_all_rate_limits() -> dict[str, dict[str, int]]:
        """
        Get rate limit statistics for all providers.

        Returns:
            Dict mapping provider IDs to their rate limit statistics
        """
        return {
            **rate_limiter_manager.get_all_usage(),
            **rate_limiter_manager.get_all_remaining(),
        }

    @staticmethod
    def get_all_budgets() -> dict[str, dict[str, Decimal]]:
        """
        Get budget statistics for all providers.

        Returns:
            Dict mapping provider IDs to their budget statistics
        """
        return {
            **budget_tracker_manager.get_all_usage(),
            **budget_tracker_manager.get_all_remaining(),
        }

    @staticmethod
    def get_rate_limited_providers() -> list[str]:
        """
        Get a list of providers that are currently rate limited.

        Returns:
            List of rate-limited provider IDs
        """
        limited_providers = []
        for provider_id, limiter in rate_limiter_manager.limiters.items():
            if limiter.is_in_cooldown():
                limited_providers.append(provider_id)
        return limited_providers

    @staticmethod
    def get_budget_exceeded_providers() -> list[str]:
        """
        Get a list of providers that have exceeded their budget.

        Returns:
            List of budget-exceeded provider IDs
        """
        exceeded_providers = []
        for provider_id, tracker in budget_tracker_manager.trackers.items():
            # Check if daily budget is exceeded
            remaining = tracker.get_remaining_budget()
            if remaining["daily_remaining"] <= Decimal("0"):
                exceeded_providers.append(provider_id)
        return exceeded_providers

    @staticmethod
    def get_provider_status_report() -> dict[str, dict]:
        """
        Generate a comprehensive status report for all providers.

        Returns:
            Dict mapping provider IDs to status reports
        """
        rate_limited = UsageStats.get_rate_limited_providers()
        budget_exceeded = UsageStats.get_budget_exceeded_providers()
        rate_limits = rate_limiter_manager.get_all_remaining()
        budgets = budget_tracker_manager.get_all_remaining()

        report = {}
        all_providers = set(
            list(rate_limiter_manager.limiters.keys())
            + list(budget_tracker_manager.trackers.keys())
        )

        for provider_id in all_providers:
            rate_limit_info = rate_limits.get(provider_id, {})
            budget_info = budgets.get(provider_id, {})

            report[provider_id] = {
                "status": "degraded"
                if provider_id in rate_limited or provider_id in budget_exceeded
                else "ok",
                "rate_limited": provider_id in rate_limited,
                "budget_exceeded": provider_id in budget_exceeded,
                "rate_limits": rate_limit_info,
                "budget": budget_info,
            }

        return report
