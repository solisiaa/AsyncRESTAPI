"""Single-task endpoints: get / patch / delete."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.deps import get_current_user, get_redis_dep
from app.core.exceptions import AppError
from app.schemas.task import TaskRead, TaskUpdate
from app.services.task import TaskService

router = APIRouter(prefix="/tasks", tags=["tasks"])


def get_task_service(
    session: AsyncSession = Depends(get_db_session),
    redis: Any = Depends(get_redis_dep),
) -> TaskService:
    """Build TaskService per request."""
    try:
        return TaskService(session, redis)
    except Exception:
        return TaskService(session, None)


@router.get("/{task_id}", response_model=TaskRead, summary="Get task by id")
async def get_task(
    task_id: int,
    svc: TaskService = Depends(get_task_service),
    user: Any = Depends(get_current_user),
) -> TaskRead:
    """Fetch one task."""
    try:
        task = await svc.get_by_id(task_id)
    except AppError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from None
    return TaskRead.model_validate(task)


@router.patch("/{task_id}", response_model=TaskRead, summary="Update task")
async def update_task(
    task_id: int,
    payload: TaskUpdate,
    svc: TaskService = Depends(get_task_service),
    user: Any = Depends(get_current_user),
) -> TaskRead:
    """Partially update a task (closed_at invariant enforced)."""
    try:
        task = await svc.update(task_id, payload.model_dump(exclude_unset=True))
    except AppError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from None
    return TaskRead.model_validate(task)


@router.delete(
    "/{task_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="Delete task",
)
async def delete_task(
    task_id: int,
    svc: TaskService = Depends(get_task_service),
    user: Any = Depends(get_current_user),
) -> None:
    """Hard-delete a task."""
    try:
        await svc.delete(task_id)
    except AppError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from None
    return None
