"""Tests for the error handler middleware."""

import pytest
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from mcp_search_hub.middleware.error_handler import ErrorHandlerMiddleware
from mcp_search_hub.utils.errors import (
    AuthenticationError,
    ProviderRateLimitError,
    SearchError,
)


def create_test_app(include_traceback=False):
    """Create a test Starlette app with error handler middleware."""

    async def success_endpoint(request):
        return JSONResponse({"result": "success"})

    async def search_error_endpoint(request):
        raise SearchError(
            message="Search failed",
            details={"provider": "test"},
            status_code=400,
        )

    async def auth_error_endpoint(request):
        raise AuthenticationError(message="Invalid API key")

    async def rate_limit_error_endpoint(request):
        raise ProviderRateLimitError(
            provider="test_provider",
            retry_after=60,
            message="Rate limit exceeded",
        )

    async def generic_error_endpoint(request):
        raise ValueError("Something went wrong")

    routes = [
        Route("/success", success_endpoint),
        Route("/search_error", search_error_endpoint),
        Route("/auth_error", auth_error_endpoint),
        Route("/rate_limit_error", rate_limit_error_endpoint),
        Route("/generic_error", generic_error_endpoint),
    ]

    app = Starlette(routes=routes)
    app.add_middleware(
        ErrorHandlerMiddleware,
        include_traceback=include_traceback,
        redact_sensitive_data=True,
    )
    return app


@pytest.mark.asyncio
async def test_pass_through_success():
    """Test that the middleware passes through successful responses."""
    app = create_test_app()
    client = TestClient(app)

    response = client.get("/success")
    assert response.status_code == 200
    assert response.json() == {"result": "success"}


@pytest.mark.asyncio
async def test_search_error_handling():
    """Test handling of SearchError exceptions."""
    app = create_test_app()
    client = TestClient(app)

    response = client.get("/search_error")
    assert response.status_code == 400
    data = response.json()
    assert data["message"] == "Search failed"
    assert data["error_type"] == "SearchError"
    assert data["details"]["provider"] == "test"


@pytest.mark.asyncio
async def test_auth_error_handling():
    """Test handling of AuthenticationError exceptions."""
    app = create_test_app()
    client = TestClient(app)

    response = client.get("/auth_error")
    assert response.status_code == 401
    data = response.json()
    assert data["message"] == "Invalid API key"
    assert data["error_type"] == "AuthenticationError"


@pytest.mark.asyncio
async def test_rate_limit_error_handling():
    """Test handling of ProviderRateLimitError exceptions."""
    app = create_test_app()
    client = TestClient(app)

    response = client.get("/rate_limit_error")
    assert response.status_code == 429
    data = response.json()
    assert data["message"] == "Rate limit exceeded"
    assert data["error_type"] == "ProviderRateLimitError"
    assert data["provider"] == "test_provider"
    assert data["details"]["retry_after_seconds"] == 60

    # Check for rate limit headers
    assert "X-RateLimit-Retry-After" in response.headers
    assert response.headers["X-RateLimit-Retry-After"] == "60"


@pytest.mark.asyncio
async def test_generic_error_handling():
    """Test handling of generic exceptions."""
    app = create_test_app()
    client = TestClient(app)

    response = client.get("/generic_error")
    assert response.status_code == 500
    data = response.json()
    assert data["message"] == "Something went wrong"
    assert data["error_type"] == "ValueError"


@pytest.mark.asyncio
async def test_include_traceback_option():
    """Test that traceback is included when option is enabled."""
    app = create_test_app(include_traceback=True)
    client = TestClient(app)

    response = client.get("/generic_error")
    assert response.status_code == 500
    data = response.json()
    assert "traceback" in data


@pytest.mark.asyncio
async def test_exclude_traceback_option():
    """Test that traceback is excluded when option is disabled."""
    app = create_test_app(include_traceback=False)
    client = TestClient(app)

    response = client.get("/generic_error")
    assert response.status_code == 500
    data = response.json()
    assert "traceback" not in data
