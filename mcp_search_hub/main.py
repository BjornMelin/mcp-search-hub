"""Main entry point for the MCP Search Hub server."""

from .server import SearchServer
from .config import get_settings
import signal
import asyncio
import logging


async def shutdown(server: SearchServer):
    """Gracefully shutdown the server."""
    logging.info("Shutting down server...")
    await server.close()
    logging.info("Server shutdown complete")


def main():
    """Run the FastMCP search server."""
    settings = get_settings()
    server = SearchServer()
    
    # Setup signal handlers for graceful shutdown
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(
            sig, lambda s=sig: asyncio.create_task(shutdown(server))
        )
    
    # Run the server
    server.run(
        transport="streamable-http",
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level
    )


if __name__ == "__main__":
    main()