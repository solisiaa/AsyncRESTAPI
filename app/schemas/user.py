"""User-related Pydantic schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserRegister(BaseModel):
    """Registration payload."""

    model_config = ConfigDict(str_strip_whitespace=True)

    email: EmailStr = Field(description="Unique e-mail")
    username: str = Field(min_length=3, max_length=100, description="Unique username")
    password: str = Field(min_length=8, max_length=128, description="Plain password")


class UserLogin(BaseModel):
    """Login payload (username or e-mail + password)."""

    model_config = ConfigDict(str_strip_whitespace=True)

    username: str = Field(description="Username or e-mail")
    password: str = Field(description="Plain password")


class TokenPair(BaseModel):
    """Access + refresh token pair."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    """Refresh-token payload."""

    refresh_token: str = Field(description="Valid refresh JWT")


class UserRead(BaseModel):
    """Public user representation."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    username: str
    role: str
    is_active: bool
    created_at: Optional[datetime] = None
