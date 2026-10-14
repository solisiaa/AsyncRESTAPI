"""Analytical queries with window functions (raw SQL)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, SQLAlchemyError

from app.repositories.base import BaseRepository


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _round2(value: object) -> Optional[float]:
    if value is None:
        return None
    try:
        return round(float(str(value)), 2)
    except (ValueError, TypeError):
        return None


class AnalyticsRepository(BaseRepository):
    """Raw-SQL analytics using window functions.

    Production SQL targets PostgreSQL (see README). SQLite-compatible
    fallbacks are provided so the test suite runs without Postgres.
    """

    async def top_assignees(self, since: datetime, limit: int) -> List[Dict[str, Any]]:
        """Rank assignees by closed tasks with RANK() + avg close time.

        Args:
            since: Only tasks created at/after this moment.
            limit: Max rows.

        Returns:
            Rows with id, username, closed_tasks, rank, avg_hours_to_close.
        """
        pg_sql = text(
            """
            SELECT
                u.id AS id,
                u.username AS username,
                COUNT(*) FILTER (WHERE t.status = 'done') AS closed_tasks,
                RANK() OVER (
                    ORDER BY COUNT(*) FILTER (WHERE t.status = 'done') DESC
                ) AS rank,
                ROUND(
                    AVG(EXTRACT(EPOCH FROM (t.closed_at - t.created_at)) / 3600), 2
                ) AS avg_hours_to_close
            FROM users u
            JOIN tasks t ON t.assignee_id = u.id
            WHERE t.created_at >= :since
            GROUP BY u.id, u.username
            ORDER BY rank
            LIMIT :limit
            """
        )
        try:
            result = await self.session.execute(pg_sql, {"since": since, "limit": limit})
            rows = result.mappings().all()
            return [
                {
                    "id": int(r["id"]),
                    "username": str(r["username"]),
                    "closed_tasks": int(r["closed_tasks"]),
                    "rank": int(r["rank"]),
                    "avg_hours_to_close": _round2(r["avg_hours_to_close"]),
                }
                for r in rows
            ]
        except (DBAPIError, SQLAlchemyError):
            await self.session.rollback()

        lite_sql = text(
            """
            SELECT
                u.id AS id,
                u.username AS username,
                SUM(CASE WHEN t.status = 'done' THEN 1 ELSE 0 END) AS closed_tasks,
                RANK() OVER (
                    ORDER BY SUM(CASE WHEN t.status = 'done' THEN 1 ELSE 0 END) DESC
                ) AS rank,
                AVG(
                    CASE WHEN t.status = 'done'
                    THEN (julianday(t.closed_at) - julianday(t.created_at)) * 24
                    ELSE NULL END
                ) AS avg_hours_to_close
            FROM users u
            JOIN tasks t ON t.assignee_id = u.id
            WHERE t.created_at >= :since
            GROUP BY u.id, u.username
            ORDER BY rank
            LIMIT :limit
            """
        )
        result = await self.session.execute(lite_sql, {"since": since, "limit": limit})
        rows = result.mappings().all()
        return [
            {
                "id": int(r["id"]),
                "username": str(r["username"]),
                "closed_tasks": int(r["closed_tasks"] or 0),
                "rank": int(r["rank"]),
                "avg_hours_to_close": _round2(r["avg_hours_to_close"]),
            }
            for r in rows
        ]

    async def cumulative_closed(self, since: datetime) -> List[Dict[str, Any]]:
        """Daily closed counts + running total (SUM OVER ORDER BY day)."""
        sql = text(
            """
            SELECT
                day,
                daily_closed,
                SUM(daily_closed) OVER (ORDER BY day) AS cumulative_closed
            FROM (
                SELECT DATE(closed_at) AS day, COUNT(*) AS daily_closed
                FROM tasks
                WHERE closed_at IS NOT NULL AND closed_at >= :since
                GROUP BY DATE(closed_at)
            ) d
            ORDER BY day
            """
        )
        result = await self.session.execute(sql, {"since": since})
        rows = result.mappings().all()
        out: List[Dict[str, Any]] = []
        for r in rows:
            day_val = r["day"]
            day_str = str(day_val)[:10]  # works for date/datetime/str
            out.append(
                {
                    "day": day_str,
                    "daily_closed": int(r["daily_closed"]),
                    "cumulative_closed": int(r["cumulative_closed"]),
                }
            )
        return out

    async def project_velocity(self, weeks: int) -> List[Dict[str, Any]]:
        """Closed tasks per project per week with PARTITION BY running total."""
        since = _utcnow() - timedelta(weeks=weeks)
        pg_sql = text(
            """
            SELECT
                p.id AS project_id,
                p.name AS project_name,
                DATE_TRUNC('week', t.closed_at)::date AS week_start,
                COUNT(*) AS closed_tasks,
                SUM(COUNT(*)) OVER (
                    PARTITION BY p.id ORDER BY DATE_TRUNC('week', t.closed_at)
                ) AS running_total
            FROM tasks t
            JOIN projects p ON p.id = t.project_id
            WHERE t.closed_at IS NOT NULL
              AND t.closed_at >= :since
              AND t.status = 'done'
            GROUP BY p.id, p.name, DATE_TRUNC('week', t.closed_at)
            ORDER BY p.id, week_start
            """
        )
        try:
            result = await self.session.execute(pg_sql, {"since": since})
            rows = result.mappings().all()
            return [
                {
                    "project_id": int(r["project_id"]),
                    "project_name": str(r["project_name"]),
                    "week_start": str(r["week_start"])[:10],
                    "closed_tasks": int(r["closed_tasks"]),
                    "running_total": int(r["running_total"]),
                }
                for r in rows
            ]
        except (DBAPIError, SQLAlchemyError):
            await self.session.rollback()

        lite_sql = text(
            """
            SELECT
                p.id AS project_id,
                p.name AS project_name,
                date(t.closed_at, 'weekday 0', '-6 days') AS week_start,
                COUNT(*) AS closed_tasks,
                SUM(COUNT(*)) OVER (
                    PARTITION BY p.id
                    ORDER BY date(t.closed_at, 'weekday 0', '-6 days')
                ) AS running_total
            FROM tasks t
            JOIN projects p ON p.id = t.project_id
            WHERE t.closed_at IS NOT NULL
              AND t.closed_at >= :since
              AND t.status = 'done'
            GROUP BY p.id, p.name, date(t.closed_at, 'weekday 0', '-6 days')
            ORDER BY p.id, week_start
            """
        )
        result = await self.session.execute(lite_sql, {"since": since})
        rows = result.mappings().all()
        return [
            {
                "project_id": int(r["project_id"]),
                "project_name": str(r["project_name"]),
                "week_start": str(r["week_start"])[:10],
                "closed_tasks": int(r["closed_tasks"]),
                "running_total": int(r["running_total"]),
            }
            for r in rows
        ]

    async def overdue(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Overdue open tasks with DENSE_RANK() by urgency (earliest due first)."""
        now = _utcnow()
        sql = text(
            """
            SELECT
                id, title, project_id, assignee_id, due_date,
                DENSE_RANK() OVER (ORDER BY due_date ASC) AS urgency_rank
            FROM tasks
            WHERE due_date IS NOT NULL
              AND due_date < :now
              AND status != 'done'
            ORDER BY due_date ASC
            LIMIT :limit
            """
        )
        result = await self.session.execute(sql, {"now": now, "limit": limit})
        rows = result.mappings().all()
        out: List[Dict[str, Any]] = []
        for r in rows:
            due = r["due_date"]
            days_overdue = 0
            due_date_str: Optional[str] = None
            if due is not None:
                if isinstance(due, datetime):
                    due_dt = due
                    if due_dt.tzinfo is None:
                        due_dt = due_dt.replace(tzinfo=timezone.utc)
                    days_overdue = max(0, (now - due_dt).days)
                    due_date_str = due_dt.date().isoformat()
                else:
                    # SQLite returns 'YYYY-MM-DD HH:MM:SS' strings.
                    due_s = str(due)
                    due_date_str = due_s[:10]
                    try:
                        parsed = datetime.fromisoformat(due_s)
                        if parsed.tzinfo is None:
                            parsed = parsed.replace(tzinfo=timezone.utc)
                        days_overdue = max(0, (now - parsed).days)
                    except ValueError:
                        days_overdue = 0
            out.append(
                {
                    "id": int(r["id"]),
                    "title": str(r["title"]),
                    "project_id": int(r["project_id"]),
                    "assignee_id": (
                        int(r["assignee_id"]) if r["assignee_id"] is not None else None
                    ),
                    "due_date": due_date_str,
                    "days_overdue": int(days_overdue),
                    "urgency_rank": int(r["urgency_rank"]),
                }
            )
        return out
