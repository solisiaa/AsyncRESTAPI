"""Task data access with filtering + pagination."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional, Tuple

from sqlalchemy import func, select

from app.models.task import Task
from app.repositories.base import BaseRepository


class TaskRepository(BaseRepository):
    """Data access for tasks."""

    async def create(self, data: Dict[str, Any]) -> Task:
        """Insert a task from a field dict."""
        task = Task(**data)
        self.session.add(task)
        await self.session.flush()
        await self.session.refresh(task)
        return task

    async def get_by_id(self, task_id: int) -> Optional[Task]:
        """Fetch one task by id."""
        result = await self.session.execute(select(Task).where(Task.id == task_id))
        return result.scalars().first()

    async def list_by_project(
        self,
        project_id: int,
        limit: int,
        offset: int,
        status: Optional[str] = None,
        assignee_id: Optional[int] = None,
        priority: Optional[str] = None,
        due_before: Optional[datetime] = None,
    ) -> Tuple[list[Task], int]:
        """List tasks of a project with filters + total.

        Returns:
            Tuple of (items, total).
        """
        filters: list[Any] = [Task.project_id == project_id]
        if status is not None:
            filters.append(Task.status == status)
        if assignee_id is not None:
            filters.append(Task.assignee_id == assignee_id)
        if priority is not None:
            filters.append(Task.priority == priority)
        if due_before is not None:
            filters.append(Task.due_date.is_not(None))
            filters.append(Task.due_date < due_before)

        count_stmt = select(func.count()).select_from(Task).where(*filters)
        total = int((await self.session.execute(count_stmt)).scalar_one())

        stmt = select(Task).where(*filters).order_by(Task.id.desc()).limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        return list(result.scalars().all()), total

    async def update(self, task: Task, fields: Dict[str, Any]) -> Task:
        """Apply a field dict to a managed task."""
        for key, value in fields.items():
            if hasattr(task, key):
                setattr(task, key, value)
        await self.session.flush()
        await self.session.refresh(task)
        return task

    async def delete(self, task: Task) -> None:
        """Hard-delete a task row."""
        await self.session.delete(task)
        await self.session.flush()
