"""
app/api/auth.py
===============
Authentication API endpoints — register, login (issue JWT), and token refresh.

All endpoints are public (no auth dependency required).

Endpoints:
    POST /api/v1/auth/register  — create a new user account
    POST /api/v1/auth/login     — authenticate and receive access + refresh tokens
    POST /api/v1/auth/refresh   — exchange a refresh token for a new access token
    GET  /api/v1/auth/me        — return the current user info (requires auth)
"""

import hashlib
import os
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import text

from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_current_user,
    hash_password,
    verify_password,
)
from app.services.database import DatabaseService

router = APIRouter(prefix="/api/v1/auth", tags=["authentication"])

# ─────────────────────────────────────────────────────────────────────────────
# Pydantic models
# ─────────────────────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50, description="Unique username")
    email: str = Field(..., description="User email address")
    password: str = Field(..., min_length=8, description="Plain-text password (min 8 chars)")
    full_name: str = Field("", description="Optional full name")


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Access token TTL in seconds")


class RefreshRequest(BaseModel):
    refresh_token: str


class UserInfo(BaseModel):
    username: str
    email: str
    full_name: str


# ─────────────────────────────────────────────────────────────────────────────
# Helper — get or create the user_accounts table
# ─────────────────────────────────────────────────────────────────────────────

_ACCOUNTS_DDL = """
CREATE TABLE IF NOT EXISTS user_accounts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    username    TEXT UNIQUE NOT NULL,
    email       TEXT UNIQUE NOT NULL,
    full_name   TEXT NOT NULL DEFAULT '',
    hashed_pw   TEXT NOT NULL,
    is_active   INTEGER NOT NULL DEFAULT 1,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


def _get_db() -> DatabaseService:
    db = DatabaseService()
    # Ensure table exists (idempotent)
    try:
        with db.engine.connect() as conn:
            conn.execute(text(_ACCOUNTS_DDL))
            conn.commit()
    except Exception:
        pass
    return db


def _fetch_user(db: DatabaseService, username: str) -> dict | None:
    """Return user row dict or None if not found."""
    rows = db.execute_query(
        "SELECT id, username, email, full_name, hashed_pw, is_active FROM user_accounts WHERE username = :u",
        {"u": username},
    )
    if not rows:
        return None
    row = rows[0]
    keys = ["id", "username", "email", "full_name", "hashed_pw", "is_active"]
    return dict(zip(keys, row))


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/register", response_model=UserInfo, status_code=status.HTTP_201_CREATED)
async def register(req: RegisterRequest):
    """
    Register a new user account.

    - **username**: 3–50 character unique handle
    - **email**: Valid email address (uniqueness enforced)
    - **password**: Minimum 8 characters, stored as bcrypt hash
    """
    db = _get_db()

    # Check username uniqueness
    existing = _fetch_user(db, req.username)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Username '{req.username}' is already taken",
        )

    hashed = hash_password(req.password)
    try:
        db.execute_query(
            "INSERT INTO user_accounts (username, email, full_name, hashed_pw) VALUES (:u, :e, :f, :h)",
            {"u": req.username, "e": req.email, "f": req.full_name, "h": hashed},
        )
    except Exception as exc:
        if "UNIQUE" in str(exc).upper():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email address is already registered",
            )
        raise HTTPException(status_code=500, detail=f"Registration failed: {exc}")

    return UserInfo(username=req.username, email=req.email, full_name=req.full_name)


@router.post("/login", response_model=TokenResponse)
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    """
    Authenticate with username + password and receive JWT tokens.

    Accepts standard OAuth2 form body: ``username`` and ``password`` fields.

    Returns:
        access_token  — short-lived bearer token (default 60 min)
        refresh_token — long-lived token for silent renewal (7 days)
    """
    from app.core.config import settings

    db = _get_db()
    user = _fetch_user(db, form_data.username)

    if not user or not verify_password(form_data.password, user["hashed_pw"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user["is_active"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated",
        )

    token_data = {"sub": user["username"], "email": user["email"]}
    access_token = create_access_token(token_data)
    refresh_token = create_refresh_token(token_data)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(req: RefreshRequest):
    """
    Exchange a valid refresh token for a new access + refresh token pair.
    """
    from app.core.config import settings

    payload = decode_token(req.refresh_token)
    username = payload.get("sub")
    if not username:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    token_data = {k: v for k, v in payload.items() if k not in ("exp", "iat")}
    access_token = create_access_token(token_data)
    new_refresh = create_refresh_token(token_data)

    return TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.get("/me", response_model=UserInfo)
async def get_me(current_user: dict = Depends(get_current_user)):
    """
    Return the current authenticated user info.

    Requires a valid Bearer token in the Authorization header.
    """
    db = _get_db()
    user = _fetch_user(db, current_user["username"])
    if not user:
        raise HTTPException(status_code=404, detail="User account not found")
    return UserInfo(username=user["username"], email=user["email"], full_name=user["full_name"])


# ─────────────────────────────────────────────────────────────────────────────
# Google OAuth 2.0 / Sign-in with Google Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/google/login", tags=["authentication"])
async def google_login():
    """
    Initiate 'Sign in with Google' flow.
    Returns the Google OAuth 2.0 authorization URL to redirect the user to Google login.
    """
    from app.services.google_sheets_sync import get_google_oauth_auth_url
    from app.core.config import settings

    redirect_uri = settings.GOOGLE_REDIRECT_URI
    auth_url = get_google_oauth_auth_url(redirect_uri=redirect_uri)
    return {
        "status": "ok",
        "auth_url": auth_url,
        "redirect_uri": redirect_uri,
        "message": "Redirect user to auth_url to complete Google Sign-In"
    }


@router.get("/google/callback", tags=["authentication"])
async def google_callback(code: str, state: str = "insightos_gsheets"):
    """
    OAuth 2.0 Callback handler for Google Sign-In.
    Receives authorization code from Google, exchanges it for access & refresh tokens,
    and stores tokens securely for automated retail data sync.
    """
    from app.services.google_sheets_sync import handle_google_oauth_callback, sync_google_sheets
    from app.core.config import settings

    try:
        token_data = handle_google_oauth_callback(
            auth_code=code,
            redirect_uri=settings.GOOGLE_REDIRECT_URI
        )

        # Trigger immediate sync if sheet ID is configured
        sync_result = None
        if settings.GOOGLE_SHEET_ID:
            sync_result = sync_google_sheets()

        return {
            "status": "SUCCESS",
            "message": "Google Account connected successfully and token stored securely.",
            "token_created_at": token_data.get("created_at"),
            "sync_result": sync_result
        }
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Google OAuth callback failed: {exc}"
        )

