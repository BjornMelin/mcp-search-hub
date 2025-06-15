"""Tests for the component interfaces and base classes."""

import asyncio
from typing import Any

import pytest

from mcp_search_hub.models.base import HealthStatus
from mcp_search_hub.models.component import (
    AsyncExecutableBase,
    CompleteComponentBase,
    Component,
    ConfigurableComponentBase,
    ErrorBoundaryBase,
    MetricsProviderBase,
)
from mcp_search_hub.config.settings import (
    ComponentConfig,
)
from mcp_search_hub.models.interfaces import (
    AsyncExecutable,
    ConfigurableComponent,
    HealthCheck,
    MetricsProvider,
    ServiceLifecycle,
)
from mcp_search_hub.providers.base import SearchProvider
from mcp_search_hub.query_routing.unified_router import UnifiedRouter
from mcp_search_hub.result_processing.deduplication import DuplicateRemover
from mcp_search_hub.result_processing.merger import ResultMerger


class TestComponentBase:
    """Tests for the Component base class."""

    @pytest.mark.asyncio
    async def test_component_lifecycle(self):
        """Test component lifecycle methods."""
        component = Component("test_component")

        # Should not be initialized by default
        assert not component.initialized

        # Initialize
        await component.initialize()
        assert component.initialized
        assert component.healthy

        # Cleanup
        await component.cleanup()
        assert not component.initialized

        # Reset
        await component.reset()
        assert component.initialized

    @pytest.mark.asyncio
    async def test_component_health_check(self):
        """Test component health checks."""
        component = Component("test_component")

        # Before initialization
        status, message = await component.check_health()
        assert status == HealthStatus.UNHEALTHY
        assert "not initialized" in message.lower()

        # After initialization
        await component.initialize()
        status, message = await component.check_health()
        assert status == HealthStatus.HEALTHY

        # Test is_healthy
        assert component.is_healthy()

        # Test unhealthy state
        component.healthy = False
        component.health_message = "Something bad happened"
        status, message = await component.check_health()
        assert status == HealthStatus.UNHEALTHY
        assert message == "Something bad happened"
        assert not component.is_healthy()


class TestConfigurableComponent:
    """Tests for the ConfigurableComponentBase class."""

    class TestConfig(ComponentConfig):
        """Test configuration."""

        test_value: int = 42

    @pytest.mark.asyncio
    async def test_configurable_component(self):
        """Test configurable component methods."""
        config = self.TestConfig(name="test_config")
        component = ConfigurableComponentBase("test_component", config)

        # Test get_config
        assert component.get_config() == config
        assert component.get_config().test_value == 42

        # Test configure
        new_config = self.TestConfig(name="test_config", test_value=99)
        component.configure(new_config)
        assert component.get_config().test_value == 99

        # Test error when not configured
        component = ConfigurableComponentBase("test_component")
        with pytest.raises(ValueError):
            component.get_config()


class TestMetricsProvider:
    """Tests for the MetricsProviderBase class."""

    @pytest.mark.asyncio
    async def test_metrics_provider(self):
        """Test metrics provider methods."""
        component = MetricsProviderBase("test_component")

        # Initial metrics should be empty
        assert component.get_metrics() == {}

        # Add metrics
        component.metrics = {"test_metric": 42, "another_metric": "value"}

        # Get metrics
        metrics = component.get_metrics()
        assert metrics["test_metric"] == 42
        assert metrics["another_metric"] == "value"

        # Reset metrics
        component.reset_metrics()
        assert component.get_metrics() == {}


class TestAsyncExecutable:
    """Tests for the AsyncExecutableBase class."""

    class TestExecutable(AsyncExecutableBase[str]):
        """Test executable component."""

        async def _do_execute(self, *args, **kwargs) -> str:
            """Test execution method."""
            await asyncio.sleep(0.01)  # Simulate some work
            return "executed"

    @pytest.mark.asyncio
    async def test_async_executable(self):
        """Test async executable methods."""
        component = self.TestExecutable("test_component")

        # Execute
        result = await component.execute()
        assert result == "executed"

        # Execute with timeout
        result = await component.execute_with_timeout(100)
        assert result == "executed"

        # Test timeout too small
        with pytest.raises(asyncio.TimeoutError):
            await component.execute_with_timeout(1)  # 1ms is too small


class TestErrorBoundary:
    """Tests for the ErrorBoundaryBase class."""

    @pytest.mark.asyncio
    async def test_error_boundary(self):
        """Test error boundary methods."""
        component = ErrorBoundaryBase("test_component")

        # Test retryable error
        should_retry, message = component.handle_error(
            ConnectionError("Failed to connect")
        )
        assert should_retry
        assert "Failed to connect" in message
        assert component.error_count == 1

        # Test non-retryable error
        should_retry, message = component.handle_error(ValueError("Invalid value"))
        assert not should_retry
        assert "Invalid value" in message
        assert component.error_count == 2


class TestCompleteComponent:
    """Tests for the CompleteComponentBase class."""

    class TestConfig(ComponentConfig):
        """Test configuration."""

        test_value: int = 42

    class TestCompleteComponent(
        CompleteComponentBase[ComponentConfig, str, dict[str, Any]]
    ):
        """Test complete component."""

        async def _do_execute(self, *args, **kwargs) -> str:
            """Test execution method."""
            await asyncio.sleep(0.01)  # Simulate some work
            return "executed"

    @pytest.mark.asyncio
    async def test_complete_component(self):
        """Test complete component inherits all interfaces correctly."""
        config = self.TestConfig(name="test_config")
        component = self.TestCompleteComponent("test_component", config)

        # Test initialization
        await component.initialize()
        assert component.initialized

        # Test configuration
        assert component.get_config() == config

        # Test metrics
        component.metrics = {"test_metric": 42}
        assert component.get_metrics()["test_metric"] == 42

        # Test execution
        result = await component.execute()
        assert result == "executed"

        # Test error handling
        should_retry, message = component.handle_error(
            ConnectionError("Failed to connect")
        )
        assert should_retry

        # Test health check
        status, message = await component.check_health()
        assert status == HealthStatus.HEALTHY


class TestConcreteImplementations:
    """Tests that concrete implementations properly implement interfaces."""

    @pytest.mark.asyncio
    async def test_provider_implements_interface(self):
        """Test that SearchProvider implements SearchProviderProtocol."""
        # We can't check directly because SearchProvider is abstract
        # But this test ensures that the inheritance is properly set up
        assert issubclass(SearchProvider, ServiceLifecycle)
        assert issubclass(SearchProvider, HealthCheck)
        assert issubclass(SearchProvider, ConfigurableComponent)
        assert issubclass(SearchProvider, MetricsProvider)

    @pytest.mark.asyncio
    async def test_router_implements_interface(self):
        """Test that UnifiedRouter implements RouterProtocol."""
        router = UnifiedRouter()

        # Check implementation of protocol interfaces
        assert isinstance(router, ServiceLifecycle)
        assert isinstance(router, HealthCheck)
        assert isinstance(router, ConfigurableComponent)
        assert isinstance(router, MetricsProvider)
        assert isinstance(router, AsyncExecutable)

        # Check core methods are properly implemented
        assert hasattr(router, "initialize")
        assert hasattr(router, "cleanup")
        assert hasattr(router, "reset")
        assert hasattr(router, "check_health")
        assert hasattr(router, "route")
        assert hasattr(router, "route_and_execute")
        assert hasattr(router, "get_metrics")
        assert hasattr(router, "reset_metrics")

    @pytest.mark.asyncio
    async def test_duplicate_remover_implements_interface(self):
        """Test that DuplicateRemover implements ResultProcessorProtocol."""
        deduplicator = DuplicateRemover()

        # Check implementation of protocol interfaces
        assert isinstance(deduplicator, ServiceLifecycle)
        assert isinstance(deduplicator, HealthCheck)
        assert isinstance(deduplicator, ConfigurableComponent)
        assert isinstance(deduplicator, MetricsProvider)

        # Check core methods are properly implemented
        assert hasattr(deduplicator, "initialize")
        assert hasattr(deduplicator, "cleanup")
        assert hasattr(deduplicator, "reset")
        assert hasattr(deduplicator, "check_health")
        assert hasattr(deduplicator, "process_results")
        assert hasattr(deduplicator, "get_metrics")
        assert hasattr(deduplicator, "reset_metrics")

    @pytest.mark.asyncio
    async def test_result_merger_implements_interface(self):
        """Test that ResultMerger implements ResultMergerProtocol."""
        merger = ResultMerger()

        # Check implementation of protocol interfaces
        assert isinstance(merger, ServiceLifecycle)
        assert isinstance(merger, HealthCheck)
        assert isinstance(merger, ConfigurableComponent)
        assert isinstance(merger, MetricsProvider)

        # Check core methods are properly implemented
        assert hasattr(merger, "initialize")
        assert hasattr(merger, "cleanup")
        assert hasattr(merger, "reset")
        assert hasattr(merger, "check_health")
        assert hasattr(merger, "merge_results")
        assert hasattr(merger, "get_metrics")
        assert hasattr(merger, "reset_metrics")
