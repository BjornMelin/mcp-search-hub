"""Caching mechanisms."""

import time
from typing import Any, TypeVar

from ..models.results import CombinedSearchResponse

T = TypeVar("T")


class QueryCache:
    """Cache for search query results."""

    def __init__(self, ttl: int = 3600):
        """
        Initialize cache with time-to-live in seconds.

        Args:
            ttl: Time-to-live in seconds (default: 1 hour)
        """
        self.cache: dict[str, dict[str, Any]] = {}
        self.ttl = ttl

    def get(self, key: str) -> CombinedSearchResponse | None:
        """
        Get cached result for a key if available and not expired.

        Args:
            key: Cache key

        Returns:
            Cached result or None if not found or expired
        """
        if key in self.cache:
            entry = self.cache[key]
            if time.time() - entry["timestamp"] < self.ttl:
                return entry["result"]

        return None

    def set(self, key: str, result: CombinedSearchResponse):
        """
        Cache a result with the current timestamp.

        Args:
            key: Cache key
            result: Result to cache
        """
        self.cache[key] = {"result": result, "timestamp": time.time()}

    def clear(self, key: str | None = None):
        """
        Clear cache for a specific key or the entire cache.

        Args:
            key: Specific key to clear, or None to clear all
        """
        if key:
            if key in self.cache:
                del self.cache[key]
        else:
            self.cache.clear()

    def clean_expired(self):
        """Remove expired entries from the cache."""
        current_time = time.time()
        keys_to_remove = []

        for key, entry in self.cache.items():
            if current_time - entry["timestamp"] >= self.ttl:
                keys_to_remove.append(key)

        for key in keys_to_remove:
            del self.cache[key]
