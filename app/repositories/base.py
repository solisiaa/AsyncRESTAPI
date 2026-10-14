"""Base repository holding an AsyncSession."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession


class BaseRepository:
    """Base class for data-access repositories (no HTTP knowledge)."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
