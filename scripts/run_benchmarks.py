#!/usr/bin/env python3
"""
Script to run performance benchmarks for MCP Search Hub.

This script runs the benchmark tests and outputs detailed performance metrics.
"""

import argparse
import asyncio
import os
import sys
import time
from datetime import datetime

# Add parent directory to path to allow importing from mcp_search_hub
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from mcp_search_hub.models.query import QueryFeatures, SearchQuery
from mcp_search_hub.models.router import TimeoutConfig
from mcp_search_hub.query_routing.unified_router import (
    CascadeExecutionStrategy,
    ParallelExecutionStrategy,
    UnifiedRouter,
)
from mcp_search_hub.result_processing.merger import ResultMerger
from tests.test_performance_benchmark import BenchmarkProvider


async def benchmark_parallel_strategy(provider_counts=None, result_counts=None):
    """Benchmark parallel execution strategy with different provider counts."""
    if provider_counts is None:
        provider_counts = [2, 5, 10]
    if result_counts is None:
        result_counts = [10, 20, 50]

    print("\n======== Parallel Strategy Benchmark ========")

    for provider_count in provider_counts:
        print(f"\nRunning with {provider_count} providers:")

        # Create providers with varying response times
        providers = {}
        for i in range(provider_count):
            # Response times between 50-200ms
            response_time = 50 + (i % 3) * 75
            providers[f"provider_{i}"] = BenchmarkProvider(
                f"provider_{i}", response_time_ms=response_time
            )

        # Create query
        query = SearchQuery(query=f"benchmark query with {provider_count} providers")
        features = QueryFeatures(
            length=10,
            word_count=3,
            content_type="general",
            complexity=0.5,
            time_sensitivity=0.3,
            factual_nature=0.7,
            contains_question=False,
        )
        timeout_config = TimeoutConfig(base_timeout_ms=5000)

        # Create strategy
        strategy = ParallelExecutionStrategy()

        # Run benchmark
        start_time = time.time()
        results = await strategy.execute(
            query=query,
            features=features,
            providers=providers,
            selected_providers=list(providers.keys()),
            timeout_config=timeout_config,
        )
        execution_time = time.time() - start_time

        # Print results
        print(f"  Execution time: {execution_time:.3f}s")
        print(
            f"  Successful providers: {sum(1 for r in results.values() if r.success)}/{provider_count}"
        )
        response_times = [p.response_time_ms for p in providers.values()]
        print(
            f"  Provider response times: min={min(response_times):.0f}ms, max={max(response_times):.0f}ms"
        )
        print(f"  Theoretical minimum time: {max(response_times) / 1000:.3f}s")
        print(f"  Overhead: {execution_time - max(response_times) / 1000:.3f}s")


async def benchmark_cascade_strategy(provider_counts=None, fail_rates=None):
    """Benchmark cascade execution strategy with different failure rates."""
    if provider_counts is None:
        provider_counts = [2, 5, 10]
    if fail_rates is None:
        fail_rates = [0, 0.5]

    print("\n======== Cascade Strategy Benchmark ========")

    for provider_count in provider_counts:
        for fail_rate in fail_rates:
            print(
                f"\nRunning with {provider_count} providers, {fail_rate * 100:.0f}% fail rate:"
            )

            # Create providers
            providers = {}
            for i in range(provider_count):
                # Response times between 50-150ms
                response_time = 50 + (i % 2) * 50

                # Should this provider fail?
                should_fail = (i / provider_count) < fail_rate

                providers[f"provider_{i}"] = BenchmarkProvider(
                    f"provider_{i}", response_time_ms=response_time
                )
                if should_fail:
                    # Make provider fail
                    providers[f"provider_{i}"].should_fail = True

            # Create query
            query = SearchQuery(query="benchmark cascade query")
            features = QueryFeatures(
                length=10,
                word_count=3,
                content_type="general",
                complexity=0.5,
                time_sensitivity=0.3,
                factual_nature=0.7,
                contains_question=False,
            )
            timeout_config = TimeoutConfig(base_timeout_ms=5000)

            # Create strategy
            strategy = CascadeExecutionStrategy()

            # Run benchmark
            start_time = time.time()
            results = await strategy.execute(
                query=query,
                features=features,
                providers=providers,
                selected_providers=list(providers.keys()),
                timeout_config=timeout_config,
            )
            execution_time = time.time() - start_time

            # Print results
            print(f"  Execution time: {execution_time:.3f}s")
            print(f"  Providers tried: {len(results)}/{provider_count}")
            print(
                f"  Successful providers: {sum(1 for r in results.values() if r.success)}/{len(results)}"
            )

            # Calculate how long before we found a successful provider
            fail_count = sum(1 for r in results.values() if not r.success)
            response_times = [
                p.response_time_ms for p in list(providers.values())[: fail_count + 1]
            ]
            print(f"  Theoretical minimum time: {sum(response_times) / 1000:.3f}s")
            print(f"  Overhead: {execution_time - sum(response_times) / 1000:.3f}s")


async def benchmark_result_merger(result_counts=None):
    """Benchmark result merger with different numbers of results."""
    if result_counts is None:
        result_counts = [50, 100, 500, 1000]

    print("\n======== Result Merger Benchmark ========")

    merger = ResultMerger()

    for result_count in result_counts:
        print(f"\nMerging {result_count} total results:")

        # Create mock provider results (5 providers with result_count/5 results each)
        from mcp_search_hub.models.results import SearchResponse, SearchResult
        from mcp_search_hub.models.router import ProviderExecutionResult

        provider_count = 5
        results_per_provider = result_count // provider_count
        provider_results = {}

        for i in range(provider_count):
            provider_name = f"provider_{i}"
            results = []

            for j in range(results_per_provider):
                # Add some duplicates for deduplication testing
                url_suffix = j if j % 5 != 0 else (j // 5)

                results.append(
                    SearchResult(
                        title=f"Result {j} from {provider_name}",
                        url=f"https://example.com/result{url_suffix}",
                        snippet=f"This is result {j} from provider {i}",
                        score=0.9 - (0.01 * j),
                        source=provider_name,
                    )
                )

            provider_results[provider_name] = ProviderExecutionResult(
                provider_name=provider_name,
                success=True,
                response=SearchResponse(
                    results=results,
                    query="benchmark merger query",
                    total_results=len(results),
                    provider=provider_name,
                ),
                duration_ms=100,
            )

        # Run benchmark
        start_time = time.time()
        merged_results = merger.merge_results(provider_results)
        execution_time = time.time() - start_time

        # Print results
        print(f"  Execution time: {execution_time:.3f}s")
        print(f"  Results per provider: {results_per_provider}")
        print(f"  Input result count: {result_count}")
        print(f"  Output result count: {len(merged_results)}")
        print(
            f"  Deduplication rate: {(result_count - len(merged_results)) / result_count * 100:.1f}%"
        )
        print(f"  Processing rate: {result_count / execution_time:.1f} results/second")


async def benchmark_throughput(concurrent_queries=None):
    """Benchmark system throughput with concurrent queries."""
    if concurrent_queries is None:
        concurrent_queries = [5, 10, 20, 50]

    print("\n======== System Throughput Benchmark ========")

    for concurrency in concurrent_queries:
        print(f"\nConcurrent queries: {concurrency}")

        # Create a set of providers
        providers = {
            f"provider_{i}": BenchmarkProvider(f"provider_{i}", response_time_ms=100)
            for i in range(3)
        }

        # Create router and merger
        router = UnifiedRouter(providers=providers)
        merger = ResultMerger()

        # Sample query features
        features = QueryFeatures(
            length=20,
            word_count=4,
            content_type="general",
            complexity=0.5,
            time_sensitivity=0.3,
            factual_nature=0.7,
            contains_question=False,
        )

        # Create tasks
        tasks = []
        start_time = time.time()

        for i in range(concurrency):
            query = SearchQuery(query=f"throughput benchmark query {i}")

            # Create task for routing and merging
            tasks.append(
                asyncio.create_task(
                    router.route_and_execute(
                        query=query,
                        features=features,
                        strategy="parallel",
                    )
                )
            )

        # Wait for all results
        provider_results = await asyncio.gather(*tasks)

        # Merge results
        merger_tasks = []
        for results in provider_results:
            merger_tasks.append(
                asyncio.create_task(asyncio.to_thread(merger.merge_results, results))
            )

        merged_results = await asyncio.gather(*merger_tasks)

        # Calculate metrics
        total_time = time.time() - start_time

        # Print results
        print(f"  Total execution time: {total_time:.3f}s")
        print(f"  Throughput: {concurrency / total_time:.2f} queries/second")
        print(f"  Average query time: {(total_time / concurrency) * 1000:.2f}ms")
        print(
            f"  Results per query: {sum(len(r) for r in merged_results) / concurrency:.1f}"
        )


async def main():
    """Run all benchmarks and output results."""
    parser = argparse.ArgumentParser(
        description="Run MCP Search Hub performance benchmarks"
    )
    parser.add_argument(
        "--parallel", action="store_true", help="Run parallel strategy benchmarks"
    )
    parser.add_argument(
        "--cascade", action="store_true", help="Run cascade strategy benchmarks"
    )
    parser.add_argument(
        "--merger", action="store_true", help="Run result merger benchmarks"
    )
    parser.add_argument(
        "--throughput", action="store_true", help="Run throughput benchmarks"
    )
    parser.add_argument("--all", action="store_true", help="Run all benchmarks")

    args = parser.parse_args()

    # If no specific benchmarks are selected, run all
    run_all = args.all or not (
        args.parallel or args.cascade or args.merger or args.throughput
    )

    # Print header
    print("MCP Search Hub Performance Benchmarks")
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'=' * 50}")

    # Run selected benchmarks
    if args.parallel or run_all:
        await benchmark_parallel_strategy()

    if args.cascade or run_all:
        await benchmark_cascade_strategy()

    if args.merger or run_all:
        await benchmark_result_merger()

    if args.throughput or run_all:
        await benchmark_throughput()

    print(f"\n{'=' * 50}")
    print("Benchmark complete")


if __name__ == "__main__":
    asyncio.run(main())
