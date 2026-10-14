"""Current-user profile endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from app.core.deps import get_current_user
from app.schemas.user import UserRead

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserRead, summary="Get my profile")
async def get_me(user: Any = Depends(get_current_user)) -> UserRead:
    """Return the authenticated user's profile."""
    return UserRead.model_validate(user)
