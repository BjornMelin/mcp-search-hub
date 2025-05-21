"""Main entry point for the MCP Search Hub server.

This module provides the main CLI interface and server initialization logic for
the MCP Search Hub. It handles command-line argument parsing, environment
configuration, and server lifecycle management including graceful shutdown.

Example:
    Run the server with stdio transport:
        $ python -m mcp_search_hub.main --transport stdio

    Run the server with HTTP transport:
        $ python -m mcp_search_hub.main --transport streamable-http --host 0.0.0.0 --port 8000

    Run with specific API keys:
        $ python -m mcp_search_hub.main --exa-api-key your_key --tavily-api-key your_key
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal
from typing import NoReturn

from .config import get_settings
from .server import SearchServer
from .utils.logging import configure_logging


async def shutdown(server: SearchServer) -> None:
    """Gracefully shutdown the server and clean up resources.

    This function handles the complete shutdown process including:
    - Closing all provider connections
    - Cancelling remaining asyncio tasks
    - Proper cleanup for different transport types

    Args:
        server: The SearchServer instance to shutdown

    Note:
        This function is designed to be called from signal handlers and
        ensures all resources are properly cleaned up regardless of the
        transport type (stdio or HTTP).
    """
    logging.info("Shutting down server...")

    try:
        # Close all provider connections
        await server.close()
        logging.info("Server shutdown complete")
    except Exception as e:
        logging.error(f"Error during shutdown: {str(e)}")

    # For STDIO transport, we need to exit the process properly
    if get_settings().transport == "stdio":
        logging.info("Exiting STDIO transport...")

    # For any transport, ensure we exit cleanly
    try:
        tasks = [
            task for task in asyncio.all_tasks() if task is not asyncio.current_task()
        ]
        for task in tasks:
            task.cancel()

        # Wait for all tasks to be cancelled
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    except Exception as e:
        logging.error(f"Error cleaning up tasks: {str(e)}")


def parse_args() -> argparse.Namespace:
    """Parse and validate command-line arguments.

    Creates an argument parser with all supported CLI options including:
    - Transport protocol selection (streamable-http or stdio)
    - Server configuration (host, port, log level)
    - Provider API keys for all supported search providers

    Returns:
        Parsed command-line arguments as a Namespace object

    Example:
        >>> args = parse_args()
        >>> print(args.transport)  # 'stdio' or 'streamable-http'
        >>> print(args.exa_api_key)  # API key if provided
    """
    parser = argparse.ArgumentParser(description="MCP Search Hub server")
    parser.add_argument(
        "--transport",
        choices=["streamable-http", "stdio"],
        help="Transport protocol (streamable-http or stdio)",
    )
    parser.add_argument(
        "--host",
        help="Host address to bind server (for HTTP transport)",
    )
    parser.add_argument(
        "--port",
        type=int,
        help="Port to bind server (for HTTP transport)",
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging level",
    )

    # Add API key arguments for each provider
    for provider in ["linkup", "exa", "perplexity", "tavily", "firecrawl"]:
        parser.add_argument(
            f"--{provider}-api-key",
            help=f"API key for {provider} provider",
        )

    return parser.parse_args()


def main() -> NoReturn:
    """Run the FastMCP search server with complete initialization.

    This is the main entry point that:
    1. Parses command-line arguments
    2. Configures environment variables and settings
    3. Sets up logging
    4. Initializes the search server
    5. Configures signal handlers for graceful shutdown
    6. Starts the server with the specified transport

    The function does not return as it runs the server indefinitely until
    a shutdown signal is received.

    Note:
        This function will not return under normal operation. It either
        runs indefinitely or exits the process on shutdown/error.

    Example:
        This is typically called via:
            python -m mcp_search_hub.main
    """
    # Parse command-line arguments
    args = parse_args()

    # Set environment variables based on command-line arguments if provided
    if args.transport:
        os.environ["TRANSPORT"] = args.transport
    if args.host:
        os.environ["HOST"] = args.host
    if args.port:
        os.environ["PORT"] = str(args.port)
    if args.log_level:
        os.environ["LOG_LEVEL"] = args.log_level

    # Handle API keys from arguments
    for provider in ["linkup", "exa", "perplexity", "tavily", "firecrawl"]:
        api_key_arg = getattr(args, f"{provider}_api_key", None)
        if api_key_arg:
            os.environ[f"{provider.upper()}_API_KEY"] = api_key_arg

    # Get settings (now incorporating any command-line arguments)
    settings = get_settings()

    # Configure logging early based on settings
    configure_logging(settings.log_level)

    server = SearchServer()

    # Setup signal handlers for graceful shutdown
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(
            sig, lambda s=sig: asyncio.create_task(shutdown(server))
        )

    # Run the server with the configured transport
    server.run(
        transport=settings.transport,
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level,
    )


if __name__ == "__main__":
    main()
