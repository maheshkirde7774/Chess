"""
FOURX Authentication & Account Management
Implements registration, email/password login, Google OAuth,
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

from dotenv import load_dotenv
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

load_dotenv()
_root_env = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))
if os.path.exists(_root_env):
    load_dotenv(_root_env)

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


def deliver_password_reset_token(email: str, reset_token: str) -> bool:
    """Delivers password reset instructions via secure SMTP email or secure server logs in development."""
    smtp_host = os.getenv("SMTP_HOST")
    if smtp_host:
        try:
            import smtplib
            import ssl
            from email.mime.multipart import MIMEMultipart
            from email.mime.text import MIMEText

            smtp_port = int(os.getenv("SMTP_PORT", "587"))
            smtp_user = os.getenv("SMTP_USER", "")
            smtp_pass = os.getenv("SMTP_PASSWORD", "")
            smtp_from = os.getenv("SMTP_FROM", "noreply@fourxchess.com")
            use_tls = os.getenv("SMTP_USE_TLS", "true").lower() in ("true", "1", "yes")

            msg = MIMEMultipart("alternative")
            msg["Subject"] = "FOURX Chess - Password Reset Verification Code"
            msg["From"] = smtp_from
            msg["To"] = email

            text_content = (
                f"Hello Commander,\n\n"
                f"You requested to reset your password for FOURX Chess.\n"
                f"Your password reset verification code is:\n\n"
                f"    {reset_token}\n\n"
                f"This code will expire in 1 hour. If you did not request this reset, you can safely ignore this email.\n\n"
                f"The FOURX Chess Team"
            )
            html_content = (
                f"<div style='font-family:sans-serif;background:#0d0d12;color:#f0f0f5;padding:24px;border-radius:8px;max-width:500px;'>"
                f"<h2 style='color:#ffd700;margin-top:0;'>FOURX Chess</h2>"
                f"<p>You requested to reset your password. Use the verification code below to set your new password:</p>"
                f"<div style='background:#1a1a24;border:1px solid #333348;border-radius:6px;padding:16px;text-align:center;margin:20px 0;'>"
                f"<span style='font-size:22px;letter-spacing:2px;font-family:monospace;color:#00ffff;font-weight:bold;'>{reset_token}</span>"
                f"</div>"
                f"<p style='color:#a0a0b8;font-size:13px;'>This code will expire in 1 hour. If you did not request this, please ignore this email.</p>"
                f"</div>"
            )

            msg.attach(MIMEText(text_content, "plain"))
            msg.attach(MIMEText(html_content, "html"))

            ssl_context = ssl.create_default_context()
            if smtp_port == 465:
                with smtplib.SMTP_SSL(smtp_host, smtp_port, context=ssl_context, timeout=10) as server:
                    if smtp_user and smtp_pass:
                        server.login(smtp_user, smtp_pass)
                    server.sendmail(smtp_from, [email], msg.as_string())
            else:
                with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as server:
                    if use_tls:
                        server.starttls(context=ssl_context)
                    if smtp_user and smtp_pass:
                        server.login(smtp_user, smtp_pass)
                    server.sendmail(smtp_from, [email], msg.as_string())

            logger.info("Successfully sent password reset email to %s", email)
            return True
        except Exception as e:
            logger.error("Failed to send password reset email to %s: %s", email, e)
            return False
    else:
        is_prod = os.getenv("FOURX_ENV", "").lower() == "production" or os.getenv("ENVIRONMENT", "").lower() == "production"
        if is_prod:
            logger.error("SMTP_HOST is not configured in production. Password reset email cannot be dispatched.")
            return False
        # Development / test mode fallback: log only in non-production environments
        logger.info("[AUTH DELIVERY DEV MODE] Password reset code for %s: %s", email, reset_token)
        return True


@router.post("/forgot-password")
def forgot_password(
    req: ForgotPasswordRequest,
    http_request: Request,
    db: Session = Depends(get_db),
):
    """Generates a secure password reset token for the account and delivers it out-of-band."""
    enforce_room_rate_limit(http_request, "auth-forgot", limit=10)
    email_key = req.email.strip().lower()

    profile = db.query(PlayerProfileModel).filter(
        PlayerProfileModel.email_key == email_key,
        PlayerProfileModel.deleted_at.is_(None)
    ).first()

    if profile and profile.email:
        reset_token = secrets.token_urlsafe(32)
        profile.password_reset_token_hash = _token_hash(reset_token)
        profile.password_reset_expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
        db.commit()
        deliver_password_reset_token(profile.email, reset_token)
        logger.info("Dispatched password reset token delivery for %s", profile.email)

    # Standard security practice: return constant message without disclosing user existence or token
    return {
        "success": True,
        "message": "If an account with that email exists, password reset instructions have been sent to your email address.",
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
    is_registered = bool(profile.email or profile.google_sub or getattr(profile, "facebook_id", None))
    return {
        "authenticated": True,
        "is_registered": is_registered,
        "profile": _profile_payload(db, profile),
    }


# ==============================================================================
# Google OAuth 2.0 Integration
# ==============================================================================

def verify_google_id_token(credential: str, client_id: str) -> Dict[str, Any]:
    """
    Verifies the Google ID token signature, issuer, audience, and expiry
    using Google's official google-auth library.
    Never trusts profile claims directly from the client.
    """
    try:
        request = google_requests.Request()
        id_info = id_token.verify_oauth2_token(credential, request, client_id)
    except Exception as exc:
        logger.warning("Google ID token verification failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired Google credential token."
        ) from None

    # Verify issuer
    issuer = id_info.get("iss")
    if issuer not in ["accounts.google.com", "https://accounts.google.com"]:
        logger.warning("Untrusted Google token issuer: %s", issuer)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Untrusted Google token issuer."
        )

    # Verify audience matches our Client ID
    aud = id_info.get("aud")
    if aud != client_id:
        logger.warning("Google token audience mismatch: expected %s, got %s", client_id, aud)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Google credential was issued for a different client ID."
        )

    # Verify email is present and verified by Google
    email = id_info.get("email")
    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Google account does not provide an email address."
        )

    if not id_info.get("email_verified", False):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Google email address has not been verified."
        )

    sub = id_info.get("sub")
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Google account does not provide a valid subject identifier."
        )

    name = id_info.get("name") or id_info.get("given_name") or email.split("@")[0] or "Commander"
    return {
        "sub": str(sub),
        "email": email.strip().lower(),
        "name": str(name).strip(),
        "picture": id_info.get("picture"),
    }


@router.get("/google/config")
def google_client_config():
    """
    Returns public Google OAuth Client ID for frontend Google Identity Services (GIS).
    Client Secret is never exposed.
    """
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    return {
        "configured": bool(client_id),
        "client_id": client_id,
    }


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


def link_or_create_google_user(
    token_claims: Dict[str, Any],
    authorization: Optional[str],
    db: Session,
    http_request: Optional[Request] = None,
) -> tuple[str, PlayerProfileModel]:
    """
    Core account linking logic for verified Google identity claims.
    Preserves anonymous device profiles and existing game stats, ratings, and achievements.
    Prevents insecure email-based account takeovers.
    """
    google_sub = token_claims["sub"]
    email = token_claims["email"]
    name = token_claims["name"]

    # 1. Look up existing profile already bound to this Google Subject ID
    profile = db.query(PlayerProfileModel).filter(
        PlayerProfileModel.google_sub == google_sub,
        PlayerProfileModel.deleted_at.is_(None)
    ).first()

    current_profile = profile_from_authorization(authorization, db)

    if profile:
        # Existing verified Google user found!
        if not profile.full_name and name:
            profile.full_name = name
    else:
        # Check if an existing profile has this email_key
        existing_email_user = db.query(PlayerProfileModel).filter(
            PlayerProfileModel.email_key == email,
            PlayerProfileModel.deleted_at.is_(None)
        ).first()

        if existing_email_user:
            # Prevent insecure account linking.
            # If the user is currently authenticated as this exact user, they can link Google.
            # Otherwise, reject to prevent taking over password-based accounts.
            if current_profile and current_profile.id == existing_email_user.id:
                profile = current_profile
                profile.google_sub = google_sub
                profile.auth_provider = "google"
                if not profile.full_name:
                    profile.full_name = name
            else:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="An account with this email already exists with password authentication. Please sign in with your email and password first, then link Google from your profile."
                )
        elif current_profile and not current_profile.email and not current_profile.google_sub:
            # Seamless upgrade of existing anonymous device profile!
            # Preserves user's current game rating, stats, XP, and achievements.
            profile = current_profile
            profile.full_name = name
            profile.email = email
            profile.email_key = email
            profile.google_sub = google_sub
            profile.auth_provider = "google"
        else:
            # Create a brand new FOURX profile for this Google user
            import uuid
            base_user = re.sub(r"[^A-Za-z0-9_]", "", name.replace(" ", "_"))
            if len(base_user) < 3:
                base_user = re.sub(r"[^A-Za-z0-9_]", "", email.split("@")[0])
            if len(base_user) < 3:
                base_user = "Commander"
            base_user = base_user[:14]

            candidate_username = base_user
            suffix_num = 1
            while db.query(PlayerProfileModel.id).filter(
                PlayerProfileModel.username_key == candidate_username.casefold(),
                PlayerProfileModel.deleted_at.is_(None)
            ).first():
                candidate_username = f"{base_user}_{secrets.randbelow(9000) + 1000}"
                suffix_num += 1
                if suffix_num > 20:
                    candidate_username = f"Commander{secrets.randbelow(900000) + 100000}"
                    break

            profile = PlayerProfileModel(
                id=str(uuid.uuid4()),
                full_name=name,
                username=candidate_username,
                username_key=candidate_username.casefold(),
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
    _invalidate_leaderboard_cache()
    raw_token = create_user_session(profile, db, http_request)
    return raw_token, profile


@router.post("/google")
def google_token_login(
    req: GoogleAuthRequest,
    http_request: Request,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    """
    Authenticates via Google Identity Services (GIS) ID token credential.
    Verifies signature, issuer, audience, and expiry cryptographically.
    Links authenticated Google account to user profile securely while preventing
    insecure email-based account takeovers and preserving anonymous guest profile progress.
    """
    enforce_room_rate_limit(http_request, "auth-google", limit=30)
    if not req.credential:
        raise HTTPException(status_code=422, detail="Google credential token is required")

    client_id = os.getenv("GOOGLE_CLIENT_ID")
    if not client_id:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google Sign-In is not configured on the server. Set GOOGLE_CLIENT_ID."
        )

    # Cryptographically verify token claims using Google's official library
    token_claims = verify_google_id_token(req.credential, client_id)
    raw_token, profile = link_or_create_google_user(token_claims, authorization, db, http_request)

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
    """Handles Google OAuth authorization code redirect (e.g. system browser / Android WebView fallback)."""
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
        id_token_str = token_data.get("id_token")
        if not id_token_str:
            return RedirectResponse(url="/?auth_error=google_exchange_failed")

        # Cryptographically verify token claims
        token_claims = verify_google_id_token(id_token_str, client_id)
        raw_token, profile = link_or_create_google_user(token_claims, None, db, http_request)

        return RedirectResponse(url=f"/?auth_token={raw_token}")
    except HTTPException as http_exc:
        return RedirectResponse(url=f"/?auth_error={urlencode({'e': http_exc.detail})}")
    except Exception as exc:
        logger.warning("Google callback error: %s", exc)
        return RedirectResponse(url="/?auth_error=google_failed")
