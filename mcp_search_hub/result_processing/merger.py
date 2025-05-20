"""Result merger and ranking with enhanced algorithms.

This module handles all result processing including merging,
deduplication, ranking, credibility scoring, and recency factoring.
"""

import datetime
import re
from typing import Dict, List, Optional, Tuple, Union
from urllib.parse import urlparse

import dateparser

from ..models.results import SearchResponse, SearchResult
from .deduplication import remove_duplicates
from .metadata_enrichment import enrich_result_metadata


class ResultMerger:
    """Merges and ranks results from multiple providers with enhanced algorithms."""

    # Provider quality weights for ranking
    DEFAULT_WEIGHTS = {
        "linkup": 1.0,  # Excellent for real-time and factual accuracy
        "exa": 0.95,  # Strong academic and research focus
        "perplexity": 0.9,  # Good for comprehensive searches
        "tavily": 0.85,  # Good general search with relevance scoring
        "firecrawl": 0.8,  # Specialized for content extraction
    }

    # Source domain credibility tiers
    # These are just examples - should be updated with a comprehensive list
    CREDIBILITY_TIERS = {
        # Tier 1: High credibility academic and official sources
        "edu": 1.0,
        "gov": 1.0,
        "nature.com": 1.0,
        "science.org": 1.0,
        "acm.org": 1.0,
        "ieee.org": 1.0,
        "sciencedirect.com": 1.0,
        "nih.gov": 1.0,
        "who.int": 1.0,
        "un.org": 1.0,
        # Tier 2: Reputable news and information sources
        "nytimes.com": 0.9,
        "wsj.com": 0.9,
        "economist.com": 0.9,
        "bbc.com": 0.9,
        "reuters.com": 0.9,
        "ap.org": 0.9,
        "bloomberg.com": 0.9,
        # Tier 3: Good quality tech and specialized sources
        "github.com": 0.85,
        "stackoverflow.com": 0.85,
        "medium.com": 0.8,
        "techcrunch.com": 0.8,
        "wired.com": 0.8,
        "venturebeat.com": 0.8,
    }

    # Default fallback credibility score
    DEFAULT_CREDIBILITY_SCORE = 0.7

    # Recency settings for time-sensitive weighting
    # More recent results get a boost, with diminishing returns for older content
    RECENCY_DECAY_DAYS = {
        "very_recent": 7,  # Content less than 7 days old
        "recent": 30,  # Content less than 30 days old
        "somewhat_recent": 90,  # Content less than 90 days old
        "default": 365,  # Default timeframe to consider (1 year)
    }

    # Recency boost factors
    RECENCY_BOOST = {
        "very_recent": 1.3,  # 30% boost for very recent content
        "recent": 1.15,  # 15% boost for recent content
        "somewhat_recent": 1.05,  # 5% boost for somewhat recent content
        "default": 1.0,  # No boost for older content
    }

    def __init__(
        self,
        provider_weights: Optional[Dict[str, float]] = None,
        credibility_tiers: Optional[Dict[str, float]] = None,
        recency_enabled: bool = True,
        credibility_enabled: bool = True,
    ):
        """Initialize the result merger with configurable options.

        Args:
            provider_weights: Optional custom weight mapping for providers
            credibility_tiers: Optional custom credibility tiers for domains
            recency_enabled: Whether to apply recency boosting
            credibility_enabled: Whether to apply source credibility scoring
        """
        self.provider_weights = provider_weights or self.DEFAULT_WEIGHTS
        self.credibility_tiers = credibility_tiers or self.CREDIBILITY_TIERS
        self.recency_enabled = recency_enabled
        self.credibility_enabled = credibility_enabled

    def merge_results(
        self,
        provider_results: Dict[str, Union[SearchResponse, List[SearchResult]]],
        max_results: int = 10,
        raw_content: bool = False,
        use_content_similarity: bool = True,
        fuzzy_url_threshold: float = 92.0,
        content_similarity_threshold: float = 0.85,
    ) -> List[SearchResult]:
        """
        Merge results from multiple providers into a unified, ranked list.

        Args:
            provider_results: Dictionary mapping provider names to their results
                           Can accept either SearchResponse or list[SearchResult]
            max_results: Maximum number of results to return
            raw_content: Whether raw content was requested in the original query
            use_content_similarity: Whether to use content-based similarity detection
            fuzzy_url_threshold: Threshold for fuzzy URL matching (0-100)
            content_similarity_threshold: Threshold for content similarity (0-1)

        Returns:
            List of merged and ranked results
        """
        if not provider_results:
            return []

        # Collect all results
        all_results = []
        for provider, response in provider_results.items():
            if isinstance(response, SearchResponse):
                results = response.results
            else:
                # Direct list of SearchResult
                results = response

            # Add provider info to metadata if missing
            for result in results:
                # Ensure source is set
                if not result.source:
                    result.source = provider

                # Enrich with comprehensive metadata
                enrich_result_metadata(result)

                # Add credibility scoring and additional extraction
                self._extract_metadata(result)

            all_results.extend(results)

        # Handle raw content merging BEFORE deduplication to preserve metadata
        if raw_content:
            all_results = self._merge_raw_content(all_results)

        # Remove duplicates with fuzzy matching
        deduplicated = remove_duplicates(
            all_results,
            fuzzy_url_threshold=fuzzy_url_threshold,
            content_similarity_threshold=content_similarity_threshold,
            use_content_similarity=use_content_similarity,
        )

        # Rank combined results with enhanced algorithm
        ranked_results = self._rank_results(deduplicated, provider_results)

        # Limit to max_results
        return ranked_results[:max_results]

    def _extract_metadata(self, result: SearchResult) -> None:
        """
        Extract and normalize useful metadata from result.

        This extracts dates, source domain, and other metadata that might
        be embedded in the result's title, snippet, or existing metadata.

        Args:
            result: The search result to process
        """
        # Extract source domain from URL if not already in metadata
        if "source_domain" not in result.metadata:
            try:
                parsed_url = urlparse(result.url)
                domain = parsed_url.netloc.lower()
                # Remove www prefix if present
                domain = re.sub(r"^www\d?\.", "", domain)
                result.metadata["source_domain"] = domain
            except Exception:
                # If parsing fails, don't add domain metadata
                pass

        # Attempt to extract date if not already in metadata
        if "published_date" not in result.metadata:
            # Look for date patterns in title and snippet
            date_candidates = []

            # Common date formats to look for
            date_patterns = [
                r"\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{4}",
                r"\d{4}-\d{1,2}-\d{1,2}",
                r"\d{1,2}/\d{1,2}/\d{4}",
                r"\d{1,2}\.\d{1,2}\.\d{4}",
            ]

            for pattern in date_patterns:
                # Check title
                title_matches = re.findall(pattern, result.title)
                if title_matches:
                    date_candidates.extend(title_matches)

                # Check snippet
                snippet_matches = re.findall(pattern, result.snippet)
                if snippet_matches:
                    date_candidates.extend(snippet_matches)

            # Try to parse any found date strings
            for date_str in date_candidates:
                try:
                    parsed_date = dateparser.parse(
                        date_str, settings={"STRICT_PARSING": True}
                    )
                    if parsed_date:
                        result.metadata["published_date"] = parsed_date.isoformat()
                        break
                except Exception:
                    # If parsing fails, try next candidate
                    continue

        # Assign credibility score based on domain
        if (
            self.credibility_enabled
            and "credibility_score" not in result.metadata
            and "source_domain" in result.metadata
        ):
            domain = result.metadata["source_domain"]

            # Try direct domain match first
            score = self.credibility_tiers.get(domain)

            # If no direct match, try matching domain endings (.edu, .gov)
            if not score:
                for ending, tier_score in self.credibility_tiers.items():
                    if domain.endswith(ending):
                        score = tier_score
                        break

            # Assign score or default
            result.metadata["credibility_score"] = (
                score or self.DEFAULT_CREDIBILITY_SCORE
            )

    def _merge_raw_content(self, results: List[SearchResult]) -> List[SearchResult]:
        """
        For duplicate URLs where some have raw_content and others don't,
        prefer the result with raw_content while preserving metadata.

        Args:
            results: List of search results to merge

        Returns:
            List of merged results
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
                # No result has raw_content, use highest-scored one
                merged_results.append(max(group, key=lambda x: x.score))

        return merged_results

    def _rank_results(
        self,
        results: List[SearchResult],
        provider_results: Dict[str, Union[SearchResponse, List[SearchResult]]],
    ) -> List[SearchResult]:
        """Rank results with enhanced algorithm incorporating multiple factors.

        Factors include:
        1. Provider quality weight
        2. Original result score
        3. Consensus boost (results appearing in multiple providers)
        4. Recency boost (optional)
        5. Source credibility score (optional)

        Args:
            results: List of search results to rank
            provider_results: Dictionary of provider responses

        Returns:
            List of ranked search results
        """
        if not results:
            return []

        # Get current date for recency calculations
        current_date = datetime.datetime.now().date()

        # Apply consensus boost for results appearing in multiple providers
        url_counts = {}
        for result in results:
            url = result.url
            if url in url_counts:
                url_counts[url] += 1
            else:
                url_counts[url] = 1

        # Calculate combined scores with all ranking factors
        for result in results:
            # 1. Provider weight factor
            provider_weight = self.provider_weights.get(result.source, 0.8)

            # 2. Base result score
            result_score = result.score

            # 3. Consensus factor: boost for results appearing in multiple providers
            consensus_factor = url_counts[result.url] / len(provider_results)
            consensus_boost = 1.0 + (consensus_factor * 0.5)  # Up to 50% boost

            # 4. Recency factor (if enabled)
            recency_boost = 1.0
            if self.recency_enabled and "published_date" in result.metadata:
                try:
                    pub_date_str = result.metadata["published_date"]
                    pub_date = None

                    # Handle different date formats
                    if isinstance(pub_date_str, str):
                        pub_date = dateparser.parse(pub_date_str).date()
                    elif isinstance(pub_date_str, datetime.datetime):
                        pub_date = pub_date_str.date()

                    if pub_date:
                        days_old = (current_date - pub_date).days

                        # Apply recency boost based on age
                        if days_old <= self.RECENCY_DECAY_DAYS["very_recent"]:
                            recency_boost = self.RECENCY_BOOST["very_recent"]
                        elif days_old <= self.RECENCY_DECAY_DAYS["recent"]:
                            recency_boost = self.RECENCY_BOOST["recent"]
                        elif days_old <= self.RECENCY_DECAY_DAYS["somewhat_recent"]:
                            recency_boost = self.RECENCY_BOOST["somewhat_recent"]

                        # Store age info in metadata
                        result.metadata["days_old"] = days_old
                except Exception:
                    # If date parsing fails, don't apply recency boost
                    pass

            # 5. Credibility factor (if enabled)
            credibility_factor = 1.0
            if self.credibility_enabled and "credibility_score" in result.metadata:
                credibility_factor = result.metadata["credibility_score"]

            # Calculate combined score using all factors
            combined_score = (
                provider_weight
                * result_score
                * consensus_boost
                * recency_boost
                * credibility_factor
            )

            # Store all factors in metadata for debugging
            result.metadata["combined_score"] = combined_score
            result.metadata["provider_weight"] = provider_weight
            result.metadata["consensus_factor"] = consensus_factor
            result.metadata["consensus_boost"] = consensus_boost

            if recency_boost != 1.0:
                result.metadata["recency_boost"] = recency_boost

            if credibility_factor != 1.0:
                result.metadata["credibility_factor"] = credibility_factor

        # Sort by combined score
        return sorted(
            results, key=lambda x: x.metadata.get("combined_score", 0.0), reverse=True
        )

    def rank_by_weighted_score(
        self,
        results: List[SearchResult],
        custom_weights: Optional[Dict[str, float]] = None,
    ) -> List[SearchResult]:
        """Simple ranking by applying source weights to scores.

        This method is provided for compatibility and simple use cases.
        The main merge_results method provides more sophisticated ranking.

        Args:
            results: List of search results to rank
            custom_weights: Optional custom weight mapping (uses instance weights if None)

        Returns:
            Ranked list of results
        """
        if not results:
            return []

        weights = custom_weights or self.provider_weights

        for result in results:
            weight = weights.get(result.source, 0.5)
            result.metadata["weighted_score"] = result.score * weight

        return sorted(
            results, key=lambda x: x.metadata.get("weighted_score", 0.0), reverse=True
        )
