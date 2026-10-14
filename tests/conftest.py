"""Shared pytest fixtures: in-memory SQLite + FakeRedis + AsyncClient."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import AsyncIterator, Dict

import httpx
import pytest
import pytest_asyncio
from app.core.database import get_db_session
from app.core.deps import get_redis_dep
from app.core.security import get_password_hash
from app.main import create_app
from app.models.base import Base
from app.models.user import User
from fakeredis.aioredis import FakeRedis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool


def _test_engine():  # type: ignore[no-untyped-def]
    return create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


@pytest_asyncio.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    """Fresh in-memory DB per test."""
    engine = _test_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def fake_redis() -> AsyncIterator[FakeRedis]:
    """Fake async Redis per test."""
    redis = FakeRedis(decode_responses=True)
    yield redis
    try:
        await redis.flushall()  # type: ignore[no-untyped-call]
    except Exception:
        pass
    try:
        await redis.aclose()  # type: ignore[no-untyped-call]
    except Exception:
        try:
            redis.close()  # type: ignore[no-untyped-call]
        except Exception:
            pass


@pytest_asyncio.fixture
async def app(db_session: AsyncSession, fake_redis: FakeRedis):  # type: ignore[no-untyped-def]
    """FastAPI app with overridden DB + Redis dependencies."""
    application = create_app()

    async def _override_db():  # type: ignore[no-untyped-def]
        yield db_session

    async def _override_redis():  # type: ignore[no-untyped-def]
        return fake_redis

    application.dependency_overrides[get_db_session] = _override_db
    application.dependency_overrides[get_redis_dep] = _override_redis
    return application


@pytest_asyncio.fixture
async def client(app):  # type: ignore[no-untyped-def]
    """HTTPX async client bound to the test app."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def _make_user(
    session: AsyncSession, email: str, username: str, password: str, role: str
) -> User:
    user = User(
        email=email, username=username, hashed_password=get_password_hash(password), role=role
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


@pytest_asyncio.fixture
async def users(db_session: AsyncSession) -> Dict[str, User]:
    """Pre-created admin / manager / regular user."""
    admin = await _make_user(db_session, "admin@test.io", "admin", "admin12345", "admin")
    manager = await _make_user(db_session, "manager@test.io", "manager", "manager12345", "manager")
    user = await _make_user(db_session, "user@test.io", "user", "user12345", "user")
    return {"admin": admin, "manager": manager, "user": user}


@pytest_asyncio.fixture
async def tokens(users: Dict[str, User]) -> Dict[str, str]:
    """Bearer tokens for each role (created directly, no HTTP)."""
    from app.core.security import create_access_token

    out: Dict[str, str] = {}
    for role, user in users.items():
        out[role] = create_access_token(str(user.id), user.role)
    return out


@pytest.fixture
def auth_headers(tokens: Dict[str, str]) -> Dict[str, Dict[str, str]]:
    """Ready-to-use Authorization headers per role."""
    return {role: {"Authorization": f"Bearer {tok}"} for role, tok in tokens.items()}


@pytest.fixture
def utcnow() -> datetime:
    """Fixed-ish current time helper."""
    return datetime.now(timezone.utc)
