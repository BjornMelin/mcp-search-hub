"""Rate limiting middleware for MCP Search Hub."""

import asyncio
import time
from collections import defaultdict
from typing import Any

from fastmcp import Context
from starlette.requests import Request
from starlette.responses import JSONResponse

from ..models.base import ErrorResponse
from ..utils.errors import ProviderRateLimitError
from ..utils.logging import get_logger
from .base import BaseMiddleware

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


class RateLimitMiddleware(BaseMiddleware):
    """Middleware to implement rate limiting."""

    def _initialize(self, **options):
        """Initialize rate limiting middleware.

        Args:
            **options: Configuration options including:
                - limit: Requests per window
                - window: Time window in seconds
                - key_func: Function to extract client ID from request
                - skip_paths: List of paths to skip rate limiting
        """
        self.order = options.get("order", 20)  # Run after auth
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

    def _get_client_id(self, request: Any) -> str:
        """Extract client identifier from request.

        Args:
            request: The request object

        Returns:
            Client identifier string
        """
        if isinstance(request, Request):
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
            client_host = request.client.host if request.client else "unknown"
            return client_host

        # For tool requests, use "tool" as client id (no rate limiting for tools)
        return "tool"

    async def process_request(
        self, request: Any, context: Context | None = None
    ) -> Any:
        """Process the incoming request for rate limiting.

        Args:
            request: The incoming request (HTTP or tool params)
            context: Optional Context object for tool requests

        Returns:
            The request if rate limit not exceeded

        Raises:
            Exception: If rate limit exceeded
        """
        # Only rate limit HTTP requests
        if not isinstance(request, Request):
            return request

        # Skip rate limiting for allowed paths
        if any(request.url.path.startswith(path) for path in self.skip_paths):
            return request

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

        return request

    async def process_response(
        self, response: Any, request: Any, context: Context | None = None
    ) -> Any:
        """Add rate limit headers to the response.

        Args:
            response: The response object
            request: The original request
            context: Optional Context object

        Returns:
            The response with rate limit headers
        """
        # Only add headers for HTTP responses
        if not isinstance(request, Request) or not hasattr(response, "headers"):
            return response

        # Skip adding headers for exempt paths
        if any(request.url.path.startswith(path) for path in self.skip_paths):
            return response

        # Add rate limit headers
        client_id = self._get_client_id(request)
        limiter = self.limiters[client_id]

        # Just check current state without incrementing
        remaining = max(0, limiter.limit - len(limiter.requests))

        response.headers["X-RateLimit-Limit"] = str(limiter.limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(int(time.time() + limiter.window))

        return response
