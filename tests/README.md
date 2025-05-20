# MCP Search Hub Test Suite

This directory contains the comprehensive test suite for MCP Search Hub, including unit tests, integration tests, and performance benchmarks.

## Test Organization

The test suite is organized as follows:

- **Unit Tests**: Test individual components in isolation
- **Integration Tests**: Test components working together
- **End-to-End Tests**: Test the complete search flow with mocked providers
- **Performance Benchmarks**: Measure execution time and throughput for key components

## Running Tests

### Basic Test Execution

Run all tests with pytest:

```bash
# Run all tests except benchmarks (recommended for regular development)
pytest

# Run tests with coverage report
pytest --cov=mcp_search_hub --cov-report=html
```

### Specific Test Categories

```bash
# Run only unit tests for a specific component
pytest tests/test_unified_router.py

# Run end-to-end tests
pytest tests/test_end_to_end.py

# Run performance benchmarks (these are slow)
pytest -m benchmark

# Run specific benchmark test
pytest tests/test_performance_benchmark.py::test_result_merger_benchmark -v
```

## Specialized Test Runners

### Performance Benchmarks

The `scripts/run_benchmarks.py` script provides a dedicated performance testing tool:

```bash
# Run all benchmarks
python scripts/run_benchmarks.py --all

# Run specific benchmark categories
python scripts/run_benchmarks.py --parallel --merger
```

### CI Pipeline

The GitHub Actions CI pipeline executes tests on each push and pull request. The pipeline performs:

1. **Unit Tests**: Runs all unit tests with code coverage
2. **Linting**: Checks code formatting and style with ruff
3. **Integration Tests**: Runs end-to-end tests with mocked providers
4. **Startup Test**: Verifies the server starts properly

## Writing Tests

### Guidelines for Adding Tests

1. **Unit Tests**:
   - Test one component at a time
   - Mock external dependencies
   - Name tests with `test_` prefix

2. **Integration Tests**:
   - Focus on component interactions
   - Use the fixtures in `conftest.py`
   - Test error handling between components

3. **End-to-End Tests**:
   - Add new scenarios to `test_end_to_end.py`
   - Mock provider responses
   - Test complete request flows

4. **Performance Benchmarks**:
   - Add `@pytest.mark.benchmark` decorator
   - Include self-reporting metrics
   - Test with various input sizes

### Fixtures

Common fixtures are defined in `conftest.py` and include:

- `mock_env`: Sets up environment variables for testing
- `mock_providers`: Creates mock provider instances
- `mock_server`: Sets up a test server with mock providers
- `sample_query`: Creates a sample search query
- `sample_features`: Creates sample query features

### Mocking Providers

Use the `MockProvider` class for test provider objects:

```python
# Example of creating a test provider
mock_provider = MockProvider(
    name="test_provider",
    response=SearchResponse(...),
    should_fail=False,
    delay=0.0
)
```

## Router Testing

The router tests cover both parallel and cascade execution modes:

- **Parallel Mode**: Tests concurrent execution of multiple providers
- **Cascade Mode**: Tests sequential fallback execution

The test cases include:
- Basic functionality verification
- Error handling and timeouts
- Dynamic timeout adjustment
- Provider selection strategies

## Performance Testing

Performance tests measure:

1. **Execution Time**: How long operations take to complete
2. **Throughput**: How many requests can be processed concurrently
3. **Scaling Characteristics**: How performance scales with input size

These tests help identify bottlenecks and optimize performance-critical code paths.

## CI/CD Integration

The CI pipeline is defined in `.github/workflows/tests.yml` and integrates with:

- GitHub Actions for test execution
- Codecov for coverage reporting
- Automated linting and formatting checks