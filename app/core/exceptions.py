"""Domain exceptions mapped to HTTP responses by global handlers."""

from __future__ import annotations


class AppError(Exception):
    """Base application error with machine-readable code."""

    code: str = "app_error"
    status_code: int = 500

    def __init__(self, detail: str = "Internal error") -> None:
        super().__init__(detail)
        self.detail = detail


class NotFoundError(AppError):
    """Resource not found (HTTP 404)."""

    code = "not_found"
    status_code = 404


class ConflictError(AppError):
    """Resource conflict, e.g. duplicate email (HTTP 409)."""

    code = "conflict"
    status_code = 409


class UnauthorizedError(AppError):
    """Authentication failure (HTTP 401)."""

    code = "unauthorized"
    status_code = 401


class ForbiddenError(AppError):
    """Authorization failure (HTTP 403)."""

    code = "forbidden"
    status_code = 403


class ValidationError(AppError):
    """Business-rule validation failure (HTTP 422)."""

    code = "validation_error"
    status_code = 422
