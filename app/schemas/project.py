"""Project Pydantic schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

ProjectStatus = Literal["active", "archived", "completed"]


class ProjectCreate(BaseModel):
    """Payload for creating a project."""

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=5000)
    status: ProjectStatus = Field(default="active")


class ProjectUpdate(BaseModel):
    """Partial update payload (all fields optional)."""

    model_config = ConfigDict(str_strip_whitespace=True)

    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=5000)
    status: Optional[ProjectStatus] = None


class ProjectRead(BaseModel):
    """Project representation."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: Optional[str] = None
    status: str
    owner_id: int
    is_deleted: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
