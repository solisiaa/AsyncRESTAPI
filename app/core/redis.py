"""Async Redis client singleton."""

from __future__ import annotations

from typing import Optional

import redis.asyncio as redis_async

from app.core.config import get_settings

_client: Optional[redis_async.Redis] = None


def get_redis_client() -> redis_async.Redis:
    """Return a process-wide async Redis client."""
    global _client
    if _client is None:
        settings = get_settings()
        # redis.asyncio has no type stubs for from_url; ignore untyped call (justified).
        _client = redis_async.from_url(  # type: ignore[no-untyped-call]
            settings.redis_url, decode_responses=True
        )
    return _client


async def close_redis() -> None:
    """Close the global Redis client (used on app shutdown)."""
    global _client
    if _client is not None:
        try:
            await _client.aclose()
        except Exception:
            try:
                await _client.close()
            except Exception:
                pass
        _client = None


async def get_redis() -> redis_async.Redis:
    """FastAPI dependency returning the shared Redis client."""
    return get_redis_client()
