"""CLI entry point for launching the MCP Search Hub."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
from typing import NoReturn

from .config import get_settings
from .server import SearchServer


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the MCP Search Hub server")
    parser.add_argument(
        "--transport",
        choices=["streamable-http", "stdio"],
        help="Transport to use when launching the server",
    )
    parser.add_argument("--host", help="Override host for HTTP transport")
    parser.add_argument("--port", type=int, help="Override port for HTTP transport")
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Override log level",
    )
    return parser.parse_args()


def main() -> NoReturn:
    args = parse_args()

    if args.transport:
        os.environ["TRANSPORT"] = args.transport
    if args.host:
        os.environ["HOST"] = args.host
    if args.port:
        os.environ["PORT"] = str(args.port)
    if args.log_level:
        os.environ["LOG_LEVEL"] = args.log_level

    settings = get_settings()
    logging.basicConfig(level=getattr(logging, settings.log_level, logging.INFO))

    server = SearchServer(settings=settings)

    try:
        if settings.transport == "stdio":
            asyncio.run(server.run_stdio())
        else:
            asyncio.run(server.run_http())
    except KeyboardInterrupt:  # pragma: no cover - CLI interruption
        logging.info("Shutting down MCP Search Hub")
        raise SystemExit(0) from None


if __name__ == "__main__":
    main()
