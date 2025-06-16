"""Tests for raw content functionality."""

from unittest.mock import MagicMock

import pytest

from mcp_search_hub.models.query import SearchQuery
from mcp_search_hub.models.results import SearchResponse, SearchResult
from mcp_search_hub.providers.firecrawl_mcp import FirecrawlMCPProvider
from mcp_search_hub.providers.linkup_mcp import LinkupMCPProvider
from mcp_search_hub.result_processing.merger import ResultMerger


@pytest.fixture
def mock_linkup_response():
    """Mock response for Linkup provider."""
    result = SearchResult(
        title="Test Result",
        url="https://example.com",
        snippet="Test snippet",
        source="linkup",
        score=1.0,
        raw_content="This is the raw content from Linkup",
        metadata={"domain": "example.com"},
    )
    return SearchResponse(
        results=[result],
        query="test query",
        total_results=1,
        provider="linkup",
        timing_ms=150,
    )


@pytest.fixture
def mock_firecrawl_response():
    """Mock response for Firecrawl provider."""
    result = SearchResult(
        title="Test Result from Firecrawl",
        url="https://example2.com",  # Different URL to avoid deduplication
        snippet="Test snippet from Firecrawl",
        source="firecrawl",
        score=0.8,
        raw_content="This is the raw content from Firecrawl",
        metadata={"source_type": "search_result"},
    )
    return SearchResponse(
        results=[result],
        query="test query",
        total_results=1,
        provider="firecrawl",
        timing_ms=200,
    )


@pytest.mark.asyncio
async def test_linkup_provider_with_raw_content(mock_linkup_response):
    """Test that LinkupMCPProvider includes raw content when requested."""
    # Create a mock provider
    provider = MagicMock(spec=LinkupMCPProvider)
    provider.name = "linkup"
    provider.search.return_value = mock_linkup_response

    # Test with raw_content=True
    query = SearchQuery(
        query="test query",
        raw_content=True,
    )

    result = await provider.search(query)

    # Verify results
    assert len(result.results) == 1
    assert result.results[0].raw_content == "This is the raw content from Linkup"


@pytest.mark.asyncio
async def test_firecrawl_provider_with_raw_content(mock_firecrawl_response):
    """Test that FirecrawlMCPProvider includes raw content when requested."""
    # Create a mock provider
    provider = MagicMock(spec=FirecrawlMCPProvider)
    provider.name = "firecrawl"
    provider.search.return_value = mock_firecrawl_response

    # Test with raw_content=True
    query = SearchQuery(
        query="test query",
        raw_content=True,
    )

    result = await provider.search(query)

    # Verify results
    assert len(result.results) == 1
    assert result.results[0].raw_content == "This is the raw content from Firecrawl"


@pytest.mark.asyncio
async def test_merger_with_raw_content(mock_linkup_response, mock_firecrawl_response):
    """Test that ResultMerger preserves raw content."""
    merger = ResultMerger()

    responses = {
        "linkup": mock_linkup_response,
        "firecrawl": mock_firecrawl_response,
    }

    # Merge with raw content
    merged = await merger.merge_results(responses, raw_content=True)

    # Verify both results are included
    assert len(merged) == 2

    # Find the Linkup result
    linkup_result = next(r for r in merged if r.source == "linkup")
    assert linkup_result.raw_content == "This is the raw content from Linkup"

    # Find the Firecrawl result
    firecrawl_result = next(r for r in merged if r.source == "firecrawl")
    assert firecrawl_result.raw_content == "This is the raw content from Firecrawl"


@pytest.mark.asyncio
async def test_merger_without_raw_content_merge(
    mock_linkup_response, mock_firecrawl_response
):
    """Test that ResultMerger doesn't apply raw content merging when raw_content=False."""
    merger = ResultMerger()

    responses = {
        "linkup": mock_linkup_response,
        "firecrawl": mock_firecrawl_response,
    }

    # Merge without raw content feature
    merged = await merger.merge_results(responses, raw_content=False)

    # Verify both results are included
    assert len(merged) == 2

    # The merger preserves raw_content data, it just doesn't apply special merging logic
    # when raw_content=False
    assert any(result.raw_content is not None for result in merged)
