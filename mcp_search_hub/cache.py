"""Caching helpers built on top of FastMCP storage utilities."""

from __future__ import annotations

import hashlib
import json
import logging
import random
import time

import pydantic_core

try:  # pragma: no cover - optional dependency
    import redis.asyncio as redis
except Exception:  # noqa: BLE001 - optional dependency not required for tests
    redis = None

from fastmcp.utilities.storage import InMemoryStorage

from .models import CombinedSearchResponse, SearchQuery

logger = logging.getLogger(__name__)


class SearchCache:
    """Hybrid in-memory/Redis cache for search responses."""

    def __init__(
        self,
        *,
        memory_ttl: int,
        redis_enabled: bool,
        redis_url: str | None,
        redis_ttl: int,
        prefix: str,
        ttl_jitter: int,
    ) -> None:
        self._memory = InMemoryStorage()
        self._memory_ttl = memory_ttl
        self._redis_ttl = redis_ttl
        self._prefix = prefix.rstrip(":") + ":"
        self._ttl_jitter = max(0, ttl_jitter)
        self._redis = None
        if redis_enabled:
            if redis is None:
                logger.warning(
                    "Redis caching requested but redis-py not installed; falling back to memory"
                )
            elif not redis_url:
                logger.warning(
                    "Redis caching requested without redis_url; falling back to memory"
                )
            else:  # pragma: no cover - requires redis server
                self._redis = redis.from_url(redis_url, decode_responses=True)

    async def get(self, query: SearchQuery) -> CombinedSearchResponse | None:
        """Fetch a cached response if available and not expired."""

        key = self._make_key(query)
        now = time.time()

        entry = await self._memory.get(key)
        if entry:
            if entry["expires_at"] > now:
                logger.debug("Cache hit (memory) for %s", key)
                return CombinedSearchResponse.model_validate(entry["payload"])
            await self._memory.delete(key)

        if self._redis is not None:  # pragma: no branch - optional path
            raw = await self._redis.get(key)
            if raw:
                try:
                    decoded = json.loads(raw)
                    if decoded["expires_at"] > now:
                        logger.debug("Cache hit (redis) for %s", key)
                        await self._memory.set(key, decoded)
                        return CombinedSearchResponse.model_validate(decoded["payload"])
                except json.JSONDecodeError:  # pragma: no cover - defensive
                    logger.warning("Failed to decode redis cache payload for %s", key)
                await self._redis.delete(key)

        logger.debug("Cache miss for %s", key)
        return None

    async def set(self, query: SearchQuery, response: CombinedSearchResponse) -> None:
        """Store a response in the cache."""

        key = self._make_key(query)
        expires_at = (
            time.time() + self._memory_ttl + random.uniform(0, self._ttl_jitter)
        )
        payload = {
            "expires_at": expires_at,
            "payload": response.model_dump(mode="json"),
        }

        await self._memory.set(key, payload)

        if self._redis is not None:  # pragma: no branch - optional path
            redis_payload = json.dumps(
                {
                    "expires_at": time.time()
                    + self._redis_ttl
                    + random.uniform(0, self._ttl_jitter),
                    "payload": response.model_dump(mode="json"),
                }
            )
            await self._redis.setex(key, self._redis_ttl, redis_payload)

    async def invalidate(self, query: SearchQuery) -> None:
        """Remove a cached response."""

        key = self._make_key(query)
        await self._memory.delete(key)
        if self._redis is not None:  # pragma: no cover - optional path
            await self._redis.delete(key)

    def _make_key(self, query: SearchQuery) -> str:
        fingerprint = self.fingerprint(query)
        return f"{self._prefix}{fingerprint}"

    @staticmethod
    def fingerprint(query: SearchQuery) -> str:
        """Return a deterministic fingerprint for a query."""

        payload = query.fingerprint_payload()
        canonical = pydantic_core.to_json(payload, fallback=str)
        return hashlib.sha256(canonical).hexdigest()


__all__ = ["SearchCache"]
