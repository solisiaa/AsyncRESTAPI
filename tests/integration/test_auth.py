"""Auth flow tests: register / login / refresh / me / 401s."""

from __future__ import annotations

import httpx


async def test_register_success(client: httpx.AsyncClient) -> None:
    """New user can register and then fetch profile."""
    r = await client.post(
        "/api/v1/auth/register",
        json={"email": "new@test.io", "username": "newuser", "password": "strongpass1"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["email"] == "new@test.io"
    assert body["role"] == "user"


async def test_register_duplicate_email(client: httpx.AsyncClient, users: dict) -> None:
    """Duplicate e-mail is rejected with 409."""
    r = await client.post(
        "/api/v1/auth/register",
        json={"email": "user@test.io", "username": "other", "password": "strongpass1"},
    )
    assert r.status_code == 409


async def test_register_duplicate_username(client: httpx.AsyncClient, users: dict) -> None:
    """Duplicate username is rejected with 409."""
    r = await client.post(
        "/api/v1/auth/register",
        json={"email": "other@test.io", "username": "user", "password": "strongpass1"},
    )
    assert r.status_code == 409


async def test_login_success(client: httpx.AsyncClient, users: dict) -> None:
    """Login with username returns token pair."""
    r = await client.post("/api/v1/auth/login", json={"username": "user", "password": "user12345"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert "access_token" in body and "refresh_token" in body


async def test_login_with_email(client: httpx.AsyncClient, users: dict) -> None:
    """Login with e-mail also works."""
    r = await client.post(
        "/api/v1/auth/login", json={"username": "user@test.io", "password": "user12345"}
    )
    assert r.status_code == 200


async def test_login_wrong_password(client: httpx.AsyncClient, users: dict) -> None:
    """Wrong password yields 401."""
    r = await client.post("/api/v1/auth/login", json={"username": "user", "password": "wrongpass"})
    assert r.status_code == 401


async def test_login_unknown_user(client: httpx.AsyncClient) -> None:
    """Unknown login yields 401."""
    r = await client.post(
        "/api/v1/auth/login", json={"username": "ghost", "password": "whatever123"}
    )
    assert r.status_code == 401


async def test_refresh_success(client: httpx.AsyncClient, users: dict) -> None:
    """Valid refresh token returns a new pair."""
    login = await client.post(
        "/api/v1/auth/login", json={"username": "user", "password": "user12345"}
    )
    refresh_token = login.json()["refresh_token"]
    r = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert r.status_code == 200, r.text
    assert "access_token" in r.json()


async def test_refresh_invalid(client: httpx.AsyncClient) -> None:
    """Garbage refresh token yields 401."""
    r = await client.post("/api/v1/auth/refresh", json={"refresh_token": "bad.token.here"})
    assert r.status_code == 401


async def test_refresh_with_access_token(client: httpx.AsyncClient, users: dict) -> None:
    """Access token cannot be used as refresh (wrong type)."""
    login = await client.post(
        "/api/v1/auth/login", json={"username": "user", "password": "user12345"}
    )
    access = login.json()["access_token"]
    r = await client.post("/api/v1/auth/refresh", json={"refresh_token": access})
    assert r.status_code == 401


async def test_me_success(client: httpx.AsyncClient, auth_headers: dict) -> None:
    """Authenticated user gets own profile."""
    r = await client.get("/api/v1/users/me", headers=auth_headers["user"])
    assert r.status_code == 200
    assert r.json()["username"] == "user"


async def test_me_no_token(client: httpx.AsyncClient) -> None:
    """Missing token yields 401."""
    r = await client.get("/api/v1/users/me")
    assert r.status_code == 401


async def test_me_bad_token(client: httpx.AsyncClient) -> None:
    """Malformed token yields 401."""
    r = await client.get("/api/v1/users/me", headers={"Authorization": "Bearer invalid"})
    assert r.status_code == 401


async def test_expired_token_rejected(client: httpx.AsyncClient, users: dict) -> None:
    """Expired access token is rejected."""
    from datetime import timedelta

    from app.core.security import create_token

    user = users["user"]
    expired = create_token(str(user.id), user.role, timedelta(seconds=-1), "access")
    r = await client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {expired}"})
    assert r.status_code == 401
