"""FastAPI application entrypoint: routers, lifespan, error handlers, logging."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Dict, cast

import structlog
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.exceptions import AppError
from app.schemas.common import HealthResponse

settings = get_settings()

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(
        getattr(logging, settings.log_level.upper(), logging.INFO)
    ),
)
logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup/shutdown: warm Redis client, close on exit."""
    logger.info("app_startup", env=settings.app_env)
    try:
        from app.core.redis import get_redis_client

        client = get_redis_client()
        await cast(Any, client.ping())
        logger.info("redis_connected")
    except Exception as exc:
        logger.warning("redis_unavailable", error=str(exc))
    yield
    try:
        from app.core.redis import close_redis

        await close_redis()
    except Exception:
        pass
    logger.info("app_shutdown")


def create_app() -> FastAPI:
    """Application factory used by uvicorn and tests."""
    app = FastAPI(
        title="Task Analytics API",
        description="Async REST API for tasks + SQL analytics (Jira/Trello-like)",
        version="0.1.0",
        lifespan=lifespan,
    )

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code, content={"detail": exc.detail, "code": exc.code}
        )

    @app.exception_handler(HTTPException)
    async def http_error_handler(request: Request, exc: HTTPException) -> JSONResponse:
        detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        return JSONResponse(
            status_code=exc.status_code, content={"detail": detail, "code": "http_error"}
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422, content={"detail": str(exc), "code": "validation_error"}
        )

    @app.get("/health", response_model=HealthResponse, tags=["health"], summary="Liveness probe")
    async def health() -> Dict[str, Any]:
        return {"status": "ok", "version": "0.1.0"}

    app.include_router(api_router)
    return app


app = create_app()
