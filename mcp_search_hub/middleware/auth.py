"""Authentication middleware for MCP Search Hub."""

import os
from collections.abc import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from ..utils.errors import AuthenticationError
from ..utils.logging import get_logger

logger = get_logger(__name__)


class AuthMiddleware(BaseHTTPMiddleware):
    """Middleware to handle API key authentication for HTTP requests."""

    def __init__(self, app, **options):
        """Initialize authentication middleware.

        Args:
            app: ASGI application
            **options: Configuration options including:
                - api_keys: Optional list of valid API keys
                - skip_auth_paths: List of paths that don't require authentication
        """
        super().__init__(app)

        # Get API keys from options or environment
        self.api_keys = options.get("api_keys", [])
        if not self.api_keys:
            api_key = os.getenv("MCP_SEARCH_HUB_API_KEY")
            if api_key:
                self.api_keys = [api_key]

        # Paths that don't require authentication
        self.skip_auth_paths = options.get(
            "skip_auth_paths",
            ["/health", "/metrics", "/docs", "/redoc", "/openapi.json"],
        )

        logger.info(
            f"Authentication middleware initialized with "
            f"{len(self.api_keys)} API keys and {len(self.skip_auth_paths)} skipped paths"
        )

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process HTTP requests for authentication.

        Args:
            request: The incoming HTTP request
            call_next: The next middleware or handler

        Returns:
            The response from downstream

        Raises:
            AuthenticationError: If authentication fails
        """
        # Skip authentication if no API keys are configured
        if not self.api_keys:
            return await call_next(request)

        # Skip authentication for allowed paths
        if any(request.url.path.startswith(path) for path in self.skip_auth_paths):
            return await call_next(request)

        # Get API key from header - case insensitive
        api_key = (
            request.headers.get("X-API-Key")
            or request.headers.get("x-api-key")
            or request.headers.get("Authorization")
            or request.headers.get("authorization")
        )
        if api_key and api_key.lower().startswith("bearer "):
            api_key = api_key[7:]  # Remove 'Bearer ' prefix

        # Validate API key
        if not api_key or api_key not in self.api_keys:
            logger.warning(f"Authentication failed for request to {request.url.path}")
            raise AuthenticationError(
                message="Invalid or missing API key",
            )

        return await call_next(request)
