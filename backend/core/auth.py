"""
VisionX Auth
Password hashing (bcrypt) and JWT access/refresh tokens.
"""

from __future__ import annotations

import time
from typing import Any, Dict

import bcrypt
import jwt

from backend.core.config import settings
from backend.core.exceptions import InvalidTokenError

ACCESS = "access"
REFRESH = "refresh"


def hash_password(password: str) -> str:
    # bcrypt only uses the first 72 bytes
    return bcrypt.hashpw(password.encode("utf-8")[:72], bcrypt.gensalt(settings.PASSWORD_BCRYPT_ROUNDS)).decode()


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8")[:72], password_hash.encode())
    except ValueError:
        return False


def _encode(user_id: str, email: str, typ: str, ttl_seconds: int) -> tuple[str, int]:
    now = int(time.time())
    exp = now + ttl_seconds
    token = jwt.encode(
        {"sub": user_id, "email": email, "typ": typ, "iss": settings.JWT_ISSUER, "iat": now, "exp": exp},
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )
    return token, exp


def create_session(user_id: str, email: str) -> Dict[str, Any]:
    """Issue an access + refresh token pair (same shape the frontend expects)."""
    access, expires_at = _encode(user_id, email, ACCESS, settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60)
    refresh, _ = _encode(user_id, email, REFRESH, settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS * 86400)
    return {
        "access_token": access,
        "refresh_token": refresh,
        "expires_at": expires_at,
        "token_type": "bearer",
    }


def decode_token(token: str, typ: str = ACCESS) -> Dict[str, Any]:
    """Validate a token and return its claims."""
    try:
        claims = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            issuer=settings.JWT_ISSUER,
        )
    except jwt.ExpiredSignatureError as exc:
        raise InvalidTokenError(message="Token expired") from exc
    except jwt.PyJWTError as exc:
        raise InvalidTokenError(message="Invalid token") from exc
    if claims.get("typ") != typ or not claims.get("sub"):
        raise InvalidTokenError(message="Invalid token")
    return claims
