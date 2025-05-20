"""Result processing package for search results.

This package contains modules for processing search results:
- deduplication: Remove duplicates based on URL and content similarity
- merger: Merge and rank results from multiple providers
- metadata_enrichment: Extract and normalize metadata from results
"""

from .deduplication import remove_duplicates
from .merger import ResultMerger
from .metadata_enrichment import enrich_result_metadata

__all__ = ["ResultMerger", "remove_duplicates", "enrich_result_metadata"]
