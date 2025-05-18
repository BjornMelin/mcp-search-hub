"""Result merger and ranking.

This module handles all result processing including merging,
deduplication, ranking, and consensus scoring.
"""

from ..models.results import SearchResponse, SearchResult
from .deduplication import remove_duplicates


class ResultMerger:
    """Merges and ranks results from multiple providers."""

    # Provider quality weights for ranking
    DEFAULT_WEIGHTS = {
        "linkup": 1.0,  # Excellent for real-time and factual accuracy
        "exa": 0.95,  # Strong academic and research focus
        "perplexity": 0.9,  # Good for comprehensive searches
        "tavily": 0.85,  # Good general search with relevance scoring
        "firecrawl": 0.8,  # Specialized for content extraction
    }

    def __init__(self, provider_weights: dict[str, float] | None = None):
        """Initialize the result merger.

        Args:
            provider_weights: Optional custom weight mapping for providers
        """
        self.provider_weights = provider_weights or self.DEFAULT_WEIGHTS

    def merge_results(
        self,
        provider_results: dict[str, SearchResponse | list[SearchResult]],
        max_results: int = 10,
        raw_content: bool = False,
    ) -> list[SearchResult]:
        """
        Merge results from multiple providers into a unified ranked list.

        Args:
            provider_results: Dictionary mapping provider names to their results
                             Can accept either SearchResponse or list[SearchResult]
            max_results: Maximum number of results to return
            raw_content: Whether raw content was requested in the original query

        Returns:
            List of merged and ranked results
        """
        # Collect all results
        all_results = []
        for _provider, response in provider_results.items():
            if isinstance(response, SearchResponse):
                all_results.extend(response.results)
            else:
                # Direct list of SearchResult
                all_results.extend(response)

        # Handle raw content merging BEFORE deduplication to preserve metadata
        if raw_content:
            all_results = self._merge_raw_content(all_results)

        # Remove duplicates based on URL
        deduplicated = remove_duplicates(all_results)

        # Rank combined results
        ranked_results = self._rank_results(deduplicated, provider_results)

        # Limit to max_results
        return ranked_results[:max_results]

    def _merge_raw_content(self, results: list[SearchResult]) -> list[SearchResult]:
        """
        For duplicate URLs where some have raw_content and others don't,
        prefer the result with raw_content while preserving metadata.
        """
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
            results_with_content = [result for result in group if result.raw_content]

            if results_with_content:
                # If multiple results have raw_content, choose the one with highest score
                # and merge metadata from all
                result_with_content = max(results_with_content, key=lambda x: x.score)

                # Merge metadata from all results in the group
                for result in group:
                    if result != result_with_content:
                        # Add non-overlapping metadata
                        for key, value in result.metadata.items():
                            if key not in result_with_content.metadata:
                                result_with_content.metadata[key] = value

                merged_results.append(result_with_content)
            else:
                # No result has raw_content, use the first one
                merged_results.append(group[0])

        return merged_results

    def _rank_results(
        self,
        results: list[SearchResult],
        provider_results: dict[str, SearchResponse | list[SearchResult]],
    ) -> list[SearchResult]:
        """Rank results based on provider quality and result scores.

        Uses a multi-factor ranking algorithm:
            1. Provider quality weight
            2. Original result score
            3. Consensus boost (results appearing in multiple providers)
        """
        # Apply consensus boost for results appearing in multiple providers
        url_counts = {}
        for result in results:
            url = result.url
            if url in url_counts:
                url_counts[url] += 1
            else:
                url_counts[url] = 1

        # Calculate combined scores
        for result in results:
            provider_weight = self.provider_weights.get(result.source, 0.8)
            result_score = result.score

            # Apply consensus boost
            consensus_factor = url_counts[result.url] / len(provider_results)
            consensus_boost = 1.0 + (consensus_factor * 0.5)  # Up to 50% boost

            # Calculate combined score
            combined_score = provider_weight * result_score * consensus_boost

            # Store in metadata for debugging
            result.metadata["combined_score"] = combined_score
            result.metadata["provider_weight"] = provider_weight
            result.metadata["consensus_factor"] = consensus_factor

        # Sort by combined score
        return sorted(
            results, key=lambda x: x.metadata.get("combined_score", 0.0), reverse=True
        )

    def rank_by_weighted_score(
        self,
        results: list[SearchResult],
        custom_weights: dict[str, float] | None = None,
    ) -> list[SearchResult]:
        """Simple ranking by applying source weights to scores.

        This method is provided for compatibility and simple use cases.
        The main merge_results method provides more sophisticated ranking.

        Args:
            results: List of search results to rank
            custom_weights: Optional custom weight mapping (uses instance weights if None)

        Returns:
            Ranked list of results
        """
        weights = custom_weights or self.provider_weights

        for result in results:
            weight = weights.get(result.source, 0.5)
            result.metadata["weighted_score"] = result.score * weight

        return sorted(
            results, key=lambda x: x.metadata.get("weighted_score", 0.0), reverse=True
        )
