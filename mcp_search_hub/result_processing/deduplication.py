"""Duplicate removal with fuzzy matching support."""

import re
from typing import List

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
    """Remove duplicate results based on URL and content similarity."""
    if not results:
        return []

    # Step 1: Normalize URLs and group exact duplicates
    normalized_urls = {}
    unique_results = []

    for result in results:
        normalized_url = _normalize_url(result.url)

        if normalized_url in normalized_urls:
            # Handle exact URL duplicates - keep the highest score
            existing_result = normalized_urls[normalized_url]
            if result.score > existing_result.score:
                # Merge metadata before replacing
                _merge_metadata(result, existing_result)
                idx = unique_results.index(existing_result)
                unique_results[idx] = result
                normalized_urls[normalized_url] = result
            else:
                # If keeping existing result, merge metadata
                _merge_metadata(existing_result, result)
        else:
            normalized_urls[normalized_url] = result
            unique_results.append(result)

    # Step 2: Apply fuzzy URL matching if needed
    if len(unique_results) > 1:
        unique_results = _apply_fuzzy_matching(
            unique_results,
            threshold=fuzzy_url_threshold,
            use_content_similarity=use_content_similarity,
            content_threshold=content_similarity_threshold,
        )

    return unique_results


def _normalize_url(url: str) -> str:
    """Normalize URL for comparison."""
    # Basic normalization with w3lib
    normalized = canonicalize_url(
        url,
        keep_blank_values=False,
        keep_fragments=False,
    )

    # Remove tracking parameters
    if "?" in normalized:
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
            "token=",
            "auth=",
            "_hsenc=",
            "_ga=",
            "_gl=",
        ]

        base, params = normalized.split("?", 1)
        params_to_keep = []

        for param in params.split("&"):
            if not any(tracker in param.lower() for tracker in tracking_params):
                params_to_keep.append(param)

        normalized = base + "?" + "&".join(params_to_keep) if params_to_keep else base

    # Remove common URL prefixes (only www and m subdomains)
    normalized = re.sub(r"^(https?://)?(www\d?\.|m\.)?", "", normalized)

    # Remove trailing slashes and lowercase
    return normalized.rstrip("/").lower()


def _merge_metadata(target: SearchResult, source: SearchResult) -> None:
    """Merge metadata from source to target."""
    # Add all metadata from source that doesn't exist in target
    for key, value in source.metadata.items():
        # Skip scoring and similarity metrics
        if key in [
            "combined_score",
            "weighted_score",
            "url_similarity_score",
            "content_similarity_score",
            "matched_against_url",
        ]:
            continue

        # Only add if the key doesn't exist in target
        if key not in target.metadata:
            target.metadata[key] = value


def _apply_fuzzy_matching(
    results: List[SearchResult],
    threshold: float = 92.0,
    use_content_similarity: bool = True,
    content_threshold: float = 0.85,
) -> List[SearchResult]:
    """Apply fuzzy matching to find near-duplicates."""
    # Sort by score to prioritize higher-scored results
    sorted_results = sorted(results, key=lambda x: x.score, reverse=True)

    # Keep track of which results to include in the final set
    keep_indices = set([0])  # Always keep the highest-scored result

    # For fuzzy URL matching
    for i in range(1, len(sorted_results)):
        is_duplicate = False
        result = sorted_results[i]
        norm_url_i = _normalize_url(result.url)

        # Compare against all kept results so far
        for j in keep_indices:
            kept_result = sorted_results[j]
            norm_url_j = _normalize_url(kept_result.url)

            # Skip exact matches (handled earlier)
            if norm_url_i == norm_url_j:
                is_duplicate = True
                break

            # Check URL similarity
            url_similarity = fuzz.ratio(norm_url_i, norm_url_j)
            result.metadata["url_similarity_score"] = url_similarity

            if url_similarity >= threshold:
                is_duplicate = True
                _merge_metadata(kept_result, result)
                break

        # If not a duplicate by URL, keep it (for now)
        if not is_duplicate:
            keep_indices.add(i)

    # For content similarity (if enabled)
    if use_content_similarity and len(keep_indices) > 1:
        # Get the results we're keeping so far
        kept_results = [sorted_results[i] for i in keep_indices]

        # Create vectors of title+snippet
        contents = [f"{r.title} {r.snippet}" for r in kept_results]

        try:
            # Generate TF-IDF vectors
            vectorizer = TfidfVectorizer(lowercase=True, stop_words="english")
            tfidf_matrix = vectorizer.fit_transform(contents)
            similarity_matrix = cosine_similarity(tfidf_matrix)

            # Find content duplicates
            final_indices = set([0])  # Always keep highest scored
            for i in range(1, len(kept_results)):
                content_duplicate = False

                for j in final_indices:
                    similarity = similarity_matrix[i, j]
                    kept_results[i].metadata["content_similarity_score"] = similarity

                    if similarity >= content_threshold:
                        content_duplicate = True
                        _merge_metadata(kept_results[j], kept_results[i])
                        break

                if not content_duplicate:
                    final_indices.add(i)

            return [kept_results[i] for i in final_indices]
        except Exception:
            # If vectorization fails, just return the URL-deduplicated results
            pass

    # Return URL-deduplicated results
    return [sorted_results[i] for i in keep_indices]
