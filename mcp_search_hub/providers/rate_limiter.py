"""
Provider-specific rate limiting functionality.

This module implements rate limiting for individual providers to enforce
API rate limits and prevent quota exhaustion.
"""

import asyncio
import time
from dataclasses import dataclass, field

from pydantic import BaseModel


class RateLimitConfig(BaseModel):
    """Configuration for a provider rate limiter."""

    requests_per_minute: int = 60
    requests_per_hour: int = 1000
    requests_per_day: int = 10000
    concurrent_requests: int = 10
    cooldown_period: int = 5  # seconds to wait when limit is reached


@dataclass
class RateLimitState:
    """Tracks the current state of a rate limiter for a provider."""

    # Timestamps of recent requests
    minute_requests: list[float] = field(default_factory=list)
    hour_requests: list[float] = field(default_factory=list)
    day_requests: list[float] = field(default_factory=list)

    # Set of active request IDs for tracking concurrent requests
    active_requests: set[str] = field(default_factory=set)

    # Cooldown state
    in_cooldown: bool = False
    cooldown_until: float = 0.0

    # Lock for thread safety
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class ProviderRateLimiter:
    """
    Rate limiter for provider API calls.

    Enforces per-minute, per-hour, and per-day rate limits as well as
    limiting concurrent requests. Implements cooldown periods when
    limits are exceeded.
    """

    def __init__(self, config: RateLimitConfig):
        """Initialize the rate limiter with the given configuration."""
        self.config = config
        self.state = RateLimitState()

    async def acquire(self, request_id: str) -> bool:
        """
        Attempt to acquire permission to make a request.

        Args:
            request_id: Unique identifier for this request

        Returns:
            bool: True if the request is allowed, False if rate limited
        """
        async with self.state.lock:
            current_time = time.time()

            # Check if we're in cooldown
            if self.state.in_cooldown:
                if current_time < self.state.cooldown_until:
                    return False
                self.state.in_cooldown = False

            # Clean up old request timestamps
            self._clean_old_requests(current_time)

            # Check if any limits are exceeded
            if (
                len(self.state.minute_requests) >= self.config.requests_per_minute
                or len(self.state.hour_requests) >= self.config.requests_per_hour
                or len(self.state.day_requests) >= self.config.requests_per_day
                or len(self.state.active_requests) >= self.config.concurrent_requests
            ):
                # Enter cooldown mode
                self.state.in_cooldown = True
                self.state.cooldown_until = current_time + self.config.cooldown_period
                return False

            # Record this request
            self.state.minute_requests.append(current_time)
            self.state.hour_requests.append(current_time)
            self.state.day_requests.append(current_time)
            self.state.active_requests.add(request_id)
            return True

    async def release(self, request_id: str) -> None:
        """
        Release a request, marking it as completed.

        Args:
            request_id: Identifier of the request to release
        """
        async with self.state.lock:
            if request_id in self.state.active_requests:
                self.state.active_requests.remove(request_id)

    def _clean_old_requests(self, current_time: float) -> None:
        """
        Clean up old request timestamps.

        Args:
            current_time: Current Unix timestamp
        """
        minute_ago = current_time - 60
        hour_ago = current_time - 3600
        day_ago = current_time - 86400

        self.state.minute_requests = [
            t for t in self.state.minute_requests if t > minute_ago
        ]
        self.state.hour_requests = [t for t in self.state.hour_requests if t > hour_ago]
        self.state.day_requests = [t for t in self.state.day_requests if t > day_ago]

    def get_current_usage(self) -> dict[str, int]:
        """
        Get the current usage statistics.

        Returns:
            Dict with counts of requests in various time windows
        """
        return {
            "minute_requests": len(self.state.minute_requests),
            "hour_requests": len(self.state.hour_requests),
            "day_requests": len(self.state.day_requests),
            "concurrent_requests": len(self.state.active_requests),
        }

    def get_remaining_quota(self) -> dict[str, int]:
        """
        Get the remaining quota for each time window.

        Returns:
            Dict with remaining request counts for each time window
        """
        return {
            "minute_remaining": max(
                0, self.config.requests_per_minute - len(self.state.minute_requests)
            ),
            "hour_remaining": max(
                0, self.config.requests_per_hour - len(self.state.hour_requests)
            ),
            "day_remaining": max(
                0, self.config.requests_per_day - len(self.state.day_requests)
            ),
            "concurrent_remaining": max(
                0,
                self.config.concurrent_requests - len(self.state.active_requests),
            ),
        }

    def is_in_cooldown(self) -> bool:
        """Check if the provider is currently in cooldown mode."""
        if not self.state.in_cooldown:
            return False

        current_time = time.time()
        if current_time >= self.state.cooldown_until:
            self.state.in_cooldown = False
            return False

        return True

    async def wait_if_limited(self, request_id: str) -> bool:
        """
        Wait if rate limited and retry once after cooldown.

        Args:
            request_id: Unique identifier for this request

        Returns:
            bool: True if the request is allowed after waiting, False if still limited
        """
        if await self.acquire(request_id):
            return True

        if self.is_in_cooldown():
            # Wait for cooldown period
            wait_time = max(0, self.state.cooldown_until - time.time())
            await asyncio.sleep(wait_time + 0.1)  # Add a small buffer

            # Try again after waiting
            return await self.acquire(request_id)

        return False


class RateLimiterManager:
    """
    Manages rate limiters for all providers.

    Maintains a collection of rate limiters, one per provider,
    and provides access to them.
    """

    def __init__(self):
        """Initialize an empty rate limiter manager."""
        self.limiters: dict[str, ProviderRateLimiter] = {}

    def get_limiter(
        self, provider_id: str, config: RateLimitConfig | None = None
    ) -> ProviderRateLimiter:
        """
        Get or create a rate limiter for the specified provider.

        Args:
            provider_id: Identifier of the provider
            config: Optional rate limit configuration; used only if creating a new limiter

        Returns:
            The rate limiter for the specified provider
        """
        if provider_id not in self.limiters:
            if config is None:
                config = RateLimitConfig()
            self.limiters[provider_id] = ProviderRateLimiter(config)
        return self.limiters[provider_id]

    def get_all_usage(self) -> dict[str, dict[str, int]]:
        """
        Get usage statistics for all providers.

        Returns:
            Dict mapping provider IDs to their usage statistics
        """
        return {
            provider_id: limiter.get_current_usage()
            for provider_id, limiter in self.limiters.items()
        }

    def get_all_remaining(self) -> dict[str, dict[str, int]]:
        """
        Get remaining quota for all providers.

        Returns:
            Dict mapping provider IDs to their remaining quota
        """
        return {
            provider_id: limiter.get_remaining_quota()
            for provider_id, limiter in self.limiters.items()
        }


# Global instance for application-wide use
rate_limiter_manager = RateLimiterManager()
