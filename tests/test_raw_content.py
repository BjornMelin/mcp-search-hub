"""Tests for raw content functionality."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp_search_hub.models.query import SearchQuery
from mcp_search_hub.models.results import SearchResponse, SearchResult
from mcp_search_hub.providers.firecrawl import FirecrawlProvider
from mcp_search_hub.providers.linkup import LinkupProvider
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
        timing_ms=100,
    )


@pytest.fixture
def mock_firecrawl_response():
    """Mock response for Firecrawl provider."""
    result = SearchResult(
        title="Test Result",
        url="https://example.com",
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
async def test_linkup_provider_with_raw_content():
    """Test that LinkupProvider includes raw content when requested."""
    with patch("httpx.AsyncClient") as mock_client:
        # Setup mock response
        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.elapsed.total_seconds.return_value = 0.1
        mock_response.json.return_value = {
            "results": [
                {
                    "title": "Test Title",
                    "url": "https://example.com",
                    "snippet": "Test snippet",
                    "score": 0.95,
                    "domain": "example.com",
                    "content": "Raw content from the page",
                }
            ]
        }

        # Setup client mock
        mock_client_instance = AsyncMock()
        mock_client_instance.post.return_value = mock_response
        mock_client.return_value = mock_client_instance

        # Create provider
        provider = LinkupProvider()
        provider.client = mock_client_instance

        # Test with raw_content=True
        query = SearchQuery(
            query="test query",
            raw_content=True,
        )

        result = await provider.search(query)

        # Verify results
        assert len(result.results) == 1
        assert result.results[0].raw_content == "Raw content from the page"

        # Verify API was called with correct parameters
        mock_client_instance.post.assert_called_once()
        call_args = mock_client_instance.post.call_args[1]
        assert call_args["json"]["output_type"] == "detailed"


@pytest.mark.asyncio
async def test_firecrawl_provider_with_raw_content():
    """Test that FirecrawlProvider includes raw content when requested."""
    with patch("httpx.AsyncClient") as mock_client:
        # Setup mock response
        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.json.return_value = {
            "results": [
                {
                    "title": "Test Title",
                    "url": "https://example.com",
                    "description": "Test description",
                    "markdown": "# Test Markdown\nContent from the page",
                    "html": "<html><body><h1>Test HTML</h1><p>Content from the page</p></body></html>",
                }
            ]
        }

        # Setup client mock
        mock_client_instance = AsyncMock()
        mock_client_instance.post.return_value = mock_response
        mock_client.return_value = mock_client_instance

        # Create provider
        provider = FirecrawlProvider()
        provider.client = mock_client_instance

        # Test with raw_content=True
        query = SearchQuery(
            query="test query",
            raw_content=True,
        )

        result = await provider.search(query)

        # Verify results
        assert len(result.results) == 1
        assert result.results[0].raw_content is not None
        assert "<html>" in result.results[0].raw_content

        # Verify API was called with correct parameters
        mock_client_instance.post.assert_called_once()
        call_args = mock_client_instance.post.call_args[1]
        assert "scrapeOptions" in call_args["json"]
        assert "html" in call_args["json"]["scrapeOptions"]["formats"]


def test_merger_with_raw_content(mock_linkup_response, mock_firecrawl_response):
    """Test that ResultMerger preserves raw content during merging."""
    # Create a scenario with duplicate URLs but different content
    linkup_result = mock_linkup_response.results[0]
    firecrawl_result = mock_firecrawl_response.results[0]

    # Both results have the same URL but different content
    assert linkup_result.url == firecrawl_result.url
    assert linkup_result.raw_content != firecrawl_result.raw_content

    # Create merger
    merger = ResultMerger()

    # Test merging with raw_content=True
    merged_results = merger.merge_results(
        {
            "linkup": mock_linkup_response,
            "firecrawl": mock_firecrawl_response,
        },
        max_results=10,
        raw_content=True,
    )

    # Verify results
    assert len(merged_results) == 1  # Should be deduplicated to 1 result
    assert merged_results[0].raw_content is not None

    # Verify metadata from both sources was preserved
    assert "domain" in merged_results[0].metadata
    assert "source_type" in merged_results[0].metadata
