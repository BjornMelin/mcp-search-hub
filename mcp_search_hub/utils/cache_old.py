"""Caching mechanisms with tiered memory and Redis support."""

import hashlib
import json
import logging
import time
from typing import Any, TypeVar

# Import Redis conditionally to allow use without Redis installed
try:
    import redis.asyncio as async_redis
    from redis import Redis

    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

    # Create dummy classes for static type checking
    class Redis:
        @classmethod
        def from_url(cls, *args, **kwargs):
            return None

    class async_redis:
        @classmethod
        def from_url(cls, *args, **kwargs):
            return None


from ..models.query import SearchQuery
from ..models.results import CombinedSearchResponse

T = TypeVar("T")
logger = logging.getLogger(__name__)


class TieredCache:
    """
    Tiered cache implementation with in-memory and Redis backends.

    Features:
    - Fast in-memory first-level cache
    - Redis-backed distributed second-level cache
    - Different TTLs for each cache level
    - Support for cache invalidation by pattern
    - Query fingerprinting for semantically similar cache hits
    - Both sync and async interfaces
    """

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379",
        memory_ttl: int = 300,  # 5 minutes for memory cache
        redis_ttl: int = 3600,  # 1 hour for Redis cache
        prefix: str = "search:",
        fingerprint_enabled: bool = True,
        redis_enabled: bool = False,  # Default to not using Redis
    ):
        """
        Initialize tiered cache.

        Args:
            redis_url: Redis connection URL
            memory_ttl: Time-to-live for memory cache in seconds
            redis_ttl: Time-to-live for Redis cache in seconds
            prefix: Key prefix for Redis cache
            fingerprint_enabled: Whether to enable query fingerprinting
            redis_enabled: Whether to enable Redis caching
        """
        self.memory_cache: dict[str, dict[str, Any]] = {}
        self.memory_ttl = memory_ttl
        self.redis_ttl = redis_ttl
        self.prefix = prefix
        self.fingerprint_enabled = fingerprint_enabled

        # Initialize Redis clients if Redis is enabled and available
        self.redis = None
        self.async_redis = None
        self.redis_enabled = redis_enabled and REDIS_AVAILABLE

        if self.redis_enabled:
            try:
                self.redis = Redis.from_url(redis_url)
                self.async_redis = async_redis.from_url(redis_url)
                logger.info(f"Redis cache initialized at {redis_url}")
            except Exception as e:
                logger.warning(
                    f"Failed to initialize Redis cache: {e}. Using memory cache only."
                )
                self.redis = None
                self.async_redis = None
                self.redis_enabled = False

    def _redis_key(self, key: str) -> str:
        """
        Generate Redis key with prefix.

        Args:
            key: The original key

        Returns:
            Prefixed key for Redis
        """
        return f"{self.prefix}{key}"

    def generate_key(self, query: SearchQuery) -> str:
        """
        Generate a cache key for a search query with optional fingerprinting.

        Args:
            query: The search query

        Returns:
            A unique key for the query
        """
        # Convert query to a normalized form
        query_dict = query.model_dump()

        if self.fingerprint_enabled:
            # Keep only the important parts of the query for fingerprinting
            fingerprint_dict = {
                "query": query_dict["query"],
                "max_results": query_dict["max_results"],
                "raw_content": query_dict["raw_content"],
            }

            # Sort dictionary to ensure consistent ordering
            query_str = json.dumps(fingerprint_dict, sort_keys=True)
        else:
            # Use the full query for an exact match
            query_str = json.dumps(query_dict, sort_keys=True)

        # Create a hash
        return hashlib.md5(query_str.encode()).hexdigest()

    def get(self, key: str) -> CombinedSearchResponse | None:
        """
        Get cached result from tiered cache.

        Checks memory cache first, then Redis if not found.

        Args:
            key: Cache key

        Returns:
            Cached result or None if not found or expired
        """
        # Check memory cache first (fastest)
        if key in self.memory_cache:
            entry = self.memory_cache[key]
            if time.time() - entry["timestamp"] < self.memory_ttl:
                logger.debug(f"Memory cache hit for key: {key}")
                return entry["result"]

        # Check Redis cache if enabled and not in memory
        if self.redis_enabled and self.redis:
            redis_data = self.redis.get(self._redis_key(key))
            if redis_data:
                try:
                    result = self._deserialize(redis_data)
                    # Update memory cache
                    self.memory_cache[key] = {
                        "result": result,
                        "timestamp": time.time(),
                    }
                    logger.debug(f"Redis cache hit for key: {key}")
                    return result
                except Exception as e:
                    logger.warning(f"Failed to deserialize Redis data: {e}")

        return None

    async def get_async(self, key: str) -> CombinedSearchResponse | None:
        """
        Async version of get method.

        Args:
            key: Cache key

        Returns:
            Cached result or None if not found or expired
        """
        # Check memory cache first (fastest)
        if key in self.memory_cache:
            entry = self.memory_cache[key]
            if time.time() - entry["timestamp"] < self.memory_ttl:
                logger.debug(f"Memory cache hit for key: {key}")
                return entry["result"]

        # Check Redis cache if enabled and not in memory
        if self.redis_enabled and self.async_redis:
            try:
                redis_data = await self.async_redis.get(self._redis_key(key))
                if redis_data:
                    result = self._deserialize(redis_data)
                    # Update memory cache
                    self.memory_cache[key] = {
                        "result": result,
                        "timestamp": time.time(),
                    }
                    logger.debug(f"Redis cache hit for key: {key}")
                    return result
            except Exception as e:
                logger.warning(f"Failed to get data from Redis: {e}")

        return None

    def set(self, key: str, result: CombinedSearchResponse) -> None:
        """
        Set result in both memory and Redis caches.

        Args:
            key: Cache key
            result: Result to cache
        """
        # Update memory cache
        self.memory_cache[key] = {"result": result, "timestamp": time.time()}

        # Update Redis cache if enabled
        if self.redis_enabled and self.redis:
            try:
                serialized = self._serialize(result)
                self.redis.setex(self._redis_key(key), self.redis_ttl, serialized)
                logger.debug(f"Set key in Redis cache: {key}")
            except Exception as e:
                logger.warning(f"Failed to set data in Redis: {e}")

    async def set_async(self, key: str, result: CombinedSearchResponse) -> None:
        """
        Async version of set method.

        Args:
            key: Cache key
            result: Result to cache
        """
        # Update memory cache
        self.memory_cache[key] = {"result": result, "timestamp": time.time()}

        # Update Redis cache if enabled
        if self.redis_enabled and self.async_redis:
            try:
                serialized = self._serialize(result)
                await self.async_redis.setex(
                    self._redis_key(key), self.redis_ttl, serialized
                )
                logger.debug(f"Set key in Redis cache: {key}")
            except Exception as e:
                logger.warning(f"Failed to set data in Redis: {e}")

    def clear(self, key: str = None, pattern: str = None) -> None:
        """
        Clear cache for a specific key, pattern, or the entire cache.

        Args:
            key: Specific key to clear
            pattern: Pattern to match keys for clearing
        """
        if key:
            # Clear specific key
            if key in self.memory_cache:
                del self.memory_cache[key]
                logger.debug(f"Cleared key from memory cache: {key}")

            if self.redis_enabled and self.redis:
                try:
                    self.redis.delete(self._redis_key(key))
                    logger.debug(f"Cleared key from Redis cache: {key}")
                except Exception as e:
                    logger.warning(f"Failed to clear key from Redis: {e}")

        elif pattern:
            # Clear keys matching pattern
            if self.redis_enabled and self.redis:
                try:
                    redis_keys = self.redis.keys(f"{self.prefix}{pattern}")
                    if redis_keys:
                        self.redis.delete(*redis_keys)
                        logger.debug(
                            f"Cleared {len(redis_keys)} keys matching pattern from Redis: {pattern}"
                        )

                        # Also clear from memory cache if keys match the pattern
                        memory_keys = [
                            k for k in self.memory_cache.keys() if pattern in k
                        ]
                        for k in memory_keys:
                            del self.memory_cache[k]
                            logger.debug(f"Cleared key from memory cache: {k}")
                except Exception as e:
                    logger.warning(f"Failed to clear keys by pattern from Redis: {e}")

            # Also clear memory cache based on pattern
            memory_keys = [k for k in list(self.memory_cache.keys()) if pattern in k]
            for k in memory_keys:
                del self.memory_cache[k]

        else:
            # Clear all cache
            self.memory_cache.clear()
            logger.debug("Cleared entire memory cache")

            if self.redis_enabled and self.redis:
                try:
                    # Delete all keys with the prefix
                    redis_keys = self.redis.keys(f"{self.prefix}*")
                    if redis_keys:
                        self.redis.delete(*redis_keys)
                        logger.debug(f"Cleared {len(redis_keys)} keys from Redis cache")
                except Exception as e:
                    logger.warning(f"Failed to clear all keys from Redis: {e}")

    async def clear_async(self, key: str = None, pattern: str = None) -> None:
        """
        Async version of clear method.

        Args:
            key: Specific key to clear
            pattern: Pattern to match keys for clearing
        """
        if key:
            # Clear specific key
            if key in self.memory_cache:
                del self.memory_cache[key]
                logger.debug(f"Cleared key from memory cache: {key}")

            if self.redis_enabled and self.async_redis:
                try:
                    await self.async_redis.delete(self._redis_key(key))
                    logger.debug(f"Cleared key from Redis cache: {key}")
                except Exception as e:
                    logger.warning(f"Failed to clear key from Redis: {e}")

        elif pattern:
            # Clear keys matching pattern
            if self.redis_enabled and self.async_redis:
                try:
                    # Scan for keys matching pattern
                    cursor = b"0"
                    redis_keys = []

                    while cursor:
                        cursor, keys = await self.async_redis.scan(
                            cursor=cursor, match=f"{self.prefix}{pattern}*"
                        )
                        redis_keys.extend(keys)

                        # Avoid infinite loops
                        if cursor == b"0":
                            break

                    if redis_keys:
                        # Note: * unpacking doesn't work with await, need to pass the list directly
                        await self.async_redis.delete(*redis_keys)
                        logger.debug(
                            f"Cleared {len(redis_keys)} keys matching pattern from Redis: {pattern}"
                        )
                except Exception as e:
                    logger.warning(f"Failed to clear keys by pattern from Redis: {e}")

            # Also clear memory cache based on pattern
            memory_keys = [k for k in list(self.memory_cache.keys()) if pattern in k]
            for k in memory_keys:
                del self.memory_cache[k]

        else:
            # Clear all cache
            self.memory_cache.clear()
            logger.debug("Cleared entire memory cache")

            if self.redis_enabled and self.async_redis:
                try:
                    # Scan for all keys with prefix
                    cursor = b"0"
                    redis_keys = []

                    while cursor:
                        cursor, keys = await self.async_redis.scan(
                            cursor=cursor, match=f"{self.prefix}*"
                        )
                        redis_keys.extend(keys)

                        # Avoid infinite loops
                        if cursor == b"0":
                            break

                    if redis_keys:
                        await self.async_redis.delete(*redis_keys)
                        logger.debug(f"Cleared {len(redis_keys)} keys from Redis cache")
                except Exception as e:
                    logger.warning(f"Failed to clear all keys from Redis: {e}")

    def clean_expired_memory(self) -> None:
        """
        Remove expired entries from memory cache.
        """
        current_time = time.time()
        keys_to_remove = []

        for key, entry in self.memory_cache.items():
            if current_time - entry["timestamp"] >= self.memory_ttl:
                keys_to_remove.append(key)

        for key in keys_to_remove:
            del self.memory_cache[key]
            logger.debug(f"Removed expired key from memory cache: {key}")

    async def clean_expired_redis(self) -> None:
        """
        Clean up expired Redis keys (though Redis does this automatically).

        This is mostly for maintenance and monitoring purposes.
        """
        if not self.redis_enabled or not self.async_redis:
            return

        try:
            # This is a no-op since Redis automatically removes expired keys
            # But we can log current cache stats
            info = await self.async_redis.info("memory")
            used_memory = info.get("used_memory_human", "unknown")
            logger.info(f"Redis memory usage: {used_memory}")
        except Exception as e:
            logger.warning(f"Failed to get Redis stats: {e}")

    def _serialize(self, result: CombinedSearchResponse) -> bytes:
        """
        Serialize result to JSON bytes.

        Args:
            result: The result to serialize

        Returns:
            Serialized bytes
        """
        try:
            return json.dumps(result.model_dump()).encode("utf-8")
        except Exception as e:
            logger.error(f"Failed to serialize result: {e}")
            raise

    def _deserialize(self, data: bytes) -> CombinedSearchResponse:
        """
        Deserialize JSON bytes to result object.

        Args:
            data: Serialized data

        Returns:
            Deserialized CombinedSearchResponse
        """
        try:
            return CombinedSearchResponse.model_validate(
                json.loads(data.decode("utf-8"))
            )
        except Exception as e:
            logger.error(f"Failed to deserialize data: {e}")
            raise

    async def close(self) -> None:
        """
        Close Redis connections.
        """
        if self.redis_enabled and self.async_redis:
            try:
                await self.async_redis.aclose()
                logger.debug("Closed Redis connection")
            except Exception as e:
                logger.warning(f"Failed to close Redis connection: {e}")
