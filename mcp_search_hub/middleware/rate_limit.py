"""Rate limiting middleware for MCP Search Hub."""

import asyncio
import time
from collections import defaultdict
from collections.abc import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from ..utils.errors import ProviderRateLimitError
from ..utils.logging import get_logger

logger = get_logger(__name__)


class RateLimiter:
    """Implements a sliding window rate limiter."""

    def __init__(self, limit: int, window: int):
        """Initialize rate limiter.

        Args:
            limit: Maximum number of requests
            window: Time window in seconds
        """
        self.limit = limit
        self.window = window
        self.requests = []
        self._lock = asyncio.Lock()

    async def check_rate_limit(self, identifier: str) -> tuple[bool, int, float]:
        """Check if a request exceeds the rate limit.

        Args:
            identifier: Client identifier (IP, API key, etc.)

        Returns:
            Tuple of (allowed, remaining_requests, reset_time)
        """
        async with self._lock:
            # Current time
            now = time.time()

            # Filter out old requests
            self.requests = [r for r in self.requests if r > now - self.window]

            # Check if we're over the limit
            if len(self.requests) >= self.limit:
                # Calculate time until the oldest request expires
                reset_time = self.window - (now - self.requests[0])
                return False, 0, reset_time

            # Add current request
            self.requests.append(now)

            # Return allowed with remaining requests
            return True, self.limit - len(self.requests), self.window


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Middleware to implement rate limiting."""

    def __init__(self, app, **options):
        """Initialize rate limiting middleware.

        Args:
            app: ASGI application
            **options: Configuration options including:
                - limit: Requests per window
                - window: Time window in seconds
                - global_limit: Global requests per window
                - global_window: Global time window in seconds
                - skip_paths: List of paths to skip rate limiting
        """
        super().__init__(app)
        self.limit = options.get("limit", 100)
        self.window = options.get("window", 60)  # Default: 100 requests per minute
        self.skip_paths = options.get("skip_paths", ["/health", "/metrics"])

        # Create a rate limiter for each unique client
        self.limiters = defaultdict(lambda: RateLimiter(self.limit, self.window))

        # Overall rate limit for the server
        self.global_limiter = RateLimiter(
            options.get("global_limit", 1000), options.get("global_window", 60)
        )

        logger.info(
            f"Rate limiting middleware initialized: {self.limit} requests per {self.window}s "
            f"per client, {len(self.skip_paths)} skipped paths"
        )

    def _get_client_id(self, request: Request) -> str:
        """Extract client identifier from request.

        Args:
            request: The HTTP request object

        Returns:
            Client identifier string
        """
        # For HTTP requests, use client IP or forwarded IP
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()

        api_key = request.headers.get("X-API-Key") or request.headers.get(
            "Authorization"
        )
        if api_key:
            if api_key.startswith("Bearer "):
                api_key = api_key.replace("Bearer ", "")
            # Use first 8 chars of API key as identifier
            return api_key[:8]

        # Fall back to client host
        return request.client.host if request.client else "unknown"

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process HTTP requests for rate limiting.

        Args:
            request: The incoming HTTP request
            call_next: The next middleware or handler

        Returns:
            The response from downstream

        Raises:
            ProviderRateLimitError: If rate limit exceeded
        """
        # Skip rate limiting for allowed paths
        if any(request.url.path.startswith(path) for path in self.skip_paths):
            return await call_next(request)

        # Check global rate limit first
        allowed, remaining, reset = await self.global_limiter.check_rate_limit("global")
        if not allowed:
            logger.warning("Global rate limit exceeded")

            # Use ProviderRateLimitError from the error hierarchy for consistency
            # This integrates with the retry middleware and error handling pipeline
            error = ProviderRateLimitError(
                provider="global",
                limit_type="global",
                retry_after=reset,
                message=f"Global rate limit exceeded. Try again in {reset:.1f} seconds",
            )

            # Store headers in error details for response processing
            error.details["headers"] = {
                "X-RateLimit-Limit": str(self.global_limiter.limit),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(int(reset)),
                "Retry-After": str(int(reset)),
            }

            raise error

        # Check client-specific rate limit
        client_id = self._get_client_id(request)
        allowed, remaining, reset = await self.limiters[client_id].check_rate_limit(
            client_id
        )

        if not allowed:
            logger.warning(f"Rate limit exceeded for client {client_id}")

            # Use ProviderRateLimitError from the error hierarchy for consistency
            # This integrates with the retry middleware and error handling pipeline
            error = ProviderRateLimitError(
                provider="client",
                limit_type="client",
                retry_after=reset,
                message=f"Rate limit exceeded for client {client_id}. Try again in {reset:.1f} seconds",
            )

            # Store client ID and headers in error details for response processing
            error.details["client_id"] = client_id
            error.details["headers"] = {
                "X-RateLimit-Limit": str(self.limiters[client_id].limit),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(int(reset)),
                "Retry-After": str(int(reset)),
            }

            raise error

        # Call the next middleware/handler
        response = await call_next(request)

        # Add rate limit headers to the response
        if hasattr(response, "headers"):
            # Add rate limit headers
            limiter = self.limiters[client_id]

            # Just check current state without incrementing
            remaining = max(0, limiter.limit - len(limiter.requests))

            response.headers["X-RateLimit-Limit"] = str(limiter.limit)
            response.headers["X-RateLimit-Remaining"] = str(remaining)
            response.headers["X-RateLimit-Reset"] = str(
                int(time.time() + limiter.window)
            )

        return response
