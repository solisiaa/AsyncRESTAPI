"""Analytics endpoints backed by window-function SQL."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.deps import get_current_user, get_redis_dep
from app.schemas.analytics import (
    CumulativeClosedRow,
    OverdueRow,
    ProjectVelocityRow,
    TopAssigneeRow,
)
from app.services.analytics import AnalyticsService

router = APIRouter(prefix="/analytics", tags=["analytics"])


def get_analytics_service(
    session: AsyncSession = Depends(get_db_session),
    redis: Any = Depends(get_redis_dep),
) -> AnalyticsService:
    """Build AnalyticsService per request."""
    try:
        return AnalyticsService(session, redis)
    except Exception:
        return AnalyticsService(session, None)


def _default_since(days: int = 90) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days)


@router.get(
    "/top-assignees",
    response_model=List[TopAssigneeRow],
    summary="Top assignees by closed tasks (RANK)",
)
async def top_assignees(
    since: Optional[datetime] = Query(default=None),
    limit: int = Query(default=10, ge=1, le=100),
    svc: AnalyticsService = Depends(get_analytics_service),
    user: Any = Depends(get_current_user),
) -> List[TopAssigneeRow]:
    """Ranking with RANK() + avg hours to close (cached 300s)."""
    since_val = since if since is not None else _default_since()
    rows = await svc.top_assignees(since_val, limit)
    return [TopAssigneeRow(**r) for r in rows]


@router.get(
    "/cumulative-closed",
    response_model=List[CumulativeClosedRow],
    summary="Cumulative closed tasks per day",
)
async def cumulative_closed(
    since: Optional[datetime] = Query(default=None),
    svc: AnalyticsService = Depends(get_analytics_service),
    user: Any = Depends(get_current_user),
) -> List[CumulativeClosedRow]:
    """Daily closed + SUM() OVER (ORDER BY day)."""
    since_val = since if since is not None else _default_since()
    rows = await svc.cumulative_closed(since_val)
    return [CumulativeClosedRow(**r) for r in rows]


@router.get(
    "/project-velocity",
    response_model=List[ProjectVelocityRow],
    summary="Weekly velocity per project",
)
async def project_velocity(
    weeks: int = Query(default=8, ge=1, le=52),
    svc: AnalyticsService = Depends(get_analytics_service),
    user: Any = Depends(get_current_user),
) -> List[ProjectVelocityRow]:
    """Closed tasks per week per project (PARTITION BY project_id)."""
    rows = await svc.project_velocity(weeks)
    return [ProjectVelocityRow(**r) for r in rows]


@router.get(
    "/overdue",
    response_model=List[OverdueRow],
    summary="Overdue tasks with urgency rank",
)
async def overdue(
    limit: int = Query(default=100, ge=1, le=500),
    svc: AnalyticsService = Depends(get_analytics_service),
    user: Any = Depends(get_current_user),
) -> List[OverdueRow]:
    """Overdue open tasks with DENSE_RANK() by due_date."""
    rows = await svc.overdue(limit)
    return [OverdueRow(**r) for r in rows]
