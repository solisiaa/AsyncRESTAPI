"""Shared paginated envelope and error schemas."""

from __future__ import annotations

from typing import Generic, List, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    """Generic paginated response."""

    model_config = ConfigDict(from_attributes=True)

    items: List[T] = Field(description="Page items")
    total: int = Field(description="Total matching rows")
    limit: int = Field(description="Page size")
    offset: int = Field(description="Rows skipped")


class ErrorResponse(BaseModel):
    """Unified error payload."""

    model_config = ConfigDict(from_attributes=True)

    detail: str = Field(description="Human-readable message")
    code: str = Field(description="Machine-readable code")


class HealthResponse(BaseModel):
    """Liveness probe response."""

    model_config = ConfigDict(from_attributes=True)

    status: str = "ok"
    version: str = "0.1.0"
