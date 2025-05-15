"""Main entry point for the MCP Search Hub server."""

from .server import SearchServer
from .config import get_settings
import signal
import asyncio
import logging
import argparse
import os


async def shutdown(server: SearchServer):
    """Gracefully shutdown the server."""
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
        tasks = [task for task in asyncio.all_tasks() if task is not asyncio.current_task()]
        for task in tasks:
            task.cancel()
            
        # Wait for all tasks to be cancelled
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
            
    except Exception as e:
        logging.error(f"Error cleaning up tasks: {str(e)}")


def parse_args():
    """Parse command-line arguments."""
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


def main():
    """Run the FastMCP search server."""
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
