"""Middleware components for MCP Search Hub.

This package contains middleware components that provide cross-cutting
functionality such as authentication, rate limiting, logging, retry logic,
and error handling.

All middleware use standard Starlette BaseHTTPMiddleware patterns and work
directly with FastMCP's built-in middleware support.
"""

# Import middleware components
from .auth import AuthMiddleware
from .error_handler import ErrorHandlerMiddleware
from .logging import LoggingMiddleware
from .rate_limit import RateLimitMiddleware
from .retry import RetryMiddleware

__all__ = [
    "AuthMiddleware",
    "ErrorHandlerMiddleware",
    "LoggingMiddleware",
    "RateLimitMiddleware",
    "RetryMiddleware",
]
