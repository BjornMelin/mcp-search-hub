"""Result merger and ranking."""

from typing import Dict, List, Any
from ..models.results import SearchResult, SearchResponse
from .deduplication import remove_duplicates


class ResultMerger:
    """Merges and ranks results from multiple providers."""
    
    def merge_results(
        self, 
        provider_results: Dict[str, SearchResponse],
        max_results: int = 10
    ) -> List[SearchResult]:
        """
        Merge results from multiple providers into a unified ranked list.
        
        Args:
            provider_results: Dictionary mapping provider names to their results
            max_results: Maximum number of results to return
            
        Returns:
            List of merged and ranked results
        """
        # Collect all results
        all_results = []
        for provider, response in provider_results.items():
            all_results.extend(response.results)
        
        # Remove duplicates based on URL
        deduplicated = remove_duplicates(all_results)
        
        # Rank combined results
        ranked_results = self._rank_results(deduplicated, provider_results)
        
        # Limit to max_results
        return ranked_results[:max_results]
    
    def _rank_results(
        self, 
        results: List[SearchResult],
        provider_results: Dict[str, SearchResponse]
    ) -> List[SearchResult]:
        """Rank results based on provider quality and result scores."""
        # Provider quality weights
        provider_weights = {
            "linkup": 1.0,      # Excellent factual accuracy
            "exa": 0.95,        # Strong academic focus
            "perplexity": 0.9,  # Good for current events
            "tavily": 0.85,     # Good general search
            "firecrawl": 0.8    # Specialized for content extraction
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
        return sorted(results, key=lambda x: x.metadata.get("combined_score", 0.0), reverse=True)