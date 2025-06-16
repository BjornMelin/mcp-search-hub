"""Duplicate removal with fuzzy matching support."""

import re
import time
from typing import Any

from rapidfuzz import fuzz
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from w3lib.url import canonicalize_url

from ..models.base import HealthStatus
from ..models.component import ResultProcessorBase
from ..models.results import SearchResult
from ..utils.logging import get_logger

logger = get_logger(__name__)


# Simple config type for deduplication
DuplicationConfig = dict[str, Any]


class DuplicateRemover(ResultProcessorBase[DuplicationConfig]):
    """Component for removing duplicate search results."""

    def __init__(
        self,
        name: str = "deduplicator",
        config: DuplicationConfig | None = None,
    ):
        """Initialize the duplicate remover."""
        # If no config is provided, create a default one
        if config is None:
            config = {
                "name": name,
                "fuzzy_url_threshold": 92.0,
                "content_similarity_threshold": 0.85,
                "use_content_similarity": True,
            }

        super().__init__(name, config)

        # Initialize metrics
        self.metrics = {
            "total_deduplication_runs": 0,
            "total_input_results": 0,
            "total_output_results": 0,
            "avg_deduplication_ratio": 0.0,
            "avg_processing_time_ms": 0.0,
            "last_run_time": None,
        }

        self.initialized = False

    async def initialize(self) -> None:
        """Initialize the deduplicator component."""
        await super().initialize()
        self.initialized = True
        logger.info("Initialized DuplicateRemover component")

    def process_results(
        self,
        results: list[SearchResult],
        fuzzy_url_threshold: float | None = None,
        content_similarity_threshold: float | None = None,
        use_content_similarity: bool | None = None,
    ) -> list[SearchResult]:
        """
        Process search results to remove duplicates.

        Args:
            results: List of search results to deduplicate
            fuzzy_url_threshold: Threshold for fuzzy URL matching (0-100)
            content_similarity_threshold: Threshold for content similarity (0.0-1.0)
            use_content_similarity: Whether to use content similarity for deduplication

        Returns:
            Deduplicated search results
        """
        start_time = time.time()

        # Use defaults from config if not specified
        if fuzzy_url_threshold is None:
            fuzzy_url_threshold = self.config["fuzzy_url_threshold"]

        if content_similarity_threshold is None:
            content_similarity_threshold = self.config["content_similarity_threshold"]

        if use_content_similarity is None:
            use_content_similarity = self.config["use_content_similarity"]

        # Perform deduplication
        output_results = remove_duplicates(
            results=results,
            fuzzy_url_threshold=fuzzy_url_threshold,
            content_similarity_threshold=content_similarity_threshold,
            use_content_similarity=use_content_similarity,
        )

        # Update metrics
        self._update_metrics(
            input_count=len(results),
            output_count=len(output_results),
            duration=time.time() - start_time,
        )

        return output_results

    def _update_metrics(
        self,
        input_count: int,
        output_count: int,
        duration: float,
    ) -> None:
        """Update component metrics."""
        self.metrics["total_deduplication_runs"] += 1
        self.metrics["total_input_results"] += input_count
        self.metrics["total_output_results"] += output_count
        self.metrics["last_run_time"] = time.time()

        # Calculate deduplication ratio
        if input_count > 0:
            dedup_ratio = 1.0 - (output_count / input_count)

            # Update with moving average
            prev_avg = self.metrics.get("avg_deduplication_ratio", 0.0)
            prev_count = self.metrics["total_deduplication_runs"] - 1
            self.metrics["avg_deduplication_ratio"] = (
                prev_avg * prev_count + dedup_ratio
            ) / self.metrics["total_deduplication_runs"]

        # Update avg processing time with moving average
        prev_avg = self.metrics.get("avg_processing_time_ms", 0.0)
        prev_count = self.metrics["total_deduplication_runs"] - 1
        self.metrics["avg_processing_time_ms"] = (
            prev_avg * prev_count + duration * 1000
        ) / self.metrics["total_deduplication_runs"]

    def get_metrics(self) -> dict[str, Any]:
        """Get component metrics."""
        metrics = dict(self.metrics)

        # Add derived metrics
        if self.metrics["total_deduplication_runs"] > 0:
            metrics["avg_removed_per_run"] = (
                self.metrics["total_input_results"]
                - self.metrics["total_output_results"]
            ) / self.metrics["total_deduplication_runs"]

        return metrics

    def reset_metrics(self) -> None:
        """Reset all metrics."""
        self.metrics = {
            "total_deduplication_runs": 0,
            "total_input_results": 0,
            "total_output_results": 0,
            "avg_deduplication_ratio": 0.0,
            "avg_processing_time_ms": 0.0,
            "last_run_time": None,
        }

    async def check_health(self) -> tuple[HealthStatus, str]:
        """Check component health."""
        if not self.initialized:
            return HealthStatus.UNHEALTHY, "DuplicateRemover not initialized"

        return HealthStatus.HEALTHY, "DuplicateRemover is healthy"

    async def _do_execute(self, *args: Any, **kwargs: Any) -> list[SearchResult]:
        """Execute the processor with the given arguments."""
        # Extract results from args or kwargs
        results = None
        if args and isinstance(args[0], list):
            results = args[0]
        elif "results" in kwargs:
            results = kwargs["results"]
        else:
            raise ValueError("No results provided to execute")

        # Extract other parameters
        fuzzy_url_threshold = kwargs.get(
            "fuzzy_url_threshold", self.config["fuzzy_url_threshold"]
        )
        content_similarity_threshold = kwargs.get(
            "content_similarity_threshold", self.config["content_similarity_threshold"]
        )
        use_content_similarity = kwargs.get(
            "use_content_similarity", self.config["use_content_similarity"]
        )

        # Process results
        return self.process_results(
            results,
            fuzzy_url_threshold,
            content_similarity_threshold,
            use_content_similarity,
        )


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
    results: list[SearchResult],
    threshold: float = 92.0,
    use_content_similarity: bool = True,
    content_threshold: float = 0.85,
) -> list[SearchResult]:
    """Apply fuzzy matching to find near-duplicates."""
    # Sort by score to prioritize higher-scored results
    sorted_results = sorted(results, key=lambda x: x.score, reverse=True)

    # Keep track of which results to include in the final set
    keep_indices = {0}  # Always keep the highest-scored result

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
            final_indices = {0}  # Always keep highest scored
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
        except Exception as e:
            # If vectorization fails, just return the URL-deduplicated results
            logger.warning(f"Content similarity check failed: {e}")

    # Return URL-deduplicated results
    return [sorted_results[i] for i in keep_indices]
