"""Duplicate removal functions with fuzzy matching support."""

import re
from typing import List, Optional, Tuple

from rapidfuzz import fuzz
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from w3lib.url import canonicalize_url

from ..models.results import SearchResult


def remove_duplicates(
    results: list[SearchResult],
    fuzzy_url_threshold: float = 92.0,
    content_similarity_threshold: float = 0.85,
    use_content_similarity: bool = True,
) -> list[SearchResult]:
    """
    Remove duplicate results using both URL and content-based similarity.

    Args:
        results: List of search results to deduplicate
        fuzzy_url_threshold: Threshold for fuzzy URL matching (0-100)
        content_similarity_threshold: Threshold for content similarity (0-1)
        use_content_similarity: Whether to use content-based similarity detection

    Returns:
        Deduplicated list of search results
    """
    if not results:
        return []

    # Step 1: Normalize URLs and group exact duplicates
    unique_results: List[SearchResult] = []
    normalized_urls = {}

    for result in results:
        normalized_url = _normalize_url(result.url)

        if normalized_url in normalized_urls:
            # Keep the result with the higher score if it's an exact URL match
            existing_result = normalized_urls[normalized_url]
            if result.score > existing_result.score:
                # Merge metadata before replacing the result
                _merge_duplicate_metadata(result, existing_result)
                idx = unique_results.index(existing_result)
                unique_results[idx] = result
                normalized_urls[normalized_url] = result
            else:
                # If keeping the existing result, merge metadata from the duplicate
                _merge_duplicate_metadata(existing_result, result)
        else:
            normalized_urls[normalized_url] = result
            unique_results.append(result)

    # Step 2: Apply fuzzy URL matching
    fuzzy_deduplicated = _fuzzy_url_deduplication(
        unique_results, threshold=fuzzy_url_threshold
    )

    # Step 3: Apply content-based similarity (if enabled)
    if use_content_similarity and len(fuzzy_deduplicated) > 1:
        return _content_based_deduplication(
            fuzzy_deduplicated, threshold=content_similarity_threshold
        )

    return fuzzy_deduplicated


def _normalize_url(url: str) -> str:
    """
    Normalize URL for comparison by removing tracking parameters,
    fragments, and other variations.

    Args:
        url: URL to normalize

    Returns:
        Normalized URL string
    """
    # Use w3lib's canonicalize_url for comprehensive normalization
    # This handles percent encoding, query param sorting, and more
    normalized = canonicalize_url(
        url,
        keep_blank_values=False,  # Remove empty query params
        keep_fragments=False,  # Remove URL fragments
    )

    # Additional domain-specific filtering
    if "?" in normalized:
        # Remove common tracking and session parameters
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
            "token=",
            "auth=",
            "_hsenc=",
            "yclid=",
            "_ga=",
            "_gl=",
            "oly_",
            "msclkid=",
            "at_",
            "cmp=",
            "adg=",
            "kwd=",
            "dvc=",
            "plc=",
        ]

        base, params = normalized.split("?", 1)
        params_to_keep = []

        for param in params.split("&"):
            # Skip tracking parameters beyond w3lib's normalization
            if not any(tracker in param.lower() for tracker in tracking_params):
                params_to_keep.append(param)

        normalized = base + "?" + "&".join(params_to_keep) if params_to_keep else base

    # Remove common URL prefixes (only www and m subdomains)
    normalized = re.sub(r"^(https?://)?(www\d?\.|m\.)?", "", normalized)

    # Remove trailing slashes
    normalized = normalized.rstrip("/")

    # Lowercase the URL
    normalized = normalized.lower()

    # Remove language/locale path segments if present
    # For example: example.com/en-us/page -> example.com/page
    normalized = re.sub(r"/[a-z]{2}(-[a-z]{2})?/", "/", normalized)

    return normalized


def _fuzzy_url_deduplication(
    results: List[SearchResult], threshold: float = 92.0
) -> List[SearchResult]:
    """
    Remove near-duplicate results based on fuzzy URL matching.

    Args:
        results: List of search results
        threshold: Similarity threshold (0-100) for fuzzy URL matching

    Returns:
        Deduplicated list of search results
    """
    if len(results) <= 1:
        return results

    # Sort by score (highest first) to prioritize better results
    sorted_results = sorted(results, key=lambda x: x.score, reverse=True)
    deduplicated = [sorted_results[0]]

    # Check each result against the deduplicated list
    for result in sorted_results[1:]:
        is_duplicate = False
        normalized_url = _normalize_url(result.url)

        for kept_result in deduplicated:
            kept_normalized_url = _normalize_url(kept_result.url)

            # Skip exact matches (should be caught in previous step)
            if normalized_url == kept_normalized_url:
                is_duplicate = True
                break

            # Calculate fuzzy similarity
            similarity = fuzz.ratio(normalized_url, kept_normalized_url)

            # Store similarity score in metadata for debugging
            result.metadata["url_similarity_score"] = similarity

            if similarity >= threshold:
                # Mark as duplicate if similarity is above threshold
                is_duplicate = True

                # Store the URL it matched against for debugging
                result.metadata["matched_against_url"] = kept_result.url

                # Merge any metadata we might want to keep
                _merge_duplicate_metadata(kept_result, result)
                break

        if not is_duplicate:
            deduplicated.append(result)

    return deduplicated


def _content_based_deduplication(
    results: List[SearchResult], threshold: float = 0.85
) -> List[SearchResult]:
    """
    Remove near-duplicate results based on content similarity.

    Uses TF-IDF vectorization and cosine similarity to identify content
    that is semantically similar despite having different URLs.

    Args:
        results: List of search results
        threshold: Similarity threshold (0-1) for content similarity

    Returns:
        Deduplicated list of search results
    """
    if len(results) <= 1:
        return results

    # Get content for comparison (title + snippet)
    contents = [f"{r.title} {r.snippet}" for r in results]

    # Skip if content is too short
    if any(len(content) < 20 for content in contents):
        return results

    # Calculate content similarity using TF-IDF and cosine similarity
    vectorizer = TfidfVectorizer(lowercase=True, stop_words="english")
    try:
        tfidf_matrix = vectorizer.fit_transform(contents)
        similarity_matrix = cosine_similarity(tfidf_matrix)
    except Exception:
        # If vectorization fails, return the original results
        return results

    # Sort by score (highest first) to prioritize better results
    sorted_indices = sorted(
        range(len(results)), key=lambda i: results[i].score, reverse=True
    )

    keep_indices = set()
    keep_indices.add(sorted_indices[0])  # Always keep the highest-scored result

    # Check each result against the ones we're keeping
    for i in sorted_indices[1:]:
        is_duplicate = False
        for j in keep_indices:
            similarity = similarity_matrix[i, j]

            # Store similarity in metadata for debugging
            results[i].metadata["content_similarity_score"] = similarity

            if similarity >= threshold:
                # Mark as duplicate if similarity is above threshold
                is_duplicate = True

                # Store which result it matched against for debugging
                results[i].metadata["matched_against_content"] = results[j].title

                # Merge any metadata we might want to keep
                _merge_duplicate_metadata(results[j], results[i])
                break

        if not is_duplicate:
            keep_indices.add(i)

    # Return only the results we decided to keep
    return [results[i] for i in keep_indices]


def _merge_duplicate_metadata(
    kept_result: SearchResult, duplicate_result: SearchResult
) -> None:
    """
    Merge relevant metadata from the duplicate result to the kept result.

    Args:
        kept_result: The result being kept
        duplicate_result: The duplicate result whose metadata might be merged
    """
    # Always merge all metadata keys
    for key, value in duplicate_result.metadata.items():
        # Skip combined_score and other ranking-related keys
        if key in [
            "combined_score",
            "weighted_score",
            "url_similarity_score",
            "content_similarity_score",
            "matched_against_url",
            "matched_against_content",
        ]:
            continue

        # Only add if the key doesn't exist in the kept result
        if key not in kept_result.metadata:
            kept_result.metadata[key] = value
