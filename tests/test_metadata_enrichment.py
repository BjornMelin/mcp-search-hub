"""Tests for metadata enrichment functionality."""

import re
from datetime import datetime, timedelta

import pytest

from mcp_search_hub.models.results import SearchResult
from mcp_search_hub.result_processing.metadata_enrichment import (
    enrich_result_metadata,
    extract_and_normalize_date,
    extract_content_metrics,
    extract_source_info,
    generate_citation,
)


def test_extract_and_normalize_date():
    """Test date extraction and normalization from different sources."""
    # Test with date in title
    result1 = SearchResult(
        title="News article from March 15, 2023",
        url="https://example.com/article",
        snippet="This is a news article.",
        source="provider1",
        score=0.9,
    )
    extract_and_normalize_date(result1)
    assert "normalized_date" in result1.metadata
    assert result1.metadata.get("year") == 2023
    assert result1.metadata.get("month") == 3
    assert result1.metadata.get("day") == 15
    assert result1.metadata.get("human_date") == "March 15, 2023"
    
    # Test with date in snippet
    result2 = SearchResult(
        title="Technology news",
        url="https://example.com/tech",
        snippet="Latest updates from May 5, 2024.",
        source="provider1",
        score=0.9,
    )
    extract_and_normalize_date(result2)
    assert "normalized_date" in result2.metadata
    assert result2.metadata.get("year") == 2024
    assert result2.metadata.get("month") == 5
    assert result2.metadata.get("day") == 5
    
    # Test with ISO date format
    result3 = SearchResult(
        title="Report",
        url="https://example.com/report",
        snippet="Published on 2023-12-25.",
        source="provider1",
        score=0.9,
    )
    extract_and_normalize_date(result3)
    assert "normalized_date" in result3.metadata
    assert result3.metadata.get("year") == 2023
    assert result3.metadata.get("month") == 12
    assert result3.metadata.get("day") == 25
    
    # Test with existing date in metadata
    result4 = SearchResult(
        title="Existing metadata",
        url="https://example.com/report",
        snippet="Some text.",
        source="provider1",
        score=0.9,
        metadata={"published_date": "2022-11-30T15:30:00"},
    )
    extract_and_normalize_date(result4)
    assert "normalized_date" in result4.metadata
    assert result4.metadata.get("year") == 2022
    assert result4.metadata.get("month") == 11
    assert result4.metadata.get("day") == 30
    
    # Test relative time descriptions
    # Create dates at various time points in the past
    now = datetime.now()
    hours_ago = (now - timedelta(hours=3)).isoformat()
    yesterday = (now - timedelta(days=1)).isoformat()
    days_ago = (now - timedelta(days=5)).isoformat()
    weeks_ago = (now - timedelta(days=21)).isoformat()
    months_ago = (now - timedelta(days=100)).isoformat()
    years_ago = (now - timedelta(days=800)).isoformat()
    
    # Hours ago
    result5 = SearchResult(
        title="Recent news",
        url="https://example.com/recent",
        snippet="Text",
        source="provider1",
        score=0.9,
        metadata={"published_date": hours_ago},
    )
    extract_and_normalize_date(result5)
    assert "relative_time" in result5.metadata
    assert "hour" in result5.metadata["relative_time"]
    
    # Yesterday
    result6 = SearchResult(
        title="Yesterday news",
        url="https://example.com/yesterday",
        snippet="Text",
        source="provider1",
        score=0.9,
        metadata={"published_date": yesterday},
    )
    extract_and_normalize_date(result6)
    assert "relative_time" in result6.metadata
    assert "Yesterday" in result6.metadata["relative_time"]
    
    # Days ago
    result7 = SearchResult(
        title="Days ago news",
        url="https://example.com/days",
        snippet="Text",
        source="provider1",
        score=0.9,
        metadata={"published_date": days_ago},
    )
    extract_and_normalize_date(result7)
    assert "relative_time" in result7.metadata
    assert "days ago" in result7.metadata["relative_time"]
    
    # Weeks ago
    result8 = SearchResult(
        title="Weeks ago news",
        url="https://example.com/weeks",
        snippet="Text",
        source="provider1",
        score=0.9,
        metadata={"published_date": weeks_ago},
    )
    extract_and_normalize_date(result8)
    assert "relative_time" in result8.metadata
    assert "week" in result8.metadata["relative_time"]
    
    # Months ago
    result9 = SearchResult(
        title="Months ago news",
        url="https://example.com/months",
        snippet="Text",
        source="provider1",
        score=0.9,
        metadata={"published_date": months_ago},
    )
    extract_and_normalize_date(result9)
    assert "relative_time" in result9.metadata
    assert "month" in result9.metadata["relative_time"]
    
    # Years ago
    result10 = SearchResult(
        title="Years ago news",
        url="https://example.com/years",
        snippet="Text",
        source="provider1",
        score=0.9,
        metadata={"published_date": years_ago},
    )
    extract_and_normalize_date(result10)
    assert "relative_time" in result10.metadata
    assert "year" in result10.metadata["relative_time"]


def test_extract_source_info():
    """Test extraction of source domain and organization."""
    # Test with commercial domain
    result1 = SearchResult(
        title="Commercial site",
        url="https://example.com/article",
        snippet="This is from a commercial site.",
        source="provider1",
        score=0.9,
    )
    extract_source_info(result1)
    assert result1.metadata.get("source_domain") == "example.com"
    assert result1.metadata.get("organization") == "Example"
    
    # Test with academic domain
    result2 = SearchResult(
        title="Academic site",
        url="https://research.stanford.edu/paper",
        snippet="This is from an academic site.",
        source="provider1",
        score=0.9,
    )
    extract_source_info(result2)
    assert result2.metadata.get("source_domain") == "research.stanford.edu"
    assert "organization" in result2.metadata
    assert "stanford" in result2.metadata["organization"].lower()
    
    # Test with government domain
    result3 = SearchResult(
        title="Government site",
        url="https://nih.gov/research",
        snippet="This is from a government site.",
        source="provider1",
        score=0.9,
    )
    extract_source_info(result3)
    assert result3.metadata.get("source_domain") == "nih.gov"
    assert "organization" in result3.metadata
    
    # Test with kebab-case domain
    result4 = SearchResult(
        title="Kebab case domain",
        url="https://new-york-times.com/article",
        snippet="This is from a hyphenated domain.",
        source="provider1",
        score=0.9,
    )
    extract_source_info(result4)
    assert result4.metadata.get("source_domain") == "new-york-times.com"
    assert result4.metadata.get("organization") == "New York Times"


def test_extract_content_metrics():
    """Test extraction of content metrics like reading time."""
    # Test with raw content
    result1 = SearchResult(
        title="Article with raw content",
        url="https://example.com/article",
        snippet="Short snippet",
        source="provider1",
        score=0.9,
        raw_content=" ".join(["word"] * 1000),  # 1000 words
    )
    extract_content_metrics(result1)
    assert "word_count" in result1.metadata
    assert result1.metadata["word_count"] == 1000
    assert "reading_time" in result1.metadata
    assert 4 <= result1.metadata["reading_time"] <= 5  # ~4-5 minutes at 225 wpm
    assert "reading_time_display" in result1.metadata
    assert "minute" in result1.metadata["reading_time_display"]
    
    # Test with snippet only
    result2 = SearchResult(
        title="Article with snippet only",
        url="https://example.com/article",
        snippet=" ".join(["word"] * 50),  # 50 words
        source="provider1",
        score=0.9,
    )
    extract_content_metrics(result2)
    assert "word_count" in result2.metadata
    assert result2.metadata["word_count"] == 50
    assert "reading_time" in result2.metadata
    assert result2.metadata["reading_time"] == 1  # Minimum 1 minute
    
    # Test with images in raw content
    result3 = SearchResult(
        title="Article with images",
        url="https://example.com/article",
        snippet="Short snippet",
        source="provider1",
        score=0.9,
        raw_content=(
            "Text with an <img src='image1.jpg'> embedded image "
            "and another <img src=\"https://example.com/image2.jpg\"> image. "
            "Also a ![Markdown Image](image3.jpg) syntax."
        ),
    )
    extract_content_metrics(result3)
    assert "image_count" in result3.metadata
    assert result3.metadata["image_count"] >= 3  # Should detect all 3 images


def test_generate_citation():
    """Test generation of citations in different formats."""
    # Test with complete metadata
    result1 = SearchResult(
        title="Comprehensive Article",
        url="https://example.com/article",
        snippet="Complete metadata test",
        source="provider1",
        score=0.9,
        metadata={
            "author": "Jane Smith",
            "organization": "Example News",
            "published_date": "2023-08-15",
            "source_domain": "example.com",
        },
    )
    generate_citation(result1)
    assert "citation" in result1.metadata
    assert "academic_citation" in result1.metadata
    assert "Jane Smith" in result1.metadata["citation"]
    assert "Example News" in result1.metadata["citation"]
    assert "2023" in result1.metadata["citation"]
    assert "Jane Smith" in result1.metadata["academic_citation"]
    
    # Test with minimal metadata
    result2 = SearchResult(
        title="Minimal Metadata",
        url="https://minimal.com/article",
        snippet="Just the basics",
        source="provider1",
        score=0.9,
        metadata={
            "source_domain": "minimal.com",
        },
    )
    generate_citation(result2)
    assert "citation" in result2.metadata
    assert "minimal.com" in result2.metadata["citation"]
    
    # Test with no extractable metadata
    result3 = SearchResult(
        title="No Metadata",
        url="https://example.org",
        snippet="No extractable metadata",
        source="provider1",
        score=0.9,
    )
    # First extract domain info to simulate real-world usage
    extract_source_info(result3)
    generate_citation(result3)
    assert "citation" in result3.metadata
    assert "No Metadata" in result3.metadata["citation"]


def test_enrich_result_metadata_full_pipeline():
    """Test the complete metadata enrichment pipeline."""
    # Create a result with minimal initial metadata
    result = SearchResult(
        title="Python Programming Guide for 2023",
        url="https://python-tips.org/guide/2023",
        snippet="Published May 15, 2023. This comprehensive guide covers Python programming techniques for beginners and experienced developers.",
        source="provider1",
        score=0.9,
        raw_content=(
            "# Python Programming Guide 2023\n\n"
            "Published on May 15, 2023 by John Smith.\n\n"
            "This comprehensive guide covers Python programming techniques "
            "for both beginners and experienced developers.\n\n"
            "![Python Logo](python-logo.png)\n\n"
            + " ".join(["word"] * 1000)  # Add 1000 more words
        ),
    )
    
    # Run the complete enrichment pipeline
    enrich_result_metadata(result)
    
    # Verify all types of metadata were added
    assert "normalized_date" in result.metadata
    assert result.metadata.get("year") == 2023
    assert result.metadata.get("month") == 5
    assert result.metadata.get("day") == 15
    
    assert "source_domain" in result.metadata
    assert result.metadata.get("source_domain") == "python-tips.org"
    assert "organization" in result.metadata
    assert "Python Tips" in result.metadata.get("organization")
    
    assert "word_count" in result.metadata
    assert result.metadata.get("word_count") > 1000
    assert "reading_time" in result.metadata
    assert result.metadata.get("reading_time") >= 4  # Should be at least 4 minutes
    assert "image_count" in result.metadata
    assert result.metadata.get("image_count") >= 1
    
    assert "citation" in result.metadata
    assert "Python Programming Guide" in result.metadata.get("citation")
    assert "2023" in result.metadata.get("citation")