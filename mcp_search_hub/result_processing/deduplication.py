"""Duplicate removal functions."""

from w3lib.url import canonicalize_url

from ..models.results import SearchResult


def remove_duplicates(results: list[SearchResult]) -> list[SearchResult]:
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
    # Use w3lib's canonicalize_url for comprehensive normalization
    # This handles percent encoding, query param sorting, and more
    normalized = canonicalize_url(
        url,
        keep_blank_values=False,  # Remove empty query params
        keep_fragments=False,  # Remove URL fragments
    )

    # Additional domain-specific filtering
    if "?" in normalized:
        # Remove common tracking parameters that w3lib doesn't handle
        tracking_params = [
            "utm_",
            "gclid",
            "fbclid",
            "ref=",
            "source=",
            "track=",
            "campaign=",
            "affiliate=",
            "click_id=",
            "session_id=",
            "mc_",
            "pk_",
            "piwik_",
        ]

        base, params = normalized.split("?", 1)
        params_to_keep = []

        for param in params.split("&"):
            # Skip tracking parameters beyond w3lib's normalization
            if not any(tracker in param.lower() for tracker in tracking_params):
                params_to_keep.append(param)

        normalized = base + "?" + "&".join(params_to_keep) if params_to_keep else base

    return normalized
