"""Performance tracking for providers to enable adaptive scoring."""

import json
import time
from datetime import UTC, datetime
from pathlib import Path

from ..models.router import ProviderPerformanceMetrics


class PerformanceTracker:
    """Tracks and manages provider performance metrics."""

    def __init__(self, metrics_file: Path | None = None):
        self.metrics_file = metrics_file or Path("provider_metrics.json")
        self.metrics: dict[str, ProviderPerformanceMetrics] = {}
        self._load_metrics()

    def _load_metrics(self):
        """Load metrics from file if it exists."""
        if self.metrics_file.exists():
            try:
                with open(self.metrics_file) as f:
                    data = json.load(f)
                    for provider, metrics in data.items():
                        self.metrics[provider] = ProviderPerformanceMetrics(**metrics)
            except Exception as e:
                print(f"Error loading metrics: {e}")

    def _save_metrics(self):
        """Save metrics to file."""
        try:
            data = {
                provider: metrics.model_dump()
                for provider, metrics in self.metrics.items()
            }
            with open(self.metrics_file, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"Error saving metrics: {e}")

    def record_query_result(
        self,
        provider_name: str,
        response_time_ms: float,
        success: bool,
        result_quality: float = 0.5,
    ):
        """Record the result of a query to a provider."""
        if provider_name not in self.metrics:
            self.metrics[provider_name] = ProviderPerformanceMetrics(
                provider_name=provider_name,
                avg_response_time=0.0,
                success_rate=0.0,
                avg_result_quality=0.0,
                total_queries=0,
                last_updated=datetime.now(UTC).isoformat(),
            )

        metrics = self.metrics[provider_name]

        # Update moving averages
        total_queries = metrics.total_queries
        metrics.avg_response_time = (
            metrics.avg_response_time * total_queries + response_time_ms
        ) / (total_queries + 1)

        # Update success rate
        successful_queries = metrics.success_rate * total_queries
        if success:
            successful_queries += 1
        metrics.success_rate = successful_queries / (total_queries + 1)

        # Update quality score
        metrics.avg_result_quality = (
            metrics.avg_result_quality * total_queries + result_quality
        ) / (total_queries + 1)

        # Update query count and timestamp
        metrics.total_queries += 1
        metrics.last_updated = datetime.now(UTC).isoformat()

        # Save metrics
        self._save_metrics()

    def get_metrics(self, provider_name: str) -> ProviderPerformanceMetrics | None:
        """Get metrics for a specific provider."""
        return self.metrics.get(provider_name)

    def get_all_metrics(self) -> dict[str, ProviderPerformanceMetrics]:
        """Get metrics for all providers."""
        return self.metrics

    def reset_metrics(self, provider_name: str | None = None):
        """Reset metrics for a provider or all providers."""
        if provider_name:
            if provider_name in self.metrics:
                del self.metrics[provider_name]
        else:
            self.metrics.clear()
        self._save_metrics()

    def measure_query_time(self, provider_name: str):
        """Context manager to measure query time."""
        return QueryTimeMeasurer(self, provider_name)


class QueryTimeMeasurer:
    """Context manager for measuring query execution time."""

    def __init__(self, tracker: PerformanceTracker, provider_name: str):
        self.tracker = tracker
        self.provider_name = provider_name
        self.start_time = None

    def __enter__(self):
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.start_time:
            response_time_ms = (time.time() - self.start_time) * 1000
            success = exc_type is None
            # Default quality score - should be set by the actual result evaluation
            self.tracker.record_query_result(
                self.provider_name, response_time_ms, success, 0.5
            )
