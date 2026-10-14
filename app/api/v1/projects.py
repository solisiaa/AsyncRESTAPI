"""Project CRUD + task listing scoped to a project."""

from __future__ import annotations

from datetime import datetime
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.deps import get_current_user, get_redis_dep, require_role
from app.core.exceptions import AppError
from app.schemas.common import Page
from app.schemas.project import ProjectCreate, ProjectRead, ProjectUpdate
from app.schemas.task import TaskCreate, TaskRead
from app.services.project import ProjectService
from app.services.task import TaskService
from app.utils.pagination import make_page

router = APIRouter(prefix="/projects", tags=["projects"])


def get_project_service(
    session: AsyncSession = Depends(get_db_session),
    redis: Any = Depends(get_redis_dep),
) -> ProjectService:
    """Build ProjectService with optional Redis."""
    try:
        return ProjectService(session, redis)
    except Exception:
        return ProjectService(session, None)


def get_task_service(
    session: AsyncSession = Depends(get_db_session),
    redis: Any = Depends(get_redis_dep),
) -> TaskService:
    """Build TaskService with optional Redis."""
    try:
        return TaskService(session, redis)
    except Exception:
        return TaskService(session, None)


def _to_read(p: Any) -> ProjectRead:
    return ProjectRead.model_validate(p)


def _task_to_read(t: Any) -> TaskRead:
    return TaskRead.model_validate(t)


@router.post(
    "",
    response_model=ProjectRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create project (manager/admin)",
    dependencies=[Depends(require_role("admin", "manager"))],
)
async def create_project(
    payload: ProjectCreate,
    svc: ProjectService = Depends(get_project_service),
    user: Any = Depends(get_current_user),
) -> ProjectRead:
    """Create a project owned by the caller."""
    project = await svc.create(payload.name, payload.description, payload.status, int(user.id))
    return _to_read(project)


@router.get("", response_model=Page[ProjectRead], summary="List projects")
async def list_projects(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    status: Optional[str] = Query(default=None),
    owner_id: Optional[int] = Query(default=None),
    created_after: Optional[datetime] = Query(default=None),
    svc: ProjectService = Depends(get_project_service),
    user: Any = Depends(get_current_user),
) -> Page[ProjectRead]:
    """Paginated + filtered project list (cached 30s)."""
    items, total = await svc.list(limit, offset, status, owner_id, created_after)
    return make_page([_to_read(p) for p in items], total, limit, offset)


@router.get("/{project_id}", response_model=ProjectRead, summary="Get project details")
async def get_project(
    project_id: int,
    svc: ProjectService = Depends(get_project_service),
    user: Any = Depends(get_current_user),
) -> ProjectRead:
    """Project details (cached 60s)."""
    try:
        project = await svc.get_by_id(project_id)
    except AppError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from None
    return _to_read(project)


@router.patch(
    "/{project_id}",
    response_model=ProjectRead,
    summary="Update project (manager/admin)",
    dependencies=[Depends(require_role("admin", "manager"))],
)
async def update_project(
    project_id: int,
    payload: ProjectUpdate,
    svc: ProjectService = Depends(get_project_service),
    user: Any = Depends(get_current_user),
) -> ProjectRead:
    """Partially update a project."""
    try:
        project = await svc.update(project_id, payload.model_dump(exclude_unset=True))
    except AppError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from None
    return _to_read(project)


@router.delete(
    "/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="Soft-delete project (manager/admin)",
    dependencies=[Depends(require_role("admin", "manager"))],
)
async def delete_project(
    project_id: int,
    svc: ProjectService = Depends(get_project_service),
    user: Any = Depends(get_current_user),
) -> None:
    """Soft-delete a project."""
    try:
        await svc.delete(project_id)
    except AppError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from None
    return None


# ---- Tasks scoped to a project ----


@router.post(
    "/{project_id}/tasks",
    response_model=TaskRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create task in project",
)
async def create_task(
    project_id: int,
    payload: TaskCreate,
    svc: TaskService = Depends(get_task_service),
    user: Any = Depends(get_current_user),
) -> TaskRead:
    """Create a task inside a project."""
    try:
        task = await svc.create(project_id, payload.model_dump(exclude_unset=True))
    except AppError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from None
    return _task_to_read(task)


@router.get("/{project_id}/tasks", response_model=Page[TaskRead], summary="List project tasks")
async def list_project_tasks(
    project_id: int,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    status: Optional[str] = Query(default=None),
    assignee_id: Optional[int] = Query(default=None),
    priority: Optional[str] = Query(default=None),
    due_before: Optional[datetime] = Query(default=None),
    svc: TaskService = Depends(get_task_service),
    user: Any = Depends(get_current_user),
) -> Page[TaskRead]:
    """Filtered + paginated tasks of a project."""
    try:
        items, total = await svc.list_by_project(
            project_id, limit, offset, status, assignee_id, priority, due_before
        )
    except AppError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from None
    reads: List[TaskRead] = [_task_to_read(t) for t in items]
    return make_page(reads, total, limit, offset)
