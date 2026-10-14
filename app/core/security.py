"""JWT tokens and password hashing helpers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import jwt
from passlib.context import CryptContext

from app.core.config import get_settings

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def get_password_hash(password: str) -> str:
    """Hash a plain password with bcrypt.

    Args:
        password: Plain-text password.

    Returns:
        Bcrypt hash string.
    """
    return str(_pwd_context.hash(password))


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against its bcrypt hash.

    Args:
        plain_password: Candidate password.
        hashed_password: Stored bcrypt hash.

    Returns:
        True if the password matches.
    """
    return bool(_pwd_context.verify(plain_password, hashed_password))


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def create_token(subject: str, role: str, expires_delta: timedelta, token_type: str) -> str:
    """Create a signed JWT.

    Args:
        subject: Token subject (user id as string).
        role: User role claim.
        expires_delta: Lifetime of the token.
        token_type: Either ``access`` or ``refresh``.

    Returns:
        Encoded JWT string.
    """
    settings = get_settings()
    now = _utcnow()
    payload: Dict[str, Any] = {
        "sub": subject,
        "role": role,
        "type": token_type,
        "iat": int(now.timestamp()),
        "exp": int((now + expires_delta).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_access_token(subject: str, role: str) -> str:
    """Create a short-lived access JWT."""
    settings = get_settings()
    return create_token(subject, role, timedelta(seconds=settings.jwt_access_ttl), "access")


def create_refresh_token(subject: str, role: str) -> str:
    """Create a long-lived refresh JWT."""
    settings = get_settings()
    return create_token(subject, role, timedelta(seconds=settings.jwt_refresh_ttl), "refresh")


def decode_token(token: str) -> Dict[str, Any]:
    """Decode and validate a JWT, raising on expiry/invalidity.

    Args:
        token: Encoded JWT.

    Returns:
        Decoded payload dict.

    Raises:
        jwt.ExpiredSignatureError: If the token is expired.
        jwt.InvalidTokenError: If the token is invalid.
    """
    settings = get_settings()
    decoded: Dict[str, Any] = jwt.decode(
        token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
    )
    return decoded


def create_token_pair(user_id: int, role: str) -> Dict[str, str]:
    """Create access + refresh token pair for a user."""
    sub = str(user_id)
    return {
        "access_token": create_access_token(sub, role),
        "refresh_token": create_refresh_token(sub, role),
        "token_type": "bearer",
    }


def decode_refresh_token(token: str) -> Optional[Dict[str, Any]]:
    """Decode a refresh token, returning None if it is not a refresh token."""
    try:
        payload = decode_token(token)
    except jwt.InvalidTokenError:
        return None
    if payload.get("type") != "refresh":
        return None
    return payload
