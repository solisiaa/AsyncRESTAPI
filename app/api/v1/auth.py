"""Auth endpoints: register / login / refresh."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.exceptions import AppError
from app.schemas.user import RefreshRequest, TokenPair, UserLogin, UserRead, UserRegister
from app.services.auth import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


def get_auth_service(session: AsyncSession = Depends(get_db_session)) -> AuthService:
    """Build AuthService per request."""
    return AuthService(session)


@router.post(
    "/register",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
)
async def register(payload: UserRegister, svc: AuthService = Depends(get_auth_service)) -> UserRead:
    """Register with e-mail, username and password."""
    try:
        user = await svc.register(payload.email, payload.username, payload.password)
    except AppError as exc:
        from fastapi import HTTPException

        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from None
    return UserRead.model_validate(user)


@router.post("/login", response_model=TokenPair, summary="Login and get tokens")
async def login(payload: UserLogin, svc: AuthService = Depends(get_auth_service)) -> TokenPair:
    """Authenticate and receive access + refresh JWTs."""
    try:
        pair = await svc.login(payload.username, payload.password)
    except AppError as exc:
        from fastapi import HTTPException

        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from None
    return TokenPair(**pair)


@router.post("/refresh", response_model=TokenPair, summary="Refresh access token")
async def refresh(
    payload: RefreshRequest, svc: AuthService = Depends(get_auth_service)
) -> TokenPair:
    """Exchange a refresh token for a new pair."""
    try:
        pair = await svc.refresh(payload.refresh_token)
    except AppError as exc:
        from fastapi import HTTPException

        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from None
    return TokenPair(**pair)
