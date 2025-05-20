"""Result merger and ranking functions."""

import datetime
from typing import Dict, List, Optional, Union

from ..models.results import SearchResponse, SearchResult
from .deduplication import remove_duplicates
from .metadata_enrichment import enrich_result_metadata


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
        provider_weights: Optional[Dict[str, float]] = None,
        recency_enabled: bool = True,
        credibility_enabled: bool = True,
    ):
        """Initialize the merger with configuration options."""
        self.provider_weights = provider_weights or self.DEFAULT_WEIGHTS
        self.recency_enabled = recency_enabled
        self.credibility_enabled = credibility_enabled

    def merge_results(
        self,
        provider_results: Dict[str, Union[SearchResponse, List[SearchResult]]],
        max_results: int = 10,
        raw_content: bool = False,
        use_content_similarity: bool = True,
    ) -> List[SearchResult]:
        """Merge results from multiple providers into a unified ranked list."""
        if not provider_results:
            return []

        # Collect and normalize all results
        all_results = []
        for provider, response in provider_results.items():
            # Extract results from provider response
            if isinstance(response, SearchResponse):
                results = response.results
            else:
                results = response

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
        )

        # Rank the results
        ranked_results = self._rank_results(deduplicated, provider_results)

        # Return only the requested number
        return ranked_results[:max_results]

    def _merge_raw_content(self, results: List[SearchResult]) -> List[SearchResult]:
        """Merge results with the same URL, preferring those with raw content."""
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
        results: List[SearchResult],
        provider_results: Dict[str, Union[SearchResponse, List[SearchResult]]],
    ) -> List[SearchResult]:
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
            consensus_boost = 1.0 + (consensus_factor * 0.5)

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
