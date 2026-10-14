"""Project CRUD, RBAC, pagination, filters and cache tests."""

from __future__ import annotations

import httpx


async def _create_project(
    client: httpx.AsyncClient, headers: dict, name: str = "P1", status: str = "active"
) -> dict:
    r = await client.post(
        "/api/v1/projects", json={"name": name, "status": status}, headers=headers
    )
    assert r.status_code == 201, r.text
    return r.json()  # type: ignore[no-any-return]


async def test_manager_can_create_project(client: httpx.AsyncClient, auth_headers: dict) -> None:
    """Manager role may create projects."""
    body = await _create_project(client, auth_headers["manager"], "M project")
    assert body["name"] == "M project"


async def test_admin_can_create_project(client: httpx.AsyncClient, auth_headers: dict) -> None:
    """Admin role may create projects."""
    body = await _create_project(client, auth_headers["admin"], "A project")
    assert body["owner_id"] > 0


async def test_user_cannot_create_project(client: httpx.AsyncClient, auth_headers: dict) -> None:
    """Regular user is forbidden from creating projects (403)."""
    r = await client.post("/api/v1/projects", json={"name": "X"}, headers=auth_headers["user"])
    assert r.status_code == 403


async def test_unauthenticated_cannot_create(client: httpx.AsyncClient) -> None:
    """No token -> 401."""
    r = await client.post("/api/v1/projects", json={"name": "X"})
    assert r.status_code == 401


async def test_get_project_and_cache(
    client: httpx.AsyncClient, auth_headers: dict, fake_redis: object
) -> None:
    """GET /projects/{id} populates Redis; second GET is served from cache."""
    from fakeredis.aioredis import FakeRedis

    redis = fake_redis
    assert isinstance(redis, FakeRedis)
    proj = await _create_project(client, auth_headers["manager"], "Cached")
    pid = proj["id"]

    r1 = await client.get(f"/api/v1/projects/{pid}", headers=auth_headers["manager"])
    assert r1.status_code == 200
    cached = await redis.get(f"project:{pid}")
    assert cached is not None  # first read warms the cache

    r2 = await client.get(f"/api/v1/projects/{pid}", headers=auth_headers["manager"])
    assert r2.status_code == 200
    assert r2.json() == r1.json()


async def test_get_project_404(client: httpx.AsyncClient, auth_headers: dict) -> None:
    """Unknown project id yields 404."""
    r = await client.get("/api/v1/projects/999999", headers=auth_headers["user"])
    assert r.status_code == 404


async def test_update_project_invalidates_cache(
    client: httpx.AsyncClient, auth_headers: dict, fake_redis: object
) -> None:
    """PATCH updates data and clears project:{id} cache."""
    from fakeredis.aioredis import FakeRedis

    redis = fake_redis
    assert isinstance(redis, FakeRedis)
    proj = await _create_project(client, auth_headers["manager"], "To update")
    pid = proj["id"]
    await client.get(f"/api/v1/projects/{pid}", headers=auth_headers["manager"])
    assert await redis.get(f"project:{pid}") is not None

    r = await client.patch(
        f"/api/v1/projects/{pid}", json={"name": "Renamed"}, headers=auth_headers["manager"]
    )
    assert r.status_code == 200
    assert r.json()["name"] == "Renamed"
    assert await redis.get(f"project:{pid}") is None


async def test_user_cannot_update_project(client: httpx.AsyncClient, auth_headers: dict) -> None:
    """User role cannot PATCH (403)."""
    proj = await _create_project(client, auth_headers["manager"], "Locked")
    r = await client.patch(
        f"/api/v1/projects/{proj['id']}", json={"name": "Hack"}, headers=auth_headers["user"]
    )
    assert r.status_code == 403


async def test_delete_project_soft(client: httpx.AsyncClient, auth_headers: dict) -> None:
    """DELETE soft-deletes; subsequent GET is 404 and list excludes it."""
    proj = await _create_project(client, auth_headers["manager"], "To delete")
    pid = proj["id"]
    r = await client.delete(f"/api/v1/projects/{pid}", headers=auth_headers["manager"])
    assert r.status_code == 204
    r2 = await client.get(f"/api/v1/projects/{pid}", headers=auth_headers["manager"])
    assert r2.status_code == 404
    lst = await client.get("/api/v1/projects", headers=auth_headers["manager"])
    ids = [p["id"] for p in lst.json()["items"]]
    assert pid not in ids


async def test_list_pagination_and_filters(client: httpx.AsyncClient, auth_headers: dict) -> None:
    """Pagination metadata + status/owner filters work."""
    h = auth_headers["manager"]
    for i in range(5):
        await _create_project(client, h, f"Pag {i}", status="active" if i % 2 == 0 else "archived")

    r = await client.get("/api/v1/projects?limit=2&offset=0", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["limit"] == 2 and body["offset"] == 0
    assert body["total"] >= 5
    assert len(body["items"]) == 2

    r2 = await client.get("/api/v1/projects?limit=2&offset=2", headers=h)
    assert len(r2.json()["items"]) == 2

    r3 = await client.get("/api/v1/projects?status=archived", headers=h)
    assert r3.status_code == 200
    assert all(p["status"] == "archived" for p in r3.json()["items"])
    assert r3.json()["total"] >= 2


async def test_list_limit_clamped(client: httpx.AsyncClient, auth_headers: dict) -> None:
    """Huge limit is rejected by Query validation (422)."""
    h = auth_headers["manager"]
    r = await client.get("/api/v1/projects", params={"limit": 1000, "offset": 0}, headers=h)
    assert r.status_code == 422
