"""Analytics service with Redis caching for heavy queries."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List

import redis.asyncio as redis_async
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import hash_params, top_assignees_key
from app.repositories.analytics import AnalyticsRepository


class AnalyticsService:
    """Thin layer over AnalyticsRepository adding cache."""

    TOP_TTL = 300

    def __init__(self, session: AsyncSession, redis: redis_async.Redis | None = None) -> None:
        self.session = session
        self.repo = AnalyticsRepository(session)
        self.redis = redis

    async def top_assignees(self, since: datetime, limit: int) -> List[Dict[str, Any]]:
        """Ranked assignees, cached 300s by (since, limit)."""
        if self.redis is not None:
            key = top_assignees_key(hash_params({"since": since.isoformat(), "limit": limit}))
            try:
                cached = await self.redis.get(key)
                if cached is not None:
                    data = json.loads(cached)
                    if isinstance(data, list):
                        return data
            except Exception:
                pass
            rows = await self.repo.top_assignees(since, limit)
            try:
                await self.redis.set(key, json.dumps(rows, default=str), ex=self.TOP_TTL)
            except Exception:
                pass
            return rows
        return await self.repo.top_assignees(since, limit)

    async def cumulative_closed(self, since: datetime) -> List[Dict[str, Any]]:
        """Running total of closed tasks per day."""
        return await self.repo.cumulative_closed(since)

    async def project_velocity(self, weeks: int) -> List[Dict[str, Any]]:
        """Weekly closed counts per project with running totals."""
        return await self.repo.project_velocity(weeks)

    async def overdue(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Overdue tasks ranked by urgency."""
        return await self.repo.overdue(limit)
