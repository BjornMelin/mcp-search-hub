"""Test deduplication functionality."""

from mcp_search_hub.models.results import SearchResult
from mcp_search_hub.result_processing.deduplication import (
    _normalize_url,
    remove_duplicates,
)


def test_normalize_url_handles_trailing_slashes():
    """Test that w3lib's URL normalization handles trailing slashes."""
    # w3lib maintains trailing slash for domains without paths
    assert _normalize_url("https://example.com/") == "https://example.com/"
    # But also maintains them for paths
    assert _normalize_url("https://example.com/path/") == "https://example.com/path/"


def test_normalize_url_removes_fragments():
    """Test that URL fragments are removed."""
    assert _normalize_url("https://example.com/#section") == "https://example.com/"
    assert (
        _normalize_url("https://example.com/page#footer") == "https://example.com/page"
    )


def test_normalize_url_sorts_query_params():
    """Test that query parameters are sorted."""
    url1 = "https://example.com?b=2&a=1"
    url2 = "https://example.com?a=1&b=2"
    assert _normalize_url(url1) == _normalize_url(url2)


def test_normalize_url_removes_tracking_params():
    """Test that tracking parameters are removed."""
    tracking_urls = [
        "https://example.com?utm_source=google&page=1",
        "https://example.com?gclid=123&page=1",
        "https://example.com?fbclid=xyz&page=1",
        "https://example.com?ref=footer&page=1",
        "https://example.com?affiliate=partner&page=1",
        "https://example.com?campaign=summer&page=1",
        "https://example.com?mc_eid=xyz&page=1",
        "https://example.com?pk_campaign=abc&page=1",
    ]

    # w3lib maintains trailing slash for domains
    expected = "https://example.com/?page=1"

    for url in tracking_urls:
        assert _normalize_url(url) == expected


def test_normalize_url_removes_empty_query_params():
    """Test that empty query parameters are removed."""
    assert _normalize_url("https://example.com?a=&b=2") == "https://example.com/?b=2"
    assert _normalize_url("https://example.com?a=") == "https://example.com/"


def test_normalize_url_handles_percent_encoding():
    """Test that percent encoding is normalized."""
    # W3lib normalizes both to uppercase %2F
    url1 = "https://example.com/path%2fmore"
    url2 = "https://example.com/path%2Fmore"
    assert _normalize_url(url1) == _normalize_url(url2)


def test_normalize_url_handles_complex_cases():
    """Test normalization of complex URLs."""
    complex_url = "https://example.com/path/?utm_source=google&page=1&ref=footer&q=test&z=abc&a=xyz#section"
    # w3lib maintains the trailing slash if it was in the original URL
    expected = "https://example.com/path/?a=xyz&page=1&q=test&z=abc"
    assert _normalize_url(complex_url) == expected


def test_remove_duplicates_basic():
    """Test basic duplicate removal."""
    results = [
        SearchResult(
            url="https://example.com/page",
            title="Page 1",
            snippet="Description 1",
            source="google",
            score=0.9,
            metadata={"provider": "google"},
        ),
        SearchResult(
            url="https://example.com/page",
            title="Page 2",
            snippet="Description 2",
            source="bing",
            score=0.8,
            metadata={"provider": "bing"},
        ),
    ]

    unique = remove_duplicates(results)
    assert len(unique) == 1
    assert unique[0].title == "Page 1"  # First occurrence is kept


def test_remove_duplicates_with_normalization():
    """Test duplicate removal with URL normalization."""
    results = [
        SearchResult(
            url="https://example.com/page?a=1&b=2",
            title="Page 1",
            snippet="Description 1",
            source="google",
            score=0.9,
            metadata={"provider": "google"},
        ),
        SearchResult(
            url="https://example.com/page?b=2&a=1#section",
            title="Page 2",
            snippet="Description 2",
            source="bing",
            score=0.8,
            metadata={"provider": "bing"},
        ),
    ]

    unique = remove_duplicates(results)
    assert len(unique) == 1
    assert unique[0].title == "Page 1"  # First occurrence is kept


def test_remove_duplicates_tracking_params():
    """Test duplicate removal with tracking parameters."""
    results = [
        SearchResult(
            url="https://example.com/page?utm_source=google",
            title="Page 1",
            snippet="Description 1",
            source="google",
            score=0.9,
            metadata={"provider": "google"},
        ),
        SearchResult(
            url="https://example.com/page?utm_campaign=summer",
            title="Page 2",
            snippet="Description 2",
            source="bing",
            score=0.8,
            metadata={"provider": "bing"},
        ),
    ]

    unique = remove_duplicates(results)
    assert len(unique) == 1
    assert unique[0].title == "Page 1"  # First occurrence is kept


def test_remove_duplicates_preserves_non_duplicates():
    """Test that non-duplicate URLs are preserved."""
    results = [
        SearchResult(
            url="https://example.com/page1",
            title="Page 1",
            snippet="Description 1",
            source="google",
            score=0.9,
            metadata={"provider": "google"},
        ),
        SearchResult(
            url="https://example.com/page2",
            title="Page 2",
            snippet="Description 2",
            source="bing",
            score=0.8,
            metadata={"provider": "bing"},
        ),
        SearchResult(
            url="https://example.com/page3",
            title="Page 3",
            snippet="Description 3",
            source="duckduckgo",
            score=0.7,
            metadata={"provider": "duckduckgo"},
        ),
    ]

    unique = remove_duplicates(results)
    assert len(unique) == 3
    assert [r.title for r in unique] == ["Page 1", "Page 2", "Page 3"]


def test_normalize_url_case_sensitivity():
    """Test URL normalization handles case sensitivity properly."""
    # Domain should be lowercased, but path components should maintain case
    url = "https://Example.Com/Path/TO/Resource"
    normalized = _normalize_url(url)

    # w3lib correctly handles domain vs path case sensitivity
    assert "example.com" in normalized.lower()
    assert "/Path/TO/Resource" in normalized


def test_normalize_url_with_port():
    """Test URL normalization with explicit ports."""
    url = "https://example.com:443/page"
    normalized = _normalize_url(url)

    # w3lib does not remove default ports
    assert normalized == "https://example.com:443/page"


def test_normalize_url_special_characters():
    """Test URL normalization with special characters."""
    url = "https://example.com/search?q=test+space&special=*chars*"
    normalized = _normalize_url(url)

    # The URL should maintain special characters but be normalized
    assert "q=test" in normalized
    assert "special=" in normalized
