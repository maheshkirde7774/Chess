"""
FOURX Authentication & Account Management
Implements registration, email/password login, Google OAuth, Facebook OAuth architecture,
password reset, and secure session management.
"""

import os
import re
import json
import secrets
import hashlib
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any
from urllib.request import Request as URLRequest, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Header, Request, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db import (
    get_db, PlayerProfileModel, ActiveSessionModel, get_utc_now
)
from app.profiles import (
    _profile_payload, _token_hash, profile_from_authorization,
    _authenticated_profile, _invalidate_leaderboard_cache
)
from app.room_limits import enforce_room_rate_limit

logger = logging.getLogger("fourx_auth")
router = APIRouter(prefix="/api/auth", tags=["auth"])

EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")
USERNAME_REGEX = re.compile(r"^[A-Za-z0-9_]{3,20}$")
PBKDF2_ITERATIONS = 600_000


# ==============================================================================
# Password Hashing & Verification (OWASP PBKDF2-HMAC-SHA256)
# ==============================================================================

def hash_password(password: str) -> str:
    """Hashes password with 600,000 PBKDF2-HMAC-SHA256 iterations and 16-byte random salt."""
    salt = secrets.token_bytes(16)
    hash_bytes = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${salt.hex()}${hash_bytes.hex()}"


def verify_password(password: str, stored_hash: Optional[str]) -> bool:
    """Verifies password against stored PBKDF2 hash using constant-time comparison."""
    if not stored_hash or not stored_hash.startswith("pbkdf2_sha256$"):
        return False
    try:
        parts = stored_hash.split("$")
        if len(parts) != 3:
            return False
        _, salt_hex, expected_hex = parts
        salt = bytes.fromhex(salt_hex)
        computed = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
        return secrets.compare_digest(computed.hex(), expected_hex)
    except Exception:
        return False


def validate_password_strength(password: str) -> None:
    """Enforces minimum 8 chars, at least one letter, and at least one digit."""
    if len(password) < 8:
        raise HTTPException(status_code=422, detail="Password must be at least 8 characters long")
    if len(password) > 100:
        raise HTTPException(status_code=422, detail="Password cannot exceed 100 characters")
    if not re.search(r"[A-Za-z]", password):
        raise HTTPException(status_code=422, detail="Password must contain at least one letter")
    if not re.search(r"\d", password):
        raise HTTPException(status_code=422, detail="Password must contain at least one number")


# ==============================================================================
# Pydantic Schemas
# ==============================================================================

class RegisterRequest(BaseModel):
    full_name: str = Field(..., min_length=1, max_length=100)
    username: str = Field(..., min_length=3, max_length=20)
    email: str = Field(..., min_length=5, max_length=254)
    password: str = Field(..., min_length=8, max_length=100)
    confirm_password: str = Field(..., min_length=8, max_length=100)


class LoginRequest(BaseModel):
    email_or_username: str = Field(..., min_length=3, max_length=254)
    password: str = Field(..., min_length=1, max_length=100)


class ForgotPasswordRequest(BaseModel):
    email: str = Field(..., min_length=5, max_length=254)


class ResetPasswordRequest(BaseModel):
    reset_token: str = Field(..., min_length=10, max_length=128)
    new_password: str = Field(..., min_length=8, max_length=100)
    confirm_password: str = Field(..., min_length=8, max_length=100)


class GoogleAuthRequest(BaseModel):
    credential: Optional[str] = None
    code: Optional[str] = None


class FacebookAuthRequest(BaseModel):
    access_token: Optional[str] = None
    code: Optional[str] = None


# ==============================================================================
# Session Helpers
# ==============================================================================

def create_user_session(profile: PlayerProfileModel, db: Session, request: Optional[Request] = None) -> str:
    """Issues a fresh 48-byte URL-safe bearer token, registers an active session, and updates profile."""
    raw_token = secrets.token_urlsafe(48)
    token_hash = _token_hash(raw_token)
    profile.token_hash = token_hash
    profile.last_login_at = datetime.now(timezone.utc)

    ip_address = request.client.host if request and request.client else None
    user_agent = request.headers.get("user-agent", "")[:255] if request else None

    session_rec = ActiveSessionModel(
        profile_id=profile.id,
        token_hash=token_hash,
        created_at=datetime.now(timezone.utc),
        last_used_at=datetime.now(timezone.utc),
        ip_address=ip_address,
        user_agent=user_agent,
        is_revoked=False,
    )
    db.add(session_rec)
    db.commit()
    return raw_token


# ==============================================================================
# Authentication Endpoints
# ==============================================================================

@router.post("/register")
def register_account(
    req: RegisterRequest,
    http_request: Request,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    """Creates a new FOURX user account or upgrades an existing anonymous device profile."""
    enforce_room_rate_limit(http_request, "auth-register", limit=15)

    full_name = req.full_name.strip()
    if not full_name:
        raise HTTPException(status_code=422, detail="Full name is required")

    username = req.username.strip()
    if not USERNAME_REGEX.match(username):
        raise HTTPException(
            status_code=422,
            detail="Username must be 3–20 characters using only letters, numbers, and underscores"
        )

    email = req.email.strip().lower()
    if not EMAIL_REGEX.match(email):
        raise HTTPException(status_code=422, detail="Please enter a valid email address")

    if req.password != req.confirm_password:
        raise HTTPException(status_code=422, detail="Passwords do not match")
    validate_password_strength(req.password)

    username_key = username.casefold()
    email_key = email

    # Check for duplicate email
    existing_email = db.query(PlayerProfileModel).filter(
        PlayerProfileModel.email_key == email_key,
        PlayerProfileModel.deleted_at.is_(None)
    ).first()
    if existing_email:
        raise HTTPException(status_code=409, detail="An account with this email already exists")

    # Check for duplicate username
    existing_user = db.query(PlayerProfileModel).filter(
        PlayerProfileModel.username_key == username_key,
        PlayerProfileModel.deleted_at.is_(None)
    ).first()

    current_profile = profile_from_authorization(authorization, db)

    # If current device profile exists and is anonymous, upgrade it!
    if current_profile and not current_profile.email and not existing_user:
        profile = current_profile
        profile.full_name = full_name
        profile.username = username
        profile.username_key = username_key
        profile.email = email
        profile.email_key = email_key
        profile.password_hash = hash_password(req.password)
        profile.auth_provider = "email"
    else:
        if existing_user:
            raise HTTPException(status_code=409, detail="This username is already taken")
        import uuid
        profile = PlayerProfileModel(
            id=str(uuid.uuid4()),
            full_name=full_name,
            username=username,
            username_key=username_key,
            email=email,
            email_key=email_key,
            password_hash=hash_password(req.password),
            auth_provider="email",
            avatar="knight",
            token_hash=_token_hash(secrets.token_urlsafe(48)),
            created_at=datetime.now(timezone.utc),
            xp=0,
            classic_rating=1200,
            four_player_rating=1200,
            timezone="UTC",
        )
        db.add(profile)

    db.commit()
    _invalidate_leaderboard_cache()

    raw_token = create_user_session(profile, db, http_request)
    return {
        "success": True,
        "access_token": raw_token,
        "profile": _profile_payload(db, profile),
        "message": "Welcome to FOURX! Your account has been created.",
    }


@router.post("/login")
def login_account(
    req: LoginRequest,
    http_request: Request,
    db: Session = Depends(get_db),
):
    """Authenticates using email or username and password."""
    enforce_room_rate_limit(http_request, "auth-login", limit=30)
    query = req.email_or_username.strip().lower()

    profile = db.query(PlayerProfileModel).filter(
        (PlayerProfileModel.email_key == query) | (PlayerProfileModel.username_key == query.casefold()),
        PlayerProfileModel.deleted_at.is_(None)
    ).first()

    if not profile or not profile.password_hash:
        raise HTTPException(status_code=401, detail="Invalid email/username or password")

    if not verify_password(req.password, profile.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email/username or password")

    if profile.is_suspended:
        raise HTTPException(status_code=403, detail="This account has been suspended")

    raw_token = create_user_session(profile, db, http_request)
    return {
        "success": True,
        "access_token": raw_token,
        "profile": _profile_payload(db, profile),
        "message": f"Welcome back, {profile.username}!",
    }


@router.post("/logout")
def logout_account(
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    """Invalidates the active session and rotates profile credentials."""
    profile = _authenticated_profile(authorization, db)
    token = authorization[7:]
    current_hash = _token_hash(token)

    # Invalidate session in active_sessions
    db.query(ActiveSessionModel).filter(
        ActiveSessionModel.token_hash == current_hash
    ).update({"is_revoked": True})

    # Rotate profile token_hash to permanently revoke this bearer token
    profile.token_hash = _token_hash(secrets.token_urlsafe(48))
    db.commit()

    return {"success": True, "message": "Logged out successfully"}


@router.post("/forgot-password")
def forgot_password(
    req: ForgotPasswordRequest,
    http_request: Request,
    db: Session = Depends(get_db),
):
    """Generates a secure password reset token for the account."""
    enforce_room_rate_limit(http_request, "auth-forgot", limit=10)
    email_key = req.email.strip().lower()

    profile = db.query(PlayerProfileModel).filter(
        PlayerProfileModel.email_key == email_key,
        PlayerProfileModel.deleted_at.is_(None)
    ).first()

    reset_token = None
    if profile:
        reset_token = secrets.token_urlsafe(32)
        profile.password_reset_token_hash = _token_hash(reset_token)
        profile.password_reset_expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
        db.commit()
        logger.info("Generated password reset token for %s", profile.email)

    return {
        "success": True,
        "message": "If an account with that email exists, password reset instructions have been generated.",
        "reset_token": reset_token,
    }


@router.post("/reset-password")
def reset_password(
    req: ResetPasswordRequest,
    http_request: Request,
    db: Session = Depends(get_db),
):
    """Resets user password with a verified, unexpired reset token."""
    enforce_room_rate_limit(http_request, "auth-reset", limit=10)

    if req.new_password != req.confirm_password:
        raise HTTPException(status_code=422, detail="Passwords do not match")
    validate_password_strength(req.new_password)

    token_hash = _token_hash(req.reset_token.strip())
    now = datetime.now(timezone.utc)

    profile = db.query(PlayerProfileModel).filter(
        PlayerProfileModel.password_reset_token_hash == token_hash,
        PlayerProfileModel.password_reset_expires_at > now,
        PlayerProfileModel.deleted_at.is_(None)
    ).first()

    if not profile:
        raise HTTPException(
            status_code=400,
            detail="Password reset code is invalid or has expired. Please request a new one."
        )

    profile.password_hash = hash_password(req.new_password)
    profile.password_reset_token_hash = None
    profile.password_reset_expires_at = None
    # Invalidate existing sessions
    profile.token_hash = _token_hash(secrets.token_urlsafe(48))
    db.commit()

    return {
        "success": True,
        "message": "Password reset successfully. Please log in with your new password.",
    }


@router.get("/status")
def auth_status(
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    """Returns the current authentication and registration status."""
    profile = profile_from_authorization(authorization, db)
    if not profile:
        return {
            "authenticated": False,
            "is_registered": False,
            "profile": None,
        }
    is_registered = bool(profile.email or profile.google_sub or profile.facebook_id)
    return {
        "authenticated": True,
        "is_registered": is_registered,
        "profile": _profile_payload(db, profile),
    }


# ==============================================================================
# Google OAuth 2.0 Integration
# ==============================================================================

@router.get("/google/url")
def google_oauth_url(http_request: Request):
    """Returns Google OAuth 2.0 authorization URL if credentials are configured."""
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    if not client_id:
        return {
            "configured": False,
            "message": "Google OAuth is pending credentials in Google Cloud Console. Set GOOGLE_CLIENT_ID.",
        }

    # Redirect URI
    base_url = str(http_request.base_url).rstrip("/")
    redirect_uri = f"{base_url}/api/auth/google/callback"

    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "online",
        "prompt": "select_account",
    }
    url = f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"
    return {"configured": True, "url": url}


@router.post("/google")
def google_token_login(
    req: GoogleAuthRequest,
    http_request: Request,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    """Authenticates via Google Identity Services ID token credential."""
    if not req.credential:
        raise HTTPException(status_code=422, detail="Google credential token is required")

    # Verify ID token with Google's tokeninfo endpoint
    try:
        url = f"https://oauth2.googleapis.com/tokeninfo?id_token={req.credential}"
        request = URLRequest(url, headers={"User-Agent": "FOURX-Chess/1.0"})
        with urlopen(request, timeout=8) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as e:
        logger.warning("Google token verification failed: %s", e)
        raise HTTPException(status_code=401, detail="Google token verification failed") from None

    google_sub = payload.get("sub")
    email = payload.get("email", "").lower()
    name = payload.get("name") or payload.get("given_name") or "Commander"

    if not google_sub or not email:
        raise HTTPException(status_code=400, detail="Invalid Google profile data")

    # Check for existing user by Google sub or email
    profile = db.query(PlayerProfileModel).filter(
        PlayerProfileModel.google_sub == google_sub,
        PlayerProfileModel.deleted_at.is_(None)
    ).first()

    if not profile:
        profile = db.query(PlayerProfileModel).filter(
            PlayerProfileModel.email_key == email,
            PlayerProfileModel.deleted_at.is_(None)
        ).first()
        if profile:
            profile.google_sub = google_sub
            if not profile.full_name:
                profile.full_name = name

    current_profile = profile_from_authorization(authorization, db)

    if not profile:
        if current_profile and not current_profile.email and not current_profile.google_sub:
            profile = current_profile
            profile.full_name = name
            profile.email = email
            profile.email_key = email
            profile.google_sub = google_sub
            profile.auth_provider = "google"
        else:
            import uuid
            suffix = secrets.randbelow(900_000) + 100_000
            username = f"Commander{suffix}"
            profile = PlayerProfileModel(
                id=str(uuid.uuid4()),
                full_name=name,
                username=username,
                username_key=username.casefold(),
                email=email,
                email_key=email,
                google_sub=google_sub,
                auth_provider="google",
                avatar="knight",
                token_hash=_token_hash(secrets.token_urlsafe(48)),
                created_at=datetime.now(timezone.utc),
                xp=0,
                classic_rating=1200,
                four_player_rating=1200,
                timezone="UTC",
            )
            db.add(profile)

    db.commit()
    raw_token = create_user_session(profile, db, http_request)
    return {
        "success": True,
        "access_token": raw_token,
        "profile": _profile_payload(db, profile),
        "message": f"Signed in with Google as {profile.username}!",
    }


@router.get("/google/callback")
def google_oauth_callback(
    code: Optional[str] = None,
    error: Optional[str] = None,
    http_request: Request = None,
    db: Session = Depends(get_db),
):
    """Handles Google OAuth authorization code redirect."""
    if error or not code:
        return RedirectResponse(url="/?auth_error=google_denied")

    client_id = os.getenv("GOOGLE_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
    if not client_id or not client_secret:
        return RedirectResponse(url="/?auth_error=google_not_configured")

    base_url = str(http_request.base_url).rstrip("/")
    redirect_uri = f"{base_url}/api/auth/google/callback"

    # Exchange code for tokens
    try:
        data = urlencode({
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }).encode("utf-8")
        token_req = URLRequest(
            "https://oauth2.googleapis.com/token",
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        with urlopen(token_req, timeout=10) as resp:
            token_data = json.loads(resp.read().decode("utf-8"))
        id_token = token_data.get("id_token")
        if not id_token:
            return RedirectResponse(url="/?auth_error=google_exchange_failed")

        # Verify ID token
        info_req = URLRequest(f"https://oauth2.googleapis.com/tokeninfo?id_token={id_token}")
        with urlopen(info_req, timeout=8) as resp:
            payload = json.loads(resp.read().decode("utf-8"))

        google_sub = payload.get("sub")
        email = payload.get("email", "").lower()
        name = payload.get("name") or "Commander"

        profile = db.query(PlayerProfileModel).filter(
            (PlayerProfileModel.google_sub == google_sub) | (PlayerProfileModel.email_key == email),
            PlayerProfileModel.deleted_at.is_(None)
        ).first()

        if not profile:
            import uuid
            suffix = secrets.randbelow(900_000) + 100_000
            username = f"Commander{suffix}"
            profile = PlayerProfileModel(
                id=str(uuid.uuid4()),
                full_name=name,
                username=username,
                username_key=username.casefold(),
                email=email,
                email_key=email,
                google_sub=google_sub,
                auth_provider="google",
                avatar="knight",
                token_hash=_token_hash(secrets.token_urlsafe(48)),
                created_at=datetime.now(timezone.utc),
            )
            db.add(profile)

        db.commit()
        raw_token = create_user_session(profile, db, http_request)
        return RedirectResponse(url=f"/?auth_token={raw_token}")
    except Exception as exc:
        logger.warning("Google callback error: %s", exc)
        return RedirectResponse(url="/?auth_error=google_failed")


# ==============================================================================
# Facebook OAuth Integration (Prepared for Credentials)
# ==============================================================================

@router.get("/facebook/url")
def facebook_oauth_url(http_request: Request):
    """Returns Facebook OAuth authorization URL if configured."""
    client_id = os.getenv("FACEBOOK_CLIENT_ID")
    if not client_id:
        return {
            "configured": False,
            "message": "Facebook Login is pending credentials. Set FACEBOOK_CLIENT_ID and FACEBOOK_CLIENT_SECRET.",
        }

    base_url = str(http_request.base_url).rstrip("/")
    redirect_uri = f"{base_url}/api/auth/facebook/callback"

    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": "email,public_profile",
        "response_type": "code",
    }
    url = f"https://www.facebook.com/v19.0/dialog/oauth?{urlencode(params)}"
    return {"configured": True, "url": url}


@router.post("/facebook")
def facebook_token_login(
    req: FacebookAuthRequest,
    http_request: Request,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    """Authenticates using Facebook access token from SDK."""
    client_id = os.getenv("FACEBOOK_CLIENT_ID")
    if not client_id and not req.access_token:
        raise HTTPException(
            status_code=503,
            detail="Facebook Login is pending configuration. Set FACEBOOK_CLIENT_ID and FACEBOOK_CLIENT_SECRET."
        )

    if not req.access_token:
        raise HTTPException(status_code=422, detail="Facebook access token is required")

    try:
        url = f"https://graph.facebook.com/v19.0/me?fields=id,name,email&access_token={req.access_token}"
        req_obj = URLRequest(url, headers={"User-Agent": "FOURX-Chess/1.0"})
        with urlopen(req_obj, timeout=8) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as e:
        logger.warning("Facebook token verification failed: %s", e)
        raise HTTPException(status_code=401, detail="Facebook authentication failed") from None

    fb_id = payload.get("id")
    email = payload.get("email", "").lower()
    name = payload.get("name") or "Commander"

    if not fb_id:
        raise HTTPException(status_code=400, detail="Invalid Facebook user data")

    profile = db.query(PlayerProfileModel).filter(
        PlayerProfileModel.facebook_id == fb_id,
        PlayerProfileModel.deleted_at.is_(None)
    ).first()

    if not profile and email:
        profile = db.query(PlayerProfileModel).filter(
            PlayerProfileModel.email_key == email,
            PlayerProfileModel.deleted_at.is_(None)
        ).first()
        if profile:
            profile.facebook_id = fb_id

    current_profile = profile_from_authorization(authorization, db)

    if not profile:
        if current_profile and not current_profile.email and not current_profile.facebook_id:
            profile = current_profile
            profile.full_name = name
            if email:
                profile.email = email
                profile.email_key = email
            profile.facebook_id = fb_id
            profile.auth_provider = "facebook"
        else:
            import uuid
            suffix = secrets.randbelow(900_000) + 100_000
            username = f"Commander{suffix}"
            profile = PlayerProfileModel(
                id=str(uuid.uuid4()),
                full_name=name,
                username=username,
                username_key=username.casefold(),
                email=email if email else None,
                email_key=email if email else None,
                facebook_id=fb_id,
                auth_provider="facebook",
                avatar="knight",
                token_hash=_token_hash(secrets.token_urlsafe(48)),
                created_at=datetime.now(timezone.utc),
            )
            db.add(profile)

    db.commit()
    raw_token = create_user_session(profile, db, http_request)
    return {
        "success": True,
        "access_token": raw_token,
        "profile": _profile_payload(db, profile),
        "message": f"Signed in with Facebook as {profile.username}!",
    }


@router.get("/facebook/callback")
def facebook_oauth_callback(
    code: Optional[str] = None,
    error: Optional[str] = None,
    http_request: Request = None,
    db: Session = Depends(get_db),
):
    """Handles Facebook OAuth authorization code callback."""
    if error or not code:
        return RedirectResponse(url="/?auth_error=facebook_denied")

    client_id = os.getenv("FACEBOOK_CLIENT_ID")
    client_secret = os.getenv("FACEBOOK_CLIENT_SECRET")
    if not client_id or not client_secret:
        return RedirectResponse(url="/?auth_error=facebook_not_configured")

    base_url = str(http_request.base_url).rstrip("/")
    redirect_uri = f"{base_url}/api/auth/facebook/callback"

    try:
        params = {
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "code": code,
        }
        url = f"https://graph.facebook.com/v19.0/oauth/access_token?{urlencode(params)}"
        with urlopen(URLRequest(url), timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        access_token = data.get("access_token")
        if not access_token:
            return RedirectResponse(url="/?auth_error=facebook_exchange_failed")

        # Fetch profile
        info_url = f"https://graph.facebook.com/v19.0/me?fields=id,name,email&access_token={access_token}"
        with urlopen(URLRequest(info_url), timeout=8) as resp:
            payload = json.loads(resp.read().decode("utf-8"))

        fb_id = payload.get("id")
        email = payload.get("email", "").lower()
        name = payload.get("name") or "Commander"

        profile = db.query(PlayerProfileModel).filter(
            (PlayerProfileModel.facebook_id == fb_id) | (PlayerProfileModel.email_key == email if email else False),
            PlayerProfileModel.deleted_at.is_(None)
        ).first()

        if not profile:
            import uuid
            suffix = secrets.randbelow(900_000) + 100_000
            username = f"Commander{suffix}"
            profile = PlayerProfileModel(
                id=str(uuid.uuid4()),
                full_name=name,
                username=username,
                username_key=username.casefold(),
                email=email if email else None,
                email_key=email if email else None,
                facebook_id=fb_id,
                auth_provider="facebook",
                avatar="knight",
                token_hash=_token_hash(secrets.token_urlsafe(48)),
                created_at=datetime.now(timezone.utc),
            )
            db.add(profile)

        db.commit()
        raw_token = create_user_session(profile, db, http_request)
        return RedirectResponse(url=f"/?auth_token={raw_token}")
    except Exception as exc:
        logger.warning("Facebook callback error: %s", exc)
        return RedirectResponse(url="/?auth_error=facebook_failed")
