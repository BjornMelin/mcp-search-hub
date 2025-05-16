"""Tests for the MCP Search Hub query analyzer."""

import re

import pytest

from mcp_search_hub.models.query import SearchQuery
from mcp_search_hub.query_routing.analyzer import QueryAnalyzer


def test_basic_query_analyzer():
    """Test the basic query analyzer feature extraction."""
    analyzer = QueryAnalyzer()

    # Test academic query
    query = SearchQuery(query="Latest research papers on quantum computing")
    features = analyzer.extract_features(query)
    assert features.content_type == "academic"
    assert features.time_sensitivity > 0.7

    # Test news query
    query = SearchQuery(query="Latest news about AI regulations")
    features = analyzer.extract_features(query)
    assert features.content_type == "news"
    assert features.time_sensitivity > 0.7

    # Test business query
    query = SearchQuery(query="Information about Tesla company financials")
    features = analyzer.extract_features(query)
    assert features.content_type == "business"

    # Test web content query
    query = SearchQuery(query="Extract content from example.com website")
    features = analyzer.extract_features(query)
    assert features.content_type == "web_content"


@pytest.mark.parametrize(
    "query_text,expected_content_type",
    [
        # Academic content types - simple cases
        ("Find research papers on artificial intelligence", "academic"),
        ("Latest scientific publications about climate change", "academic"),
        ("Recent studies on COVID-19 variants", "academic"),
        ("Peer-reviewed articles on neural networks", "academic"),
        ("PhD dissertations about quantum computing", "academic"),
        # Academic content types - complex cases
        ("Find papers published in Nature about genomics", "academic"),
        ("Literature review on machine learning techniques", "academic"),
        ("Meta-analysis of clinical trials for cancer treatments", "academic"),
        ("Scientific research in the field of renewable energy", "academic"),
        ("Conference proceedings from ICML 2023", "academic"),
        # News content types - simple cases
        ("Latest news about the stock market", "news"),
        ("Today's headlines about politics", "news"),
        ("Breaking news on climate agreements", "news"),
        ("Recent updates on technology regulations", "news"),
        ("Current events in the Middle East", "news"),
        # News content types - complex cases
        ("This week's developments in AI legislation", "news"),
        ("Daily news roundup for the tech industry", "news"),
        ("News coverage of the recent elections", "news"),
        ("Press releases from major tech companies today", "news"),
        ("Headlines reported in the Financial Times yesterday", "news"),
        # Technical content types - simple cases
        ("Python programming tutorial", "technical"),
        ("Documentation for FastAPI framework", "technical"),
        ("How to use Docker for containerization", "technical"),
        ("Code examples for React hooks", "technical"),
        ("Library for image processing in Python", "technical"),
        # Technical content types - complex cases
        ("API documentation for AWS S3 service", "technical"),
        ("How to implement authentication in NextJS", "technical"),
        ("Technical specification for HTTP/3 protocol", "technical"),
        ("Software architecture patterns for microservices", "technical"),
        ("Error handling best practices in Rust programming", "technical"),
        # Business content types - simple cases
        ("Company profile for Apple Inc", "business"),
        ("Market analysis of the EV industry", "business"),
        ("Financial reports for Google Q3 2023", "business"),
        ("Startup funding rounds in AI sector", "business"),
        ("LinkedIn profile of Elon Musk", "business"),
        # Business content types - complex cases
        ("Venture capital investments in biotech 2023", "business"),
        ("Competitor analysis for streaming platforms", "business"),
        ("Revenue growth forecast for SaaS companies", "business"),
        ("Series A funding announcements this month", "business"),
        ("Market share data for cloud providers", "business"),
        # Web content types - simple cases
        ("Extract content from nytimes.com", "web_content"),
        ("Scrape product information from amazon.com", "web_content"),
        ("Get text from wikipedia article", "web_content"),
        ("Content from https://example.com/about", "web_content"),
        ("Fetch data from CNN website", "web_content"),
        # Web content types - complex cases
        ("Extract financial data from investor relations page", "web_content"),
        ("Scrape job listings from company career sites", "web_content"),
        ("Web crawling for research paper citations", "web_content"),
        ("Extract information from website about AI ethics", "web_content"),
        ("Get content from multiple pages on github.com", "web_content"),
        # General queries
        ("What is artificial intelligence", "general"),
        ("How to learn piano", "general"),
        ("Definition of blockchain", "general"),
        ("Explain quantum physics", "general"),
        ("Benefits of regular exercise", "general"),
    ],
)
def test_content_type_detection(query_text, expected_content_type):
    """Test content type detection with various query types."""
    analyzer = QueryAnalyzer()
    query = SearchQuery(query=query_text)
    features = analyzer.extract_features(query)
    assert features.content_type == expected_content_type, (
        f"Failed on query: '{query_text}'"
    )


@pytest.mark.parametrize(
    "query_text,expected_content_type",
    [
        # Academic with specialized pattern (peer-reviewed)
        (
            "Find peer-reviewed articles about machine learning",
            "academic",
        ),
        # News with day pattern (today's headlines)
        (
            "What's in today's news headlines?",
            "news",
        ),
        # Technical with how-to pattern
        (
            "How to implement authentication in React",
            "technical",
        ),
        # Business with financial report pattern
        (
            "Financial report for Amazon Q2 2023",
            "business",
        ),
        # Web content with extract data pattern
        (
            "Extract data from https://example.com/products",
            "web_content",
        ),
    ],
)
def test_pattern_matching(query_text, expected_content_type):
    """Test that regex patterns are correctly detected."""
    analyzer = QueryAnalyzer()
    query = SearchQuery(query=query_text)
    features = analyzer.extract_features(query)
    assert features.content_type == expected_content_type


@pytest.mark.parametrize(
    "query_text,expected_content_type",
    [
        # Context adjustments - "research" about companies (should be business, not academic)
        ("Research about Tesla company performance", "business"),
        # Context adjustments - "paper" in technical context (should be technical, not academic)
        ("White paper on the impact of blockchain technology", "technical"),
        # Context adjustments - "latest update" for software (should be technical, not news)
        ("Latest update for Windows 11 operating system", "technical"),
        # Context adjustments - "content" in technical docs (should be technical, not web_content)
        ("Documentation content for Python libraries", "technical"),
        # No context adjustment needed (should be academic)
        ("Research papers in physics", "academic"),
    ],
)
def test_context_awareness(query_text, expected_content_type):
    """
    Test that the analyzer correctly adjusts based on context.

    This test verifies that context adjustments are being made for potentially
    ambiguous terms like "research" (academic vs business) depending on surrounding terms.
    """
    analyzer = QueryAnalyzer()
    query = SearchQuery(query=query_text)
    features = analyzer.extract_features(query)

    # Content type should match expected after context adjustment
    assert features.content_type == expected_content_type, (
        f"Failed on query: '{query_text}'"
    )


@pytest.mark.parametrize(
    "query_text,primary_type,secondary_types",
    [
        # Academic + Business
        (
            "Research papers about Tesla company business model",
            "academic",  # Primary type (highest score)
            ["business"],  # Secondary types that should have significant scores
        ),
        # News + Technical
        (
            "Latest news about Python 3.11 release",
            "news",
            ["technical"],
        ),
        # Academic + Technical
        (
            "Recent research papers on software development methodologies",
            "academic",
            ["technical"],
        ),
        # Business + Web content
        (
            "Extract financial data from Apple company website",
            "web_content",
            ["business"],
        ),
        # News + Business
        (
            "Breaking news about Amazon's latest acquisition",
            "news",
            ["business"],
        ),
    ],
)
def test_mixed_content_detection(query_text, primary_type, secondary_types):
    """
    Test that the analyzer can identify mixed content types in queries.

    This test verifies two things:
    1. The primary content type is correctly identified
    2. We're detecting multiple significant content types internally
    """
    analyzer = QueryAnalyzer()

    # Test that the main content type is correctly identified
    query = SearchQuery(query=query_text)
    features = analyzer.extract_features(query)
    assert features.content_type == primary_type, (
        f"Primary type not correctly identified for: '{query_text}'"
    )

    # Test that we're also detecting the secondary types internally
    text_lower = query_text.lower()
    scores = dict.fromkeys(analyzer.content_type_data.keys(), 0.0)

    # Run keyword matching
    for category, category_data in analyzer.content_type_data.items():
        for _importance_level, keyword_list in category_data.items():
            for keyword, weight in keyword_list:
                if keyword in text_lower:
                    scores[category] += weight

    # Run pattern matching
    for category, patterns in analyzer.content_type_patterns.items():
        for pattern, weight in patterns:
            if re.search(pattern, text_lower):
                scores[category] += weight

    # Adjust for context
    analyzer._adjust_for_context(text_lower, scores)

    # Each secondary type should have a significant score
    for secondary_type in secondary_types:
        assert scores[secondary_type] >= 0.5, (
            f"Secondary type {secondary_type} doesn't have significant score for: '{query_text}'"
        )


@pytest.mark.parametrize(
    "query_text,expected_time_sensitivity",
    [
        # High time sensitivity
        ("Breaking news about the election", 1.0),
        ("What's happening right now in the stock market", 1.0),
        ("Latest research on COVID variants", 1.0),
        # Medium time sensitivity
        ("Recent developments in AI", 0.7),
        ("This week's top stories in tech", 0.7),
        ("Updates on climate policy negotiations", 0.7),
        # Low time sensitivity
        ("This year's trends in fashion", 0.4),
        ("Modern approaches to software architecture", 0.3),
        # Very low/no time sensitivity
        ("Historical analysis of World War II", 0.3),
        ("Theoretical principles of quantum mechanics", 0.3),
    ],
)
def test_time_sensitivity_detection(query_text, expected_time_sensitivity):
    """Test the time sensitivity detection accuracy."""
    analyzer = QueryAnalyzer()
    query = SearchQuery(query=query_text)
    features = analyzer.extract_features(query)
    # Allow for some wiggle room in the comparison
    assert abs(features.time_sensitivity - expected_time_sensitivity) <= 0.1


@pytest.mark.parametrize(
    "query_text,complexity_range",
    [
        # High complexity queries
        (
            "Compare and analyze the relationship between climate change and biodiversity loss, explaining the impact with examples",
            (0.8, 1.0),
        ),
        # Medium complexity queries
        (
            "What are the advantages and disadvantages of electric vehicles compared to hybrid vehicles?",
            (0.5, 0.7),
        ),
        # Low complexity queries
        ("Who is the CEO of Apple?", (0.2, 0.4)),
        ("What is artificial intelligence?", (0.2, 0.4)),
    ],
)
def test_complexity_detection(query_text, complexity_range):
    """Test the query complexity detection accuracy."""
    analyzer = QueryAnalyzer()
    query = SearchQuery(query=query_text)
    features = analyzer.extract_features(query)

    # Check if the complexity is within the expected range
    lower_bound, upper_bound = complexity_range
    assert lower_bound <= features.complexity <= upper_bound, (
        f"Complexity score {features.complexity} for '{query_text}' is outside expected range {complexity_range}"
    )


@pytest.mark.parametrize(
    "query_text,factual_range",
    [
        # Highly factual queries
        ("What is the population of Japan?", (0.7, 1.0)),
        ("When was the first iPhone released?", (0.7, 1.0)),
        ("How many planets are in the solar system?", (0.7, 1.0)),
        # Mixed factual/opinion queries
        ("What are the benefits of remote work?", (0.3, 0.7)),
        # Opinion-seeking queries
        ("What's your opinion on climate change policies?", (0.0, 0.3)),
        ("Why is modern art controversial?", (0.0, 0.3)),
        ("Should companies invest in blockchain technology?", (0.0, 0.3)),
    ],
)
def test_factual_nature_detection(query_text, factual_range):
    """Test the factual nature detection accuracy."""
    analyzer = QueryAnalyzer()
    query = SearchQuery(query=query_text)
    features = analyzer.extract_features(query)

    # Check if the factual_nature is within the expected range
    lower_bound, upper_bound = factual_range
    assert lower_bound <= features.factual_nature <= upper_bound, (
        f"Factual nature score {features.factual_nature} for '{query_text}' is outside expected range {factual_range}"
    )


def test_explicit_content_type_override():
    """Test that explicitly provided content_type overrides detection."""
    analyzer = QueryAnalyzer()

    # Query that would normally be detected as "technical"
    query_text = "How to use React hooks in a web application"

    # Create query without explicit content_type
    query = SearchQuery(query=query_text)
    features = analyzer.extract_features(query)
    assert features.content_type == "technical"

    # Create query with explicit content_type
    query = SearchQuery(query=query_text, content_type="web_content")
    features = analyzer.extract_features(query)
    assert features.content_type == "web_content"


def test_empty_query_handling():
    """Test that empty or minimal queries default to general content type."""
    analyzer = QueryAnalyzer()

    # Empty query
    query = SearchQuery(query="")
    features = analyzer.extract_features(query)
    assert features.content_type == "general"

    # Very short query with no clear indicators
    query = SearchQuery(query="hello")
    features = analyzer.extract_features(query)
    assert features.content_type == "general"
