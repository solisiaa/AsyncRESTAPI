"""Analytics response schemas (window-function results)."""

from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class TopAssigneeRow(BaseModel):
    """One row of the top-assignees ranking."""

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(description="User id")
    username: str = Field(description="Username")
    closed_tasks: int = Field(description="Closed tasks in period")
    rank: int = Field(description="RANK() over closed_tasks desc")
    avg_hours_to_close: Optional[float] = Field(
        default=None, description="Average hours from creation to close"
    )


class CumulativeClosedRow(BaseModel):
    """Daily closed + running total."""

    model_config = ConfigDict(from_attributes=True)

    day: date = Field(description="Calendar day")
    daily_closed: int = Field(description="Tasks closed that day")
    cumulative_closed: int = Field(description="SUM() OVER (ORDER BY day)")


class ProjectVelocityRow(BaseModel):
    """Closed tasks per project per week."""

    model_config = ConfigDict(from_attributes=True)

    project_id: int
    project_name: str
    week_start: date = Field(description="Start of ISO week")
    closed_tasks: int
    running_total: int = Field(description="SUM() OVER (PARTITION BY project_id ORDER BY week)")


class OverdueRow(BaseModel):
    """Overdue task with urgency rank."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    project_id: int
    assignee_id: Optional[int] = None
    due_date: Optional[date] = None
    days_overdue: int = Field(description="Days past due_date")
    urgency_rank: int = Field(description="DENSE_RANK() by urgency")
