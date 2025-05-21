"""Authentication middleware for MCP Search Hub."""

import os
from typing import Any

from fastmcp import Context
from starlette.requests import Request

from ..utils.errors import AuthenticationError
from ..utils.logging import get_logger
from .base import BaseMiddleware

logger = get_logger(__name__)


class AuthMiddleware(BaseMiddleware):
    """Middleware to handle API key authentication for HTTP and tool requests."""

    def _initialize(self, **options):
        """Initialize authentication middleware.

        Args:
            **options: Configuration options including:
                - api_keys: Optional list of valid API keys
                - skip_auth_paths: List of paths that don't require authentication
        """
        self.order = options.get("order", 10)  # Auth should run early

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

    async def process_request(
        self, request: Any, context: Context | None = None
    ) -> Any:
        """Process the incoming request for authentication.

        Args:
            request: The incoming request (HTTP or tool params)
            context: Optional Context object for tool requests

        Returns:
            The request if authentication succeeds

        Raises:
            AuthenticationError: If authentication fails
        """
        # Skip authentication if no API keys are configured
        if not self.api_keys:
            return request

        # Handle HTTP requests
        if isinstance(request, Request):
            return await self._authenticate_http_request(request)

        # Tool requests don't need auth - they've already been authenticated
        # at the HTTP layer or via MCP client authentication
        return request

    async def _authenticate_http_request(self, request: Request) -> Request:
        """Authenticate an HTTP request.

        Args:
            request: The HTTP request

        Returns:
            The request if authentication succeeds

        Raises:
            AuthenticationError: If authentication fails
        """
        # Skip authentication for allowed paths
        if any(request.url.path.startswith(path) for path in self.skip_auth_paths):
            return request

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

        return request

    async def process_response(
        self, response: Any, request: Any, context: Context | None = None
    ) -> Any:
        """Process the outgoing response (not used for authentication).

        Args:
            response: The response
            request: The original request
            context: Optional Context object

        Returns:
            The unmodified response
        """
        return response
