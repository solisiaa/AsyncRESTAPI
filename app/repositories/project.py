"""Project data access with filtering + pagination."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional, Tuple

from sqlalchemy import func, select

from app.models.project import Project
from app.repositories.base import BaseRepository


class ProjectRepository(BaseRepository):
    """Data access for projects (soft-delete aware)."""

    async def create(
        self, name: str, description: Optional[str], status: str, owner_id: int
    ) -> Project:
        """Insert a project row."""
        project = Project(name=name, description=description, status=status, owner_id=owner_id)
        self.session.add(project)
        await self.session.flush()
        await self.session.refresh(project)
        return project

    async def get_by_id(self, project_id: int, include_deleted: bool = False) -> Optional[Project]:
        """Fetch one project by id."""
        stmt = select(Project).where(Project.id == project_id)
        if not include_deleted:
            stmt = stmt.where(Project.is_deleted.is_(False))
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def list(
        self,
        limit: int,
        offset: int,
        status: Optional[str] = None,
        owner_id: Optional[int] = None,
        created_after: Optional[datetime] = None,
    ) -> Tuple[list[Project], int]:
        """List projects with filters + total count.

        Returns:
            Tuple of (items, total).
        """
        filters: list[Any] = [Project.is_deleted.is_(False)]
        if status is not None:
            filters.append(Project.status == status)
        if owner_id is not None:
            filters.append(Project.owner_id == owner_id)
        if created_after is not None:
            filters.append(Project.created_at >= created_after)

        count_stmt = select(func.count()).select_from(Project).where(*filters)
        total_res = await self.session.execute(count_stmt)
        total = int(total_res.scalar_one())

        stmt = (
            select(Project).where(*filters).order_by(Project.id.desc()).limit(limit).offset(offset)
        )
        result = await self.session.execute(stmt)
        items = list(result.scalars().all())
        return items, total

    async def update(self, project: Project, **fields: object) -> Project:
        """Apply partial fields to a managed project instance."""
        for key, value in fields.items():
            if value is not None and hasattr(project, key):
                setattr(project, key, value)
        await self.session.flush()
        await self.session.refresh(project)
        return project

    async def soft_delete(self, project: Project) -> Project:
        """Mark a project as deleted."""
        project.is_deleted = True
        await self.session.flush()
        await self.session.refresh(project)
        return project
