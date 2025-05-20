"""Tests for the OpenAPI schema generation."""

import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
from fastapi.testclient import TestClient

from mcp_search_hub.models.base import HealthResponse, MetricsResponse
from mcp_search_hub.models.query import SearchQuery
from mcp_search_hub.models.results import CombinedSearchResponse
from mcp_search_hub.openapi.schema import custom_openapi


@pytest.fixture
def mock_app():
    """Create a mock FastAPI app with routes."""
    app = FastAPI()
    
    @app.post("/search/combined")
    async def search_combined(query: SearchQuery) -> CombinedSearchResponse:
        """Execute a combined search across multiple providers."""
        return CombinedSearchResponse(
            results=[],
            query=query.query,
            providers_used=[],
            total_results=0,
            total_cost=0.0,
            timing_ms=0.0,
        )
    
    @app.get("/health")
    async def health_check() -> HealthResponse:
        """Health check endpoint."""
        return HealthResponse(
            status="healthy",
            healthy_providers=0,
            total_providers=0,
            providers={},
        )
    
    @app.get("/metrics")
    async def metrics() -> MetricsResponse:
        """Metrics endpoint."""
        return MetricsResponse()
    
    return app


def test_custom_openapi_generation(mock_app):
    """Test that the custom OpenAPI schema is generated correctly."""
    # Create a test client
    client = TestClient(mock_app)
    
    # Override the app's openapi method with our custom one
    mock_app.openapi = lambda: custom_openapi(mock_app)
    
    # Get the OpenAPI schema
    response = client.get("/openapi.json")
    assert response.status_code == 200
    
    schema = response.json()
    
    # Check basic schema properties
    assert schema["openapi"] in ["3.1.0", "3.0.2"]  # Both are valid, depends on FastAPI version
    assert schema["info"]["title"] == "MCP Search Hub API"
    assert schema["info"]["version"] == "1.0.0"
    
    # Check that our custom server is defined
    assert "servers" in schema
    assert len(schema["servers"]) > 0
    assert schema["servers"][0]["url"] == "/"
    
    # Check that our security scheme is defined
    assert "components" in schema
    assert "securitySchemes" in schema["components"]
    assert "ApiKeyHeader" in schema["components"]["securitySchemes"]
    assert schema["components"]["securitySchemes"]["ApiKeyHeader"]["type"] == "apiKey"
    assert schema["components"]["securitySchemes"]["ApiKeyHeader"]["in"] == "header"
    assert schema["components"]["securitySchemes"]["ApiKeyHeader"]["name"] == "X-API-Key"
    
    # Check that global security is defined
    assert "security" in schema
    assert schema["security"][0]["ApiKeyHeader"] == []
    
    # Check that our tags are defined
    assert "tags" in schema
    assert any(tag["name"] == "Search" for tag in schema["tags"])
    assert any(tag["name"] == "Health" for tag in schema["tags"])
    assert any(tag["name"] == "Metrics" for tag in schema["tags"])
    
    # Check that our paths are defined
    assert "paths" in schema
    assert "/search/combined" in schema["paths"]
    assert "/health" in schema["paths"]
    assert "/metrics" in schema["paths"]


def test_export_openapi_endpoint(mock_app):
    """Test the export-openapi endpoint."""
    # Create a test client
    client = TestClient(mock_app)
    
    # Define the export-openapi endpoint
    @mock_app.get("/export-openapi")
    async def export_openapi():
        """Export OpenAPI schema as a downloadable file."""
        from fastapi.responses import Response
        
        schema = mock_app.openapi()
        return Response(
            content=json.dumps(schema, indent=2),
            media_type="application/json",
            headers={"Content-Disposition": "attachment; filename=mcp-search-hub-openapi.json"},
        )
    
    # Override the app's openapi method with our custom one
    mock_app.openapi = lambda: custom_openapi(mock_app)
    
    # Get the OpenAPI schema
    response = client.get("/export-openapi")
    assert response.status_code == 200
    
    # Check the content type and headers
    assert response.headers["content-type"] == "application/json"
    assert response.headers["content-disposition"] == "attachment; filename=mcp-search-hub-openapi.json"
    
    # Check that the response contains valid JSON
    schema = response.json()
    assert "openapi" in schema
    assert "info" in schema
    assert "paths" in schema