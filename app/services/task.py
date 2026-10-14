"""Task business logic incl. closed_at invariant."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

import redis.asyncio as redis_async
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.task import Task
from app.repositories.project import ProjectRepository
from app.repositories.task import TaskRepository


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TaskService:
    """Task CRUD scoped to projects."""

    def __init__(self, session: AsyncSession, redis: redis_async.Redis | None = None) -> None:
        self.session = session
        self.repo = TaskRepository(session)
        self.projects = ProjectRepository(session)
        self.redis = redis

    async def _ensure_project(self, project_id: int) -> None:
        project = await self.projects.get_by_id(project_id)
        if project is None:
            raise NotFoundError("Project not found")

    async def _invalidate_analytics(self) -> None:
        if self.redis is not None:
            try:
                async for key in self.redis.scan_iter(match="analytics:*"):
                    await self.redis.delete(key)
            except Exception:
                pass

    async def create(self, project_id: int, data: Dict[str, Any]) -> Task:
        """Create a task in a project, setting closed_at when needed."""
        await self._ensure_project(project_id)
        payload = dict(data)
        payload["project_id"] = project_id
        if payload.get("status") == "done" and payload.get("closed_at") is None:
            payload["closed_at"] = _utcnow()
        task = await self.repo.create(payload)
        await self.session.commit()
        await self.session.refresh(task)
        await self._invalidate_analytics()
        return task

    async def list_by_project(
        self,
        project_id: int,
        limit: int,
        offset: int,
        status: Optional[str] = None,
        assignee_id: Optional[int] = None,
        priority: Optional[str] = None,
        due_before: Optional[datetime] = None,
    ) -> tuple[list[Task], int]:
        """List tasks of a project with filters."""
        await self._ensure_project(project_id)
        return await self.repo.list_by_project(
            project_id, limit, offset, status, assignee_id, priority, due_before
        )

    async def get_by_id(self, task_id: int) -> Task:
        """Fetch one task or raise 404."""
        task = await self.repo.get_by_id(task_id)
        if task is None:
            raise NotFoundError("Task not found")
        return task

    async def update(self, task_id: int, fields: Dict[str, Any]) -> Task:
        """Update a task; maintains the closed_at invariant.

        Invariant: status == 'done'  <=>  closed_at is set.
        - Moving to done without closed_at stamps now.
        - Moving away from done clears closed_at.
        """
        task = await self.repo.get_by_id(task_id)
        if task is None:
            raise NotFoundError("Task not found")
        clean = {k: v for k, v in fields.items() if v is not None or k == "due_date"}
        # Explicit None for due_date is allowed (clear deadline); other Nones mean "no change"
        # except assignee_id which may be cleared.
        new_status = str(clean.get("status", task.status))
        if new_status == "done" and task.status != "done":
            clean["closed_at"] = _utcnow()
        elif new_status != "done" and task.status == "done":
            clean["closed_at"] = None
        # Drop None-valued keys except explicit clears.
        final: Dict[str, Any] = {}
        for k, v in clean.items():
            if v is None and k not in ("due_date", "assignee_id", "closed_at", "description"):
                continue
            final[k] = v
        updated = await self.repo.update(task, final)
        await self.session.commit()
        await self.session.refresh(updated)
        await self._invalidate_analytics()
        return updated

    async def delete(self, task_id: int) -> None:
        """Delete a task."""
        task = await self.repo.get_by_id(task_id)
        if task is None:
            raise NotFoundError("Task not found")
        await self.repo.delete(task)
        await self.session.commit()
        await self._invalidate_analytics()
