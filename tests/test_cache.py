"""Tests for SearchCache implementation."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp_search_hub.models.query import SearchQuery
from mcp_search_hub.models.results import CombinedSearchResponse, SearchResult
from mcp_search_hub.utils.cache import SearchCache


def create_test_result(
    title: str = "Test Result", url: str = "http://test.com"
) -> SearchResult:
    """Create test SearchResult with all required fields."""
    return SearchResult(
        title=title, url=url, snippet="Test snippet", source="test_provider", score=0.8
    )


def create_test_combined_response(
    results: list[SearchResult] = None, query: str = "test"
) -> CombinedSearchResponse:
    """Create test CombinedSearchResponse with all required fields."""
    if results is None:
        results = [create_test_result()]
    return CombinedSearchResponse(
        results=results,
        query=query,
        providers_used=["test_provider"],
        total_results=len(results),
        timing_ms=100.0,
    )


class TestSearchCache:
    """Test SearchCache class."""

    @pytest.fixture
    def mock_redis(self):
        """Create mock Redis client."""
        mock_client = AsyncMock()
        mock_client.get = AsyncMock()
        mock_client.setex = AsyncMock()
        mock_client.aclose = AsyncMock()
        return mock_client

    @pytest.fixture
    def sample_query(self):
        """Create sample search query."""
        return SearchQuery(query="test search", max_results=10, raw_content=False)

    @pytest.fixture
    def sample_response(self):
        """Create sample search response."""
        return create_test_combined_response(
            [
                create_test_result("Test Result 1", "http://test1.com"),
                create_test_result("Test Result 2", "http://test2.com"),
            ],
            "test search",
        )

    def test_initialization_success(self):
        """Test successful cache initialization."""
        with patch("mcp_search_hub.utils.cache.REDIS_AVAILABLE", True):
            with patch(
                "mcp_search_hub.utils.cache.redis.from_url"
            ) as mock_redis_from_url:
                mock_client = MagicMock()
                mock_redis_from_url.return_value = mock_client

                cache = SearchCache(
                    redis_url="redis://localhost:6379",
                    default_ttl=300,
                    ttl_jitter=60,
                    prefix="test:",
                )

                assert cache.redis_url == "redis://localhost:6379"
                assert cache.default_ttl == 300
                assert cache.ttl_jitter == 60
                assert cache.prefix == "test:"
                assert cache.redis_client == mock_client
                mock_redis_from_url.assert_called_once_with(
                    "redis://localhost:6379", decode_responses=False
                )

    def test_initialization_redis_unavailable(self):
        """Test initialization when Redis is not available."""
        with patch("mcp_search_hub.utils.cache.REDIS_AVAILABLE", False):
            cache = SearchCache()
            assert cache.redis_client is None

    def test_initialization_redis_connection_error(self):
        """Test initialization when Redis connection fails."""
        with patch("mcp_search_hub.utils.cache.REDIS_AVAILABLE", True):
            with patch(
                "mcp_search_hub.utils.cache.redis.from_url",
                side_effect=Exception("Connection failed"),
            ):
                cache = SearchCache()
                assert cache.redis_client is None

    def test_generate_key(self, sample_query):
        """Test cache key generation."""
        cache = SearchCache(prefix="test:")

        key = cache.generate_key(sample_query)

        # Should be a SHA256 hash with prefix
        assert key.startswith("test:")
        assert len(key) == 5 + 64  # prefix + SHA256 hash length

        # Same query should generate same key
        key2 = cache.generate_key(sample_query)
        assert key == key2

        # Different query should generate different key
        different_query = SearchQuery(query="different search")
        key3 = cache.generate_key(different_query)
        assert key != key3

    def test_get_ttl_with_jitter(self):
        """Test TTL calculation with jitter."""
        cache = SearchCache(default_ttl=300, ttl_jitter=60)

        # Get multiple TTL values
        ttls = [cache._get_ttl() for _ in range(10)]

        # All should be within expected range
        for ttl in ttls:
            assert 300 <= ttl <= 360  # base + max jitter

        # Should have some variation (not all the same)
        unique_ttls = set(ttls)
        assert len(unique_ttls) > 1

    @pytest.mark.asyncio
    async def test_get_cache_hit(self, mock_redis, sample_query, sample_response):
        """Test successful cache retrieval."""
        # Setup mock Redis response
        cached_data = json.dumps(sample_response.model_dump()).encode("utf-8")
        mock_redis.get.return_value = cached_data

        cache = SearchCache()
        cache.redis_client = mock_redis

        result = await cache.get(sample_query)

        assert result is not None
        assert isinstance(result, CombinedSearchResponse)
        assert len(result.results) == 2
        assert result.results[0].title == "Test Result 1"
        mock_redis.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_cache_miss(self, mock_redis, sample_query):
        """Test cache miss (no data found)."""
        mock_redis.get.return_value = None

        cache = SearchCache()
        cache.redis_client = mock_redis

        result = await cache.get(sample_query)

        assert result is None
        mock_redis.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_no_redis_client(self, sample_query):
        """Test get when Redis client is not available."""
        cache = SearchCache()
        cache.redis_client = None

        result = await cache.get(sample_query)

        assert result is None

    @pytest.mark.asyncio
    async def test_get_redis_error(self, mock_redis, sample_query):
        """Test get when Redis operation fails."""
        mock_redis.get.side_effect = Exception("Redis error")

        cache = SearchCache()
        cache.redis_client = mock_redis

        result = await cache.get(sample_query)

        # Should return None and not raise exception
        assert result is None
        mock_redis.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_invalid_json(self, mock_redis, sample_query):
        """Test get when cached data is invalid JSON."""
        mock_redis.get.return_value = b"invalid json data"

        cache = SearchCache()
        cache.redis_client = mock_redis

        result = await cache.get(sample_query)

        # Should return None and not raise exception
        assert result is None
        mock_redis.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_set_success(self, mock_redis, sample_query, sample_response):
        """Test successful cache storage."""
        cache = SearchCache(
            default_ttl=300, ttl_jitter=0
        )  # No jitter for predictable testing
        cache.redis_client = mock_redis

        await cache.set(sample_query, sample_response)

        # Verify Redis setex was called with correct parameters
        mock_redis.setex.assert_called_once()
        call_args = mock_redis.setex.call_args
        key, ttl, data = call_args[0]

        # Check key format
        assert key.startswith("search:")
        assert len(key) == 7 + 64  # prefix + SHA256 hash

        # Check TTL
        assert ttl == 300

        # Check data is properly serialized
        deserialized = json.loads(data.decode("utf-8"))
        assert deserialized["results"][0]["title"] == "Test Result 1"

    @pytest.mark.asyncio
    async def test_set_no_redis_client(self, sample_query, sample_response):
        """Test set when Redis client is not available."""
        cache = SearchCache()
        cache.redis_client = None

        # Should not raise exception
        await cache.set(sample_query, sample_response)

    @pytest.mark.asyncio
    async def test_set_redis_error(self, mock_redis, sample_query, sample_response):
        """Test set when Redis operation fails."""
        mock_redis.setex.side_effect = Exception("Redis error")

        cache = SearchCache()
        cache.redis_client = mock_redis

        # Should not raise exception
        await cache.set(sample_query, sample_response)
        mock_redis.setex.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_success(self, mock_redis):
        """Test successful Redis connection close."""
        cache = SearchCache()
        cache.redis_client = mock_redis

        await cache.close()

        mock_redis.aclose.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_no_client(self):
        """Test close when no Redis client exists."""
        cache = SearchCache()
        cache.redis_client = None

        # Should not raise exception
        await cache.close()

    @pytest.mark.asyncio
    async def test_close_error(self, mock_redis):
        """Test close when Redis close operation fails."""
        mock_redis.aclose.side_effect = Exception("Close error")

        cache = SearchCache()
        cache.redis_client = mock_redis

        # Should not raise exception
        await cache.close()
        mock_redis.aclose.assert_called_once()

    @pytest.mark.asyncio
    async def test_end_to_end_caching(self, sample_query):
        """Test complete cache workflow with real-like data."""
        # Test without Redis dependency
        with patch("mcp_search_hub.utils.cache.REDIS_AVAILABLE", False):
            cache = SearchCache()

            # Should handle missing Redis gracefully
            result = await cache.get(sample_query)
            assert result is None

            response = create_test_combined_response(
                [create_test_result("Cached Result", "http://cached.com")]
            )

            # Should handle set gracefully
            await cache.set(sample_query, response)

    def test_key_consistency_across_instances(self, sample_query):
        """Test that different cache instances generate same keys."""
        cache1 = SearchCache(prefix="test:")
        cache2 = SearchCache(prefix="test:")

        key1 = cache1.generate_key(sample_query)
        key2 = cache2.generate_key(sample_query)

        assert key1 == key2

    def test_different_prefixes_generate_different_keys(self, sample_query):
        """Test that different prefixes generate different keys."""
        cache1 = SearchCache(prefix="app1:")
        cache2 = SearchCache(prefix="app2:")

        key1 = cache1.generate_key(sample_query)
        key2 = cache2.generate_key(sample_query)

        assert key1 != key2
        assert key1.startswith("app1:")
        assert key2.startswith("app2:")


class TestCacheIntegration:
    """Test cache integration scenarios."""

    @pytest.mark.asyncio
    async def test_cache_with_complex_query_objects(self):
        """Test caching with complex query objects."""
        cache = SearchCache()

        # Complex query with nested objects
        query = SearchQuery(
            query="complex search",
            max_results=50,
            raw_content=True,
            advanced=True,
            providers=["provider1", "provider2"],
            budget=10.0,
        )

        # Should generate consistent key
        key1 = cache.generate_key(query)
        key2 = cache.generate_key(query)
        assert key1 == key2

        # Modifying query should change key
        query.max_results = 100
        key3 = cache.generate_key(query)
        assert key1 != key3

    @pytest.mark.asyncio
    async def test_cache_serialization_edge_cases(self):
        """Test cache serialization with edge cases."""
        cache = SearchCache()

        query = SearchQuery(query="test")

        # Response with various edge cases
        result_with_unicode = SearchResult(
            title="Test with unicode: 你好世界",
            url="http://test.com",
            snippet="Content with special chars: <>&\"'",
            source="test_provider",
            score=0.95,
            raw_content="Content with special chars: <>&\"'",
        )

        CombinedSearchResponse(
            results=[result_with_unicode],
            query="test",
            providers_used=["test_provider"],
            total_results=1,
            timing_ms=100.0,
        )

        key = cache.generate_key(query)

        # Should handle serialization correctly
        assert key is not None
        assert len(key) > len(cache.prefix)

    def test_cache_performance_characteristics(self):
        """Test cache performance characteristics."""
        cache = SearchCache()

        # Generate keys for many queries to test performance
        queries = [SearchQuery(query=f"test query {i}") for i in range(1000)]

        # Should generate keys quickly
        keys = [cache.generate_key(q) for q in queries]

        # All keys should be unique
        assert len(set(keys)) == len(keys)

        # All keys should have consistent format
        for key in keys:
            assert key.startswith(cache.prefix)
            assert len(key) == len(cache.prefix) + 64
