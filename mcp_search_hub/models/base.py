"""Base model definitions."""

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


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
    rate_limited: bool = Field(
        False, description="Whether the provider is rate limited"
    )
    budget_exceeded: bool = Field(
        False, description="Whether the provider's budget is exceeded"
    )
    rate_limits: dict | None = Field(None, description="Rate limit information")
    budget: dict | None = Field(None, description="Budget information")


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    healthy_providers: int
    total_providers: int
    providers: dict[str, ProviderStatus]


class MetricsData(BaseModel):
    """Data structure for tracking metrics."""

    total_requests: int = 0
    total_queries: int = 0
    total_response_time_ms: float = 0.0
    cache_hits: int = 0
    cache_misses: int = 0
    provider_usage: dict[str, int] = Field(default_factory=dict)


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


class UsageStatsResponse(BaseModel):
    """Usage statistics response."""

    provider_stats: dict[str, dict[str, Any]]
    rate_limited_providers: list[str] = []
    budget_exceeded_providers: list[str] = []
    total_daily_cost: float = 0.0
    total_monthly_cost: float = 0.0
    total_remaining_budget: float = 0.0
