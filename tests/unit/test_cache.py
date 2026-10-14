"""Unit tests for Redis cache helpers and decorator."""

from __future__ import annotations

import json

import pytest
from app.core import cache as cache_mod
from app.core.cache import (
    cache,
    hash_params,
    invalidate_pattern,
    project_key,
    projects_list_key,
    top_assignees_key,
)
from fakeredis.aioredis import FakeRedis


def test_key_builders() -> None:
    """Key formats are stable and namespaced."""
    assert project_key(5) == "project:5"
    assert projects_list_key("abc").startswith("projects:list:")
    assert top_assignees_key("abc").startswith("analytics:top_assignees:")


def test_hash_params_stable() -> None:
    """Same params -> same hash regardless of key order."""
    a = hash_params({"b": 1, "a": 2})
    b = hash_params({"a": 2, "b": 1})
    assert a == b
    assert hash_params({"a": 1}) != hash_params({"a": 2})


async def test_cache_decorator_hit_and_miss(monkeypatch: pytest.MonkeyPatch) -> None:
    """First call executes, second call hits Redis."""
    redis = FakeRedis(decode_responses=True)
    monkeypatch.setattr(cache_mod, "get_redis_client", lambda: redis)
    calls = {"n": 0}

    @cache(ttl=60, key_builder=lambda x: f"k:{x}")
    async def _fn(x: int) -> dict[str, int]:
        calls["n"] += 1
        return {"v": x * 2}

    first = await _fn(21)
    assert first == {"v": 42}
    assert calls["n"] == 1
    second = await _fn(21)
    assert second == {"v": 42}
    assert calls["n"] == 1  # served from cache
    raw = await redis.get("k:21")
    assert raw is not None and json.loads(raw) == {"v": 42}


async def test_invalidate_pattern() -> None:
    """Pattern invalidation removes matching keys only."""
    redis = FakeRedis(decode_responses=True)
    await redis.set("projects:list:a", "1")
    await redis.set("projects:list:b", "1")
    await redis.set("project:1", "1")
    deleted = await invalidate_pattern(redis, "projects:list:*")
    assert deleted == 2
    assert await redis.get("projects:list:a") is None
    assert await redis.get("project:1") == "1"


async def test_cache_decorator_redis_down(monkeypatch: pytest.MonkeyPatch) -> None:
    """Cache decorator falls back to function when Redis fails."""

    class _Broken:
        async def get(self, *args: object, **kwargs: object) -> str:
            raise ConnectionError("down")

        async def set(self, *args: object, **kwargs: object) -> None:
            raise ConnectionError("down")

    monkeypatch.setattr(cache_mod, "get_redis_client", lambda: _Broken())

    @cache(ttl=60, key_builder=lambda: "k")
    async def _fn() -> int:
        return 7

    assert await _fn() == 7
