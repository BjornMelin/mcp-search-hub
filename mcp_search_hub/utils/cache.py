"""Simple Redis-based cache implementation with minimal complexity."""

import hashlib
import json
import logging
import random
import time
from typing import Any

try:
    import redis.asyncio as redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    redis = None

from ..models.query import SearchQuery
from ..models.results import CombinedSearchResponse

logger = logging.getLogger(__name__)


class SearchCache:
    """Redis-based cache with async interface and graceful error handling.

    This cache implementation focuses on simplicity and reliability:
    - Redis-only backend (no memory tier)
    - Async-only interface (no sync methods)
    - SHA256 key generation
    - TTL with jitter to prevent cache stampede
    - Graceful error handling - cache errors never break the app
    - JSON serialization for search results

    Attributes:
        redis_client: The async Redis client instance
        default_ttl: Default time-to-live in seconds
        ttl_jitter: Random jitter range in seconds
    """

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379",
        default_ttl: int = 300,
        ttl_jitter: int = 60,
        prefix: str = "search:",
    ):
        """Initialize the cache.

        Args:
            redis_url: Redis connection URL
            default_ttl: Default TTL in seconds (default: 300)
            ttl_jitter: TTL jitter range in seconds (default: 60)
            prefix: Key prefix for Redis (default: "search:")
        """
        self.redis_url = redis_url
        self.default_ttl = default_ttl
        self.ttl_jitter = ttl_jitter
        self.prefix = prefix
        self.redis_client = None

        # Initialize Redis client
        if not REDIS_AVAILABLE:
            logger.warning("SearchCache: Redis not available. Cache will not work.")
            return
            
        try:
            self.redis_client = redis.from_url(redis_url, decode_responses=False)
            logger.info(f"SearchCache: Redis client initialized at {redis_url}")
        except Exception as e:
            logger.error(f"SearchCache: Failed to initialize Redis client: {e}")

    def generate_key(self, query: SearchQuery) -> str:
        """Generate cache key using SHA256 hash.

        Args:
            query: The search query to generate key for

        Returns:
            SHA256 hash of the normalized query
        """
        # Convert query to normalized JSON string
        query_dict = query.model_dump()
        query_str = json.dumps(query_dict, sort_keys=True)

        # Generate SHA256 hash
        hash_obj = hashlib.sha256(query_str.encode())
        return f"{self.prefix}{hash_obj.hexdigest()}"

    def _get_ttl(self) -> int:
        """Get TTL with random jitter to prevent cache stampede.

        Returns:
            TTL in seconds with random jitter applied
        """
        jitter = random.randint(0, self.ttl_jitter)
        return self.default_ttl + jitter

    async def get(self, query: SearchQuery) -> CombinedSearchResponse | None:
        """Get cached result from Redis.

        Args:
            query: The search query to look up

        Returns:
            Cached result or None if not found, expired, or error
        """
        if not self.redis_client:
            return None

        try:
            key = self.generate_key(query)
            data = await self.redis_client.get(key)

            if data:
                # Deserialize the JSON data
                result_dict = json.loads(data.decode("utf-8"))
                result = CombinedSearchResponse.model_validate(result_dict)
                logger.debug(f"SearchCache: Cache hit for key {key[:16]}...")
                return result

            logger.debug(f"SearchCache: Cache miss for key {key[:16]}...")
            return None

        except Exception as e:
            # Log error but don't raise - cache errors shouldn't break the app
            logger.warning(f"SearchCache: Error getting from cache: {e}")
            return None

    async def set(self, query: SearchQuery, results: CombinedSearchResponse) -> None:
        """Set result in Redis with TTL.

        Args:
            query: The search query as cache key
            results: The search results to cache
        """
        if not self.redis_client:
            return

        try:
            key = self.generate_key(query)
            ttl = self._get_ttl()

            # Serialize the results to JSON
            data = json.dumps(results.model_dump()).encode("utf-8")

            # Set in Redis with TTL
            await self.redis_client.setex(key, ttl, data)
            logger.debug(f"SearchCache: Set key {key[:16]}... with TTL {ttl}s")

        except Exception as e:
            # Log error but don't raise - cache errors shouldn't break the app
            logger.warning(f"SearchCache: Error setting in cache: {e}")

    async def close(self) -> None:
        """Close Redis connection gracefully."""
        if self.redis_client:
            try:
                await self.redis_client.aclose()
                logger.info("SearchCache: Redis connection closed")
            except Exception as e:
                logger.warning(f"SearchCache: Error closing Redis connection: {e}")


class TimedCache:
    """Simple in-memory cache with TTL for backward compatibility.

    This is a minimal implementation to support legacy code that uses TimedCache.
    """

    def __init__(self, ttl_seconds: int = 3600):
        """Initialize timed cache.

        Args:
            ttl_seconds: Time-to-live in seconds
        """
        self.ttl_seconds = ttl_seconds
        self._cache: dict[str, dict[str, Any]] = {}

    def get(self, key: str) -> Any | None:
        """Get value from cache if not expired.

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found/expired
        """
        if key not in self._cache:
            return None

        entry = self._cache[key]
        if time.time() - entry["timestamp"] > self.ttl_seconds:
            del self._cache[key]
            return None

        return entry["value"]

    def set(self, key: str, value: Any) -> None:
        """Set value in cache with current timestamp.

        Args:
            key: Cache key
            value: Value to cache
        """
        self._cache[key] = {"value": value, "timestamp": time.time()}

    def clear(self) -> None:
        """Clear all cached entries."""
        self._cache.clear()
