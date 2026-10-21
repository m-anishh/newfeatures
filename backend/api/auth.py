"""
Authentication Routes - REST endpoints for authentication.
Users live in the PostgreSQL `users` table; sessions are JWTs from backend.core.auth.
"""

from __future__ import annotations

import re
import uuid
from typing import Optional, Dict, Any
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from backend.core.auth import REFRESH, create_session, decode_token, hash_password, verify_password
from backend.core.logging import get_logger
from backend.core.exceptions import ValidationError, AuthenticationError, ConflictError, InvalidTokenError
from backend.api.dependencies import verify_access_token

logger = get_logger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# Request/Response Models
class RegisterRequest(BaseModel):
    email: str
    password: str
    full_name: str


class LoginRequest(BaseModel):
    email: str
    password: str


class ResetPasswordRequest(BaseModel):
    email: str


class UpdateProfileRequest(BaseModel):
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None
    username: Optional[str] = None
    bio: Optional[str] = None


class AuthResponse(BaseModel):
    success: bool
    message: str
    user: Optional[dict] = None
    session: Optional[dict] = None
    profile: Optional[dict] = None


def get_db():
    """Get database client (lazy import to avoid circular dependencies)."""
    try:
        from backend.database.db_client import get_db_client
        return get_db_client()
    except Exception as e:
        logger.error(f"Failed to get database client: {e}")
        raise HTTPException(status_code=500, detail="Authentication service unavailable")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _find_user_by_email(db, email: str) -> Optional[Dict[str, Any]]:
    # Emails are stored lower-cased, so an exact match is case-insensitive
    result = db.table("users").select("*").eq("email", email.strip().lower()).limit(1).execute()
    return result.data[0] if result.data else None


def _get_profile(db, user_id: str) -> Optional[Dict[str, Any]]:
    result = db.table("profiles").select("*").eq("id", user_id).limit(1).execute()
    if not result.data:
        return None
    p = result.data[0]
    return {
        "id": p.get("id"),
        "email": p.get("email"),
        "full_name": p.get("full_name"),
        "username": p.get("username"),
        "avatar_url": p.get("avatar_url"),
        "bio": p.get("bio"),
        "created_at": p.get("created_at"),
    }


def _user_payload(user: Dict[str, Any], full_name: Optional[str]) -> Dict[str, Any]:
    return {
        "id": user["id"],
        "email": user["email"],
        "full_name": full_name,
        "created_at": user.get("created_at"),
        "user_metadata": {"full_name": full_name},
    }


def _bearer(request: Request) -> str:
    auth_header = request.headers.get("authorization", "")
    if not auth_header.startswith("Bearer "):
        raise AuthenticationError(message="Authentication required")
    return auth_header[7:]


@router.post("/register", response_model=AuthResponse)
async def register(request: RegisterRequest):
    """Register a new user. The user signs in separately afterwards."""
    email = request.email.strip().lower()
    if not _EMAIL_RE.match(email):
        raise ValidationError(message="Please enter a valid email address")
    if len(request.password) < 8:
        raise ValidationError(message="Password must be at least 8 characters")

    db = get_db()
    try:
        if _find_user_by_email(db, email):
            raise ConflictError(message="An account with this email already exists")

        now = _now()
        user = db.table("users").insert({
            "id": str(uuid.uuid4()),
            "email": email,
            "password_hash": hash_password(request.password),
            "last_sign_in_at": now,
            "created_at": now,
            "updated_at": now,
        }).execute().data[0]

        db.table("profiles").upsert({
            "id": user["id"],
            "email": email,
            "full_name": request.full_name,
            "role": "user",
            "created_at": now,
            "updated_at": now,
        }).execute()
        logger.info(f"[Register] User created {user['id']}")

        return AuthResponse(
            success=True,
            message="Account created. Please sign in.",
            user=_user_payload(user, request.full_name),
        )

    except (ValidationError, ConflictError):
        raise
    except Exception as e:
        logger.error(f"Registration failed: {e}")
        raise ValidationError(message="Registration failed. Please try again.")


@router.post("/login", response_model=AuthResponse)
async def login(request: LoginRequest):
    """Login with email and password."""
    db = get_db()
    try:
        user = _find_user_by_email(db, request.email)
        if user is None or not verify_password(request.password, user["password_hash"]):
            raise AuthenticationError(message="Invalid email or password")

        db.table("users").update({"last_sign_in_at": _now()}).eq("id", user["id"]).execute()

        profile_data = None
        try:
            profile_data = _get_profile(db, user["id"])
        except Exception as e:
            logger.warning(f"Profile fetch failed (non-critical): {e}")
        full_name = profile_data.get("full_name") if profile_data else None

        return AuthResponse(
            success=True,
            message="Login successful",
            user=_user_payload(user, full_name),
            session=create_session(user["id"], user["email"]),
            profile=profile_data,
        )

    except AuthenticationError:
        raise
    except Exception as e:
        logger.error(f"Login failed: {e}")
        raise HTTPException(status_code=500, detail="Login failed. Please try again.")


@router.post("/logout", response_model=AuthResponse)
async def logout(request: Request):
    """Logout. Tokens are stateless JWTs, so the client simply discards them."""
    return AuthResponse(success=True, message="Logout successful")


@router.get("/me", response_model=AuthResponse)
async def get_current_user_info(request: Request):
    """Get current user information from the access token."""
    payload = verify_access_token(_bearer(request))
    db = get_db()
    try:
        result = db.table("users").select("id,email,created_at").eq("id", payload["sub"]).limit(1).execute()
        if not result.data:
            raise AuthenticationError(message="User no longer exists")
        user = result.data[0]

        profile_data = None
        try:
            profile_data = _get_profile(db, user["id"])
        except Exception as e:
            logger.warning(f"Profile fetch failed (non-critical): {e}")
        full_name = profile_data.get("full_name") if profile_data else None

        return AuthResponse(
            success=True,
            message="User info retrieved",
            user=_user_payload(user, full_name),
            profile=profile_data,
        )

    except AuthenticationError:
        raise
    except Exception as e:
        logger.error(f"Get current user failed: {e}")
        raise HTTPException(status_code=401, detail="Failed to get user information")


@router.put("/profile", response_model=AuthResponse)
async def update_profile(request: Request, data: UpdateProfileRequest):
    """Update user profile."""
    payload = verify_access_token(_bearer(request))
    user_id = payload["sub"]
    user_email = payload.get("email", "")
    db = get_db()
    try:
        update_data: Dict[str, Any] = {"id": user_id, "email": user_email or "", "updated_at": _now()}
        for field in ("full_name", "avatar_url", "username", "bio"):
            value = getattr(data, field)
            if value is not None:
                update_data[field] = value

        db.table("profiles").upsert(update_data).execute()

        return AuthResponse(
            success=True,
            message="Profile updated successfully",
            profile=_get_profile(db, user_id),
        )

    except AuthenticationError:
        raise
    except Exception as e:
        logger.error(f"Profile update failed: {e}")
        raise HTTPException(status_code=400, detail="Failed to update profile")


@router.post("/reset-password", response_model=AuthResponse)
async def reset_password(request: ResetPasswordRequest):
    """Request password reset email.

    No email provider is configured yet (e.g. AWS SES), so this only logs the request.
    The response is the same whether or not the email exists.
    """
    logger.warning(f"Password reset requested for {request.email}, but no email service is configured")
    return AuthResponse(
        success=True,
        message="If the email exists, a password reset link has been sent.",
    )


@router.post("/refresh-token")
async def refresh_token(request: Request):
    """Refresh access token using refresh token."""
    body = await request.json()
    token = body.get("refresh_token")
    if not token:
        raise ValidationError(message="Refresh token required")

    try:
        claims = decode_token(token, REFRESH)
    except InvalidTokenError:
        raise AuthenticationError(message="Invalid refresh token")

    db = get_db()
    result = db.table("users").select("id,email").eq("id", claims["sub"]).limit(1).execute()
    if not result.data:
        raise AuthenticationError(message="Invalid refresh token")
    user = result.data[0]

    return {
        "success": True,
        "session": create_session(user["id"], user["email"]),
    }
