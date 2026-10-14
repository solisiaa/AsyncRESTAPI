"""Authentication business logic."""

from __future__ import annotations

import jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, UnauthorizedError
from app.core.security import (
    create_token_pair,
    decode_token,
    get_password_hash,
    verify_password,
)
from app.models.user import User
from app.repositories.user import UserRepository


class AuthService:
    """Registration, login and token refresh."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.users = UserRepository(session)

    async def register(self, email: str, username: str, password: str) -> User:
        """Create a new user, rejecting duplicates.

        Raises:
            ConflictError: If e-mail or username is taken.
        """
        if await self.users.get_by_email(email):
            raise ConflictError("Email already registered")
        if await self.users.get_by_username(username):
            raise ConflictError("Username already taken")
        user = await self.users.create(email, username, get_password_hash(password), role="user")
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def login(self, login: str, password: str) -> dict[str, str]:
        """Validate credentials and return a token pair.

        Raises:
            UnauthorizedError: On unknown login or bad password.
        """
        user = await self.users.get_by_login(login)
        if user is None or not user.is_active:
            raise UnauthorizedError("Invalid credentials")
        if not verify_password(password, user.hashed_password):
            raise UnauthorizedError("Invalid credentials")
        return create_token_pair(user.id, user.role)

    async def refresh(self, refresh_token: str) -> dict[str, str]:
        """Exchange a valid refresh token for a new pair.

        Raises:
            UnauthorizedError: If the token is invalid/expired.
        """
        try:
            payload = decode_token(refresh_token)
        except jwt.ExpiredSignatureError:
            raise UnauthorizedError("Refresh token expired") from None
        except jwt.InvalidTokenError:
            raise UnauthorizedError("Invalid refresh token") from None
        if payload.get("type") != "refresh":
            raise UnauthorizedError("Invalid token type")
        user_id = int(str(payload["sub"]))
        role = str(payload.get("role", "user"))
        user = await self.users.get_by_id(user_id)
        if user is None or not user.is_active:
            raise UnauthorizedError("User not found")
        # Use live role from DB to reflect promotions/demotions.
        return create_token_pair(user.id, user.role if user.role else role)
