"""
VisionX API Dependencies
FastAPI dependency injection for authentication, database sessions, and more.
"""

from __future__ import annotations

from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.auth import decode_token
from backend.core.exceptions import AuthenticationError, InvalidTokenError
from backend.database.session import get_session
from backend.core.logging import set_correlation_id, get_logger

logger = get_logger(__name__)

# Bearer token scheme
bearer_scheme = HTTPBearer(auto_error=False)


def verify_access_token(token: str) -> dict:
    """Verify a VisionX access token (JWT) and return the authenticated user data.

    Tokens are issued by backend.core.auth.
    """
    try:
        claims = decode_token(token)
    except InvalidTokenError as exc:
        logger.warning("Token verification failed: %s", exc)
        raise

    return {
        "sub": claims["sub"],
        "email": claims.get("email", "") or "",
        "user": {"id": claims["sub"], "email": claims.get("email", "")},
    }


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> str:
    """
    FastAPI dependency that extracts and validates the current user from the VisionX JWT.
    
    Returns:
        User ID string
        
    Raises:
        HTTPException 401 if authentication fails
    """
    if credentials is None:
        raise AuthenticationError(message="Authentication required")

    token = credentials.credentials
    payload = verify_access_token(token)
    user_id = payload["sub"]
    set_correlation_id(user_id)
    return user_id


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> Optional[str]:
    """
    FastAPI dependency that optionally extracts the current user.
    Returns None if no valid token is provided.
    """
    if credentials is None:
        return None
    
    try:
        return await get_current_user(credentials)
    except Exception:
        return None


async def get_db_session() -> AsyncSession:
    """
    FastAPI dependency that yields an async database session.
    """
    async for session in get_session():
        yield session
