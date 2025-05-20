"""Base model definitions."""

from enum import Enum
from typing import Any

from pydantic import BaseModel


class HealthStatus(str, Enum):
    """Health status of the server or a component."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


class ProviderStatus(BaseModel):
    """Status of a provider."""

    name: str
    health: HealthStatus
    status: bool
    message: str | None = None


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    healthy_providers: int
    total_providers: int
    providers: dict[str, ProviderStatus]


class MetricsResponse(BaseModel):
    """Metrics response."""

    total_queries: int = 0
    total_successes: int = 0
    total_failures: int = 0
    cache_hit_rate: float = 0.0
    avg_response_time: float = 0.0
    provider_metrics: dict[str, dict[str, Any]] = {}
    last_updated: float = 0.0


class ErrorResponse(BaseModel):
    """Standardized error response."""

    error: str
    message: str
    status_code: int
    details: dict[str, Any] | None = None
