"""User data access."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import select

from app.models.user import User
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository):
    """CRUD + lookups for users."""

    async def get_by_id(self, user_id: int) -> Optional[User]:
        """Fetch a user by primary key."""
        result = await self.session.execute(select(User).where(User.id == user_id))
        return result.scalars().first()

    async def get_by_email(self, email: str) -> Optional[User]:
        """Fetch a user by e-mail."""
        result = await self.session.execute(select(User).where(User.email == email))
        return result.scalars().first()

    async def get_by_username(self, username: str) -> Optional[User]:
        """Fetch a user by username."""
        result = await self.session.execute(select(User).where(User.username == username))
        return result.scalars().first()

    async def get_by_login(self, login: str) -> Optional[User]:
        """Fetch by username OR e-mail (used at login)."""
        result = await self.session.execute(
            select(User).where((User.username == login) | (User.email == login))
        )
        return result.scalars().first()

    async def create(
        self, email: str, username: str, hashed_password: str, role: str = "user"
    ) -> User:
        """Persist a new user and return it."""
        user = User(email=email, username=username, hashed_password=hashed_password, role=role)
        self.session.add(user)
        await self.session.flush()
        await self.session.refresh(user)
        return user
