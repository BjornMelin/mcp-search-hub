"""Basic tests for the MCP Search Hub server."""

import pytest
from mcp_search_hub.models.query import SearchQuery, QueryFeatures
from mcp_search_hub.query_routing.analyzer import QueryAnalyzer


def test_query_analyzer():
    """Test the query analyzer feature extraction."""
    analyzer = QueryAnalyzer()
    
    # Test academic query
    query = SearchQuery(query="Latest research papers on quantum computing")
    features = analyzer.extract_features(query)
    assert features.content_type == "academic"
    
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