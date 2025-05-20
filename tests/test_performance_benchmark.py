"""Performance benchmark tests for MCP Search Hub.

These tests measure execution time and throughput for key components.
They are not included in normal test runs and should be run explicitly.
"""

import asyncio
import time
from unittest.mock import AsyncMock, patch

import pytest

from mcp_search_hub.models.query import QueryFeatures, SearchQuery
from mcp_search_hub.models.results import SearchResponse, SearchResult
from mcp_search_hub.models.router import ProviderExecutionResult, TimeoutConfig
from mcp_search_hub.providers.base import SearchProvider
from mcp_search_hub.query_routing.unified_router import (
    CascadeExecutionStrategy,
    ParallelExecutionStrategy,
    UnifiedRouter,
)
from mcp_search_hub.result_processing.merger import ResultMerger


class BenchmarkProvider(SearchProvider):
    """Mock provider with adjustable response time for benchmarking."""
    
    def __init__(self, name: str, response_time_ms: float = 100):
        self.name = name
        self.response_time_ms = response_time_ms / 1000  # Convert to seconds
        self.initialized = True
    
    async def search(self, query: SearchQuery) -> SearchResponse:
        """Return a mock response after the configured delay."""
        await asyncio.sleep(self.response_time_ms)
        return SearchResponse(
            results=[
                SearchResult(
                    title=f"{self.name} result {i}",
                    url=f"https://{self.name}.com/result/{i}",
                    snippet=f"Result {i} from {self.name}",
                    score=0.9 - (0.01 * i),
                    source=self.name,
                )
                for i in range(10)  # 10 results per provider
            ],
            query=query.query,
            total_results=10,
            provider=self.name,
        )
    
    def get_capabilities(self) -> dict:
        """Return mock capabilities."""
        return {
            "content_types": ["general", "news", "academic"],
            "max_results": 100,
        }
    
    def estimate_cost(self, query: SearchQuery) -> float:
        """Estimate query cost."""
        return 0.01
    
    async def initialize(self):
        """Mock initialization."""
        return True
    
    async def close(self):
        """Mock cleanup."""
        return True


@pytest.fixture
def benchmark_providers():
    """Create a set of providers with varying response times."""
    return {
        "fast_provider": BenchmarkProvider("fast_provider", response_time_ms=50),
        "medium_provider": BenchmarkProvider("medium_provider", response_time_ms=100),
        "slow_provider": BenchmarkProvider("slow_provider", response_time_ms=200),
        "very_slow_provider": BenchmarkProvider("very_slow_provider", response_time_ms=300),
    }


@pytest.fixture
def sample_query():
    """Create a sample query for benchmarking."""
    return SearchQuery(query="benchmark test query", max_results=20)


@pytest.fixture
def sample_features():
    """Create sample query features for benchmarking."""
    return QueryFeatures(
        length=20,
        word_count=3,
        content_type="general",
        complexity=0.5,
        time_sensitivity=0.3,
        factual_nature=0.7,
        contains_question=False,
    )


@pytest.mark.benchmark
@pytest.mark.asyncio
async def test_parallel_execution_strategy_benchmark(benchmark_providers, sample_query, sample_features):
    """Benchmark parallel execution strategy."""
    strategy = ParallelExecutionStrategy()
    timeout_config = TimeoutConfig(base_timeout_ms=2000)
    
    # Measure execution time
    start_time = time.time()
    results = await strategy.execute(
        query=sample_query,
        features=sample_features,
        providers=benchmark_providers,
        selected_providers=list(benchmark_providers.keys()),
        timeout_config=timeout_config,
    )
    execution_time = time.time() - start_time
    
    # Verify basic results
    assert len(results) == len(benchmark_providers)
    
    # Log benchmark results
    print(f"\nParallel Execution Strategy Benchmark:")
    print(f"  Total execution time: {execution_time:.3f}s")
    print(f"  Provider count: {len(benchmark_providers)}")
    print(f"  Expected max time: {max(p.response_time_ms for p in benchmark_providers.values()):.3f}s")
    
    # Assert parallel execution is close to the slowest provider's time
    # (with some overhead for task management)
    max_provider_time = max(p.response_time_ms for p in benchmark_providers.values())
    assert execution_time <= max_provider_time * 1.5  # Allow 50% overhead


@pytest.mark.benchmark
@pytest.mark.asyncio
async def test_cascade_execution_strategy_benchmark(benchmark_providers, sample_query, sample_features):
    """Benchmark cascade execution strategy."""
    strategy = CascadeExecutionStrategy()
    timeout_config = TimeoutConfig(base_timeout_ms=2000)
    
    # Measure execution time
    start_time = time.time()
    results = await strategy.execute(
        query=sample_query,
        features=sample_features,
        providers=benchmark_providers,
        selected_providers=list(benchmark_providers.keys()),
        timeout_config=timeout_config,
    )
    execution_time = time.time() - start_time
    
    # Log benchmark results
    print(f"\nCascade Execution Strategy Benchmark:")
    print(f"  Total execution time: {execution_time:.3f}s")
    print(f"  Provider count: {len(benchmark_providers)}")
    print(f"  First provider time: {list(benchmark_providers.values())[0].response_time_ms:.3f}s")
    
    # Assert cascade execution is close to the first provider's time
    # (with some overhead for task management)
    first_provider_time = list(benchmark_providers.values())[0].response_time_ms
    assert execution_time <= first_provider_time * 1.5  # Allow 50% overhead


@pytest.mark.benchmark
@pytest.mark.asyncio
async def test_result_merger_benchmark():
    """Benchmark result merger performance with increasing number of results."""
    merger = ResultMerger()
    
    # Create test sizes with increasing number of providers/results
    test_sizes = [5, 10, 20, 50]
    
    for provider_count in test_sizes:
        # Create mock provider results
        provider_results = {}
        for i in range(provider_count):
            provider_name = f"provider_{i}"
            results = []
            
            # Each provider returns 10 results
            for j in range(10):
                results.append(
                    SearchResult(
                        title=f"Result {j} from {provider_name}",
                        url=f"https://example{i}.com/result{j}",
                        snippet=f"This is result {j} from provider {i}",
                        score=0.9 - (0.01 * j),
                        source=provider_name,
                    )
                )
            
            # Create provider execution result
            provider_results[provider_name] = ProviderExecutionResult(
                provider_name=provider_name,
                success=True,
                response=SearchResponse(
                    results=results,
                    query="benchmark query",
                    total_results=len(results),
                    provider=provider_name,
                ),
                duration_ms=100,
            )
        
        # Measure merger performance
        start_time = time.time()
        merged_results = merger.merge_results(provider_results)
        merger_time = time.time() - start_time
        
        # Log results
        print(f"\nResult Merger Benchmark - {provider_count} providers:")
        print(f"  Merger execution time: {merger_time:.3f}s")
        print(f"  Total input results: {provider_count * 10}")
        print(f"  Total output results: {len(merged_results)}")
        
        # Verify merged results
        assert len(merged_results) <= provider_count * 10  # Some may be deduplicated


@pytest.mark.benchmark
@pytest.mark.asyncio
async def test_router_benchmark(benchmark_providers, sample_query, sample_features):
    """Benchmark overall router performance."""
    router = UnifiedRouter(providers=benchmark_providers)
    
    # Test performance of different strategies
    strategies = ["parallel", "cascade"]
    
    for strategy in strategies:
        # Measure router performance
        start_time = time.time()
        results = await router.route_and_execute(
            query=sample_query,
            features=sample_features,
            strategy=strategy,
        )
        router_time = time.time() - start_time
        
        # Log results
        print(f"\nRouter Benchmark - {strategy} strategy:")
        print(f"  Total execution time: {router_time:.3f}s")
        print(f"  Provider count: {len(benchmark_providers)}")
        print(f"  Selected providers: {len(results)}")
        
        # Verify results
        assert len(results) > 0
        assert all(isinstance(r, ProviderExecutionResult) for r in results.values())


@pytest.mark.benchmark
@pytest.mark.asyncio
async def test_throughput_benchmark(sample_query, sample_features):
    """Benchmark throughput with many concurrent queries."""
    # Configure a set of fast providers for throughput testing
    providers = {f"provider_{i}": BenchmarkProvider(f"provider_{i}", response_time_ms=50) 
                 for i in range(5)}
    
    router = UnifiedRouter(providers=providers)
    merger = ResultMerger()
    
    # Define throughput test parameters
    concurrent_queries = 20
    
    # Create tasks
    tasks = []
    start_time = time.time()
    
    for i in range(concurrent_queries):
        # Customize query slightly to prevent complete cache hits
        query = SearchQuery(query=f"benchmark throughput query {i}", max_results=10)
        
        # Create and store task
        tasks.append(
            router.route_and_execute(
                query=query,
                features=sample_features,
                strategy="parallel",
            )
        )
    
    # Wait for all tasks to complete
    provider_results = await asyncio.gather(*tasks)
    
    # Process results through merger
    merged_results = []
    for results in provider_results:
        merged_results.append(merger.merge_results(results))
    
    # Calculate throughput metrics
    total_time = time.time() - start_time
    queries_per_second = concurrent_queries / total_time
    
    # Log throughput results
    print(f"\nThroughput Benchmark:")
    print(f"  Total execution time: {total_time:.3f}s")
    print(f"  Concurrent queries: {concurrent_queries}")
    print(f"  Throughput: {queries_per_second:.2f} queries/second")
    print(f"  Average query time: {(total_time / concurrent_queries) * 1000:.2f}ms")
    
    # Verify results
    assert len(merged_results) == concurrent_queries
    assert all(len(r) > 0 for r in merged_results)