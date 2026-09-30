from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from fastapi import HTTPException, status

from app.config import settings

_password_hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4)
_dummy_hash = _password_hasher.hash("timing-only-password-value")


def normalize_email(email: str) -> str:
    return email.strip().casefold()


def hash_password(password: str) -> str:
    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    candidate = password_hash or _dummy_hash
    try:
        valid = _password_hasher.verify(candidate, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        valid = False
    return bool(password_hash) and valid


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def random_token() -> str:
    return secrets.token_urlsafe(48)


def _jwt_secret() -> str:
    return settings.jwt_secret.get_secret_value()


def create_access_token(user_id: str, email: str, role: str) -> tuple[str, int]:
    now = datetime.now(timezone.utc)
    seconds = settings.access_token_minutes * 60
    claims = {
        "sub": user_id,
        "email": email,
        "role": role,
        "type": "access",
        "jti": str(uuid.uuid4()),
        "iat": now,
        "nbf": now,
        "exp": now + timedelta(seconds=seconds),
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
    }
    return jwt.encode(claims, _jwt_secret(), algorithm="HS256"), seconds


def create_refresh_token(user_id: str, session_id: str) -> tuple[str, str, datetime]:
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(days=settings.refresh_token_days)
    jti = str(uuid.uuid4())
    claims = {
        "sub": user_id,
        "sid": session_id,
        "jti": jti,
        "type": "refresh",
        "iat": now,
        "nbf": now,
        "exp": expires_at,
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
    }
    return jwt.encode(claims, _jwt_secret(), algorithm="HS256"), jti, expires_at


def create_oauth_state() -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "type": "oauth_state",
            "jti": str(uuid.uuid4()),
            "iat": now,
            "exp": now + timedelta(minutes=10),
            "iss": settings.jwt_issuer,
            "aud": settings.jwt_audience,
        },
        _jwt_secret(),
        algorithm="HS256",
    )


def decode_token(token: str, expected_type: str) -> dict[str, Any]:
    try:
        claims = jwt.decode(
            token,
            _jwt_secret(),
            algorithms=["HS256"],
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
            options={"require": ["sub", "jti", "exp", "iat", "type"]},
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token") from exc
    if claims.get("type") != expected_type:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")
    return claims


def decode_oauth_state(token: str) -> None:
    try:
        claims = jwt.decode(
            token,
            _jwt_secret(),
            algorithms=["HS256"],
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
            options={"require": ["jti", "exp", "iat", "type"]},
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=400, detail="Invalid OAuth state") from exc
    if claims.get("type") != "oauth_state":
        raise HTTPException(status_code=400, detail="Invalid OAuth state")
