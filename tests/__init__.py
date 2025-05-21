"""Tests package for MCP Search Hub.

This package contains unit tests, integration tests, and performance benchmarks.

Benchmarks are marked with @pytest.mark.benchmark decorator and are
skipped by default. To run benchmarks:

    pytest -m benchmark

To run all tests except benchmarks (default):

    pytest -k "not benchmark"

To run end-to-end tests:

    pytest tests/test_end_to_end.py
"""

import pytest


# Configure pytest to skip benchmark tests by default
def pytest_configure(config):
    """Configure pytest to skip benchmark tests by default."""
    config.addinivalue_line(
        "markers", "benchmark: mark test as a performance benchmark"
    )


def pytest_collection_modifyitems(config, items):
    """Skip benchmark tests unless explicitly requested."""
    if not config.getoption("--run-benchmarks", default=False):
        skip_benchmark = pytest.mark.skip(
            reason="Benchmark tests are skipped by default"
        )
        for item in items:
            if "benchmark" in item.keywords:
                item.add_marker(skip_benchmark)


def pytest_addoption(parser):
    """Add option to run benchmark tests."""
    parser.addoption(
        "--run-benchmarks",
        action="store_true",
        default=False,
        help="run benchmark tests",
    )
