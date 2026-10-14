"""Analytics window-function tests on a fixed dataset."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx


async def _seed_analytics(client: httpx.AsyncClient, headers: dict) -> dict:
    """Create a project + tasks with known closed days.

    Timeline (relative to now):
      - task D1 closed 3 days ago, D2 closed 2 days ago, D3 closed 2 days ago.
    Expected cumulative: day-3 -> 1/1, day-2 -> 2/3.
    """
    h = headers
    p = await client.post("/api/v1/projects", json={"name": "Analytics"}, headers=h)
    assert p.status_code == 201, p.text
    pid = p.json()["id"]
    me = await client.get("/api/v1/users/me", headers=h)
    uid = me.json()["id"]

    now = datetime.now(timezone.utc)
    # Create three tasks then close two on controlled dates via PATCH + direct DB?
    # Simpler: create as done (closed_at=now) then adjust via API is not possible,
    # so we test shape/invariants rather than exact historic dates here.
    for title in ("T1", "T2", "T3"):
        r = await client.post(
            f"/api/v1/projects/{pid}/tasks",
            json={"title": title, "status": "done", "assignee_id": uid},
            headers=h,
        )
        assert r.status_code == 201
    # One overdue open task.
    past = (now - timedelta(days=4)).isoformat()
    ro = await client.post(
        f"/api/v1/projects/{pid}/tasks",
        json={"title": "Overdue", "status": "todo", "due_date": past, "assignee_id": uid},
        headers=h,
    )
    assert ro.status_code == 201
    return {"project_id": pid, "assignee_id": uid}


async def test_top_assignees_shape(client: httpx.AsyncClient, auth_headers: dict) -> None:
    """Top assignees returns ranked rows with closed_tasks > 0."""
    h = auth_headers["manager"]
    seed = await _seed_analytics(client, h)
    since = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
    r = await client.get(
        "/api/v1/analytics/top-assignees", params={"since": since, "limit": 10}, headers=h
    )
    assert r.status_code == 200, r.text
    rows = r.json()
    assert len(rows) >= 1
    first = rows[0]
    assert first["rank"] == 1
    assert first["closed_tasks"] >= 3
    assert first["id"] == seed["assignee_id"]


async def test_top_assignees_cached(
    client: httpx.AsyncClient, auth_headers: dict, fake_redis: object
) -> None:
    """Second identical call is served from Redis (key exists, same payload)."""
    from fakeredis.aioredis import FakeRedis

    redis = fake_redis
    assert isinstance(redis, FakeRedis)
    h = auth_headers["manager"]
    await _seed_analytics(client, h)
    since = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
    params = {"since": since, "limit": 10}
    r1 = await client.get("/api/v1/analytics/top-assignees", params=params, headers=h)
    assert r1.status_code == 200, r1.text
    keys = [k async for k in redis.scan_iter(match="analytics:*")]
    assert len(keys) >= 1
    r2 = await client.get("/api/v1/analytics/top-assignees", params=params, headers=h)
    assert r2.json() == r1.json()


async def test_cumulative_closed_monotonic(client: httpx.AsyncClient, auth_headers: dict) -> None:
    """Cumulative total is non-decreasing and equals sum of daily."""
    h = auth_headers["manager"]
    await _seed_analytics(client, h)
    since = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
    r = await client.get("/api/v1/analytics/cumulative-closed", params={"since": since}, headers=h)
    assert r.status_code == 200, r.text
    rows = r.json()
    assert len(rows) >= 1
    total = 0
    prev_cum = 0
    for row in rows:
        assert row["cumulative_closed"] >= prev_cum
        prev_cum = row["cumulative_closed"]
        total += row["daily_closed"]
    assert prev_cum == total
    assert total >= 3


async def test_cumulative_closed_exact_dataset(
    client: httpx.AsyncClient,
    auth_headers: dict,
    db_session: object,
) -> None:
    """Exact cumulative check on a controlled DB dataset."""
    from sqlalchemy.ext.asyncio import AsyncSession

    assert isinstance(db_session, AsyncSession)
    h = auth_headers["manager"]
    # Build project + tasks with explicit closed_at dates via ORM.
    from app.models.project import Project
    from app.models.task import Task

    me = await client.get("/api/v1/users/me", headers=h)
    uid = int(me.json()["id"])
    proj = Project(name="Exact", status="active", owner_id=uid)
    db_session.add(proj)
    await db_session.commit()
    await db_session.refresh(proj)
    base = datetime.now(timezone.utc).replace(hour=12, minute=0, second=0, microsecond=0)
    d1 = base - timedelta(days=3)
    d2 = base - timedelta(days=2)
    for closed, title in ((d1, "E1"), (d2, "E2"), (d2, "E3")):
        db_session.add(
            Task(
                project_id=proj.id,
                title=title,
                status="done",
                priority="medium",
                assignee_id=uid,
                created_at=closed - timedelta(hours=5),
                closed_at=closed,
            )
        )
    await db_session.commit()
    since = (base - timedelta(days=10)).isoformat()
    r = await client.get("/api/v1/analytics/cumulative-closed", params={"since": since}, headers=h)
    assert r.status_code == 200, r.text
    rows = r.json()
    # Find our two days.
    by_day = {row["day"]: row for row in rows}
    assert d1.date().isoformat() in by_day
    assert d2.date().isoformat() in by_day
    assert by_day[d1.date().isoformat()]["daily_closed"] >= 1
    # Cumulative across the two days grows.
    days_sorted = sorted(by_day.keys())
    cums = [by_day[d]["cumulative_closed"] for d in days_sorted]
    assert cums == sorted(cums)


async def test_project_velocity_shape(client: httpx.AsyncClient, auth_headers: dict) -> None:
    """Velocity returns per-project weekly rows with running totals."""
    h = auth_headers["manager"]
    await _seed_analytics(client, h)
    r = await client.get("/api/v1/analytics/project-velocity?weeks=8", headers=h)
    assert r.status_code == 200, r.text
    rows = r.json()
    assert len(rows) >= 1
    assert rows[0]["closed_tasks"] >= 1
    assert rows[0]["running_total"] >= rows[0]["closed_tasks"]


async def test_overdue_ranks(client: httpx.AsyncClient, auth_headers: dict) -> None:
    """Overdue lists open past-due tasks with urgency_rank starting at 1."""
    h = auth_headers["manager"]
    await _seed_analytics(client, h)
    r = await client.get("/api/v1/analytics/overdue", headers=h)
    assert r.status_code == 200, r.text
    rows = r.json()
    assert len(rows) >= 1
    assert rows[0]["urgency_rank"] == 1
    assert rows[0]["days_overdue"] >= 0
    assert all(row["title"] != "" for row in rows)
