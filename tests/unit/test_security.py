"""Unit tests for password hashing and JWT helpers."""

from __future__ import annotations

from datetime import timedelta

import jwt
import pytest
from app.core.security import (
    create_access_token,
    create_refresh_token,
    create_token,
    decode_token,
    get_password_hash,
    verify_password,
)


def test_password_hash_and_verify() -> None:
    """Correct password verifies; wrong one does not."""
    hashed = get_password_hash("supersecret1")
    assert hashed != "supersecret1"
    assert verify_password("supersecret1", hashed) is True
    assert verify_password("wrong", hashed) is False


def test_access_token_roundtrip() -> None:
    """Access token decodes with expected claims."""
    tok = create_access_token("42", "manager")
    payload = decode_token(tok)
    assert payload["sub"] == "42"
    assert payload["role"] == "manager"
    assert payload["type"] == "access"


def test_refresh_token_type() -> None:
    """Refresh token carries type=refresh."""
    tok = create_refresh_token("7", "user")
    assert decode_token(tok)["type"] == "refresh"


def test_expired_token_raises() -> None:
    """Expired token raises ExpiredSignatureError on decode."""
    tok = create_token("1", "user", timedelta(seconds=-1), "access")
    with pytest.raises(jwt.ExpiredSignatureError):
        decode_token(tok)


def test_tampered_token_raises() -> None:
    """Modified signature raises InvalidTokenError."""
    tok = create_access_token("1", "user") + "tamper"
    with pytest.raises(jwt.InvalidTokenError):
        decode_token(tok)
