"""Tests for the tiered caching system."""

import asyncio
import json
import time
from unittest.mock import MagicMock, patch

import pytest

from mcp_search_hub.models.query import SearchQuery
from mcp_search_hub.models.results import CombinedSearchResponse, SearchResult
from mcp_search_hub.utils.cache import QueryCache, TieredCache


@pytest.fixture
def search_query():
    """Create a sample search query."""
    return SearchQuery(query="test query", max_results=10, raw_content=False)


@pytest.fixture
def search_response():
    """Create a sample search response."""
    results = [
        SearchResult(
            title="Test Result",
            url="https://example.com/test",
            snippet="This is a test result snippet",
            score=0.95,
            source="test_source",
            metadata={"source": "test"},
        )
    ]

    return CombinedSearchResponse(
        results=results,
        query="test query",
        providers_used=["test_provider"],
        total_results=1,
        total_cost=0.001,
        timing_ms=100.5,
    )


class TestQueryCache:
    """Tests for the legacy QueryCache."""

    def test_generate_key(self, search_query):
        """Test generating a cache key from a query."""
        cache = QueryCache()
        key = cache.generate_key(search_query)

        # Key should be a md5 hash
        assert len(key) == 32
        assert all(c in "0123456789abcdef" for c in key)

        # Same query should generate same key
        key2 = cache.generate_key(search_query)
        assert key == key2

        # Different query should generate different key
        different_query = SearchQuery(
            query="different query", max_results=10, raw_content=False
        )
        different_key = cache.generate_key(different_query)
        assert key != different_key

    def test_set_and_get(self, search_query, search_response):
        """Test setting and getting values from cache."""
        cache = QueryCache()
        key = cache.generate_key(search_query)

        # Initially the key should not be in the cache
        assert cache.get(key) is None

        # Add response to cache
        cache.set(key, search_response)

        # Should be able to retrieve it
        cached = cache.get(key)
        assert cached is not None
        assert cached.results[0].title == "Test Result"
        assert cached.query == "test query"

    def test_clear_specific_key(self, search_query, search_response):
        """Test clearing a specific key from the cache."""
        cache = QueryCache()
        key = cache.generate_key(search_query)

        # Add response to cache
        cache.set(key, search_response)
        assert cache.get(key) is not None

        # Clear specific key
        cache.clear(key)
        assert cache.get(key) is None

    def test_clear_all(self, search_query, search_response):
        """Test clearing the entire cache."""
        cache = QueryCache()
        key1 = cache.generate_key(search_query)

        # Different query
        key2 = cache.generate_key(
            SearchQuery(query="another query", max_results=5, raw_content=True)
        )

        # Add both to cache
        cache.set(key1, search_response)
        cache.set(key2, search_response)

        # Both should be retrievable
        assert cache.get(key1) is not None
        assert cache.get(key2) is not None

        # Clear all
        cache.clear()

        # Both should be gone
        assert cache.get(key1) is None
        assert cache.get(key2) is None

    @pytest.mark.asyncio
    async def test_expiration(self, search_query, search_response):
        """Test cache key expiration."""
        cache = QueryCache(ttl=0.1)  # Very short TTL for testing
        key = cache.generate_key(search_query)

        # Add to cache
        cache.set(key, search_response)

        # Should be available immediately
        assert cache.get(key) is not None

        # Wait for expiration
        await asyncio.sleep(0.2)

        # Should be expired now
        assert cache.get(key) is None


class TestTieredCache:
    """Tests for the TieredCache implementation."""

    @pytest.fixture
    def memory_only_cache(self):
        """Create a TieredCache with Redis disabled (memory only)."""
        return TieredCache(redis_enabled=False)

    @pytest.fixture
    def mock_redis(self):
        """Create a mocked Redis client."""
        with (
            patch("redis.asyncio.Redis.from_url") as mock_async_redis,
            patch("redis.Redis.from_url") as mock_redis,
        ):
            # Mock the synchronous Redis functions
            mock_redis_instance = MagicMock()
            mock_redis.return_value = mock_redis_instance

            # Mock the asynchronous Redis functions
            mock_async_redis_instance = MagicMock()
            mock_async_redis.return_value = mock_async_redis_instance

            # Setup mocked get/set functions
            async def mock_async_get(key):
                return None  # Default no cache hit

            async def mock_async_set(key, ex, value):
                return True

            async def mock_async_delete(*keys):
                return len(keys)  # Return number of keys deleted

            mock_async_redis_instance.get.side_effect = mock_async_get
            mock_async_redis_instance.setex.side_effect = mock_async_set
            mock_async_redis_instance.delete.side_effect = mock_async_delete

            yield {
                "sync": mock_redis_instance,
                "async": mock_async_redis_instance,
            }

    @pytest.fixture
    def redis_cache(self, mock_redis):
        """Create a TieredCache with mocked Redis."""
        return TieredCache(
            redis_url="redis://mock:6379",
            redis_enabled=True,
            memory_ttl=300,
            redis_ttl=3600,
            prefix="test:",
            fingerprint_enabled=True,
        )

    def test_generate_key_with_fingerprinting(self, search_query):
        """Test key generation with fingerprinting enabled."""
        cache = TieredCache(fingerprint_enabled=True)
        key = cache.generate_key(search_query)

        # Should be a valid md5 hash
        assert len(key) == 32
        assert all(c in "0123456789abcdef" for c in key)

        # Same query should generate same key
        assert key == cache.generate_key(search_query)

        # Similar queries should generate same key (query itself and max_results matter)
        similar_query = SearchQuery(
            query="test query",
            max_results=10,
            raw_content=False,
            # Use arbitrary but different values for other parameters
            timeout_ms=6000,
        )
        assert key == cache.generate_key(similar_query)

        # Different query should generate different key
        different_query = SearchQuery(
            query="different query", max_results=10, raw_content=False
        )
        assert key != cache.generate_key(different_query)

    def test_generate_key_without_fingerprinting(self, search_query):
        """Test key generation with fingerprinting disabled."""
        cache = TieredCache(fingerprint_enabled=False)
        key = cache.generate_key(search_query)

        # Should be a valid md5 hash
        assert len(key) == 32

        # Similar queries with different parameters should generate different keys when fingerprinting is off
        similar_query = SearchQuery(
            query="test query",
            max_results=10,
            raw_content=False,
            # Different timeout should make the key different when fingerprinting is disabled
            timeout_ms=6000,
        )
        assert key != cache.generate_key(similar_query)

    def test_memory_only_sync_operations(
        self, memory_only_cache, search_query, search_response
    ):
        """Test synchronous operations with memory-only cache."""
        cache = memory_only_cache
        key = cache.generate_key(search_query)

        # Initially not in cache
        assert cache.get(key) is None

        # Add to cache
        cache.set(key, search_response)

        # Should be retrievable
        cached = cache.get(key)
        assert cached is not None
        assert cached.results[0].title == "Test Result"

        # Clear it
        cache.clear(key)

        # Should be gone
        assert cache.get(key) is None

    @pytest.mark.asyncio
    async def test_memory_only_async_operations(
        self, memory_only_cache, search_query, search_response
    ):
        """Test asynchronous operations with memory-only cache."""
        cache = memory_only_cache
        key = cache.generate_key(search_query)

        # Initially not in cache
        assert await cache.get_async(key) is None

        # Add to cache
        await cache.set_async(key, search_response)

        # Should be retrievable
        cached = await cache.get_async(key)
        assert cached is not None
        assert cached.results[0].title == "Test Result"

        # Clear it
        await cache.clear_async(key)

        # Should be gone
        assert await cache.get_async(key) is None

    @pytest.mark.asyncio
    async def test_redis_cache_async_operations(
        self, redis_cache, mock_redis, search_query, search_response
    ):
        """Test asynchronous operations with Redis cache."""
        cache = redis_cache
        key = cache.generate_key(search_query)

        # Configure mock to return a cache hit after it's been set
        redis_data = json.dumps(search_response.model_dump()).encode("utf-8")

        # Fix the mock async methods to work properly
        async def mock_get(redis_key):
            return redis_data

        async def mock_setex(redis_key, ttl, value):
            return True

        # Replace the mock methods
        mock_redis["async"].get = mock_get
        mock_redis["async"].setex = mock_setex

        # Set the value in cache
        await cache.set_async(key, search_response)

        # Get the value from cache
        cached = await cache.get_async(key)

        # Should have gotten a valid response
        assert cached is not None
        assert cached.results[0].title == "Test Result"
        assert cached.query == "test query"

    @pytest.mark.asyncio
    async def test_redis_cache_key_pattern_clear(self, redis_cache, mock_redis):
        """Test clearing cache keys by pattern."""
        # Setup mock to return keys matching pattern
        mock_redis["async"].scan.side_effect = [(b"0", [b"test:key1", b"test:key2"])]

        # Fix the delete method to properly handle the kwargs
        async def mock_delete(*args):
            return len(args)

        mock_redis["async"].delete = mock_delete

        # Call clear by pattern
        await redis_cache.clear_async(pattern="key")

        # Should have used scan to find keys
        mock_redis["async"].scan.assert_called_once()

    @pytest.mark.asyncio
    async def test_cache_fallback_behavior(
        self, redis_cache, mock_redis, search_query, search_response
    ):
        """Test that cache falls back to memory when Redis fails."""
        cache = redis_cache
        key = cache.generate_key(search_query)

        # Make Redis get operations fail
        async def mock_get_fail(redis_key):
            raise Exception("Redis connection error")

        # Set up the mock
        mock_redis["async"].get = mock_get_fail

        # Add to memory cache directly with current time (not event loop time)
        cache.memory_cache[key] = {"result": search_response, "timestamp": time.time()}

        # Should still get the result from memory cache
        cached = await cache.get_async(key)
        assert cached is not None
        assert cached.results[0].title == "Test Result"

    @pytest.mark.asyncio
    async def test_redis_cache_close(self, redis_cache, mock_redis):
        """Test that cache properly closes Redis connections."""
        # Setup the close mock
        mock_redis["async"].aclose.side_effect = None

        # Close the cache
        await redis_cache.close()

        # Should have closed the connection
        mock_redis["async"].aclose.assert_called_once()
