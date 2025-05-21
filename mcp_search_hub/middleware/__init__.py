"""Middleware components for MCP Search Hub.

This package contains middleware components that provide cross-cutting
functionality such as authentication, rate limiting, logging, retry logic,
and error handling.
"""

# Import middleware components
from .auth import AuthMiddleware
from .base import BaseMiddleware, MiddlewareManager
from .error_handler import ErrorHandlerMiddleware
from .logging import LoggingMiddleware
from .rate_limit import RateLimitMiddleware
from .retry import RetryMiddleware

__all__ = [
    "BaseMiddleware",
    "MiddlewareManager",
    "AuthMiddleware",
    "ErrorHandlerMiddleware",
    "LoggingMiddleware",
    "RateLimitMiddleware",
    "RetryMiddleware",
]
