"""Tests for the Firecrawl provider functionality."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from mcp_search_hub.providers.firecrawl import (
    FirecrawlProvider,
    MapOptions,
    CrawlOptions,
    ExtractOptions,
    DeepResearchOptions,
    LLMsTxtOptions,
)
from mcp_search_hub.models.query import SearchQuery
from mcp_search_hub.models.base import HealthStatus


@pytest.fixture
def firecrawl_provider():
    """Create a firecrawl provider instance for testing."""
    provider = FirecrawlProvider()
    # Mock the client to avoid actual API calls
    provider.client = MagicMock()
    provider.client.post = AsyncMock()
    provider.client.get = AsyncMock()
    provider.client.aclose = AsyncMock()
    return provider


@pytest.mark.asyncio
async def test_search(firecrawl_provider):
    """Test the basic search functionality."""
    # Mock response data
    mock_data = {
        "results": [
            {
                "title": "Test Result",
                "url": "https://example.com",
                "description": "This is a test result",
                "content": "This is the full content of the page",
            }
        ]
    }

    mock_response = MagicMock()
    mock_response.json.return_value = mock_data
    mock_response.raise_for_status = MagicMock()
    firecrawl_provider.client.post.return_value = mock_response

    # Execute search
    query = SearchQuery(query="test query", max_results=1)
    response = await firecrawl_provider.search(query)

    # Verify results
    assert response.query == "test query"
    assert response.provider == "firecrawl"
    assert len(response.results) == 1
    assert response.results[0].title == "Test Result"
    assert response.results[0].url == "https://example.com"
    assert response.results[0].snippet == "This is a test result"
    assert (
        response.results[0].metadata["content"]
        == "This is the full content of the page"
    )


@pytest.mark.asyncio
async def test_search_with_raw_content(firecrawl_provider):
    """Test search with raw content requested."""
    # Mock response data
    mock_data = {
        "results": [
            {
                "title": "Test Result",
                "url": "https://example.com",
                "description": "This is a test result",
                "content": "This is the full content of the page",
                "html": "<html><body>Test HTML</body></html>",
                "markdown": "# Test Markdown\n\nThis is markdown content.",
            }
        ]
    }

    mock_response = MagicMock()
    mock_response.json.return_value = mock_data
    mock_response.raise_for_status = MagicMock()
    firecrawl_provider.client.post.return_value = mock_response

    # Execute search with raw_content=True
    query = SearchQuery(query="test query", max_results=1, raw_content=True)
    response = await firecrawl_provider.search(query)

    # Verify results include raw content
    assert response.results[0].raw_content == "<html><body>Test HTML</body></html>"

    # Verify the correct parameters were sent in the API request
    firecrawl_provider.client.post.assert_called_once()
    args, kwargs = firecrawl_provider.client.post.call_args
    assert kwargs["json"]["query"] == "test query"
    assert kwargs["json"]["limit"] == 1
    assert kwargs["json"]["scrapeOptions"]["formats"] == ["markdown", "html"]


@pytest.mark.asyncio
async def test_extraction_query(firecrawl_provider):
    """Test handling of extraction queries."""
    # Mock search response
    mock_search_response = MagicMock()
    mock_search_response.json.return_value = {
        "results": [{"url": "https://example.com"}]
    }
    mock_search_response.raise_for_status = MagicMock()

    # Mock scrape response
    mock_scrape_response = MagicMock()
    mock_scrape_response.json.return_value = {
        "title": "Example Website",
        "markdown": "# Example Website\n\nThis is example content for testing.",
    }
    mock_scrape_response.raise_for_status = MagicMock()

    # Set up the mock to return different responses for different API calls
    firecrawl_provider.client.post.side_effect = [
        mock_search_response,  # First call (search)
        mock_scrape_response,  # Second call (scrape)
    ]

    # Execute an extraction query
    query = SearchQuery(query="extract content from website")
    response = await firecrawl_provider.search(query)

    # Verify results
    assert response.provider == "firecrawl"
    assert len(response.results) == 1
    assert response.results[0].title == "Example Website"
    assert response.results[0].url == "https://example.com"
    assert response.results[0].snippet.startswith("# Example Website")


@pytest.mark.asyncio
async def test_check_status(firecrawl_provider):
    """Test the provider status check."""
    # Mock a successful response
    mock_response = MagicMock()
    mock_response.status_code = 200
    firecrawl_provider.client.get.return_value = mock_response

    status, message = await firecrawl_provider.check_status()

    assert status == HealthStatus.OK
    assert "operational" in message
    firecrawl_provider.client.get.assert_called_once()

    # Test a failed response
    firecrawl_provider.client.get.reset_mock()
    mock_response.status_code = 500
    status, message = await firecrawl_provider.check_status()

    assert status == HealthStatus.DEGRADED
    assert "500" in message


@pytest.mark.asyncio
async def test_firecrawl_map(firecrawl_provider):
    """Test the URL discovery functionality."""
    # Mock successful response
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "success": True,
        "urls": [
            "https://example.com",
            "https://example.com/about",
            "https://example.com/contact",
        ],
    }
    mock_response.raise_for_status = MagicMock()
    firecrawl_provider.client.post.return_value = mock_response

    # Test with default options
    result = await firecrawl_provider.firecrawl_map("https://example.com")

    assert result["success"] is True
    assert len(result["urls"]) == 3
    firecrawl_provider.client.post.assert_called_once()

    # Test with custom options
    firecrawl_provider.client.post.reset_mock()
    options = MapOptions(
        ignore_sitemap=True, include_subdomains=True, limit=10, search="about"
    )

    await firecrawl_provider.firecrawl_map("https://example.com", options)

    args, kwargs = firecrawl_provider.client.post.call_args
    assert kwargs["json"]["url"] == "https://example.com"
    assert kwargs["json"]["ignoreSitemap"] is True
    assert kwargs["json"]["includeSubdomains"] is True
    assert kwargs["json"]["limit"] == 10
    assert kwargs["json"]["search"] == "about"


@pytest.mark.asyncio
async def test_firecrawl_crawl(firecrawl_provider):
    """Test the website crawling functionality."""
    # Mock successful response
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "success": True,
        "crawlId": "test-crawl-id",
        "status": "in_progress",
    }
    mock_response.raise_for_status = MagicMock()
    firecrawl_provider.client.post.return_value = mock_response

    # Test with default options
    result = await firecrawl_provider.firecrawl_crawl("https://example.com")

    assert result["success"] is True
    assert result["crawlId"] == "test-crawl-id"
    firecrawl_provider.client.post.assert_called_once()

    # Test with custom options
    firecrawl_provider.client.post.reset_mock()
    options = CrawlOptions(
        limit=20,
        max_depth=3,
        include_paths=["blog/*"],
        exclude_paths=["admin/*"],
        allow_external_links=True,
        scrape_options={"formats": ["markdown"]},
    )

    await firecrawl_provider.firecrawl_crawl("https://example.com", options)

    args, kwargs = firecrawl_provider.client.post.call_args
    assert kwargs["json"]["url"] == "https://example.com"
    assert kwargs["json"]["limit"] == 20
    assert kwargs["json"]["maxDepth"] == 3
    assert kwargs["json"]["includePaths"] == ["blog/*"]
    assert kwargs["json"]["excludePaths"] == ["admin/*"]
    assert kwargs["json"]["allowExternalLinks"] is True
    assert kwargs["json"]["scrapeOptions"] == {"formats": ["markdown"]}


@pytest.mark.asyncio
async def test_firecrawl_check_crawl_status(firecrawl_provider):
    """Test checking crawl status."""
    # Mock successful response
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "success": True,
        "crawlId": "test-crawl-id",
        "status": "completed",
        "resultsCount": 10,
        "results": [{"url": "https://example.com"}],
    }
    mock_response.raise_for_status = MagicMock()
    firecrawl_provider.client.get.return_value = mock_response

    result = await firecrawl_provider.firecrawl_check_crawl_status("test-crawl-id")

    assert result["success"] is True
    assert result["status"] == "completed"
    assert result["resultsCount"] == 10
    firecrawl_provider.client.get.assert_called_once()


@pytest.mark.asyncio
async def test_firecrawl_extract(firecrawl_provider):
    """Test structured data extraction."""
    # Mock successful response
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "success": True,
        "data": {
            "company_name": "Example Corp",
            "founded_year": 2020,
            "is_public": False,
        },
    }
    mock_response.raise_for_status = MagicMock()
    firecrawl_provider.client.post.return_value = mock_response

    # Test with minimal options
    urls = ["https://example.com/about"]
    result = await firecrawl_provider.firecrawl_extract(urls)

    assert result["success"] is True
    assert "data" in result
    firecrawl_provider.client.post.assert_called_once()

    # Test with full options
    firecrawl_provider.client.post.reset_mock()
    schema = {
        "type": "object",
        "properties": {
            "company_name": {"type": "string"},
            "founded_year": {"type": "number"},
            "is_public": {"type": "boolean"},
        },
    }
    options = ExtractOptions(
        prompt="Extract company information",
        schema=schema,
        system_prompt="You are a helpful assistant",
        enable_web_search=True,
    )

    await firecrawl_provider.firecrawl_extract(urls, options)

    args, kwargs = firecrawl_provider.client.post.call_args
    assert kwargs["json"]["urls"] == urls
    assert kwargs["json"]["prompt"] == "Extract company information"
    assert kwargs["json"]["schema"] == schema
    assert kwargs["json"]["systemPrompt"] == "You are a helpful assistant"
    assert kwargs["json"]["enableWebSearch"] is True


@pytest.mark.asyncio
async def test_firecrawl_deep_research(firecrawl_provider):
    """Test deep research capability."""
    # Mock successful response
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "success": True,
        "results": {
            "summary": "This is a research summary",
            "sources": [
                {"url": "https://example.com/research", "title": "Research Article"}
            ],
        },
    }
    mock_response.raise_for_status = MagicMock()
    firecrawl_provider.client.post.return_value = mock_response

    # Test with minimal options
    result = await firecrawl_provider.firecrawl_deep_research("quantum computing")

    assert result["success"] is True
    assert "results" in result
    firecrawl_provider.client.post.assert_called_once()

    # Test with custom options
    firecrawl_provider.client.post.reset_mock()
    options = DeepResearchOptions(max_depth=5, max_urls=50, time_limit=300)

    await firecrawl_provider.firecrawl_deep_research("quantum computing", options)

    args, kwargs = firecrawl_provider.client.post.call_args
    assert kwargs["json"]["query"] == "quantum computing"
    assert kwargs["json"]["maxDepth"] == 5
    assert kwargs["json"]["maxUrls"] == 50
    assert kwargs["json"]["timeLimit"] == 300


@pytest.mark.asyncio
async def test_firecrawl_generate_llmstxt(firecrawl_provider):
    """Test LLMs.txt generation."""
    # Mock successful response
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "success": True,
        "llmstxt": "# LLMs.txt for example.com\n\nThis website allows AI indexing and summarization.",
    }
    mock_response.raise_for_status = MagicMock()
    firecrawl_provider.client.post.return_value = mock_response

    # Test with minimal options
    result = await firecrawl_provider.firecrawl_generate_llmstxt("https://example.com")

    assert result["success"] is True
    assert "llmstxt" in result
    firecrawl_provider.client.post.assert_called_once()

    # Test with custom options
    firecrawl_provider.client.post.reset_mock()
    options = LLMsTxtOptions(max_urls=20, show_full_text=True)

    await firecrawl_provider.firecrawl_generate_llmstxt("https://example.com", options)

    args, kwargs = firecrawl_provider.client.post.call_args
    assert kwargs["json"]["url"] == "https://example.com"
    assert kwargs["json"]["maxUrls"] == 20
    assert kwargs["json"]["showFullText"] is True


@pytest.mark.asyncio
async def test_url_extraction():
    """Test the URL extraction logic."""
    provider = FirecrawlProvider()

    # Test with http URL
    assert (
        provider._extract_url_from_query("Extract content from http://example.com")
        == "http://example.com"
    )

    # Test with https URL
    assert (
        provider._extract_url_from_query("Extract content from https://example.com")
        == "https://example.com"
    )

    # Test with www URL
    assert (
        provider._extract_url_from_query("Extract content from www.example.com")
        == "https://www.example.com"
    )

    # Test with domain only
    assert (
        provider._extract_url_from_query("Extract content from example.com")
        == "https://example.com"
    )

    # Test with no URL
    assert provider._extract_url_from_query("Extract content from a website") is None


def test_capabilities():
    """Test the capabilities reporting."""
    provider = FirecrawlProvider()
    capabilities = provider.get_capabilities()

    assert "web_content" in capabilities["content_types"]
    assert "extraction" in capabilities["content_types"]
    assert capabilities["features"]["content_extraction"] is True
    assert capabilities["features"]["scraping"] is True
    assert capabilities["features"]["deep_research"] is True
    assert capabilities["features"]["url_discovery"] is True
    assert capabilities["features"]["crawling"] is True
    assert capabilities["features"]["structured_data_extraction"] is True
    assert capabilities["features"]["llms_txt_generation"] is True


def test_estimate_cost():
    """Test the cost estimation logic."""
    provider = FirecrawlProvider()

    # Test basic search query
    assert provider.estimate_cost(SearchQuery(query="search for python")) == 0.02

    # Test extraction query
    assert (
        provider.estimate_cost(SearchQuery(query="extract content from example.com"))
        == 0.05
    )

    # Test research query
    assert (
        provider.estimate_cost(SearchQuery(query="research quantum computing")) == 0.10
    )
