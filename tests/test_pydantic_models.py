"""Tests for Pydantic model validation and serialization."""

import pytest

from mcp_search_hub.config.settings import (
    AppSettings,
    ProviderSettings,
)
from mcp_search_hub.models.base import (
    ErrorResponse,
    HealthResponse,
    HealthStatus,
    ProviderStatus,
)
from mcp_search_hub.models.query import SearchQuery
from mcp_search_hub.models.results import (
    SearchResponse,
    SearchResult,
)


class TestBaseModels:
    """Tests for base models in models/base.py."""

    def test_health_status_enum(self):
        """Test HealthStatus enum values."""
        assert HealthStatus.HEALTHY == "healthy"
        assert HealthStatus.DEGRADED == "degraded"
        assert HealthStatus.UNHEALTHY == "unhealthy"

    def test_provider_status_model(self):
        """Test ProviderStatus model initialization and serialization."""
        # Test minimal initialization
        status = ProviderStatus(
            name="test_provider",
            health=HealthStatus.HEALTHY,
            status=True,
        )
        assert status.name == "test_provider"
        assert status.health == HealthStatus.HEALTHY
        assert status.status is True
        assert status.message is None
        assert status.rate_limited is False
        assert status.budget_exceeded is False

        # Test full initialization
        status = ProviderStatus(
            name="test_provider",
            health=HealthStatus.DEGRADED,
            status=False,
            message="Service degraded",
            rate_limited=True,
            budget_exceeded=True,
            rate_limits={"per_minute": 10},
            budget={"remaining": 5.0},
        )

        # Test serialization with model_dump
        data = status.model_dump()
        assert data["name"] == "test_provider"
        assert data["health"] == "degraded"
        assert data["status"] is False
        assert data["message"] == "Service degraded"
        assert data["rate_limited"] is True
        assert data["budget_exceeded"] is True
        assert data["rate_limits"] == {"per_minute": 10}
        assert data["budget"] == {"remaining": 5.0}

    def test_health_response_model(self):
        """Test HealthResponse model initialization and serialization."""
        provider_status = ProviderStatus(
            name="test_provider",
            health=HealthStatus.HEALTHY,
            status=True,
        )

        response = HealthResponse(
            status="healthy",
            healthy_providers=1,
            total_providers=1,
            providers={"test_provider": provider_status},
        )

        # Test serialization
        data = response.model_dump()
        assert data["status"] == "healthy"
        assert data["healthy_providers"] == 1
        assert data["total_providers"] == 1
        assert "test_provider" in data["providers"]

        # Test JSON serialization
        json_data = response.model_dump_json()
        assert isinstance(json_data, str)
        assert "healthy" in json_data

    def test_error_response_model(self):
        """Test ErrorResponse model initialization and serialization."""
        error = ErrorResponse(
            error="NotFoundError",
            message="Resource not found",
            status_code=404,
        )

        assert error.error == "NotFoundError"
        assert error.message == "Resource not found"
        assert error.status_code == 404
        assert error.details is None

        # With details
        error = ErrorResponse(
            error="ValidationError",
            message="Invalid data",
            status_code=400,
            details={"field": "name", "error": "Required"},
        )

        data = error.model_dump()
        assert data["error"] == "ValidationError"
        assert data["details"]["field"] == "name"


class TestConfigModels:
    """Tests for configuration models in models/config.py."""

    def test_provider_settings(self):
        """Test ProviderSettings model initialization and serialization."""
        settings = ProviderSettings()
        assert settings.enabled is True
        assert settings.timeout == 30.0  # Default

        # Test with custom values
        settings = ProviderSettings(
            enabled=False,
            timeout=5.0,
        )

        assert settings.enabled is False
        assert settings.timeout == 5.0

    def test_app_settings_model(self):
        """Test AppSettings model with nested configurations."""
        settings = AppSettings(
            log_level="DEBUG",
            port=9000,
        )

        assert settings.log_level == "DEBUG"
        assert settings.port == 9000
        assert settings.linkup.enabled is True
        assert settings.cache.memory_ttl == 300
        assert settings.middleware.auth_enabled is True

        # Test validation
        data = settings.model_dump()
        assert data["log_level"] == "DEBUG"
        assert data["port"] == 9000


class TestQueryModels:
    """Tests for query models in models/query.py."""

    def test_search_query(self):
        """Test SearchQuery model initialization and validation."""
        # Minimal query
        query = SearchQuery(query="test query")
        assert query.query == "test query"
        assert query.advanced is False  # Default
        assert query.max_results == 10  # Default
        assert query.content_type is None  # Default

        # Full query
        query = SearchQuery(
            query="test query",
            advanced=True,
            max_results=20,
            content_type="news",
            providers=["exa", "tavily"],
            budget=0.1,
            timeout_ms=10000,
            raw_content=True,
            routing_strategy="parallel",
            routing_hints="prioritize recent content",
        )

        assert query.query == "test query"
        assert query.advanced is True
        assert query.max_results == 20
        assert query.content_type == "news"
        assert query.providers == ["exa", "tavily"]
        assert query.budget == 0.1
        assert query.timeout_ms == 10000
        assert query.raw_content is True
        assert query.routing_strategy == "parallel"
        assert query.routing_hints == "prioritize recent content"

        # Test validation - max_results constraint
        with pytest.raises(ValueError):
            SearchQuery(query="test", max_results=0)  # Below minimum (ge=1)

        with pytest.raises(ValueError):
            SearchQuery(query="test", max_results=101)  # Above maximum (le=100)

        # Test validation - timeout constraint
        with pytest.raises(ValueError):
            SearchQuery(query="test", timeout_ms=500)  # Below minimum (ge=1000)

        with pytest.raises(ValueError):
            SearchQuery(query="test", timeout_ms=35000)  # Above maximum (le=30000)


class TestResultModels:
    """Tests for result models in models/results.py."""

    def test_search_result(self):
        """Test SearchResult model initialization and serialization."""
        result = SearchResult(
            title="Test Result",
            url="https://example.com",
            snippet="This is a test result",
            source="test_provider",
            score=0.95,
        )

        assert result.title == "Test Result"
        assert result.url == "https://example.com"
        assert result.snippet == "This is a test result"
        assert result.source == "test_provider"
        assert result.score == 0.95
        assert result.raw_content is None
        assert result.metadata == {}

        # With optional fields
        result = SearchResult(
            title="Test Result",
            url="https://example.com",
            snippet="This is a test result",
            source="test_provider",
            score=0.95,
            raw_content="Full content here",
            metadata={"type": "article", "date": "2023-01-01"},
        )

        assert result.raw_content == "Full content here"
        assert result.metadata["type"] == "article"

        # Serialization
        data = result.model_dump()
        assert data["title"] == "Test Result"
        assert data["raw_content"] == "Full content here"
        assert data["metadata"]["date"] == "2023-01-01"

    def test_search_response(self):
        """Test SearchResponse model initialization and serialization."""
        result = SearchResult(
            title="Test Result",
            url="https://example.com",
            snippet="This is a test result",
            source="test_provider",
            score=0.95,
        )

        response = SearchResponse(
            results=[result],
            query="test query",
            total_results=1,
            provider="test_provider",
            timing_ms=150.5,
        )

        assert response.query == "test query"
        assert response.total_results == 1
        assert response.provider == "test_provider"
        assert response.timing_ms == 150.5
        assert response.error is None
        assert response.cost is None
        assert response.rate_limited is False
        assert response.budget_exceeded is False
        assert len(response.results) == 1
        assert response.results[0].title == "Test Result"

        # Serialization
        data = response.model_dump()
        assert data["query"] == "test query"
        assert data["results"][0]["title"] == "Test Result"
