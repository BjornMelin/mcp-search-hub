"""Command-line entry point."""

from __future__ import annotations

import argparse
import asyncio
import logging
from typing import Any, NoReturn

from .config import AppSettings
from .server import SearchServer


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run MCP Search Hub")
    parser.add_argument("--transport", choices=["http", "stdio"])
    parser.add_argument("--host")
    parser.add_argument("--port", type=int)
    parser.add_argument("--http-path")
    parser.add_argument("--log-level", choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])
    return parser.parse_args()


def main() -> NoReturn:
    args = parse_args()
    overrides: dict[str, Any] = {
        name: value
        for name, value in {
            "transport": args.transport,
            "host": args.host,
            "port": args.port,
            "http_path": args.http_path,
            "log_level": args.log_level,
        }.items()
        if value is not None
    }
    settings = AppSettings(**overrides)
    logging.basicConfig(level=getattr(logging, settings.log_level))
    server = SearchServer(settings)
    try:
        if settings.transport == "stdio":
            asyncio.run(server.run_stdio())
        else:
            asyncio.run(server.run_http())
    except KeyboardInterrupt:
        raise SystemExit(0) from None
    raise SystemExit(0)


if __name__ == "__main__":
    main()
