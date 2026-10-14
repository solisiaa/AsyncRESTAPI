"""Task CRUD, filters and closed_at invariant tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx


async def _project(client: httpx.AsyncClient, headers: dict) -> int:
    r = await client.post("/api/v1/projects", json={"name": "TP"}, headers=headers)
    assert r.status_code == 201, r.text
    return int(r.json()["id"])


async def test_create_and_get_task(client: httpx.AsyncClient, auth_headers: dict) -> None:
    """Create a task in a project and fetch it back."""
    pid = await _project(client, auth_headers["manager"])
    r = await client.post(
        f"/api/v1/projects/{pid}/tasks",
        json={"title": "T1", "priority": "high"},
        headers=auth_headers["manager"],
    )
    assert r.status_code == 201, r.text
    tid = r.json()["id"]
    g = await client.get(f"/api/v1/tasks/{tid}", headers=auth_headers["user"])
    assert g.status_code == 200
    assert g.json()["title"] == "T1"


async def test_create_task_unknown_project(client: httpx.AsyncClient, auth_headers: dict) -> None:
    """Creating in a missing project yields 404."""
    r = await client.post(
        "/api/v1/projects/999999/tasks",
        json={"title": "X"},
        headers=auth_headers["manager"],
    )
    assert r.status_code == 404


async def test_done_sets_closed_at(client: httpx.AsyncClient, auth_headers: dict) -> None:
    """PATCH status -> done stamps closed_at."""
    pid = await _project(client, auth_headers["manager"])
    r = await client.post(
        f"/api/v1/projects/{pid}/tasks", json={"title": "Close me"}, headers=auth_headers["manager"]
    )
    tid = r.json()["id"]
    assert r.json()["closed_at"] is None

    u = await client.patch(
        f"/api/v1/tasks/{tid}", json={"status": "done"}, headers=auth_headers["manager"]
    )
    assert u.status_code == 200
    assert u.json()["status"] == "done"
    assert u.json()["closed_at"] is not None


async def test_reopen_clears_closed_at(client: httpx.AsyncClient, auth_headers: dict) -> None:
    """Moving done -> in_progress clears closed_at (invariant)."""
    pid = await _project(client, auth_headers["manager"])
    r = await client.post(
        f"/api/v1/projects/{pid}/tasks",
        json={"title": "Reopen", "status": "done"},
        headers=auth_headers["manager"],
    )
    tid = r.json()["id"]
    assert r.json()["closed_at"] is not None
    u = await client.patch(
        f"/api/v1/tasks/{tid}", json={"status": "in_progress"}, headers=auth_headers["manager"]
    )
    assert u.json()["closed_at"] is None


async def test_create_done_sets_closed_at(client: httpx.AsyncClient, auth_headers: dict) -> None:
    """Creating with status=done immediately stamps closed_at."""
    pid = await _project(client, auth_headers["manager"])
    r = await client.post(
        f"/api/v1/projects/{pid}/tasks",
        json={"title": "Instant done", "status": "done"},
        headers=auth_headers["manager"],
    )
    assert r.status_code == 201
    assert r.json()["closed_at"] is not None


async def test_list_filters_and_pagination(client: httpx.AsyncClient, auth_headers: dict) -> None:
    """Status/priority/assignee filters + total counts."""
    h = auth_headers["manager"]
    pid = await _project(client, h)
    # Need a user id for assignee filter.
    me = await client.get("/api/v1/users/me", headers=h)
    uid = me.json()["id"]
    await client.post(
        f"/api/v1/projects/{pid}/tasks",
        json={"title": "A", "status": "todo", "priority": "low", "assignee_id": uid},
        headers=h,
    )
    await client.post(
        f"/api/v1/projects/{pid}/tasks",
        json={"title": "B", "status": "done", "priority": "high", "assignee_id": uid},
        headers=h,
    )
    await client.post(
        f"/api/v1/projects/{pid}/tasks", json={"title": "C", "status": "todo"}, headers=h
    )

    r = await client.get(f"/api/v1/projects/{pid}/tasks?status=todo", headers=h)
    assert r.json()["total"] == 2

    r2 = await client.get(f"/api/v1/projects/{pid}/tasks?priority=high", headers=h)
    assert r2.json()["total"] == 1

    r3 = await client.get(f"/api/v1/projects/{pid}/tasks?assignee_id={uid}", headers=h)
    assert r3.json()["total"] == 2

    r4 = await client.get(f"/api/v1/projects/{pid}/tasks?limit=1&offset=0", headers=h)
    assert r4.json()["total"] == 3 and len(r4.json()["items"]) == 1


async def test_due_before_filter(client: httpx.AsyncClient, auth_headers: dict) -> None:
    """due_before returns only tasks with earlier deadlines."""
    h = auth_headers["manager"]
    pid = await _project(client, h)
    past = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
    future = (datetime.now(timezone.utc) + timedelta(days=5)).isoformat()
    await client.post(
        f"/api/v1/projects/{pid}/tasks", json={"title": "Past", "due_date": past}, headers=h
    )
    await client.post(
        f"/api/v1/projects/{pid}/tasks", json={"title": "Future", "due_date": future}, headers=h
    )
    now_iso = datetime.now(timezone.utc).isoformat()
    r = await client.get(f"/api/v1/projects/{pid}/tasks", params={"due_before": now_iso}, headers=h)
    assert r.status_code == 200
    assert r.json()["total"] == 1
    assert r.json()["items"][0]["title"] == "Past"


async def test_delete_task(client: httpx.AsyncClient, auth_headers: dict) -> None:
    """DELETE removes the task; GET after is 404."""
    h = auth_headers["manager"]
    pid = await _project(client, h)
    r = await client.post(f"/api/v1/projects/{pid}/tasks", json={"title": "Gone"}, headers=h)
    tid = r.json()["id"]
    d = await client.delete(f"/api/v1/tasks/{tid}", headers=h)
    assert d.status_code == 204
    g = await client.get(f"/api/v1/tasks/{tid}", headers=h)
    assert g.status_code == 404


async def test_get_task_404(client: httpx.AsyncClient, auth_headers: dict) -> None:
    """Unknown task id yields 404."""
    r = await client.get("/api/v1/tasks/999999", headers=auth_headers["user"])
    assert r.status_code == 404


async def test_unauthenticated_tasks_rejected(client: httpx.AsyncClient) -> None:
    """Task endpoints require auth."""
    r = await client.get("/api/v1/tasks/1")
    assert r.status_code == 401
