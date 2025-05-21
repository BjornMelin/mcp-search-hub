"""Tests for Docker configuration and health checks."""

import asyncio
import os
from unittest import mock

import pytest
from fastapi.testclient import TestClient

from mcp_search_hub.models.base import HealthStatus
from mcp_search_hub.server import SearchServer


@pytest.fixture
def server():
    """Create a server instance for testing."""
    server = SearchServer()
    yield server
    # Clean up
    asyncio.run(server.close())


@pytest.fixture
def client(server):
    """Create a test client for the server."""
    with TestClient(server.mcp.http_app) as client:
        yield client


def test_health_endpoint(client):
    """Test the health check endpoint returns the correct structure."""
    response = client.get("/health")
    assert response.status_code in [200, 503]  # Either healthy or unhealthy

    data = response.json()
    assert "status" in data
    assert "healthy_providers" in data
    assert "total_providers" in data
    assert "providers" in data

    # Health status is one of the defined values
    assert data["status"] in ["HEALTHY", "DEGRADED", "UNHEALTHY"]


def test_health_check_with_mock_providers(server):
    """Test health check with mock providers in different states."""
    # Create mock providers with various health statuses
    mock_providers = {
        "provider1": mock.MagicMock(),
        "provider2": mock.MagicMock(),
        "provider3": mock.MagicMock(),
    }

    # Set up provider status returns
    mock_providers["provider1"].check_status.return_value = asyncio.Future()
    mock_providers["provider1"].check_status.return_value.set_result(
        (HealthStatus.HEALTHY, "Healthy")
    )
    mock_providers["provider1"].rate_limiter.is_in_cooldown.return_value = False
    mock_providers["provider1"].budget_tracker.get_usage_report.return_value = {
        "daily_percent_used": 50
    }

    mock_providers["provider2"].check_status.return_value = asyncio.Future()
    mock_providers["provider2"].check_status.return_value.set_result(
        (HealthStatus.DEGRADED, "Degraded")
    )
    mock_providers["provider2"].rate_limiter.is_in_cooldown.return_value = True
    mock_providers["provider2"].budget_tracker.get_usage_report.return_value = {
        "daily_percent_used": 90
    }

    mock_providers["provider3"].check_status.return_value = asyncio.Future()
    mock_providers["provider3"].check_status.return_value.set_result(
        (HealthStatus.UNHEALTHY, "Unhealthy")
    )
    mock_providers["provider3"].rate_limiter.is_in_cooldown.return_value = False
    mock_providers["provider3"].budget_tracker.get_usage_report.return_value = {
        "daily_percent_used": 100
    }

    # Replace server providers with mocks
    server.providers = mock_providers

    # Create client with updated server
    with TestClient(server.mcp.http_app) as client:
        response = client.get("/health")

        # With mixed health statuses, overall should be DEGRADED
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "DEGRADED"
        assert data["healthy_providers"] == 1
        assert data["total_providers"] == 3

        # Check provider-specific statuses
        providers = data["providers"]
        assert providers["provider1"]["health"] == "HEALTHY"
        assert providers["provider2"]["health"] == "DEGRADED"
        assert providers["provider3"]["health"] == "UNHEALTHY"

        # Check rate limit and budget info
        assert not providers["provider1"]["rate_limited"]
        assert providers["provider2"]["rate_limited"]
        assert not providers["provider3"]["budget_exceeded"]
        assert providers["provider3"]["budget_exceeded"]


def test_environment_variable_loading():
    """Test that environment variables are properly loaded in the Docker config."""
    # Mock environment variables
    test_env = {
        "HOST": "0.0.0.0",
        "PORT": "9000",
        "LOG_LEVEL": "DEBUG",
        "TRANSPORT": "http",
        "CACHE_TTL": "500",
        "REDIS_CACHE_ENABLED": "true",
        "FIRECRAWL_API_KEY": "test_key",
        "FIRECRAWL_ENABLED": "true",
        "FIRECRAWL_TIMEOUT": "12345",
    }

    with mock.patch.dict(os.environ, test_env):
        from mcp_search_hub.config import get_settings

        # Reset any cached settings
        get_settings.cache_clear()

        # Get fresh settings
        settings = get_settings()

        # Verify settings from environment
        assert settings.host == "0.0.0.0"
        assert settings.port == 9000
        assert settings.log_level == "DEBUG"
        assert settings.transport == "http"
        assert settings.cache_ttl == 500
        assert settings.cache.redis_enabled is True
        assert settings.providers.firecrawl.enabled is True
        assert settings.providers.firecrawl.timeout == 12345
        assert settings.providers.firecrawl.api_key.get_secret_value() == "test_key"


def test_docker_healthcheck_command():
    """Test that the Docker healthcheck command works as expected."""
    import socket
    import subprocess

    def check_port_open(port):
        """Check if a port is open."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            return s.connect_ex(("localhost", port)) == 0

    # Skip this test if we're not running in Docker or the server isn't running
    if not check_port_open(8000):
        pytest.skip("Server not running on port 8000, skipping Docker healthcheck test")

    # Run the healthcheck command that would be used in Docker
    result = subprocess.run(
        ["curl", "-f", "http://localhost:8000/health"],
        capture_output=True,
        text=True,
        check=False,
    )

    # Check the command executed successfully
    assert result.returncode in [0, 22]  # 0 for success, 22 for HTTP error (like 503)

    # If we got output, verify it's valid JSON with expected structure
    if result.stdout:
        import json

        data = json.loads(result.stdout)
        assert "status" in data
        assert "providers" in data
