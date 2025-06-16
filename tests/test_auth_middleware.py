"""Tests for authentication middleware."""

import os
from unittest.mock import patch

import pytest
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.testclient import TestClient

from mcp_search_hub.middleware.auth import AuthMiddleware
from mcp_search_hub.middleware.error_handler import ErrorHandlerMiddleware


def create_test_app(**middleware_options):
    """Create a test Starlette app with AuthMiddleware."""
    app = Starlette()

    # Add a simple test route
    @app.route("/test")
    async def test_route(request):
        return JSONResponse({"message": "success"})

    @app.route("/health")
    async def health_route(request):
        return JSONResponse({"status": "ok"})

    @app.route("/metrics")
    async def metrics_route(request):
        return JSONResponse({"metrics": "data"})

    @app.route("/docs")
    async def docs_route(request):
        return JSONResponse({"docs": "available"})

    # Add the auth middleware
    app.add_middleware(AuthMiddleware, **middleware_options)

    # Add error handler middleware to convert exceptions to HTTP responses
    app.add_middleware(ErrorHandlerMiddleware, include_traceback=False)

    return app


class TestAuthMiddleware:
    """Test cases for AuthMiddleware."""

    def test_initialization_with_api_keys(self):
        """Test initialization with explicit API keys."""
        app = create_test_app(
            api_keys=["test_key1", "test_key2"], skip_auth_paths=["/skip1", "/skip2"]
        )
        # Check that the middleware was added successfully by testing the app
        client = TestClient(app)
        # This should fail due to missing API key
        response = client.get("/test")
        assert response.status_code == 401

    def test_initialization_with_env_var(self):
        """Test initialization with API key from environment."""
        with patch.dict(os.environ, {"MCP_SEARCH_HUB_API_KEY": "env_key"}):
            app = create_test_app()
            client = TestClient(app)

            # Test with valid key
            response = client.get("/test", headers={"X-API-Key": "env_key"})
            assert response.status_code == 200

            # Test with invalid key
            response = client.get("/test", headers={"X-API-Key": "wrong_key"})
            assert response.status_code == 401

    def test_initialization_without_api_keys(self):
        """Test initialization without API keys."""
        with patch.dict(os.environ, clear=True):
            app = create_test_app()
            client = TestClient(app)

            # Should allow all requests when no API keys are configured
            response = client.get("/test")
            assert response.status_code == 200

    def test_skipped_paths(self):
        """Test that requests to skipped paths are allowed."""
        app = create_test_app(api_keys=["test_key"])
        client = TestClient(app)

        # Health endpoint should be accessible without auth
        response = client.get("/health")
        assert response.status_code == 200

        # Metrics endpoint should be accessible without auth
        response = client.get("/metrics")
        assert response.status_code == 200

        # Docs endpoint should be accessible without auth
        response = client.get("/docs")
        assert response.status_code == 200

    def test_valid_api_key_header(self):
        """Test requests with valid API key in X-API-Key header."""
        app = create_test_app(api_keys=["test_key1", "test_key2"])
        client = TestClient(app)

        # Valid key should work
        response = client.get("/test", headers={"X-API-Key": "test_key1"})
        assert response.status_code == 200

        # Another valid key should work
        response = client.get("/test", headers={"X-API-Key": "test_key2"})
        assert response.status_code == 200

    def test_valid_api_key_bearer(self):
        """Test requests with valid API key in Bearer token."""
        app = create_test_app(api_keys=["test_key"])
        client = TestClient(app)

        # Bearer token should work
        response = client.get("/test", headers={"Authorization": "Bearer test_key"})
        assert response.status_code == 200

    def test_invalid_api_key(self):
        """Test requests with invalid API key."""
        app = create_test_app(api_keys=["test_key"])
        client = TestClient(app)

        # Invalid key should fail
        response = client.get("/test", headers={"X-API-Key": "invalid_key"})
        assert response.status_code == 401

    def test_missing_api_key(self):
        """Test requests with missing API key."""
        app = create_test_app(api_keys=["test_key"])
        client = TestClient(app)

        # Missing key should fail
        response = client.get("/test")
        assert response.status_code == 401

    def test_case_insensitive_headers(self):
        """Test that headers are handled case-insensitively."""
        app = create_test_app(api_keys=["test_key"])
        client = TestClient(app)

        # Various header cases should work
        response = client.get("/test", headers={"x-api-key": "test_key"})
        assert response.status_code == 200

        response = client.get("/test", headers={"authorization": "Bearer test_key"})
        assert response.status_code == 200


@pytest.mark.parametrize(
    "api_keys,header_key,header_value,path,should_pass",
    [
        # No API keys configured - should always pass
        ([], None, None, "/test", True),
        # Valid API key in X-API-Key header
        (["key1", "key2"], "X-API-Key", "key1", "/test", True),
        # Valid API key in Authorization header (Bearer)
        (["key1", "key2"], "Authorization", "Bearer key2", "/test", True),
        # Invalid API key
        (["key1", "key2"], "X-API-Key", "invalid", "/test", False),
        # Missing API key
        (["key1", "key2"], None, None, "/test", False),
        # Skipped path - should pass regardless of API key
        (["key1", "key2"], None, None, "/health", True),
        (["key1", "key2"], None, None, "/metrics", True),
        (["key1", "key2"], None, None, "/docs", True),
    ],
)
def test_auth_middleware_scenarios(
    api_keys, header_key, header_value, path, should_pass
):
    """Test various authentication scenarios."""
    app = create_test_app(api_keys=api_keys)
    client = TestClient(app)

    # Setup headers
    headers = {}
    if header_key and header_value:
        headers[header_key] = header_value

    response = client.get(path, headers=headers)

    if should_pass:
        assert response.status_code == 200, (
            f"Expected success for scenario with API keys {api_keys}, header {header_key}={header_value}, path {path}"
        )
    else:
        assert response.status_code == 401, (
            f"Expected failure for scenario with API keys {api_keys}, header {header_key}={header_value}, path {path}"
        )
