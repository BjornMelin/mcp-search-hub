"""Tests for the performance tracker."""

import json
import time
from pathlib import Path

import pytest

from mcp_search_hub.query_routing.performance_tracker import PerformanceTracker


class TestPerformanceTracker:
    """Test the performance tracker."""

    @pytest.fixture
    def temp_metrics_file(self, tmp_path):
        """Create a temporary metrics file."""
        return tmp_path / "test_metrics.json"

    @pytest.fixture
    def tracker(self, temp_metrics_file):
        """Create a performance tracker with temporary file."""
        return PerformanceTracker(metrics_file=temp_metrics_file)

    def test_initial_state(self, tracker):
        """Test tracker starts with empty metrics."""
        assert len(tracker.metrics) == 0
        assert tracker.get_all_metrics() == {}

    def test_record_query_result(self, tracker):
        """Test recording a query result."""
        tracker.record_query_result(
            provider_name="test_provider",
            response_time_ms=1500.0,
            success=True,
            result_quality=0.85,
        )

        metrics = tracker.get_metrics("test_provider")
        assert metrics is not None
        assert metrics.provider_name == "test_provider"
        assert metrics.avg_response_time == 1500.0
        assert metrics.success_rate == 1.0
        assert metrics.avg_result_quality == 0.85
        assert metrics.total_queries == 1

    def test_multiple_query_results(self, tracker):
        """Test recording multiple query results."""
        # First query
        tracker.record_query_result(
            provider_name="test_provider",
            response_time_ms=1000.0,
            success=True,
            result_quality=0.80,
        )

        # Second query
        tracker.record_query_result(
            provider_name="test_provider",
            response_time_ms=2000.0,
            success=True,
            result_quality=0.90,
        )

        metrics = tracker.get_metrics("test_provider")
        assert metrics.avg_response_time == 1500.0  # Average of 1000 and 2000
        assert metrics.success_rate == 1.0
        assert (
            pytest.approx(metrics.avg_result_quality, 0.01) == 0.85
        )  # Average of 0.80 and 0.90
        assert metrics.total_queries == 2

    def test_mixed_success_rates(self, tracker):
        """Test recording mixed success/failure results."""
        # Three successful, one failure
        tracker.record_query_result("provider", 1000.0, True, 0.9)
        tracker.record_query_result("provider", 1200.0, True, 0.8)
        tracker.record_query_result("provider", 800.0, False, 0.0)
        tracker.record_query_result("provider", 1100.0, True, 0.85)

        metrics = tracker.get_metrics("provider")
        assert metrics.success_rate == 0.75  # 3 out of 4
        assert metrics.total_queries == 4

    def test_persistence(self, temp_metrics_file):
        """Test metrics persistence across tracker instances."""
        # First tracker instance
        tracker1 = PerformanceTracker(metrics_file=temp_metrics_file)
        tracker1.record_query_result("provider1", 1000.0, True, 0.85)
        tracker1.record_query_result("provider2", 1500.0, True, 0.90)

        # Second tracker instance should load saved metrics
        tracker2 = PerformanceTracker(metrics_file=temp_metrics_file)
        assert len(tracker2.metrics) == 2

        metrics1 = tracker2.get_metrics("provider1")
        assert metrics1.avg_response_time == 1000.0
        assert metrics1.avg_result_quality == 0.85

        metrics2 = tracker2.get_metrics("provider2")
        assert metrics2.avg_response_time == 1500.0
        assert metrics2.avg_result_quality == 0.90

    def test_reset_metrics(self, tracker):
        """Test resetting metrics."""
        # Add some metrics
        tracker.record_query_result("provider1", 1000.0, True, 0.85)
        tracker.record_query_result("provider2", 1500.0, True, 0.90)

        # Reset specific provider
        tracker.reset_metrics("provider1")
        assert tracker.get_metrics("provider1") is None
        assert tracker.get_metrics("provider2") is not None

        # Reset all
        tracker.reset_metrics()
        assert len(tracker.metrics) == 0

    def test_query_time_measurer(self, tracker):
        """Test the context manager for measuring query time."""
        with tracker.measure_query_time("test_provider"):
            time.sleep(0.1)  # Simulate query execution

        metrics = tracker.get_metrics("test_provider")
        assert metrics is not None
        assert metrics.avg_response_time >= 100.0  # At least 100ms
        assert metrics.success_rate == 1.0
        assert metrics.total_queries == 1

    def test_query_time_measurer_with_exception(self, tracker):
        """Test context manager handles exceptions."""
        try:
            with tracker.measure_query_time("test_provider"):
                raise ValueError("Test error")
        except ValueError:
            pass

        metrics = tracker.get_metrics("test_provider")
        assert metrics is not None
        assert metrics.success_rate == 0.0  # Failed due to exception
        assert metrics.total_queries == 1

    def test_last_updated_timestamp(self, tracker):
        """Test that last_updated is properly set."""
        tracker.record_query_result("provider", 1000.0, True, 0.85)

        metrics = tracker.get_metrics("provider")
        assert metrics.last_updated is not None
        # Should be a valid ISO format timestamp
        assert "T" in metrics.last_updated

    def test_moving_averages(self, tracker):
        """Test that averages are calculated correctly over time."""
        # Start with fast response
        tracker.record_query_result("provider", 500.0, True, 0.9)
        metrics = tracker.get_metrics("provider")
        assert metrics.avg_response_time == 500.0

        # Add slower response
        tracker.record_query_result("provider", 1500.0, True, 0.7)
        metrics = tracker.get_metrics("provider")
        assert metrics.avg_response_time == 1000.0  # (500 + 1500) / 2

        # Add another response
        tracker.record_query_result("provider", 1200.0, True, 0.8)
        metrics = tracker.get_metrics("provider")
        assert metrics.avg_response_time == pytest.approx(
            1066.67, 0.01
        )  # (500 + 1500 + 1200) / 3

    def test_json_serialization(self, temp_metrics_file, tracker):
        """Test that metrics are properly serialized to JSON."""
        tracker.record_query_result("provider", 1000.0, True, 0.85)

        # Check the JSON file
        with open(temp_metrics_file) as f:
            data = json.load(f)

        assert "provider" in data
        assert data["provider"]["provider_name"] == "provider"
        assert data["provider"]["avg_response_time"] == 1000.0
        assert data["provider"]["success_rate"] == 1.0
        assert data["provider"]["avg_result_quality"] == 0.85

    def test_error_handling_load(self, tmp_path):
        """Test error handling when loading corrupted metrics."""
        bad_file = tmp_path / "bad_metrics.json"
        bad_file.write_text("invalid json {")

        # Should not crash
        tracker = PerformanceTracker(metrics_file=bad_file)
        assert len(tracker.metrics) == 0

    def test_error_handling_save(self, tracker):
        """Test error handling when saving fails."""
        tracker.record_query_result("provider", 1000.0, True, 0.85)

        # Make the save fail by setting invalid file path
        tracker.metrics_file = Path("/invalid/path/metrics.json")

        # Should not crash when trying to save
        tracker.record_query_result("provider", 2000.0, True, 0.90)

        # Metrics should still be updated in memory
        metrics = tracker.get_metrics("provider")
        assert metrics.avg_response_time == 1500.0
