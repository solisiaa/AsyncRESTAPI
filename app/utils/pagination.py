"""Pagination helpers."""

from __future__ import annotations

from typing import List, TypeVar

from app.schemas.common import Page

T = TypeVar("T")


def make_page(items: List[T], total: int, limit: int, offset: int) -> Page[T]:
    """Build a Page envelope from items + total.

    Args:
        items: Current page rows.
        total: Total matching rows.
        limit: Page size.
        offset: Rows skipped.

    Returns:
        Populated Page object.
    """
    return Page(items=items, total=total, limit=limit, offset=offset)
