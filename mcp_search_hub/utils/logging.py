"""Logging configuration."""

import logging
import sys
from typing import Any


def configure_logging(log_level: str = "INFO") -> logging.Logger:
    """
    Configure logging for the application.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)

    Returns:
        Configured logger instance
    """
    # Convert string log level to logging constant
    numeric_level = getattr(logging, log_level.upper(), None)
    if not isinstance(numeric_level, int):
        numeric_level = logging.INFO

    # Configure root logger
    logger = logging.getLogger("mcp_search_hub")
    logger.setLevel(numeric_level)

    # Configure handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(numeric_level)

    # Configure formatter
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)

    # Add handler to logger
    logger.addHandler(handler)

    return logger


def log_query(
    logger: logging.Logger,
    query: dict[str, Any],
    features: dict[str, Any] | None = None,
):
    """
    Log query information.

    Args:
        logger: Logger instance
        query: Query information
        features: Optional extracted features
    """
    logger.info(f"Query: {query}")
    if features:
        logger.debug(f"Features: {features}")


def log_provider_selection(
    logger: logging.Logger, providers: dict[str, Any], selected: list[str]
):
    """
    Log provider selection.

    Args:
        logger: Logger instance
        providers: Available providers
        selected: Selected provider names
    """
    logger.info(f"Selected providers: {', '.join(selected)}")
    logger.debug(f"Available providers: {', '.join(providers.keys())}")


def log_results(logger: logging.Logger, results: dict[str, Any]):
    """
    Log result information.

    Args:
        logger: Logger instance
        results: Result information
    """
    logger.info(f"Total results: {results.get('total_results', 0)}")
    logger.info(f"Total cost: {results.get('total_cost', 0.0)}")
    logger.debug(f"Results: {results}")
