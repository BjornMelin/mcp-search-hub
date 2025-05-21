"""Generic MCP provider implementation using configuration."""

import logging
from decimal import Decimal
from typing import Any

from ..models.query import SearchQuery
from ..models.results import SearchResult
from ..utils.retry import RetryConfig
from .base_mcp import BaseMCPProvider
from .provider_config import PROVIDER_CONFIGS, DEFAULT_RETRY_CONFIG

logger = logging.getLogger(__name__)


class GenericMCPProvider(BaseMCPProvider):
    """Generic MCP provider that uses configuration to instantiate."""

    def __init__(self, provider_name: str, api_key: str | None = None):
        config = PROVIDER_CONFIGS.get(provider_name)
        if not config:
            raise ValueError(f"Unknown provider: {provider_name}")

        # Get provider-specific configurations
        rate_limit_config = config.get("rate_limits", None)
        budget_config = config.get("budget", None)
        retry_config = config.get("retry_config", DEFAULT_RETRY_CONFIG)
        retry_enabled = config.get("retry_enabled", True)
        self.base_cost = config.get("base_cost", Decimal("0.01"))

        super().__init__(
            name=provider_name,
            api_key=api_key,
            env_var_name=config["env_var"],
            server_type=config["server_type"],
            args=config.get("args", [config["package"]]),
            tool_name=config["tool_name"],
            api_timeout=config["timeout"],
            rate_limit_config=rate_limit_config,
            budget_config=budget_config,
        )
        
        # Set retry configuration
        self.RETRY_ENABLED = retry_enabled
        self._retry_config = retry_config

    def _prepare_search_params(self, query: SearchQuery) -> dict[str, Any]:
        """Prepare parameters for search."""
        # Default implementation - each provider may override this
        params = {
            "query": query.query,
        }

        # Provider-specific parameter mapping
        if self.name == "exa":
            params["numResults"] = query.max_results
        elif self.name == "firecrawl":
            params["limit"] = query.max_results
            if query.raw_content:
                params["formats"] = ["markdown", "links"]
        elif self.name == "linkup":
            params["depth"] = (
                query.advanced.get("depth", "standard")
                if query.advanced
                else "standard"
            )
        elif self.name == "perplexity":
            # Perplexity uses messages format
            params = {"messages": [{"role": "user", "content": query.query}]}
        elif self.name == "tavily":
            params["max_results"] = query.max_results
            # Handle deep_search flag or explicit search_depth
            if query.advanced:
                if query.advanced.get("deep_search"):
                    params["search_depth"] = "advanced"
                else:
                    params["search_depth"] = query.advanced.get("search_depth", "basic")
            else:
                params["search_depth"] = "basic"
            params["include_raw_content"] = query.raw_content

        # Add any additional advanced parameters
        if query.advanced:
            # Merge advanced parameters, but don't override existing params
            for key, value in query.advanced.items():
                if key not in params:
                    params[key] = value

        return params

    def _process_search_results(
        self, result: Any, query: SearchQuery
    ) -> list[SearchResult]:
        """Process search results from MCP server response."""
        search_results = []

        try:
            # First, try direct dictionary format (for testing)
            if isinstance(result, dict) and "results" in result:
                return self._process_dict_results(result["results"], query)

            # Handle MCP server response format
            if (
                hasattr(result, "content")
                and result.content
                and isinstance(result.content, list)
            ):
                for item in result.content:
                    if hasattr(item, "text") and item.text:
                        text_data = item.text

                        # Handle JSON data
                        if isinstance(text_data, dict):
                            return self._process_dict_results(
                                text_data.get("results", []), query
                            )

                        # Handle formatted string data
                        if isinstance(text_data, str):
                            # Try to parse as JSON first
                            try:
                                import json

                                json_data = json.loads(text_data)
                                if (
                                    isinstance(json_data, dict)
                                    and "results" in json_data
                                ):
                                    return self._process_dict_results(
                                        json_data["results"], query
                                    )
                            except json.JSONDecodeError:
                                # Parse as formatted text
                                return self._parse_formatted_text(text_data, query)

        except Exception as e:
            logger.error(f"Error processing {self.name} search results: {str(e)}")
            # Don't re-raise the exception - this is a non-critical error in result processing
            # Instead, return whatever results we were able to parse
            # If no results were found, the empty list is appropriate

        return search_results

    def _process_dict_results(
        self, results: list[dict], query: SearchQuery
    ) -> list[SearchResult]:
        """Process results in dictionary format."""
        search_results = []

        for result_item in results:
            # Extract content with provider-specific logic
            content = ""
            if query.raw_content:
                # Different providers use different keys for raw content
                content = result_item.get(
                    "raw_content",
                    result_item.get(
                        "content",
                        result_item.get("text", result_item.get("description", "")),
                    ),
                )

            # Extract snippet (fallback chain for different providers)
            snippet = result_item.get(
                "snippet",
                result_item.get(
                    "description",
                    result_item.get("excerpt", result_item.get("text", "")[:200]),
                ),
            )

            # Extract score with fallback
            score = float(
                result_item.get(
                    "score",
                    result_item.get(
                        "relevance_score", result_item.get("confidence", 1.0)
                    ),
                )
            )

            search_results.append(
                SearchResult(
                    title=result_item.get("title", ""),
                    url=result_item.get("url", ""),
                    snippet=snippet,
                    source=self.name,
                    score=score,
                    raw_content=content if query.raw_content else None,
                    metadata=self._extract_metadata(result_item),
                )
            )

        return search_results

    def _extract_metadata(self, result_item: dict) -> dict:
        """Extract metadata from result item."""
        # Common metadata fields across providers
        metadata = {}

        # Add common fields if they exist
        for field in [
            "domain",
            "source",
            "published_date",
            "publishedDate",
            "author",
            "content_type",
            "source_type",
        ]:
            if field in result_item:
                metadata[field] = result_item[field]

        # Add any scores in metadata
        for score_field in ["score", "relevance_score", "confidence"]:
            if score_field in result_item:
                metadata[score_field] = result_item[score_field]

        return metadata

    def _parse_formatted_text(
        self, text_data: str, query: SearchQuery
    ) -> list[SearchResult]:
        """Parse formatted text response (fallback parser)."""
        search_results = []
        lines = text_data.split("\n")
        current_result = {}

        for line in lines:
            stripped_line = line.strip()

            if stripped_line.startswith("Title:"):
                if current_result:
                    # Save previous result
                    search_results.append(
                        self._create_result_from_text(current_result, query)
                    )
                current_result = {"title": stripped_line[6:].strip()}

            elif stripped_line.startswith("URL:"):
                current_result["url"] = stripped_line[4:].strip()

            elif stripped_line.startswith(("Content:", "Description:")):
                current_result["content"] = stripped_line[8:].strip()

            elif stripped_line.startswith(("Snippet:", "Excerpt:")):
                current_result["snippet"] = stripped_line[8:].strip()

            elif stripped_line.startswith("Score:"):
                current_result["score"] = stripped_line[6:].strip()

            elif stripped_line.startswith(("Date:", "Published Date:")):
                prefix_len = (
                    len("Published Date:") if "Published Date:" in stripped_line else 5
                )
                current_result["date"] = stripped_line[prefix_len:].strip()

            elif stripped_line.startswith("Source:"):
                current_result["source_info"] = stripped_line[7:].strip()

        # Add the last result
        if current_result:
            search_results.append(self._create_result_from_text(current_result, query))

        return search_results

    def _create_result_from_text(self, data: dict, query: SearchQuery) -> SearchResult:
        """Create SearchResult from parsed text data."""
        return SearchResult(
            title=data.get("title", ""),
            url=data.get("url", ""),
            snippet=data.get("snippet", data.get("content", "")[:200]),
            source=self.name,
            score=float(data.get("score", 1.0)),
            raw_content=data.get("content", "") if query.raw_content else None,
            metadata={
                "published_date": data.get("date"),
                "source": data.get("source_info"),
            },
        )

    def get_retry_config(self) -> RetryConfig:
        """Get retry configuration for this provider.
        
        Overrides BaseMCPProvider.get_retry_config to use the 
        provider-specific configuration.
        
        Returns:
            RetryConfig: Provider-specific retry configuration
        """
        return self._retry_config
    
    def get_capabilities(self) -> dict[str, Any]:
        """Return provider capabilities."""
        # Base capabilities - can be overridden per provider
        base_capabilities = {
            "name": self.name,
            "supports_raw_content": True,
            "supports_advanced_search": True,
            "max_results_per_query": 10,
            "features": ["search", "content_extraction"],
            "rate_limit_info": self.rate_limiter.get_current_usage(),
            "budget_info": self.budget_tracker.get_usage_report(),
            "retry_enabled": self.RETRY_ENABLED,
            "retry_config": {
                "max_retries": self._retry_config.max_retries,
                "base_delay": self._retry_config.base_delay,
                "max_delay": self._retry_config.max_delay,
            },
        }

        # Provider-specific capabilities
        if self.name == "exa":
            base_capabilities.update(
                {
                    "features": [
                        "search_filters",
                        "date_range_filtering",
                        "content_extraction",
                        "semantic_search",
                        "highlights",
                        "research_paper_search",
                        "company_research",
                        "competitor_finder",
                        "linkedin_search",
                        "wikipedia_search",
                        "github_search",
                    ],
                }
            )
        elif self.name == "firecrawl":
            base_capabilities.update(
                {
                    "max_results_per_query": 20,
                    "features": [
                        "web_scraping",
                        "content_extraction",
                        "structured_data_extraction",
                        "crawling",
                        "deep_research",
                        "search",
                        "map_urls",
                        "llm_extraction",
                    ],
                }
            )
        elif self.name == "linkup":
            base_capabilities.update(
                {
                    "features": [
                        "real_time_search",
                        "news_aggregation",
                        "content_summarization",
                        "deep_search_mode",
                        "premium_content_access",
                        "academic_sources",
                    ],
                }
            )
        elif self.name == "perplexity":
            base_capabilities.update(
                {
                    "features": [
                        "conversation_mode",
                        "research_mode",
                        "reasoning_mode",
                        "citations",
                        "web_search",
                    ],
                }
            )
        elif self.name == "tavily":
            base_capabilities.update(
                {
                    "max_results_per_query": 20,
                    "features": [
                        "basic_search",
                        "advanced_search",
                        "domain_filtering",
                        "time_range_filtering",
                        "topic_categorization",
                        "content_extraction",
                        "news_search",
                        "relevance_scoring",
                    ],
                }
            )

        return base_capabilities

    def estimate_cost(self, query: SearchQuery) -> float:
        """Estimate the cost of a search query."""
        # Provider-specific pricing based on configuration
        base_cost = float(self.base_cost)

        # Add result count cost
        results_cost = query.max_results * 0.0005

        # Add advanced features cost
        if query.advanced:
            results_cost *= 1.2

        # Add raw content cost
        if query.raw_content:
            results_cost *= 1.5

        # Provider-specific adjustments
        if self.name == "exa":
            base_cost = 0.015
            results_cost = query.max_results * 0.0005
            if query.advanced:
                results_cost *= 1.2
            return base_cost + results_cost

        if self.name == "firecrawl":
            base_cost = 0.02
            results_cost = query.max_results * 0.001
            if query.raw_content:
                results_cost *= 2.0
            if query.advanced and query.advanced.get("crawl_depth", 1) > 1:
                results_cost *= query.advanced.get("crawl_depth", 1)
            return base_cost + results_cost

        if self.name == "linkup":
            base_cost = 0.01
            depth_multiplier = (
                2.0 if query.advanced and query.advanced.get("depth") == "deep" else 1.0
            )
            results_cost = query.max_results * 0.0005
            return (base_cost + results_cost) * depth_multiplier

        if self.name == "perplexity":
            base_cost = 0.025  # Higher base cost for AI-powered search
            results_cost = query.max_results * 0.002
            return base_cost + results_cost

        if self.name == "tavily":
            base_cost = 0.005
            search_cost = (
                0.015
                if query.advanced and query.advanced.get("search_depth") == "advanced"
                else base_cost
            )
            results_cost = query.max_results * 0.0002
            if query.raw_content:
                results_cost *= 1.5
            return search_cost + results_cost

        # Default fallback
        return base_cost + results_cost

    def _calculate_actual_cost(
        self, query: SearchQuery, results: list[SearchResult]
    ) -> Decimal:
        """Calculate the actual cost based on the results."""
        # Use the provider-specific calculation but convert to Decimal
        base_estimated_cost = Decimal(str(self.estimate_cost(query)))

        # Adjust based on actual result count
        if not results:
            return base_estimated_cost * Decimal("0.5")

        if len(results) < query.max_results:
            result_ratio = max(
                Decimal("0.75"),
                Decimal(str(len(results))) / Decimal(str(query.max_results)),
            )
            return base_estimated_cost * result_ratio

        return base_estimated_cost
