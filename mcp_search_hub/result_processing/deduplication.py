"""Duplicate removal functions."""

from typing import List
from ..models.results import SearchResult


def remove_duplicates(results: List[SearchResult]) -> List[SearchResult]:
    """Remove duplicate results based on URL."""
    unique_urls = set()
    unique_results = []

    for result in results:
        # Normalize URL
        normalized_url = _normalize_url(result.url)

        if normalized_url not in unique_urls:
            unique_urls.add(normalized_url)
            unique_results.append(result)

    return unique_results


def _normalize_url(url: str) -> str:
    """Normalize URL for comparison."""
    # Remove trailing slashes
    url = url.rstrip("/")

    # Remove query parameters if they appear to be tracking parameters
    if "?" in url:
        base, params = url.split("?", 1)
        params_to_keep = []

        for param in params.split("&"):
            # Skip common tracking parameters
            if any(
                tracker in param for tracker in ["utm_", "ref=", "source=", "track="]
            ):
                continue
            params_to_keep.append(param)

        if params_to_keep:
            url = base + "?" + "&".join(params_to_keep)
        else:
            url = base

    return url.lower()
