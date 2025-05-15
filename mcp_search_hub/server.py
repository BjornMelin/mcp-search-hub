"""FastMCP search server implementation."""

import asyncio
import time
from fastmcp import FastMCP, Context
from typing import Dict

from .models.query import SearchQuery
from .models.results import SearchResponse, CombinedSearchResponse
from .providers.base import SearchProvider
from .providers.linkup import LinkupProvider
from .providers.exa import ExaProvider
from .providers.perplexity import PerplexityProvider
from .providers.tavily import TavilyProvider
from .providers.firecrawl import FirecrawlProvider
from .query_routing.analyzer import QueryAnalyzer
from .query_routing.router import QueryRouter
from .result_processing.merger import ResultMerger
from .utils.cache import QueryCache
from .config import get_settings


class SearchServer:
    """FastMCP search server implementation."""

    def __init__(self):
        # Initialize FastMCP server
        self.mcp = FastMCP(
            name="MCP Search Hub",
            instructions="""
            This server provides access to multiple search providers through a unified interface.
            Use the search tool to find information with automatic provider selection.
            """,
            log_level=get_settings().log_level,
        )

        # Initialize providers
        self.providers: Dict[str, SearchProvider] = {
            "linkup": LinkupProvider(),
            "exa": ExaProvider(),
            "perplexity": PerplexityProvider(),
            "tavily": TavilyProvider(),
            "firecrawl": FirecrawlProvider(),
        }

        # Initialize components
        self.analyzer = QueryAnalyzer()
        self.router = QueryRouter(self.providers)
        self.merger = ResultMerger()
        self.cache = QueryCache(ttl=get_settings().cache_ttl)

        # Register tools
        self._register_tools()

    def _register_tools(self):
        """Register FastMCP tools."""

        @self.mcp.tool()
        async def search(query: SearchQuery, ctx: Context) -> CombinedSearchResponse:
            """
            Search across multiple providers with automatic selection.

            The system automatically selects the best provider(s) for your query based on
            content type, complexity, and other factors.
            """
            start_time = time.time()

            # Check cache
            cache_key = f"{query.query}:{query.advanced}:{query.max_results}:{query.raw_content}"
            cached_result = self.cache.get(cache_key)
            if (
                cached_result and not query.providers
            ):  # Skip cache if explicit providers
                await ctx.info("Retrieved results from cache")
                return cached_result

            # Extract features
            await ctx.info("Analyzing query")
            features = self.analyzer.extract_features(query)

            # Select providers (use explicit selection if provided)
            providers_to_use = query.providers or self.router.select_providers(
                query, features, query.budget
            )

            await ctx.info(f"Selected providers: {', '.join(providers_to_use)}")

            # Execute search with selected providers
            provider_tasks = {}
            for provider_name in providers_to_use:
                if provider_name in self.providers:
                    provider = self.providers[provider_name]
                    provider_tasks[provider_name] = asyncio.create_task(
                        provider.search(query)
                    )

            # Wait for all searches to complete with timeout
            timeout_sec = query.timeout_ms / 1000
            try:
                done, pending = await asyncio.wait(
                    provider_tasks.values(), timeout=timeout_sec
                )

                # Cancel any pending tasks
                for task in pending:
                    task.cancel()

                # Collect results
                provider_results = {}
                for provider_name, task in provider_tasks.items():
                    if task in done and not task.exception():
                        provider_results[provider_name] = task.result()
                    else:
                        # Handle errors or timeouts
                        if task.exception():
                            await ctx.error(
                                f"Provider {provider_name} error: {str(task.exception())}"
                            )
                        else:
                            await ctx.warn(f"Provider {provider_name} timed out")

                        # Create empty response for failed providers
                        provider_results[provider_name] = SearchResponse(
                            results=[],
                            query=query.query,
                            total_results=0,
                            provider=provider_name,
                            error="Timeout or error",
                        )

                # Merge and rank results
                combined_results = self.merger.merge_results(
                    provider_results,
                    max_results=query.max_results,
                    raw_content=query.raw_content,
                )

                # Calculate costs
                total_cost = sum(
                    self.providers[name].estimate_cost(query)
                    for name in provider_results.keys()
                )

                # Create response
                response = CombinedSearchResponse(
                    results=combined_results,
                    query=query.query,
                    providers_used=list(provider_results.keys()),
                    total_results=len(combined_results),
                    total_cost=total_cost,
                    timing_ms=(time.time() - start_time) * 1000,
                )

                # Cache the response
                self.cache.set(cache_key, response)

                return response

            except Exception as e:
                await ctx.error(f"Search error: {str(e)}")
                # Return error response
                return CombinedSearchResponse(
                    results=[],
                    query=query.query,
                    providers_used=[],
                    total_results=0,
                    total_cost=0.0,
                    timing_ms=(time.time() - start_time) * 1000,
                )

        @self.mcp.tool()
        def get_provider_info() -> Dict[str, Dict]:
            """Get information about available search providers."""
            provider_info = {}

            for name, provider in self.providers.items():
                provider_info[name] = provider.get_capabilities()

            return provider_info

    async def close(self):
        """Close all provider connections."""
        close_tasks = []
        for provider in self.providers.values():
            if hasattr(provider, "close"):
                close_tasks.append(asyncio.create_task(provider.close()))

        if close_tasks:
            await asyncio.gather(*close_tasks)

    def run(self, **kwargs):
        """Run the FastMCP server."""
        self.mcp.run(**kwargs)
