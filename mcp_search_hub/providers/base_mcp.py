"""Base implementation for MCP server providers.

This module provides a unified base class for all MCP server implementations
to reduce code duplication and standardize provider behavior.
"""

import asyncio
import logging
import os
import subprocess
import sys
from enum import Enum
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from ..models.base import HealthStatus
from ..models.query import SearchQuery
from ..models.results import SearchResponse, SearchResult
from ..utils.errors import ProviderError
from .base import SearchProvider

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
    """

    # Constants for installation and health check
    INSTALLATION_RETRY_COUNT = 2
    INSTALLATION_CHECK_TIMEOUT = 10  # seconds
    HEALTH_CHECK_TIMEOUT = 5  # seconds

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

    def _configure_api_key(self, api_key: str | None, env_var_name: str | None) -> None:
        """Configure the API key from input or environment variable."""
        if api_key:
            self.api_key = api_key
        elif env_var_name:
            self.api_key = os.getenv(env_var_name)
        else:
            self.api_key = None

        if not self.api_key:
            raise ValueError(f"{self.name} API key is required")

    def _get_default_command(self) -> str:
        """Get the default command based on server type."""
        if self.server_type == ServerType.NODE_JS:
            return "npx"
        if self.server_type == ServerType.PYTHON:
            return sys.executable
        raise ValueError(f"Unsupported server type: {self.server_type}")

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
                    raise ProviderError(f"Failed to install {self.name} MCP server")

            # Connect to the server
            logger.info(f"Connecting to {self.name} MCP server...")
            read_stream, write_stream = await stdio_client(self.server_params)
            self.session = ClientSession(read_stream, write_stream)

            # Initialize the session
            await self.session.__aenter__()

            # Verify tools are available
            tools = await self.session.list_tools()
            if not tools:
                raise ProviderError(f"No tools available from {self.name} MCP server")

            tool_names = [tool.name for tool in tools]
            if self.tool_name not in tool_names:
                raise ProviderError(
                    f"Required tool '{self.tool_name}' not available in {self.name} MCP server. "
                    f"Available tools: {', '.join(tool_names)}"
                )

            logger.info(f"Successfully connected to {self.name} MCP server")

        except Exception as e:
            logger.error(f"Error initializing {self.name} MCP server: {str(e)}")
            # Cleanup any partial initialization
            await self._cleanup()
            raise ProviderError(
                f"Failed to initialize {self.name} MCP server: {str(e)}"
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
                raise ProviderError(
                    f"Cannot install {self.name}: no package name specified"
                )

            cmd = ["npm", "install", "-g", package_name]

        elif self.server_type == ServerType.PYTHON:
            module_name = self.args[1] if len(self.args) > 1 else None
            if not module_name:
                raise ProviderError(
                    f"Cannot install {self.name}: no module name specified"
                )

            cmd = [sys.executable, "-m", "pip", "install", module_name]

        else:
            raise ProviderError(
                f"Cannot install {self.name}: unsupported server type {self.server_type}"
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
            raise ProviderError(
                f"Failed to install {self.name} MCP server: {error_msg}"
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
        """
        if not self.session:
            await self.initialize()

        if not self.session:
            return SearchResponse(
                results=[],
                query=query.query,
                total_results=0,
                provider=self.name,
                error=f"Failed to initialize {self.name} MCP server",
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

            return SearchResponse(
                results=search_results,
                query=query.query,
                total_results=len(search_results),
                provider=self.name,
                timing_ms=execution_time,
            )

        except TimeoutError:
            execution_time = (asyncio.get_event_loop().time() - start_time) * 1000
            return SearchResponse(
                results=[],
                query=query.query,
                total_results=0,
                provider=self.name,
                error=f"Search timed out after {query.timeout_ms}ms",
                timing_ms=execution_time,
            )

        except Exception as e:
            execution_time = (asyncio.get_event_loop().time() - start_time) * 1000
            logger.error(f"Error executing {self.name} search: {str(e)}")
            return SearchResponse(
                results=[],
                query=query.query,
                total_results=0,
                provider=self.name,
                error=f"Search failed: {str(e)}",
                timing_ms=execution_time,
            )

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

            return HealthStatus.OK, f"{self.name} MCP server is operational"

        except TimeoutError:
            return HealthStatus.DEGRADED, "Health check timed out"

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

    async def __aenter__(self):
        """Context manager entry."""
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        await self._cleanup()
