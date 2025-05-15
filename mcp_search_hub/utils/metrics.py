"""Metrics tracking utilities."""

import time
from datetime import datetime
from typing import Dict, Set

from ..models.base import MetricsData


class MetricsTracker:
    """Tracker for server metrics."""

    def __init__(self):
        """Initialize the metrics tracker."""
        self.start_time = datetime.utcnow()
        self.total_requests = 0
        self.total_queries = 0
        self.total_response_time_ms = 0.0
        self.cache_hits = 0
        self.cache_misses = 0
        self.provider_usage: Dict[str, int] = {}
        self.errors = 0
        self.request_durations: Dict[str, float] = {}

    def start_request(self, request_id: str) -> None:
        """Start timing a request."""
        self.request_durations[request_id] = time.time()
        self.total_requests += 1

    def end_request(self, request_id: str) -> None:
        """End timing a request and record metrics."""
        if request_id in self.request_durations:
            start_time = self.request_durations.pop(request_id)
            duration_ms = (time.time() - start_time) * 1000
            self.total_response_time_ms += duration_ms

    def record_query(self, providers_used: Set[str], from_cache: bool = False) -> None:
        """Record a query execution."""
        self.total_queries += 1

        if from_cache:
            self.cache_hits += 1
        else:
            self.cache_misses += 1

        # Record provider usage
        for provider in providers_used:
            if provider in self.provider_usage:
                self.provider_usage[provider] += 1
            else:
                self.provider_usage[provider] = 1

    def record_error(self) -> None:
        """Record an error."""
        self.errors += 1

    def get_metrics(self) -> MetricsData:
        """Get current metrics data."""
        avg_response_time = 0.0
        if self.total_requests > 0:
            avg_response_time = self.total_response_time_ms / self.total_requests

        return MetricsData(
            total_requests=self.total_requests,
            total_queries=self.total_queries,
            average_response_time_ms=avg_response_time,
            cache_hits=self.cache_hits,
            cache_misses=self.cache_misses,
            provider_usage=self.provider_usage,
            errors=self.errors,
        )

    def get_start_time_iso(self) -> str:
        """Get the start time as ISO 8601 string."""
        return self.start_time.isoformat() + "Z"
