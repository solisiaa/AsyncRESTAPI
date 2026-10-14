"""Misc unit coverage: services, deps, pagination, db/redis helpers."""

from __future__ import annotations

import pytest
from app.core.cache import cache_get, cache_set
from app.core.deps import get_pagination_params, require_role
from app.core.exceptions import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    UnauthorizedError,
    ValidationError,
)
from app.services.user import UserService
from app.utils.pagination import make_page
from sqlalchemy.ext.asyncio import AsyncSession


async def test_user_service_get_by_id(db_session: AsyncSession) -> None:
    """UserService returns user or raises 404."""
    from app.core.security import get_password_hash
    from app.models.user import User

    user = User(email="m@test.io", username="m1", hashed_password=get_password_hash("x" * 8))
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    svc = UserService(db_session)
    found = await svc.get_by_id(user.id)
    assert found.email == "m@test.io"
    with pytest.raises(NotFoundError):
        await svc.get_by_id(999999)


async def test_user_service_not_found_empty_db(db_session: AsyncSession) -> None:
    """404 on empty database."""
    svc = UserService(db_session)
    with pytest.raises(NotFoundError):
        await svc.get_by_id(1)


def test_make_page() -> None:
    """Pagination envelope fields."""
    page = make_page([1, 2], total=10, limit=2, offset=4)
    assert page.total == 10 and page.limit == 2 and page.offset == 4
    assert page.items == [1, 2]


async def test_get_pagination_params_clamps() -> None:
    """Pagination helper clamps limit/offset."""
    p = await get_pagination_params(limit=1000, offset=-5)
    assert p == {"limit": 100, "offset": 0}
    p2 = await get_pagination_params(limit=0, offset=3)
    assert p2["limit"] == 1


async def test_require_role_allows_and_forbids() -> None:
    """RBAC dependency factory."""
    from fastapi import HTTPException

    checker = require_role("admin", "manager")
    assert await checker(role="admin") == "admin"
    with pytest.raises(HTTPException) as exc:
        await checker(role="user")
    assert exc.value.status_code == 403


async def test_cache_get_set_helpers() -> None:
    """cache_get / cache_set roundtrip on FakeRedis."""
    from fakeredis.aioredis import FakeRedis

    redis = FakeRedis(decode_responses=True)
    assert await cache_get(redis, "missing") is None
    await cache_set(redis, "k", "v", ttl=60)
    assert await cache_get(redis, "k") == "v"


def test_exceptions_have_codes() -> None:
    """Domain exceptions carry status + code."""
    assert NotFoundError("x").status_code == 404
    assert ConflictError("x").code == "conflict"
    assert UnauthorizedError("x").status_code == 401
    assert ForbiddenError("x").status_code == 403
    assert ValidationError("x").status_code == 422


def test_database_singletons() -> None:
    """Engine/session factory singletons construct without connecting."""
    from app.core import database as db_mod

    # Reset singletons to avoid cross-test pollution.
    db_mod._engine = None
    db_mod._session_factory = None
    engine = db_mod.get_engine()
    assert engine is db_mod.get_engine()
    factory = db_mod.get_session_factory()
    assert factory is db_mod.get_session_factory()


async def test_redis_close_and_client() -> None:
    """Redis client singleton + close path."""
    from app.core import redis as redis_mod

    redis_mod._client = None
    client = redis_mod.get_redis_client()
    assert client is redis_mod.get_redis_client()
    await redis_mod.close_redis()
    assert redis_mod._client is None
