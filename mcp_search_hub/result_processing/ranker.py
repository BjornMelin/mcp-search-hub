"""Result ranking utilities."""

from ..models.results import SearchResult


def rank_by_weighted_score(
    results: list[SearchResult], source_weights: dict[str, float]
) -> list[SearchResult]:
    """
    Rank results by applying source weights to scores.

    Args:
        results: List of search results to rank
        source_weights: Dictionary mapping provider names to quality weights

    Returns:
        Ranked list of results
    """
    for result in results:
        weight = source_weights.get(result.source, 0.5)
        result.metadata["weighted_score"] = result.score * weight

    return sorted(
        results, key=lambda x: x.metadata.get("weighted_score", 0.0), reverse=True
    )
