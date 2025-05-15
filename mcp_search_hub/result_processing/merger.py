"""Result merger and ranking."""

from typing import Dict, List
from ..models.results import SearchResult, SearchResponse
from .deduplication import remove_duplicates


class ResultMerger:
    """Merges and ranks results from multiple providers."""

    def merge_results(
        self,
        provider_results: Dict[str, SearchResponse],
        max_results: int = 10,
        raw_content: bool = False,
    ) -> List[SearchResult]:
        """
        Merge results from multiple providers into a unified ranked list.

        Args:
            provider_results: Dictionary mapping provider names to their results
            max_results: Maximum number of results to return
            raw_content: Whether raw content was requested in the original query

        Returns:
            List of merged and ranked results
        """
        # Collect all results
        all_results = []
        for provider, response in provider_results.items():
            all_results.extend(response.results)

        # Remove duplicates based on URL
        deduplicated = remove_duplicates(all_results)

        # Handle raw content during deduplication
        if raw_content:
            deduplicated = self._merge_raw_content(deduplicated)

        # Rank combined results
        ranked_results = self._rank_results(deduplicated, provider_results)

        # Limit to max_results
        return ranked_results[:max_results]

    def _merge_raw_content(self, results: List[SearchResult]) -> List[SearchResult]:
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
        for url, group in url_groups.items():
            if len(group) == 1:
                merged_results.append(group[0])
                continue

            # Find result with raw_content
            result_with_content = None
            for result in group:
                if result.raw_content:
                    result_with_content = result
                    break

            if result_with_content:
                # Use this result but merge metadata from others
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
        self, results: List[SearchResult], provider_results: Dict[str, SearchResponse]
    ) -> List[SearchResult]:
        """Rank results based on provider quality and result scores."""
        # Provider quality weights
        provider_weights = {
            "linkup": 1.0,  # Excellent factual accuracy
            "exa": 0.95,  # Strong academic focus
            "perplexity": 0.9,  # Good for current events
            "tavily": 0.85,  # Good general search
            "firecrawl": 0.8,  # Specialized for content extraction
        }

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
            provider_weight = provider_weights.get(result.source, 0.8)
            result_score = result.score

            # Apply consensus boost
            consensus_factor = url_counts[result.url] / len(provider_results)
            consensus_boost = 1.0 + (consensus_factor * 0.5)  # Up to 50% boost

            # Calculate combined score
            combined_score = provider_weight * result_score * consensus_boost

            # Store in metadata for debugging
            result.metadata["combined_score"] = combined_score

        # Sort by combined score
        return sorted(
            results, key=lambda x: x.metadata.get("combined_score", 0.0), reverse=True
        )
