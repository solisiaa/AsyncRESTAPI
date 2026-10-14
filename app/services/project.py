"""Project business logic + Redis caching."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import redis.asyncio as redis_async
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import hash_params, invalidate_project_cache, project_key
from app.core.exceptions import NotFoundError
from app.models.project import Project
from app.repositories.project import ProjectRepository


def _parse_dt(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def _project_to_dict(p: Project) -> Dict[str, Any]:
    return {
        "id": p.id,
        "name": p.name,
        "description": p.description,
        "status": p.status,
        "owner_id": p.owner_id,
        "is_deleted": p.is_deleted,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }


def _project_from_dict(data: Dict[str, Any]) -> Project:
    p = Project(
        name=str(data.get("name", "")),
        description=data.get("description"),
        status=str(data.get("status", "active")),
        owner_id=int(data.get("owner_id", 0)),
    )
    p.id = int(data.get("id", 0))
    is_deleted = data.get("is_deleted", False)
    p.is_deleted = bool(is_deleted)
    created = _parse_dt(data.get("created_at"))
    updated = _parse_dt(data.get("updated_at"))
    if created is not None:
        p.created_at = created
    if updated is not None:
        p.updated_at = updated
    return p


class ProjectService:
    """Project CRUD with caching and soft-delete."""

    LIST_TTL = 30
    DETAIL_TTL = 60

    def __init__(self, session: AsyncSession, redis: redis_async.Redis | None = None) -> None:
        self.session = session
        self.repo = ProjectRepository(session)
        self.redis = redis

    async def create(
        self, name: str, description: Optional[str], status: str, owner_id: int
    ) -> Project:
        """Create a project and invalidate list caches."""
        project = await self.repo.create(name, description, status, owner_id)
        await self.session.commit()
        await self.session.refresh(project)
        if self.redis is not None:
            try:
                async for key in self.redis.scan_iter(match="projects:list:*"):
                    await self.redis.delete(key)
            except Exception:
                pass
        return project

    async def list(
        self,
        limit: int,
        offset: int,
        status: Optional[str] = None,
        owner_id: Optional[int] = None,
        created_after: Optional[datetime] = None,
    ) -> Tuple[List[Project], int]:
        """List projects, served from Redis when available (TTL 30s)."""
        cache_key: Optional[str] = None
        if self.redis is not None:
            params = {
                "limit": limit,
                "offset": offset,
                "status": status,
                "owner_id": owner_id,
                "created_after": created_after.isoformat() if created_after else None,
            }
            cache_key = f"projects:list:{hash_params(params)}"
            try:
                cached = await self.redis.get(cache_key)
                if cached is not None:
                    data = json.loads(cached)
                    if isinstance(data, dict) and "items" in data and "total" in data:
                        items = [_project_from_dict(d) for d in data["items"]]
                        return items, int(data["total"])
            except Exception:
                pass
        items, total = await self.repo.list(limit, offset, status, owner_id, created_after)
        if self.redis is not None and cache_key is not None:
            try:
                payload = json.dumps(
                    {"items": [_project_to_dict(p) for p in items], "total": total}
                )
                await self.redis.set(cache_key, payload, ex=self.LIST_TTL)
            except Exception:
                pass
        return items, total

    async def get_by_id(self, project_id: int) -> Project:
        """Get project details, cached in Redis (TTL 60s)."""
        if self.redis is not None:
            try:
                cached = await self.redis.get(project_key(project_id))
                if cached is not None:
                    data = json.loads(cached)
                    if isinstance(data, dict) and data.get("id") == project_id:
                        return _project_from_dict(data)
            except Exception:
                pass
        project = await self.repo.get_by_id(project_id)
        if project is None:
            raise NotFoundError("Project not found")
        if self.redis is not None:
            try:
                await self.redis.set(
                    project_key(project_id),
                    json.dumps(_project_to_dict(project)),
                    ex=self.DETAIL_TTL,
                )
            except Exception:
                pass
        return project

    async def update(self, project_id: int, fields: dict[str, object]) -> Project:
        """Partially update a project and invalidate caches."""
        project = await self.repo.get_by_id(project_id)
        if project is None:
            raise NotFoundError("Project not found")
        clean = {k: v for k, v in fields.items() if v is not None}
        updated = await self.repo.update(project, **clean)
        await self.session.commit()
        await self.session.refresh(updated)
        await invalidate_project_cache(project_id)
        # invalidate_project_cache uses the global client; also clear injected client.
        if self.redis is not None:
            try:
                await self.redis.delete(project_key(project_id))
                async for key in self.redis.scan_iter(match="projects:list:*"):
                    await self.redis.delete(key)
            except Exception:
                pass
        return updated

    async def delete(self, project_id: int) -> None:
        """Soft-delete a project and invalidate caches."""
        project = await self.repo.get_by_id(project_id)
        if project is None:
            raise NotFoundError("Project not found")
        await self.repo.soft_delete(project)
        await self.session.commit()
        await invalidate_project_cache(project_id)
        if self.redis is not None:
            try:
                await self.redis.delete(project_key(project_id))
                async for key in self.redis.scan_iter(match="projects:list:*"):
                    await self.redis.delete(key)
            except Exception:
                pass
