# Development Guide

This guide covers development workflows, testing practices, and maintenance procedures for MCP Search Hub.

## Table of Contents

- [Development Environment](#development-environment)
- [Project Structure](#project-structure)
- [Development Workflows](#development-workflows)
- [Testing Strategy](#testing-strategy)
- [Debugging and Troubleshooting](#debugging-and-troubleshooting)
- [Performance Analysis](#performance-analysis)
- [Release Process](#release-process)
- [Maintenance Tasks](#maintenance-tasks)

## Development Environment

### Quick Setup

```bash
# Clone and setup
git clone https://github.com/BjornMelin/mcp-search-hub.git
cd mcp-search-hub

# Development environment with all tools
make setup-dev
# OR manually:
python -m venv venv
source venv/bin/activate
uv pip install -r requirements.txt -r requirements-development.txt
pre-commit install
```

### Development Dependencies

The development environment includes:

```txt
# requirements-development.txt
pytest>=7.4.0
pytest-asyncio>=0.21.0
pytest-cov>=4.1.0
pytest-mock>=3.11.0
httpx>=0.24.0
ruff>=0.0.280
pre-commit>=3.3.0
mypy>=1.5.0
black>=23.7.0
```

### IDE Configuration

#### VS Code

```json
// .vscode/settings.json
{
  "python.defaultInterpreterPath": "./venv/bin/python",
  "python.linting.enabled": true,
  "python.linting.ruffEnabled": true,
  "python.formatting.provider": "ruff",
  "python.testing.pytestEnabled": true,
  "python.testing.pytestArgs": ["tests"],
  "files.exclude": {
    "**/__pycache__": true,
    "**/.pytest_cache": true,
    "**/venv": true
  }
}
```

#### PyCharm

- Set interpreter to `./venv/bin/python`
- Enable pytest as test runner
- Configure ruff as external tool
- Set up run configurations for common tasks

### Environment Variables

Development `.env` file:

```bash
# Development settings
LOG_LEVEL=DEBUG
TRANSPORT=http
HOST=127.0.0.1
PORT=8000

# Test API keys (use test/sandbox keys when available)
LINKUP_API_KEY=test_key_or_real_key
EXA_API_KEY=test_key_or_real_key
PERPLEXITY_API_KEY=test_key_or_real_key

# Development-specific settings
CACHE_TTL=60                    # Short cache for testing
MIDDLEWARE_LOGGING_INCLUDE_BODY=true
CIRCUIT_BREAKER_ENABLED=false  # Disable for easier debugging
```

## Project Structure

### Code Organization

```
mcp_search_hub/
├── __init__.py
├── main.py                     # Entry point
├── server.py                   # FastMCP server implementation
├── config/
│   ├── __init__.py
│   └── settings.py             # Configuration management
├── models/                     # Pydantic models
│   ├── __init__.py
│   ├── base.py                 # Base model classes
│   ├── query.py                # Query models
│   ├── results.py              # Result models
│   └── providers.py            # Provider models
├── providers/                  # Provider implementations
│   ├── __init__.py
│   ├── base.py                 # Base provider interface
│   ├── generic_mcp.py          # Generic MCP provider
│   ├── provider_config.py      # Provider configurations
│   ├── *_mcp.py               # Provider-specific implementations
│   ├── rate_limiter.py         # Rate limiting logic
│   └── budget_tracker.py       # Budget management
├── query_routing/              # Query analysis and routing
│   ├── __init__.py
│   ├── analyzer.py             # Query analysis
│   ├── hybrid_router.py        # Main routing logic
│   └── cost_optimizer.py       # Cost optimization
├── result_processing/          # Result handling
│   ├── __init__.py
│   ├── merger.py               # Result merging and ranking
│   └── deduplication.py        # Duplicate removal
├── middleware/                 # Cross-cutting concerns
│   ├── __init__.py
│   ├── auth.py                 # Authentication
│   ├── logging.py              # Request logging
│   ├── rate_limit.py           # Rate limiting
│   └── error_handler.py        # Error handling
└── utils/                      # Utilities
    ├── __init__.py
    ├── cache.py                # Caching implementations
    ├── errors.py               # Custom exceptions
    ├── logging.py              # Logging configuration
    └── metrics.py              # Metrics collection
```

### Key Design Patterns

1. **Provider Pattern**: All search providers implement `SearchProvider` interface
2. **Generic MCP Integration**: `GenericMCPProvider` handles common MCP server interactions
3. **Configuration-Driven**: Provider behavior controlled by `provider_config.py`
4. **Middleware Stack**: Cross-cutting concerns implemented as middleware
5. **Async-First**: All I/O operations use async/await patterns

## Development Workflows

### Daily Development

```bash
# Start development server with hot reload
python -m mcp_search_hub.main --debug

# Run tests continuously during development
pytest --watch

# Lint and format before committing
make lint
make format
```

### Common Tasks

#### Adding a New Provider

1. **Research the provider's MCP server**:
   ```bash
   # Check if official MCP server exists
   npm search @provider-name/mcp
   # OR check GitHub for provider-name-mcp-server
   ```

2. **Add provider configuration**:
   ```python
   # providers/provider_config.py
   "newprovider": {
       "name": "New Provider",
       "mcp_server": {
           "type": "node",  # or "python"
           "package": "@newprovider/mcp-server",
           "command": ["npx", "@newprovider/mcp-server"],
           "install_check": ["npm", "list", "-g", "@newprovider/mcp-server"]
       },
       # ... other config
   }
   ```

3. **Create provider wrapper**:
   ```python
   # providers/newprovider_mcp.py
   from .generic_mcp import GenericMCPProvider

   class NewProviderMCPProvider(GenericMCPProvider):
       def __init__(self):
           super().__init__("newprovider")
   ```

4. **Add tests**:
   ```python
   # tests/test_newprovider_mcp.py
   # Follow existing test patterns
   ```

5. **Update documentation**:
   - Add to `CONFIGURATION.md`
   - Update `API_REFERENCE.md`
   - Add example usage

#### Debugging Provider Issues

```python
# Enable detailed MCP logging
import logging
logging.getLogger("mcp").setLevel(logging.DEBUG)

# Test provider directly
from mcp_search_hub.providers.exa_mcp import ExaMCPProvider
provider = ExaMCPProvider()
await provider.initialize()
result = await provider.search(query)
```

#### Testing New Features

```bash
# Run specific test module
pytest tests/test_analyzer.py -v

# Test with coverage
pytest --cov=mcp_search_hub --cov-report=html

# Integration tests with real APIs (use sparingly)
pytest tests/test_integration.py --real-apis
```

## Testing Strategy

### Test Pyramid

```
    E2E Tests (Few)
   Integration Tests (Some)
  Unit Tests (Many)
```

### Test Categories

#### Unit Tests
- Fast, isolated, no external dependencies
- Mock all I/O operations
- Test individual functions and classes

```python
# Example unit test
@pytest.mark.asyncio
async def test_query_analyzer_content_type():
    analyzer = QueryAnalyzer()
    
    query = SearchQuery(query="latest research papers")
    features = await analyzer.analyze_query(query)
    
    assert features.content_type == "ACADEMIC"
    assert features.complexity > 0.5
```

#### Integration Tests
- Test component interactions
- Use test databases/caches
- Mock external APIs

```python
# Example integration test
@pytest.mark.asyncio
async def test_search_with_multiple_providers():
    # Use test configuration
    server = SearchServer(test_config)
    
    with mock_provider_responses():
        result = await server.search(SearchQuery(query="test"))
        
    assert len(result.results) > 0
    assert result.providers_used == ["linkup", "exa"]
```

#### End-to-End Tests
- Full system tests
- Real provider APIs (limited use)
- Production-like configuration

```python
# Example E2E test
@pytest.mark.e2e
@pytest.mark.skipif(not os.getenv("REAL_APIs"), reason="Real API test")
async def test_full_search_flow():
    result = await client.invoke("search", {
        "query": "Python programming tutorial",
        "max_results": 3
    })
    
    assert result["total_results"] >= 3
    assert all("python" in r["title"].lower() for r in result["results"])
```

### Test Data Management

```python
# conftest.py - Shared test fixtures
@pytest.fixture
def sample_search_query():
    return SearchQuery(
        query="artificial intelligence",
        max_results=10,
        content_type="TECHNICAL"
    )

@pytest.fixture
def mock_provider_response():
    return [
        SearchResult(
            title="AI Research Paper",
            url="https://example.com/ai-paper",
            snippet="Latest developments in AI...",
            score=0.95,
            source="test_provider"
        )
    ]
```

### Performance Testing

```bash
# Load testing with pytest-benchmark
pytest tests/test_performance.py --benchmark-only

# Memory profiling
pytest tests/test_memory.py --profile

# Async concurrency testing
pytest tests/test_concurrency.py -v
```

## Debugging and Troubleshooting

### Logging Configuration

```python
# Development logging setup
import logging

# Detailed logging for development
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# MCP-specific logging
logging.getLogger("mcp").setLevel(logging.DEBUG)
logging.getLogger("mcp_search_hub").setLevel(logging.DEBUG)
```

### Common Debug Scenarios

#### Provider Connection Issues

```python
# Debug MCP server startup
from mcp_search_hub.providers.exa_mcp import ExaMCPProvider

provider = ExaMCPProvider()
try:
    await provider.initialize()
    print("Provider initialized successfully")
except Exception as e:
    print(f"Initialization failed: {e}")
    # Check server logs, API keys, network connectivity
```

#### Cache Issues

```python
# Debug cache behavior
from mcp_search_hub.utils.cache import TieredCache

cache = TieredCache()
key = "test_key"
value = {"test": "data"}

await cache.set(key, value)
cached_value = await cache.get(key)
print(f"Cache working: {cached_value == value}")
```

#### Query Routing Issues

```python
# Debug query analysis
from mcp_search_hub.query_routing.analyzer import QueryAnalyzer

analyzer = QueryAnalyzer()
query = SearchQuery(query="your problematic query")
features = await analyzer.analyze_query(query)

print(f"Content type: {features.content_type}")
print(f"Complexity: {features.complexity}")
print(f"Keywords: {features.keywords}")
```

### Debugging Tools

```bash
# Use pdb for interactive debugging
python -m pdb -m mcp_search_hub.main

# Use asyncio debug mode
PYTHONDEV=1 python -m mcp_search_hub.main

# Memory debugging
python -m tracemalloc -m mcp_search_hub.main
```

## Performance Analysis

### Monitoring Performance

```python
# Built-in metrics collection
from mcp_search_hub.utils.metrics import MetricsCollector

metrics = MetricsCollector()
with metrics.timer("search_operation"):
    result = await search_function()

print(f"Search took: {metrics.get_timing('search_operation')}ms")
```

### Profiling

```bash
# Profile with cProfile
python -m cProfile -o profile.stats -m mcp_search_hub.main

# Analyze profile
python -c "
import pstats
p = pstats.Stats('profile.stats')
p.sort_stats('cumulative').print_stats(20)
"

# Memory profiling with memory_profiler
pip install memory_profiler
python -m memory_profiler mcp_search_hub/server.py
```

### Performance Benchmarks

```python
# Benchmark critical paths
@pytest.mark.benchmark
def test_query_analysis_performance(benchmark):
    analyzer = QueryAnalyzer()
    query = SearchQuery(query="test query")
    
    result = benchmark(analyzer.analyze_query, query)
    assert result.content_type is not None
```

### Load Testing

```bash
# Use locust for load testing
pip install locust

# Create locustfile.py for MCP Search Hub
# Run load test
locust -f tests/load_test.py --host=http://localhost:8000
```

## Release Process

### Version Management

```bash
# Update version in __init__.py
echo "__version__ = '1.2.0'" > mcp_search_hub/__init__.py

# Tag release
git tag -a v1.2.0 -m "Release version 1.2.0"
git push origin v1.2.0
```

### Pre-release Checklist

- [ ] All tests pass
- [ ] Documentation updated
- [ ] Performance regression tests pass
- [ ] Security scan clean
- [ ] Breaking changes documented
- [ ] Migration guide provided (if needed)

### Automated Release

GitHub Actions handles:
- Testing on multiple Python versions
- Security scanning
- Docker image building
- Documentation deployment
- PyPI package publishing

## Maintenance Tasks

### Regular Maintenance

```bash
# Update dependencies weekly
uv pip compile requirements.in
uv pip compile requirements-development.in

# Security updates
pip-audit

# Clean up old test artifacts
find . -type d -name "__pycache__" -exec rm -rf {} +
find . -type d -name ".pytest_cache" -exec rm -rf {} +
```

### Database Migrations

```python
# Cache schema updates
# Update cache key format when needed
CACHE_VERSION = "v2"  # Increment when format changes

# Budget tracking schema
# Migrate budget data when adding new fields
```

### Provider Updates

```bash
# Check for provider MCP server updates
npm outdated -g @modelcontextprotocol/server-exa
pip list --outdated | grep mcp-search

# Test new provider versions
pytest tests/test_provider_integration.py --provider=exa
```

### Monitoring and Alerts

```python
# Health check implementation
async def health_check():
    checks = {
        "providers": await check_all_providers(),
        "cache": await check_cache_connectivity(),
        "memory": check_memory_usage(),
        "disk": check_disk_space()
    }
    return {"status": "healthy" if all(checks.values()) else "unhealthy", **checks}
```

### Backup and Recovery

```bash
# Configuration backup
tar -czf config-backup-$(date +%Y%m%d).tar.gz .env provider_configs/

# Cache backup (if using persistent cache)
redis-cli --rdb cache-backup-$(date +%Y%m%d).rdb

# Log rotation
logrotate /etc/logrotate.d/mcp-search-hub
```

---

This development guide is a living document. Update it as the project evolves and new development practices are established.