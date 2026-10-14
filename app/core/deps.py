"""Shared FastAPI dependencies: sessions, current user, RBAC."""

from __future__ import annotations

from typing import Annotated, Any, Callable, List, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.redis import get_redis_client
from app.core.security import decode_token


async def get_redis_dep() -> Any:
    """Return the shared Redis client (overridable in tests)."""
    return get_redis_client()


bearer_scheme = HTTPBearer(auto_error=False)

SessionDep = Annotated[AsyncSession, Depends(get_db_session)]


async def get_current_user_id(
    credentials: Annotated[Optional[HTTPAuthorizationCredentials], Depends(bearer_scheme)],
) -> int:
    """Extract user id from Bearer JWT or raise 401."""
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        payload = decode_token(credentials.credentials)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token"
        ) from None
    if payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")
    try:
        return int(str(payload["sub"]))
    except (KeyError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload"
        ) from None


async def get_current_user_role(
    credentials: Annotated[Optional[HTTPAuthorizationCredentials], Depends(bearer_scheme)],
) -> str:
    """Extract role claim from Bearer JWT or raise 401."""
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        payload = decode_token(credentials.credentials)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token"
        ) from None
    role = str(payload.get("role", "user"))
    return role


async def get_current_user(
    session: SessionDep,
    user_id: Annotated[int, Depends(get_current_user_id)],
) -> Any:
    """Load the current User ORM object or raise 401."""
    from app.repositories.user import UserRepository

    repo = UserRepository(session)
    user = await repo.get_by_id(user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


def require_role(*allowed: str) -> Callable[..., object]:
    """Dependency factory enforcing RBAC roles.

    Args:
        allowed: Roles permitted to access the endpoint.

    Returns:
        FastAPI dependency raising 403 when role is not allowed.
    """

    async def _checker(
        role: Annotated[str, Depends(get_current_user_role)],
    ) -> str:
        if role not in allowed:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
        return role

    # FastAPI needs a callable; return inner function.
    return _checker


async def get_pagination_params(limit: int = 20, offset: int = 0) -> dict[str, int]:
    """Parse and clamp pagination query params."""
    limit = max(1, min(limit, 100))
    offset = max(0, offset)
    return {"limit": limit, "offset": offset}


# Re-export commonly used role sets.
ADMIN_ONLY: List[str] = ["admin"]
MANAGER_ROLES: List[str] = ["admin", "manager"]

CurrentUserIdDep = Annotated[int, Depends(get_current_user_id)]
CurrentUserDep = Annotated[Any, Depends(get_current_user)]
