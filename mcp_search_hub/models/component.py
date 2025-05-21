"""Base component implementation classes.

This module provides abstract base classes that implement the core interfaces
defined in interfaces.py. These classes provide common functionality and serve
as base classes for concrete component implementations.
"""

import asyncio
import time
from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar, cast

from pydantic import BaseModel, Field

from ..utils.logging import get_logger
from .base import HealthStatus
from .config import ComponentConfig
from .interfaces import (
    HealthCheck,
    ServiceLifecycle,
)

# Type variables for generics
T = TypeVar("T")
ConfigT = TypeVar("ConfigT", bound="ComponentConfig")
ResultT = TypeVar("ResultT")
MetricsT = TypeVar("MetricsT", bound=dict[str, Any])

logger = get_logger(__name__)


class Component(ABC, ServiceLifecycle, HealthCheck):
    """Base class for all components with lifecycle and health management."""

    def __init__(self, name: str):
        """Initialize component with a name."""
        self.name = name
        self.initialized = False
        self.healthy = True
        self.health_message = "Not initialized"
        self.last_health_check = 0.0

    async def initialize(self) -> None:
        """Initialize the component, setting up required resources."""
        self.initialized = True
        self.health_message = "Initialized"
        self.last_health_check = time.time()

    async def cleanup(self) -> None:
        """Clean up resources used by the component."""
        self.initialized = False
        self.health_message = "Cleaned up"

    async def reset(self) -> None:
        """Reset the component to its initial state."""
        await self.cleanup()
        await self.initialize()

    async def check_health(self) -> tuple[HealthStatus, str]:
        """Check component health status with basic implementation."""
        if not self.initialized:
            return HealthStatus.UNHEALTHY, "Component not initialized"

        try:
            # Perform custom health check - subclasses should override this
            await self._perform_health_check()
            self.last_health_check = time.time()
            return HealthStatus.HEALTHY, self.health_message
        except Exception as e:
            self.healthy = False
            self.health_message = f"Health check failed: {str(e)}"
            return HealthStatus.UNHEALTHY, self.health_message

    async def _perform_health_check(self) -> None:
        """
        Perform component-specific health check.

        Override this method in subclasses to implement custom health checking.
        """
        # Default implementation just sets status to healthy
        self.healthy = True
        self.health_message = "Healthy"

    def is_healthy(self) -> bool:
        """Check if the component is in a healthy state."""
        # For more accurate health status, could trigger an actual health check
        # if the last one was too long ago
        return self.healthy and self.initialized


class ConfigurableComponentBase(Component, Generic[ConfigT]):
    """Base class for components that can be configured."""

    def __init__(self, name: str, config: ConfigT | None = None):
        """Initialize with optional configuration."""
        super().__init__(name)
        self.config = config

    def configure(self, config: ConfigT) -> None:
        """Configure the component with provided configuration."""
        self.config = config

    def get_config(self) -> ConfigT:
        """Get current configuration (raises error if not configured)."""
        if self.config is None:
            raise ValueError(f"Component {self.name} has not been configured")
        return self.config


class MetricsProviderBase(Component, Generic[MetricsT]):
    """Base class for components that provide metrics."""

    def __init__(self, name: str):
        """Initialize metrics infrastructure."""
        super().__init__(name)
        self.metrics: MetricsT = cast(MetricsT, {})
        self.metrics_last_reset = time.time()

    def get_metrics(self) -> MetricsT:
        """Get current metrics."""
        return self.metrics

    def reset_metrics(self) -> None:
        """Reset all metrics to initial values."""
        self.metrics = cast(MetricsT, {})
        self.metrics_last_reset = time.time()


class AsyncExecutableBase(Component, Generic[ResultT]):
    """Base class for components that can be executed asynchronously."""

    def __init__(self, name: str):
        """Initialize executable component."""
        super().__init__(name)
        self.running_task: asyncio.Task | None = None

    async def execute(self, *args: Any, **kwargs: Any) -> ResultT:
        """Execute the component's primary function."""
        if not self.initialized:
            await self.initialize()

        return await self._do_execute(*args, **kwargs)

    async def execute_with_timeout(
        self, timeout_ms: int, *args: Any, **kwargs: Any
    ) -> ResultT:
        """Execute with a specific timeout."""
        timeout_sec = timeout_ms / 1000.0

        try:
            # Using Python 3.11+ native timeout
            async with asyncio.timeout(timeout_sec):
                return await self.execute(*args, **kwargs)
        except AttributeError:
            # Fallback for older Python versions
            try:
                # Try the 3.10 version
                async with asyncio.timeout_at(
                    asyncio.get_event_loop().time() + timeout_sec
                ):
                    return await self.execute(*args, **kwargs)
            except AttributeError:
                # Ultimate fallback using wait_for
                return await asyncio.wait_for(
                    self.execute(*args, **kwargs), timeout=timeout_sec
                )

    def cancel(self) -> bool:
        """Cancel an ongoing execution."""
        if self.running_task and not self.running_task.done():
            self.running_task.cancel()
            return True
        return False

    @abstractmethod
    async def _do_execute(self, *args: Any, **kwargs: Any) -> ResultT:
        """Implement actual execution logic in subclasses."""
        ...


class ErrorBoundaryBase(Component):
    """Base class for components with error handling."""

    def __init__(self, name: str):
        """Initialize error handling component."""
        super().__init__(name)
        self.last_error: Exception | None = None
        self.error_count = 0

    def handle_error(self, error: Exception) -> tuple[bool, str]:
        """
        Handle an error that occurred during component operation.

        Args:
            error: The exception that occurred

        Returns:
            Tuple of (should_retry, error_message)
        """
        self.last_error = error
        self.error_count += 1

        # Determine if this error is retryable
        should_retry = self.is_error_retryable(error)
        error_message = str(error)

        logger.error(
            f"Component {self.name} error: {error_message} (retryable: {should_retry})"
        )

        return should_retry, error_message

    def is_error_retryable(self, error: Exception) -> bool:
        """
        Determine if an error can be retried.

        Default implementation treats connection/timeout errors as retryable.
        Subclasses should override for more specific logic.
        """
        error_name = error.__class__.__name__

        # Common retryable errors
        retryable_errors = [
            "ConnectionError",
            "TimeoutError",
            "RequestTimeoutError",
            "ServiceUnavailableError",
            "RateLimitError",
            "TemporaryServerError",
        ]

        return any(name in error_name for name in retryable_errors)


class CompleteComponentBase(
    ConfigurableComponentBase[ConfigT],
    MetricsProviderBase[MetricsT],
    AsyncExecutableBase[ResultT],
    ErrorBoundaryBase,
    Generic[ConfigT, ResultT, MetricsT],
):
    """
    Comprehensive base class that implements all core interfaces.

    This class combines configuration, metrics, execution, and error handling
    functionality into a single base class for convenience.
    """

    def __init__(self, name: str, config: ConfigT | None = None):
        """Initialize complete component with all capabilities."""
        # Call all parent initializers
        Component.__init__(self, name)
        ConfigurableComponentBase.__init__(self, name, config)
        MetricsProviderBase.__init__(self, name)
        AsyncExecutableBase.__init__(self, name)
        ErrorBoundaryBase.__init__(self, name)


class ComponentMetrics(BaseModel):
    """Base metrics model for components."""

    total_calls: int = Field(0, description="Total number of calls to this component")
    successful_calls: int = Field(0, description="Successful calls")
    failed_calls: int = Field(0, description="Failed calls")
    avg_duration_ms: float = Field(0.0, description="Average execution duration in ms")
    last_execution_time: float | None = Field(
        None, description="Last execution timestamp"
    )
    error_rate: float = Field(0.0, description="Error rate (0-1)")


# Specific component type base classes


class SearchProviderBase(
    CompleteComponentBase[ConfigT, Any, dict[str, Any]],
    Generic[ConfigT],
):
    """Base class for search providers with all capabilities."""

    async def check_status(self) -> tuple[HealthStatus, str]:
        """Check the provider's status."""
        # Override with provider-specific implementation
        return await self.check_health()


class RouterBase(
    CompleteComponentBase[ConfigT, Any, dict[str, Any]],
    Generic[ConfigT],
):
    """Base class for routers with all capabilities."""


class ResultProcessorBase(
    CompleteComponentBase[ConfigT, list[Any], dict[str, Any]],
    Generic[ConfigT],
):
    """Base class for result processors with all capabilities."""


class ResultMergerBase(
    CompleteComponentBase[ConfigT, list[Any], dict[str, Any]],
    Generic[ConfigT],
):
    """Base class for result mergers with all capabilities."""
