"""Base model definitions."""

from enum import Enum
from pydantic import BaseModel
from typing import Dict, List, Optional


class HealthStatus(str, Enum):
    """Health status of the server or a component."""
    
    OK = "ok"
    DEGRADED = "degraded"
    FAILED = "failed"


class ProviderStatus(BaseModel):
    """Status of a provider."""
    
    name: str
    status: HealthStatus
    message: Optional[str] = None


class HealthResponse(BaseModel):
    """Health check response."""
    
    status: HealthStatus
    version: str = "1.0.0"
    providers: Dict[str, ProviderStatus]
    

class MetricsData(BaseModel):
    """Metrics data."""
    
    total_requests: int = 0
    total_queries: int = 0
    average_response_time_ms: float = 0
    cache_hits: int = 0
    cache_misses: int = 0
    provider_usage: Dict[str, int] = {}
    errors: int = 0
    

class MetricsResponse(BaseModel):
    """Metrics response."""
    
    metrics: MetricsData
    since: str  # ISO datetime when metrics collection started
