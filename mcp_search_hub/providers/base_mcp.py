"""Base implementation for MCP server providers.

This module provides a unified base class for all MCP server implementations
to reduce code duplication and standardize provider behavior.
"""

import asyncio
import logging
import os
import subprocess
import sys
import uuid
from collections.abc import Callable
from decimal import Decimal
from enum import Enum
from typing import Any, TypeVar

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from ..config import get_settings
from ..models.base import HealthStatus
from ..models.query import SearchQuery
from ..models.results import SearchResponse, SearchResult
from ..utils.errors import (
    NetworkConnectionError,
    NetworkTimeoutError,
    ProviderAuthenticationError,
    ProviderError,
    ProviderInitializationError,
    ProviderQuotaExceededError,
    ProviderRateLimitError,
    ProviderServiceError,
    ProviderTimeoutError,
)
from ..utils.retry import RetryConfig, with_exponential_backoff
from .base import SearchProvider
from .budget_tracker import BudgetConfig, budget_tracker_manager
from .rate_limiter import RateLimitConfig, rate_limiter_manager

T = TypeVar("T")  # Generic type for retry decorator

logger = logging.getLogger(__name__)


class ServerType(str, Enum):
    """Type of MCP server implementation."""

    NODE_JS = "nodejs"
    PYTHON = "python"


class BaseMCPProvider(SearchProvider):
    """
    Base class for all MCP server providers.

    This class handles common MCP server operations including:
    - Subprocess management for both Node.js and Python servers
    - Server installation and checks
    - Session management and initialization
    - Tool invocation and standardized search functionality
    - Provider state and health checking
    - Rate limiting and budget tracking
    - Retry logic with exponential backoff
    """

    # Constants for installation and health check
    INSTALLATION_RETRY_COUNT = 2
    INSTALLATION_CHECK_TIMEOUT = 10  # seconds
    HEALTH_CHECK_TIMEOUT = 5  # seconds

    # Retry configuration
    RETRY_ENABLED = True

    def __init__(
        self,
        name: str,
        api_key: str | None = None,
        env_var_name: str | None = None,
        server_type: ServerType = ServerType.NODE_JS,
        command: str | None = None,
        args: list[str] | None = None,
        additional_env: dict[str, str] | None = None,
        tool_name: str = "web_search",
        api_timeout: int = 30000,
        rate_limit_config: RateLimitConfig | None = None,
        budget_config: BudgetConfig | None = None,
    ):
        """
        Initialize the MCP provider with configuration.

        Args:
            name: The name of the provider (used for identification)
            api_key: The API key for the provider (if None, will check env_var_name)
            env_var_name: The name of the environment variable containing the API key
            server_type: Type of MCP server (nodejs or python)
            command: The command to execute the server (defaults based on server_type)
            args: Arguments to pass to the command
            additional_env: Additional environment variables to pass to the server
            tool_name: The name of the search tool to invoke
            api_timeout: The timeout for API calls in milliseconds
            rate_limit_config: Configuration for rate limiting
            budget_config: Configuration for budget tracking
        """
        self.name = name
        self._configure_api_key(api_key, env_var_name)
        self.server_type = server_type
        self.tool_name = tool_name
        self.api_timeout = api_timeout
        self.session: ClientSession | None = None

        # Configure command and args based on server type
        self.command = command or self._get_default_command()
        self.args = args or []

        # Configure environment variables
        self.env = os.environ.copy()
        if self.api_key and env_var_name:
            self.env[env_var_name] = self.api_key
        if additional_env:
            self.env.update(additional_env)

        # Configure server parameters
        self.server_params = StdioServerParameters(
            command=self.command,
            args=self.args,
            env=self.env,
        )

        # Initialize rate limiter and budget tracker
        self.rate_limiter = rate_limiter_manager.get_limiter(
            f"{self.name}", config=rate_limit_config
        )
        self.budget_tracker = budget_tracker_manager.get_tracker(
            f"{self.name}", config=budget_config
        )

    def _configure_api_key(self, api_key: str | None, env_var_name: str | None) -> None:
        """Configure the API key from input or environment variable."""
        if api_key:
            self.api_key = api_key
        elif env_var_name:
            self.api_key = os.getenv(env_var_name)
        else:
            self.api_key = None

        if not self.api_key:
            raise ProviderAuthenticationError(
                provider=self.name,
                message=f"{self.name} API key is required",
                details={"env_var": env_var_name},
            )

    def _get_default_command(self) -> str:
        """Get the default command based on server type."""
        if self.server_type == ServerType.NODE_JS:
            return "npx"
        if self.server_type == ServerType.PYTHON:
            return sys.executable
        raise ProviderInitializationError(
            provider=self.name,
            message=f"Unsupported server type: {self.server_type}",
            details={"component": "server_type", "server_type": str(self.server_type)},
        )

    async def initialize(self) -> None:
        """Initialize the connection to the MCP server."""
        try:
            # Check if the server is installed
            is_installed = await self._check_installation()

            if not is_installed:
                logger.info(f"Installing {self.name} MCP server...")
                await self._install_server()

                # Verify installation was successful
                is_installed = await self._check_installation()
                if not is_installed:
                    raise ProviderInitializationError(
                        provider=self.name,
                        message=f"Failed to install {self.name} MCP server",
                        details={"component": "installation"},
                    )

            # Connect to the server
            logger.info(f"Connecting to {self.name} MCP server...")
            read_stream, write_stream = await stdio_client(self.server_params)
            self.session = ClientSession(read_stream, write_stream)

            # Initialize the session
            await self.session.__aenter__()

            # Verify tools are available
            tools = await self.session.list_tools()
            if not tools:
                raise ProviderInitializationError(
                    provider=self.name,
                    message=f"No tools available from {self.name} MCP server",
                    details={"component": "tools"},
                )

            tool_names = [tool.name for tool in tools]
            if self.tool_name not in tool_names:
                raise ProviderInitializationError(
                    provider=self.name,
                    message=f"Required tool '{self.tool_name}' not available in {self.name} MCP server",
                    details={
                        "component": "tools",
                        "required_tool": self.tool_name,
                        "available_tools": tool_names,
                    },
                )

            logger.info(f"Successfully connected to {self.name} MCP server")

        except ProviderError:
            # If it's already a ProviderError, just cleanup and re-raise
            logger.error(f"Provider error while initializing {self.name} MCP server")
            # Cleanup any partial initialization
            await self._cleanup()
            raise

        except Exception as e:
            logger.error(f"Error initializing {self.name} MCP server: {str(e)}")
            # Cleanup any partial initialization
            await self._cleanup()

            # Map common exceptions to specific provider errors
            if isinstance(e, ConnectionError | subprocess.SubprocessError):
                raise NetworkConnectionError(
                    message=f"Failed to connect to {self.name} MCP server: {str(e)}",
                    original_error=e,
                    details={"provider": self.name},
                )
            if isinstance(e, TimeoutError):
                raise NetworkTimeoutError(
                    message=f"Connection to {self.name} MCP server timed out",
                    timeout=self.INSTALLATION_CHECK_TIMEOUT,
                    original_error=e,
                    details={"provider": self.name},
                )
            if (
                "auth" in str(e).lower()
                or "unauthorized" in str(e).lower()
                or "api key" in str(e).lower()
            ):
                raise ProviderAuthenticationError(
                    provider=self.name,
                    message=f"Authentication failed for {self.name} MCP server: {str(e)}",
                    original_error=e,
                )
            # Generic provider initialization error for unhandled cases
            raise ProviderInitializationError.from_exception(
                e,
                provider=self.name,
                message=f"Failed to initialize {self.name} MCP server",
            )

    async def _check_installation(self) -> bool:
        """
        Check if the MCP server is installed.

        Returns:
            bool: True if installed, False otherwise
        """
        try:
            # Default implementation - override in specific providers if needed
            if self.server_type == ServerType.NODE_JS:
                cmd = [self.command] + self.args + ["--version"]
            else:
                cmd = [
                    self.command,
                    "-m",
                    "pip",
                    "show",
                    self.args[1] if len(self.args) > 1 else "",
                ]

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            try:
                await asyncio.wait_for(
                    process.communicate(), timeout=self.INSTALLATION_CHECK_TIMEOUT
                )
                return process.returncode == 0
            except TimeoutError:
                logger.warning(f"Installation check for {self.name} timed out")
                if process.returncode is None:
                    process.kill()
                return False

        except (subprocess.SubprocessError, FileNotFoundError) as e:
            logger.info(f"{self.name} MCP server not found: {str(e)}")
            return False

    async def _install_server(self) -> None:
        """Install the MCP server if not already installed."""
        # Default implementation - override in specific providers if needed
        if self.server_type == ServerType.NODE_JS:
            package_name = self.args[0] if self.args else None
            if not package_name:
                raise ProviderInitializationError(
                    provider=self.name,
                    message=f"Cannot install {self.name}: no package name specified",
                    details={"component": "installation", "server_type": "nodejs"},
                )

            cmd = ["npm", "install", "-g", package_name]

        elif self.server_type == ServerType.PYTHON:
            module_name = self.args[1] if len(self.args) > 1 else None
            if not module_name:
                raise ProviderInitializationError(
                    provider=self.name,
                    message=f"Cannot install {self.name}: no module name specified",
                    details={"component": "installation", "server_type": "python"},
                )

            cmd = [sys.executable, "-m", "pip", "install", module_name]

        else:
            raise ProviderInitializationError(
                provider=self.name,
                message=f"Cannot install {self.name}: unsupported server type {self.server_type}",
                details={
                    "component": "installation",
                    "server_type": str(self.server_type),
                },
            )

        logger.info(f"Installing {self.name} MCP server: {' '.join(cmd)}")
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            error_msg = stderr.decode() if stderr else "Unknown installation error"
            raise ProviderInitializationError(
                provider=self.name,
                message=f"Failed to install {self.name} MCP server",
                details={
                    "component": "installation",
                    "error_message": error_msg,
                    "returncode": process.returncode,
                    "command": " ".join(cmd),
                },
            )

        logger.info(f"Successfully installed {self.name} MCP server")

    async def _cleanup(self) -> None:
        """Clean up resources when shutting down."""
        if self.session:
            try:
                await self.session.close()
            except Exception as e:
                logger.warning(f"Error closing {self.name} MCP session: {str(e)}")
            self.session = None

    async def search(self, query: SearchQuery) -> SearchResponse:
        """
        Execute a search query using the MCP server's search tool.

        Args:
            query: The search query to execute

        Returns:
            SearchResponse: The search results

        Raises:
            ProviderInitializationError: If the provider is not initialized
            ProviderRateLimitError: If provider rate limits are exceeded
            QueryBudgetExceededError: If query would exceed budget constraints
            ProviderQuotaExceededError: If provider budget is exceeded
            ProviderTimeoutError: If the search operation times out
            ProviderError: For other provider-specific errors
        """
        if not self.session:
            try:
                await self.initialize()
            except ProviderError as e:
                # Convert to SearchResponse with error
                return SearchResponse(
                    results=[],
                    query=query.query,
                    total_results=0,
                    provider=self.name,
                    error=str(e),
                )

        if not self.session:
            raise ProviderInitializationError(
                provider=self.name,
                message=f"Failed to initialize {self.name} MCP server",
            )

        # Generate a unique request ID for tracking
        request_id = str(uuid.uuid4())

        # Check rate limits
        rate_limited = not await self.rate_limiter.wait_if_limited(request_id)
        if rate_limited:
            cooldown = self.rate_limiter.get_cooldown_remaining()
            raise ProviderRateLimitError(
                provider=self.name,
                limit_type="requests_per_minute",
                retry_after=cooldown,
                details=self.rate_limiter.get_current_usage(),
            )

        # Estimate cost
        estimated_cost = Decimal(str(self.estimate_cost(query)))

        # Check budget if a budget constraint is specified
        if query.budget is not None and estimated_cost > Decimal(str(query.budget)):
            # Release the rate limit token
            await self.rate_limiter.release(request_id)

            from ..utils.errors import QueryBudgetExceededError

            raise QueryBudgetExceededError(
                query=query.query,
                budget=float(query.budget),
                estimated_cost=float(estimated_cost),
                details={
                    "provider": self.name,
                    "query_components": len(query.query.split()),
                },
            )

        # Check provider-level budget
        budget_exceeded = not await self.budget_tracker.check_budget(estimated_cost)
        if budget_exceeded:
            # Release the rate limit token
            await self.rate_limiter.release(request_id)

            budget_info = self.budget_tracker.get_remaining_budget()
            quota_type = "daily" if budget_info["daily_remaining"] <= 0 else "monthly"

            raise ProviderQuotaExceededError(
                provider=self.name,
                quota_type=quota_type,
                details={
                    "budget_info": budget_info,
                    "estimated_cost": float(estimated_cost),
                },
            )

        start_time = asyncio.get_event_loop().time()

        try:
            # Prepare parameters for the tool
            tool_params = self._prepare_search_params(query)

            # Call the tool with a timeout
            result = await asyncio.wait_for(
                self.session.call_tool(self.tool_name, tool_params),
                timeout=query.timeout_ms / 1000,
            )

            # Process the results
            search_results = self._process_search_results(result, query)

            # Calculate execution time
            execution_time = (asyncio.get_event_loop().time() - start_time) * 1000

            # Calculate actual cost based on result size
            actual_cost = self._calculate_actual_cost(query, search_results)

            # Record the cost
            await self.budget_tracker.record_cost(actual_cost)

            # Create response with cost information
            response = SearchResponse(
                results=search_results,
                query=query.query,
                total_results=len(search_results),
                provider=self.name,
                timing_ms=execution_time,
                cost=float(actual_cost),
            )

            # Release the rate limit token
            await self.rate_limiter.release(request_id)

            return response

        except TimeoutError:
            # Release the rate limit token
            await self.rate_limiter.release(request_id)

            execution_time = (asyncio.get_event_loop().time() - start_time) * 1000

            # Raise a proper ProviderTimeoutError
            raise ProviderTimeoutError(
                provider=self.name,
                operation="search",
                timeout=query.timeout_ms / 1000,
                details={"query": query.query, "execution_time_ms": execution_time},
            )

        except ProviderError:
            # If it's already a ProviderError, just release the token and re-raise
            await self.rate_limiter.release(request_id)
            raise

        except Exception as e:
            # Release the rate limit token
            await self.rate_limiter.release(request_id)

            execution_time = (asyncio.get_event_loop().time() - start_time) * 1000
            logger.error(f"Error executing {self.name} search: {str(e)}")

            # Map common exceptions to specific provider errors
            if isinstance(e, ConnectionError | subprocess.SubprocessError):
                raise NetworkConnectionError(
                    message=f"Failed to connect to {self.name} MCP server during search: {str(e)}",
                    url=self.name,
                    original_error=e,
                    details={"provider": self.name, "query": query.query},
                )
            # Create a generic provider service error for other exceptions
            raise ProviderServiceError.from_exception(
                e,
                provider=self.name,
                details={"query": query.query, "execution_time_ms": execution_time},
            )

    def _calculate_actual_cost(
        self, query: SearchQuery, results: list[SearchResult]
    ) -> Decimal:
        """
        Calculate the actual cost of a search based on results.

        This may differ from the estimated cost because the actual
        number of results may be different from the requested number.

        Args:
            query: The search query
            results: The search results

        Returns:
            Decimal: The actual cost in USD
        """
        # By default, use the estimated cost but adjust for actual result count
        base_cost = Decimal(str(self.estimate_cost(query)))

        # If there are no results, only charge half the base cost
        if not results:
            return base_cost * Decimal("0.5")

        # If we have fewer results than requested, adjust proportionally
        if len(results) < query.max_results:
            # Still charge at least 75% of the estimate
            result_ratio = max(
                Decimal("0.75"),
                Decimal(str(len(results))) / Decimal(str(query.max_results)),
            )
            return base_cost * result_ratio

        return base_cost

    def _prepare_search_params(self, query: SearchQuery) -> dict[str, Any]:
        """
        Prepare the parameters for the search tool call.
        Override in specific providers to customize parameters.

        Args:
            query: The search query to prepare parameters for

        Returns:
            Dict[str, Any]: The parameters to pass to the search tool
        """
        # Default implementation - basic query parameter
        return {"query": query.query}

    def _process_search_results(
        self, result: Any, query: SearchQuery
    ) -> list[SearchResult]:
        """
        Process the results from the MCP server into standardized SearchResult objects.
        Override in specific providers to handle provider-specific result formats.

        Args:
            result: The raw result from the MCP server
            query: The original query that generated these results

        Returns:
            List[SearchResult]: The processed search results
        """
        # Default implementation - assume a basic list of results
        # Most providers will need to override this
        search_results = []

        try:
            if hasattr(result, "content") and hasattr(result.content, "text"):
                # Handle text content results
                content = result.content.text
                if isinstance(content, list):
                    for item in content:
                        if isinstance(item, dict):
                            search_results.append(
                                SearchResult(
                                    title=item.get("title", ""),
                                    content=item.get("content", ""),
                                    url=item.get("url", ""),
                                    provider=self.name,
                                )
                            )
            elif isinstance(result, list):
                # Handle list results
                for item in result:
                    if isinstance(item, dict):
                        search_results.append(
                            SearchResult(
                                title=item.get("title", ""),
                                content=item.get("content", ""),
                                url=item.get("url", ""),
                                provider=self.name,
                            )
                        )
        except Exception as e:
            logger.error(f"Error processing {self.name} search results: {str(e)}")

        return search_results

    async def check_status(self) -> tuple[HealthStatus, str]:
        """
        Check the health status of the MCP server.

        Returns:
            Tuple[HealthStatus, str]: The health status and a message
        """
        if not self.session:
            try:
                await self.initialize()
            except ProviderError as e:
                # Use the specific error message but keep it classified by error type
                error_type = e.__class__.__name__
                return HealthStatus.FAILED, f"{error_type}: {str(e)}"
            except Exception as e:
                return HealthStatus.FAILED, f"Failed to initialize: {str(e)}"

        if not self.session:
            return HealthStatus.FAILED, "Not initialized"

        try:
            # Try to list tools as a lightweight health check
            tools = await asyncio.wait_for(
                self.session.list_tools(),
                timeout=self.HEALTH_CHECK_TIMEOUT,
            )

            if not tools:
                return HealthStatus.DEGRADED, "No tools available"

            # Verify our search tool is still available
            tool_names = [tool.name for tool in tools]
            if self.tool_name not in tool_names:
                return (
                    HealthStatus.DEGRADED,
                    f"Required tool '{self.tool_name}' not available",
                )

            # Check rate limit status
            if self.rate_limiter.is_in_cooldown():
                cooldown = self.rate_limiter.get_cooldown_remaining()
                return (
                    HealthStatus.DEGRADED,
                    f"{self.name} is rate limited and in cooldown for {cooldown:.1f}s",
                )

            # Check budget status
            budget_remaining = self.budget_tracker.get_remaining_budget()
            if budget_remaining["daily_remaining"] <= Decimal("0"):
                return (
                    HealthStatus.DEGRADED,
                    f"{self.name} has exhausted its daily budget",
                )

            return HealthStatus.OK, f"{self.name} MCP server is operational"

        except TimeoutError:
            return (
                HealthStatus.DEGRADED,
                f"Health check timed out after {self.HEALTH_CHECK_TIMEOUT}s",
            )

        except ProviderError as e:
            # Use the specific error message but keep it classified by error type
            error_type = e.__class__.__name__
            logger.error(
                f"{error_type} checking {self.name} MCP server status: {str(e)}"
            )
            return HealthStatus.FAILED, f"Health check failed: {error_type}: {str(e)}"

        except Exception as e:
            logger.error(f"Error checking {self.name} MCP server status: {str(e)}")
            return HealthStatus.FAILED, f"Health check failed: {str(e)}"

    def get_capabilities(self) -> dict[str, Any]:
        """Return provider capabilities."""
        return {
            "name": self.name,
            "supports_raw_content": True,
            "supports_advanced_search": False,
            "max_results_per_query": 10,
        }

    def estimate_cost(self, query: SearchQuery) -> float:
        """Estimate the cost of executing the query."""
        # Default implementation assuming a basic cost model
        # Override in specific providers with more accurate cost models
        return 0.01  # $0.01 per query as a baseline

    def get_usage_statistics(self) -> dict[str, Any]:
        """Get rate limit and budget usage statistics for this provider."""
        return {
            "rate_limits": self.rate_limiter.get_current_usage(),
            "rate_limits_remaining": self.rate_limiter.get_remaining_quota(),
            "budget": self.budget_tracker.get_usage_report(),
            "budget_remaining": self.budget_tracker.get_remaining_budget(),
            "is_rate_limited": self.rate_limiter.is_in_cooldown(),
        }

    async def __aenter__(self):
        """Context manager entry."""
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        await self._cleanup()

    def get_retry_config(self) -> RetryConfig:
        """Get retry configuration from settings.

        Returns:
            RetryConfig instance with settings from environment
        """
        settings = get_settings()
        return RetryConfig(
            max_retries=settings.retry.max_retries,
            base_delay=settings.retry.base_delay,
            max_delay=settings.retry.max_delay,
            exponential_base=settings.retry.exponential_base,
            jitter=settings.retry.jitter,
        )

    def with_retry(self, func: Callable[..., T]) -> Callable[..., T]:
        """
        Decorator to add retry logic to a method.

        Args:
            func: The async function to wrap with retry logic

        Returns:
            Wrapped function with exponential backoff retry
        """
        if not self.RETRY_ENABLED:
            return func

        return with_exponential_backoff(config=self.get_retry_config())(func)

