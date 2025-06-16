"""Result merger and ranking functions."""

import datetime
import time
from typing import Any

from ..config.settings import MergerSettings
from ..models.base import HealthStatus
from ..models.component import ResultMergerBase
from ..models.results import SearchResponse, SearchResult
from ..utils.logging import get_logger
from .deduplication import remove_duplicates
from .metadata_enrichment import enrich_result_metadata

logger = get_logger(__name__)


class ResultMerger(ResultMergerBase[MergerSettings]):
    """Merges and ranks results from multiple providers."""

    # Provider quality weights for ranking
    DEFAULT_WEIGHTS = {
        "linkup": 1.0,  # Excellent for real-time and factual accuracy
        "exa": 0.95,  # Strong academic and research focus
        "perplexity": 0.9,  # Good for comprehensive searches
        "tavily": 0.85,  # Good general search with relevance scoring
        "firecrawl": 0.8,  # Specialized for content extraction
    }

    # Credibility tiers for domains (high-quality domains get a boost)
    CREDIBILITY_TIERS = {
        # High credibility (official sources)
        "edu": 1.0,
        "gov": 1.0,
        "nih.gov": 1.0,
        "who.int": 1.0,
        # News/reference
        "nytimes.com": 0.9,
        "bbc.com": 0.9,
        "reuters.com": 0.9,
        # Tech sources
        "github.com": 0.85,
        "stackoverflow.com": 0.85,
    }

    # Default score for unknown domains
    DEFAULT_CREDIBILITY = 0.7

    # Recency boosts for time-sensitive content
    RECENCY_BOOSTS = {
        7: 1.3,  # Past week: 30% boost
        30: 1.15,  # Past month: 15% boost
        90: 1.05,  # Past quarter: 5% boost
    }

    def __init__(
        self,
        name: str = "result_merger",
        config: MergerSettings | None = None,
    ):
        """Initialize the merger with configuration options."""
        # If no config is provided, create a default one
        if config is None:
            config = MergerSettings(
                provider_weights=self.DEFAULT_WEIGHTS,
                recency_enabled=True,
                credibility_enabled=True,
                consensus_weight=0.5,
            )

        super().__init__(name, config)

        # Initialize provider weights
        self.provider_weights = config.provider_weights or self.DEFAULT_WEIGHTS
        self.recency_enabled = config.recency_enabled
        self.credibility_enabled = config.credibility_enabled
        self.max_results = config.max_results

        # Merger metrics
        self.metrics = {
            "total_merges": 0,
            "total_input_results": 0,
            "total_output_results": 0,
            "avg_merge_time_ms": 0.0,
            "avg_deduplication_ratio": 0.0,
            "last_merge_time": None,
        }

        self.initialized = False

    async def initialize(self) -> None:
        """Initialize the merger component."""
        await super().initialize()
        self.initialized = True
        logger.info(
            f"Initialized ResultMerger component with {len(self.provider_weights)} provider weights"
        )

    async def merge_results(
        self,
        provider_results: dict[str, SearchResponse | list[SearchResult]],
        max_results: int | None = None,
        raw_content: bool = False,
        use_content_similarity: bool | None = None,
    ) -> list[SearchResult]:
        """Merge results from multiple providers into a unified ranked list."""
        start_time = time.time()

        if not provider_results:
            return []

        if max_results is None:
            max_results = self.config.max_results

        if use_content_similarity is None:
            use_content_similarity = self.config.use_content_similarity

        # Collect and normalize all results
        all_results = []
        total_input_results = 0
        for provider, response in provider_results.items():
            # Extract results from provider response
            if isinstance(response, SearchResponse):
                results = response.results
            else:
                results = response

            total_input_results += len(results)

            # Ensure source is set and enrich metadata
            for result in results:
                if not result.source:
                    result.source = provider
                enrich_result_metadata(result)

            all_results.extend(results)

        # Merge raw content before deduplication (if requested)
        if raw_content:
            all_results = self._merge_raw_content(all_results)

        # Remove duplicates with fuzzy matching
        deduplicated = remove_duplicates(
            all_results,
            use_content_similarity=use_content_similarity,
            fuzzy_url_threshold=self.config.fuzzy_url_threshold,
            content_similarity_threshold=self.config.content_similarity_threshold,
        )

        # Rank the results
        ranked_results = self._rank_results(deduplicated, provider_results)

        # Update metrics
        self._update_metrics(
            total_input_results=total_input_results,
            deduplicated_count=len(deduplicated),
            final_count=min(len(ranked_results), max_results),
            duration=time.time() - start_time,
        )

        # Return only the requested number
        return ranked_results[:max_results]

    def _merge_raw_content(self, results: list[SearchResult]) -> list[SearchResult]:
        """Merge results with the same URL, preferring those with raw content."""
        # Group by URL
        url_groups = {}
        for result in results:
            if result.url not in url_groups:
                url_groups[result.url] = []
            url_groups[result.url].append(result)

        # Process groups with more than one result
        merged_results = []
        for _url, group in url_groups.items():
            if len(group) == 1:
                merged_results.append(group[0])
                continue

            # Find results with raw_content
            with_content = [r for r in group if r.raw_content]
            if with_content:
                # Keep the highest-scored one with content
                best_result = max(with_content, key=lambda x: x.score)
                merged_results.append(best_result)
            else:
                # No raw content - keep highest-scored result
                merged_results.append(max(group, key=lambda x: x.score))

        return merged_results

    def _rank_results(
        self,
        results: list[SearchResult],
        provider_results: dict[str, SearchResponse | list[SearchResult]],
    ) -> list[SearchResult]:
        """Rank results using provider quality, recency, and other factors."""
        if not results:
            return []

        # Current date for recency calculations
        current_date = datetime.datetime.now().date()

        # Count how many providers each URL appears in (for consensus boost)
        url_counts = {}
        for result in results:
            url = result.url
            if url in url_counts:
                url_counts[url] += 1
            else:
                url_counts[url] = 1

        # Calculate final score combining multiple factors
        for result in results:
            # Base factors
            provider_weight = self.provider_weights.get(result.source, 0.8)
            result_score = result.score

            # Consensus boost (up to 50% for results in all providers)
            consensus_factor = url_counts[result.url] / len(provider_results)
            consensus_boost = 1.0 + (consensus_factor * self.config.consensus_weight)

            # Recency boost (if enabled)
            recency_boost = 1.0
            if self.recency_enabled and "published_date" in result.metadata:
                try:
                    # Parse the date
                    pub_date_str = result.metadata["published_date"]
                    pub_date = None

                    if isinstance(pub_date_str, str):
                        pub_date = datetime.datetime.fromisoformat(pub_date_str).date()
                    elif isinstance(pub_date_str, datetime.datetime):
                        pub_date = pub_date_str.date()

                    if pub_date:
                        days_old = (current_date - pub_date).days
                        result.metadata["days_old"] = days_old

                        # Apply appropriate boost based on age
                        if days_old <= 7:
                            recency_boost = self.RECENCY_BOOSTS[7]
                        elif days_old <= 30:
                            recency_boost = self.RECENCY_BOOSTS[30]
                        elif days_old <= 90:
                            recency_boost = self.RECENCY_BOOSTS[90]
                except Exception:
                    pass

            # Credibility boost (if enabled)
            credibility_factor = 1.0
            if self.credibility_enabled and "source_domain" in result.metadata:
                domain = result.metadata["source_domain"]

                # Look for exact domain match
                credibility = self.CREDIBILITY_TIERS.get(domain)

                # If no match, check domain endings
                if not credibility:
                    for ending, score in self.CREDIBILITY_TIERS.items():
                        if domain.endswith(ending):
                            credibility = score
                            break

                credibility_factor = credibility or self.DEFAULT_CREDIBILITY
                result.metadata["credibility_score"] = credibility_factor

            # Combine all factors
            combined_score = (
                provider_weight
                * result_score
                * consensus_boost
                * recency_boost
                * credibility_factor
            )

            # Store score components in metadata
            result.metadata["combined_score"] = combined_score
            result.metadata["provider_weight"] = provider_weight
            result.metadata["consensus_boost"] = consensus_boost

            if recency_boost > 1.0:
                result.metadata["recency_boost"] = recency_boost

            if credibility_factor != 1.0:
                result.metadata["credibility_factor"] = credibility_factor

        # Sort by combined score (highest first)
        return sorted(
            results, key=lambda x: x.metadata.get("combined_score", 0.0), reverse=True
        )

    def _update_metrics(
        self,
        total_input_results: int,
        deduplicated_count: int,
        final_count: int,
        duration: float,
    ) -> None:
        """Update merger metrics."""
        self.metrics["total_merges"] += 1
        self.metrics["total_input_results"] += total_input_results
        self.metrics["total_output_results"] += final_count
        self.metrics["last_merge_time"] = time.time()

        # Calculate deduplication ratio
        if total_input_results > 0:
            dedup_ratio = 1.0 - (deduplicated_count / total_input_results)

            # Update with moving average
            prev_avg = self.metrics.get("avg_deduplication_ratio", 0.0)
            prev_count = self.metrics["total_merges"] - 1
            self.metrics["avg_deduplication_ratio"] = (
                prev_avg * prev_count + dedup_ratio
            ) / self.metrics["total_merges"]

        # Update avg merge time with moving average
        prev_avg = self.metrics.get("avg_merge_time_ms", 0.0)
        prev_count = self.metrics["total_merges"] - 1
        self.metrics["avg_merge_time_ms"] = (
            prev_avg * prev_count + duration * 1000
        ) / self.metrics["total_merges"]

    def get_metrics(self) -> dict[str, Any]:
        """Get merger metrics."""
        metrics = dict(self.metrics)

        # Add derived metrics
        if self.metrics["total_merges"] > 0:
            metrics["avg_results_per_merge"] = (
                self.metrics["total_output_results"] / self.metrics["total_merges"]
            )

        return metrics

    def reset_metrics(self) -> None:
        """Reset all metrics."""
        self.metrics = {
            "total_merges": 0,
            "total_input_results": 0,
            "total_output_results": 0,
            "avg_merge_time_ms": 0.0,
            "avg_deduplication_ratio": 0.0,
            "last_merge_time": None,
        }

    async def check_health(self) -> tuple[HealthStatus, str]:
        """Check component health."""
        if not self.initialized:
            return HealthStatus.UNHEALTHY, "ResultMerger not initialized"

        return HealthStatus.HEALTHY, "ResultMerger is healthy"

    async def process(
        self,
        provider_results: dict[str, SearchResponse | list[SearchResult]],
        max_results: int | None = None,
        raw_content: bool = False,
        use_content_similarity: bool | None = None,
    ) -> list[SearchResult]:
        """Process search results - alias for merge_results."""
        return await self.merge_results(
            provider_results,
            max_results,
            raw_content,
            use_content_similarity,
        )

    async def _do_execute(self, *args: Any, **kwargs: Any) -> list[SearchResult]:
        """Execute the merger with the given arguments."""
        # Extract provider_results from args or kwargs
        provider_results = None
        if args and isinstance(args[0], dict):
            provider_results = args[0]
        elif "provider_results" in kwargs:
            provider_results = kwargs["provider_results"]
        else:
            raise ValueError("No provider_results provided to execute")

        # Extract other parameters
        max_results = kwargs.get("max_results", self.config.max_results)
        raw_content = kwargs.get("raw_content", False)
        use_content_similarity = kwargs.get(
            "use_content_similarity", self.config.use_content_similarity
        )

        # Execute merger
        return await self.merge_results(
            provider_results, max_results, raw_content, use_content_similarity
        )
