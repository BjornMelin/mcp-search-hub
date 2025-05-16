"""Tests for the health check and metrics endpoints."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.requests import Request
from starlette.responses import JSONResponse

from mcp_search_hub.models.base import HealthStatus
from mcp_search_hub.server import SearchServer


@pytest.fixture
def mock_providers():
    """Mock providers for testing."""
    linkup = MagicMock()
    linkup.check_status = AsyncMock(
        return_value=(HealthStatus.OK, "Provider is operational")
    )
    linkup.name = "linkup"

    exa = MagicMock()
    exa.check_status = AsyncMock(
        return_value=(HealthStatus.OK, "Provider is operational")
    )
    exa.name = "exa"

    perplexity = MagicMock()
    perplexity.check_status = AsyncMock(
        return_value=(HealthStatus.OK, "Provider is operational")
    )
    perplexity.name = "perplexity"

    tavily = MagicMock()
    tavily.check_status = AsyncMock(
        return_value=(HealthStatus.OK, "Provider is operational")
    )
    tavily.name = "tavily"

    firecrawl = MagicMock()
    firecrawl.check_status = AsyncMock(
        return_value=(HealthStatus.OK, "Provider is operational")
    )
    firecrawl.name = "firecrawl"

    return {
        "linkup": linkup,
        "exa": exa,
        "perplexity": perplexity,
        "tavily": tavily,
        "firecrawl": firecrawl,
    }


@pytest.fixture
def server(mock_providers):
    """Create a server with mock providers for testing."""
    # Configure mock settings
    settings = MagicMock()
    settings.providers.linkup.enabled = True
    settings.providers.exa.enabled = True
    settings.providers.perplexity.enabled = True
    settings.providers.tavily.enabled = True
    settings.providers.firecrawl.enabled = True

    # Create server with patch for providers
    with patch.object(SearchServer, "__init__", return_value=None):
        server = SearchServer()
        server.providers = mock_providers
        server.mcp = MagicMock()

        # Track registered routes
        server._health_check_func = None
        server._metrics_func = None

        # Mock decorator behavior
        def mock_decorator(path, methods=None):
            def decorator(func):
                if path == "/health":
                    server._health_check_func = func
                elif path == "/metrics":
                    server._metrics_func = func
                return func

            return decorator

        server.mcp.custom_route = mock_decorator

        server.metrics = MagicMock()
        # Create a proper MetricsData mock
        metrics_data = {
            "request_count": {"total": 0, "by_provider": {}, "success": 0, "error": 0},
            "latency": {"average": 0.0, "by_provider": {}},
            "uptime": 0.0,
            "provider_status": {},
        }
        server.metrics.get_metrics.return_value = metrics_data
        server.metrics.get_start_time_iso.return_value = "2025-01-01T00:00:00Z"

        # Patch get_settings specifically when running
        with patch("mcp_search_hub.server.get_settings", return_value=settings):
            # Initialize custom routes registration
            server._register_custom_routes()

        yield server


@pytest.mark.asyncio
async def test_health_check_all_ok(server):
    """Test health check with all providers operational."""
    # Configure mock settings
    settings = MagicMock()
    settings.providers.linkup.enabled = True
    settings.providers.exa.enabled = True
    settings.providers.perplexity.enabled = True
    settings.providers.tavily.enabled = True
    settings.providers.firecrawl.enabled = True

    with patch("mcp_search_hub.server.get_settings", return_value=settings):
        # Get the registered health check function
        health_check_func = server._health_check_func

        # Mock request
        request = MagicMock(spec=Request)

        # Call health check function
        response = await health_check_func(request)

        # Verify response
        assert isinstance(response, JSONResponse)
        data = json.loads(response.body.decode())

        assert data["status"] == HealthStatus.OK
        assert "version" in data
        assert len(data["providers"]) == 5  # All providers are included

        # Check that all providers were checked
        for provider in server.providers.values():
            provider.check_status.assert_called_once()


@pytest.mark.asyncio
async def test_health_check_degraded(server):
    """Test health check with one provider failing."""
    # Make one provider fail
    server.providers["linkup"].check_status.return_value = (
        HealthStatus.FAILED,
        "Provider failing",
    )

    # Configure mock settings
    settings = MagicMock()
    settings.providers.linkup.enabled = True
    settings.providers.exa.enabled = True
    settings.providers.perplexity.enabled = True
    settings.providers.tavily.enabled = True
    settings.providers.firecrawl.enabled = True

    with patch("mcp_search_hub.server.get_settings", return_value=settings):
        # Get the registered health check function
        health_check_func = server._health_check_func

        # Mock request
        request = MagicMock(spec=Request)

        # Call health check function
        response = await health_check_func(request)

        # Verify response
        assert isinstance(response, JSONResponse)
        data = json.loads(response.body.decode())

        assert (
            data["status"] == HealthStatus.DEGRADED
        )  # Overall status should be degraded
        assert data["providers"]["linkup"]["status"] == HealthStatus.FAILED
        assert data["providers"]["linkup"]["message"] == "Provider failing"

        # Other providers should still be OK
        assert data["providers"]["exa"]["status"] == HealthStatus.OK


@pytest.mark.asyncio
async def test_health_check_provider_error(server):
    """Test health check when a provider check throws an exception."""
    # Make one provider throw an exception
    server.providers["exa"].check_status.side_effect = Exception("Connection error")

    # Configure mock settings
    settings = MagicMock()
    settings.providers.linkup.enabled = True
    settings.providers.exa.enabled = True
    settings.providers.perplexity.enabled = True
    settings.providers.tavily.enabled = True
    settings.providers.firecrawl.enabled = True

    with patch("mcp_search_hub.server.get_settings", return_value=settings):
        # Get the registered health check function
        health_check_func = server._health_check_func

        # Mock request
        request = MagicMock(spec=Request)

        # Call health check function
        response = await health_check_func(request)

        # Verify response
        assert isinstance(response, JSONResponse)
        data = json.loads(response.body.decode())

        assert (
            data["status"] == HealthStatus.DEGRADED
        )  # Overall status should be degraded
        assert data["providers"]["exa"]["status"] == HealthStatus.FAILED
        assert "Check failed: Connection error" in data["providers"]["exa"]["message"]


@pytest.mark.asyncio
async def test_metrics_endpoint(server):
    """Test the metrics endpoint."""
    # Get the registered metrics function
    metrics_func = server._metrics_func

    # Mock request
    request = MagicMock(spec=Request)

    # Call metrics function
    response = await metrics_func(request)

    # Verify response
    assert isinstance(response, JSONResponse)
    data = json.loads(response.body.decode())

    assert "metrics" in data
    assert "since" in data
    assert data["since"] == "2025-01-01T00:00:00Z"

    # Verify that get_metrics was called
    server.metrics.get_metrics.assert_called_once()
