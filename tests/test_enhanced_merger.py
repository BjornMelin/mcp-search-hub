"""Tests for enhanced result merger functionality."""

import datetime

from mcp_search_hub.models.results import SearchResponse, SearchResult
from mcp_search_hub.result_processing.merger import ResultMerger


def test_extract_metadata():
    """Test the metadata extraction functionality."""
    merger = ResultMerger()

    # Create a test result with minimal metadata
    result = SearchResult(
        title="Article from March 15, 2023",
        url="https://example.com/article",
        snippet="This is a snippet from yesterday. Published on 2023-03-15.",
        source="provider1",
        score=0.9,
    )

    # Extract metadata
    merger._extract_metadata(result)

    # Check domain extraction
    assert result.metadata.get("source_domain") == "example.com"

    # Check date extraction
    assert "published_date" in result.metadata
    extracted_date = result.metadata["published_date"]
    assert "2023-03-15" in extracted_date

    # Check credibility scoring
    assert "credibility_score" in result.metadata
    assert result.metadata["credibility_score"] == 0.7  # Default score


def test_credibility_scoring():
    """Test the credibility scoring with various domains."""
    merger = ResultMerger()

    # Create results with different domains
    results = [
        # Tier 1: Academic/government
        SearchResult(
            title="EDU Domain",
            url="https://stanford.edu/research",
            snippet="Academic research",
            source="provider1",
            score=0.9,
        ),
        SearchResult(
            title="Government Domain",
            url="https://nih.gov/research",
            snippet="Government research",
            source="provider1",
            score=0.9,
        ),
        # Tier 2: Reputable news
        SearchResult(
            title="News Domain",
            url="https://nytimes.com/article",
            snippet="News article",
            source="provider1",
            score=0.9,
        ),
        # Tier 3: Tech sources
        SearchResult(
            title="Tech Domain",
            url="https://github.com/repo",
            snippet="Code repository",
            source="provider1",
            score=0.9,
        ),
        # Unknown domain
        SearchResult(
            title="Unknown Domain",
            url="https://example-blog.com/post",
            snippet="Random blog post",
            source="provider1",
            score=0.9,
        ),
    ]

    # Extract metadata for all results
    for result in results:
        merger._extract_metadata(result)

    # Verify credibility scores
    assert results[0].metadata["credibility_score"] == 1.0  # .edu domain
    assert results[1].metadata["credibility_score"] == 1.0  # nih.gov domain
    assert results[2].metadata["credibility_score"] == 0.9  # nytimes.com
    assert results[3].metadata["credibility_score"] == 0.85  # github.com
    assert results[4].metadata["credibility_score"] == 0.7  # Default score


def test_recency_boosting():
    """Test that recency boosting is correctly applied to results with dates."""
    # Create a merger with recency enabled
    merger = ResultMerger(recency_enabled=True)

    # Get current date for relative calculations
    today = datetime.datetime.now().date()

    # Create results with different dates
    results = [
        # Very recent (within 7 days)
        SearchResult(
            title="Very Recent",
            url="https://example.com/recent",
            snippet="Recent article",
            source="provider1",
            score=0.9,
            metadata={
                "published_date": (today - datetime.timedelta(days=3)).isoformat()
            },
        ),
        # Recent (within 30 days)
        SearchResult(
            title="Recent",
            url="https://example.com/somewhat-recent",
            snippet="Somewhat recent article",
            source="provider1",
            score=0.9,
            metadata={
                "published_date": (today - datetime.timedelta(days=20)).isoformat()
            },
        ),
        # Somewhat recent (within 90 days)
        SearchResult(
            title="Somewhat Recent",
            url="https://example.com/less-recent",
            snippet="Less recent article",
            source="provider1",
            score=0.9,
            metadata={
                "published_date": (today - datetime.timedelta(days=60)).isoformat()
            },
        ),
        # Old (over 90 days)
        SearchResult(
            title="Old Article",
            url="https://example.com/old",
            snippet="Old article",
            source="provider1",
            score=0.9,
            metadata={
                "published_date": (today - datetime.timedelta(days=120)).isoformat()
            },
        ),
    ]

    # Create a mock provider result for the rank_results method
    provider_results = {"provider1": results}

    # Rank the results
    ranked = merger._rank_results(results, provider_results)

    # Check that recency boosts were applied
    assert ranked[0].metadata.get("recency_boost") == 1.3  # Very recent
    assert ranked[1].metadata.get("recency_boost") == 1.15  # Recent
    assert ranked[2].metadata.get("recency_boost") == 1.05  # Somewhat recent
    assert "recency_boost" not in ranked[3].metadata  # Old (no boost)

    # Verify order
    assert ranked[0].title == "Very Recent"
    assert ranked[1].title == "Recent"
    assert ranked[2].title == "Somewhat Recent"
    assert ranked[3].title == "Old Article"


def test_consensus_boosting():
    """Test that consensus boosting works for results from multiple providers."""
    # Create a merger
    merger = ResultMerger()

    # Create results that appear in multiple providers
    common_result = SearchResult(
        title="Common Result",
        url="https://example.com/common",
        snippet="This appears in multiple providers",
        source="provider1",
        score=0.9,
    )

    common_result_variant = SearchResult(
        title="Common Result Variant",
        url="https://example.com/common",  # Same URL, different title/source
        snippet="This is the same result from a different provider",
        source="provider2",
        score=0.85,
    )

    unique_result = SearchResult(
        title="Unique Result",
        url="https://example.com/unique",
        snippet="This only appears in one provider",
        source="provider1",
        score=0.9,
    )

    # Create provider results dictionary
    provider_results = {
        "provider1": [common_result, unique_result],
        "provider2": [common_result_variant],
        "provider3": [],  # Empty provider to test edge cases
    }

    # Collect all results for ranking
    all_results = [common_result, common_result_variant, unique_result]

    # Rank the results
    ranked = merger._rank_results(all_results, provider_results)

    # Check consensus factors and boosts
    assert (
        ranked[0].metadata["consensus_factor"] == 2 / 3
    )  # Appears in 2 of 3 providers
    assert ranked[0].metadata["consensus_boost"] > 1.0  # Should get a boost
    assert (
        ranked[2].metadata["consensus_factor"] == 1 / 3
    )  # Appears in 1 of 3 providers
    assert (
        ranked[2].metadata["consensus_boost"] > 1.0
        and ranked[2].metadata["consensus_boost"]
        < ranked[0].metadata["consensus_boost"]
    )

    # Verify that common result ranks higher than unique, despite same score
    assert ranked[0].url == "https://example.com/common"


def test_combined_ranking_factors():
    """Test that all ranking factors work together correctly."""
    # Create a merger with all features enabled
    merger = ResultMerger(
        recency_enabled=True,
        credibility_enabled=True,
    )

    # Get current date for relative calculations
    today = datetime.datetime.now().date()

    # Create diverse results to test various factors together
    results = [
        # Result with high credibility, recent, from good provider
        SearchResult(
            title="High Quality Recent Result",
            url="https://nih.gov/research/recent",
            snippet="Recent high-quality research",
            source="exa",  # High weight provider
            score=0.9,
            metadata={
                "published_date": (today - datetime.timedelta(days=5)).isoformat(),
                # nih.gov will get credibility=1.0 from domain detection
            },
        ),
        # Result with medium credibility, old, from top provider
        SearchResult(
            title="Medium Quality Old Result",
            url="https://medium.com/blog/old",
            snippet="Old article from medium provider",
            source="linkup",  # Highest weight provider
            score=0.9,
            metadata={
                "published_date": (today - datetime.timedelta(days=100)).isoformat(),
                # medium.com will get credibility=0.8 from domain detection
            },
        ),
        # Result with low credibility, very recent, from low provider
        SearchResult(
            title="Low Quality Very Recent Result",
            url="https://unknown-blog.com/recent",
            snippet="Very recent but low quality article",
            source="firecrawl",  # Lower weight provider
            score=0.95,  # Higher base score
            metadata={
                "published_date": (today - datetime.timedelta(days=1)).isoformat(),
                # unknown domain will get default credibility score
            },
        ),
    ]

    # Create a mock provider result for the rank_results method
    # Ensure each result appears in only its provider
    provider_results = {
        "exa": [results[0]],
        "linkup": [results[1]],
        "firecrawl": [results[2]],
    }

    # Add duplicate result to simulate consensus (appears in 2 providers)
    consensus_result = SearchResult(
        title="Consensus Result",
        url="https://example.com/consensus",
        snippet="This appears in multiple providers",
        source="linkup",  # Highest weight provider
        score=0.88,
        metadata={
            "published_date": (today - datetime.timedelta(days=10)).isoformat(),
        },
    )
    results.append(consensus_result)
    consensus_variant = SearchResult(
        title="Consensus Variant",
        url="https://example.com/consensus",  # Same URL
        snippet="Slightly different description",
        source="exa",  # Also high weight
        score=0.85,
    )
    results.append(consensus_variant)

    # Update provider results to include consensus result
    provider_results["linkup"].append(consensus_result)
    provider_results["exa"].append(consensus_variant)

    # Extract metadata for all results
    for result in results:
        merger._extract_metadata(result)

    # Rank the results
    ranked = merger._rank_results(results, provider_results)

    # Print scores for debugging (these are stored in metadata)
    scores = [(r.title, r.metadata.get("combined_score")) for r in ranked]

    # Verify that all ranking factors are present in the metadata
    for result in ranked:
        assert "provider_weight" in result.metadata
        assert "consensus_factor" in result.metadata
        assert "consensus_boost" in result.metadata
        assert "combined_score" in result.metadata

        # Check domain and credibility
        assert "source_domain" in result.metadata

        # Check factors that might not be present in all results
        if "nih.gov" in result.url:
            assert result.metadata.get("credibility_score") == 1.0

        if "days_old" in result.metadata and result.metadata["days_old"] <= 7:
            assert "recency_boost" in result.metadata

    # Check that there's at least one result with consensus boost
    boosted_results = [
        r for r in ranked if r.metadata.get("consensus_boost", 1.0) > 1.0
    ]
    assert len(boosted_results) > 0


def test_merge_results_complete_pipeline():
    """Test the complete merger pipeline with all features enabled."""
    # Create a merger with all features enabled
    merger = ResultMerger(
        recency_enabled=True,
        credibility_enabled=True,
    )

    # Get current date for relative calculations
    today = datetime.datetime.now().date()

    # Create provider results
    provider1_results = [
        SearchResult(
            title="Provider 1 Result A",
            url="https://example.com/result-a",
            snippet="Description A from provider 1",
            source="linkup",
            score=0.95,
            metadata={
                "published_date": (today - datetime.timedelta(days=5)).isoformat(),
            },
        ),
        SearchResult(
            title="Provider 1 Result B",
            url="https://example.com/result-b",
            snippet="Description B from provider 1",
            source="linkup",
            score=0.9,
            metadata={
                "published_date": (today - datetime.timedelta(days=20)).isoformat(),
            },
        ),
        SearchResult(
            title="Duplicate Result",
            url="https://example.com/duplicate",
            snippet="This result appears in multiple providers",
            source="linkup",
            score=0.88,
            raw_content="Raw content from provider 1",
            metadata={
                "published_date": (today - datetime.timedelta(days=10)).isoformat(),
                "author": "John Doe",
            },
        ),
    ]

    provider2_results = [
        SearchResult(
            title="Provider 2 Result C",
            url="https://example.com/result-c",
            snippet="Description C from provider 2",
            source="exa",
            score=0.92,
            metadata={
                "published_date": (today - datetime.timedelta(days=15)).isoformat(),
            },
        ),
        SearchResult(
            title="Duplicate Result Variant",
            url="https://example.com/duplicate",  # Same URL
            snippet="This is the same result seen from provider 2",
            source="exa",
            score=0.85,
            metadata={
                "published_date": (today - datetime.timedelta(days=10)).isoformat(),
                "word_count": 1200,
            },
        ),
        SearchResult(
            title="Similar Content Result",
            url="https://other-domain.com/similar",
            snippet="This result has content similar to Result C but from a different URL",
            source="exa",
            score=0.80,
            metadata={
                "published_date": (today - datetime.timedelta(days=18)).isoformat(),
            },
        ),
    ]

    # Create provider results dictionary with different formats
    provider_results = {
        "linkup": SearchResponse(
            results=provider1_results,
            provider="linkup",
            query="test query",
            total_results=len(provider1_results),
        ),
        "exa": provider2_results,
    }

    # Run complete pipeline
    merged_results = merger.merge_results(
        provider_results,
        max_results=5,
        raw_content=True,
        use_content_similarity=True,
    )

    # Verify results
    # Different content similarity thresholds may result in different numbers of results
    # but we should at least have the most important ones
    assert len(merged_results) >= 3  # At minimum the top results should be present

    # Check that duplicate was properly merged
    duplicate = [r for r in merged_results if r.url == "https://example.com/duplicate"]
    assert len(duplicate) == 1

    # Check that some metadata was merged
    dup_result = duplicate[0]
    assert dup_result.raw_content == "Raw content from provider 1"
    assert dup_result.metadata.get("author") == "John Doe"
    # Note: word_count will be recalculated based on the raw content
    assert "word_count" in dup_result.metadata

    # Check that similar content was deduplicated if threshold was appropriate
    all_urls = [r.url for r in merged_results]
    if "https://other-domain.com/similar" not in all_urls:
        # It was deduplicated with Result C, verify Result C is present
        assert "https://example.com/result-c" in all_urls
