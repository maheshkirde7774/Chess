import pytest
import os
from unittest.mock import patch
from starlette.requests import Request
from fastapi import HTTPException

from app.db import init_db, SessionLocal, PlayerProfileModel, ActiveSessionModel
from app.auth import (
    hash_password, verify_password,
    register_account, login_account, logout_account,
    forgot_password, reset_password, auth_status,
    google_oauth_url, facebook_oauth_url, google_client_config,
    google_token_login, verify_google_id_token,
    RegisterRequest, LoginRequest, ForgotPasswordRequest, ResetPasswordRequest, GoogleAuthRequest
)
from app.profiles import _authenticated_profile


@pytest.fixture(scope="module", autouse=True)
def setup_db():
    init_db()


@pytest.fixture
def fake_request():
    return Request({
        "type": "http",
        "client": ("127.0.0.1", 54321),
        "headers": [(b"user-agent", b"Pytest-Auth-Agent/1.0")],
        "server": ("localhost", 8000),
        "scheme": "http",
        "path": "/api/auth",
    })


def test_password_hashing():
    pwd = "SecureMasterPassword2026!"
    hashed = hash_password(pwd)
    assert verify_password(pwd, hashed) is True
    assert verify_password("WrongPassword!", hashed) is False


def test_registration_and_login_lifecycle(fake_request):
    db = SessionLocal()
    try:
        # 1. Register a new account
        reg_req = RegisterRequest(
            full_name="Grandmaster Elena",
            username="elena_gm",
            email="elena@example.com",
            password="Password123!",
            confirm_password="Password123!"
        )
        reg_res = register_account(reg_req, fake_request, authorization=None, db=db)
        assert reg_res["success"] is True
        token = reg_res["access_token"]
        assert token
        assert reg_res["profile"]["username"] == "elena_gm"
        assert reg_res["profile"]["email"] == "elena@example.com"
        assert reg_res["profile"]["is_registered"] is True

        # 2. Duplicate registration check (email conflict)
        with pytest.raises(HTTPException) as exc_dup_email:
            register_account(reg_req, fake_request, authorization=None, db=db)
        assert exc_dup_email.value.status_code == 409

        # 3. Status check with active token
        status_res = auth_status(authorization=f"Bearer {token}", db=db)
        assert status_res["authenticated"] is True
        assert status_res["is_registered"] is True
        assert status_res["profile"]["email"] == "elena@example.com"

        # 4. Authenticated profile check
        prof = _authenticated_profile(f"Bearer {token}", db=db)
        assert prof.username == "elena_gm"
        assert prof.email == "elena@example.com"

        # 5. Login using Email
        login_req_email = LoginRequest(
            email_or_username="elena@example.com",
            password="Password123!"
        )
        login_res_email = login_account(login_req_email, fake_request, db=db)
        assert login_res_email["success"] is True
        token_after_login = login_res_email["access_token"]
        assert token_after_login

        # 6. Login using Username
        login_req_user = LoginRequest(
            email_or_username="elena_gm",
            password="Password123!"
        )
        login_res_user = login_account(login_req_user, fake_request, db=db)
        assert login_res_user["success"] is True

        # 7. Login with invalid password
        with pytest.raises(HTTPException) as exc_login_fail:
            login_account(LoginRequest(email_or_username="elena_gm", password="WrongPassword!"), fake_request, db=db)
        assert exc_login_fail.value.status_code == 401

        # 8. Logout
        logout_res = logout_account(authorization=f"Bearer {token_after_login}", db=db)
        assert logout_res["success"] is True

        # 9. Verify revoked session cannot be authenticated
        with pytest.raises(HTTPException) as exc_revoked:
            _authenticated_profile(f"Bearer {token_after_login}", db=db)
        assert exc_revoked.value.status_code == 401

    finally:
        db.close()


def test_forgot_and_reset_password_flow(fake_request):
    db = SessionLocal()
    try:
        # Register user
        reg_req = RegisterRequest(
            full_name="Alexander Pawn",
            username="alex_pawn",
            email="alex@example.com",
            password="InitialPass123!",
            confirm_password="InitialPass123!"
        )
        register_account(reg_req, fake_request, authorization=None, db=db)

        # Request reset token
        forgot_res = forgot_password(ForgotPasswordRequest(email="alex@example.com"), fake_request, db=db)
        assert forgot_res["success"] is True
        reset_token = forgot_res["reset_token"]
        assert reset_token is not None

        # Reset password
        reset_res = reset_password(
            ResetPasswordRequest(
                reset_token=reset_token,
                new_password="NewSecretPassword2026!",
                confirm_password="NewSecretPassword2026!"
            ),
            fake_request,
            db=db
        )
        assert reset_res["success"] is True

        # Verify old password fails
        with pytest.raises(HTTPException) as exc_old_pass:
            login_account(LoginRequest(email_or_username="alex@example.com", password="InitialPass123!"), fake_request, db=db)
        assert exc_old_pass.value.status_code == 401

        # Verify new password succeeds
        login_res = login_account(
            LoginRequest(email_or_username="alex@example.com", password="NewSecretPassword2026!"),
            fake_request,
            db=db
        )
        assert login_res["success"] is True
        assert login_res["access_token"] is not None

    finally:
        db.close()


def test_google_client_config():
    client_id = "822220189205-test.apps.googleusercontent.com"
    os.environ["GOOGLE_CLIENT_ID"] = client_id
    config = google_client_config()
    assert config["configured"] is True
    assert config["client_id"] == client_id
    # Ensure client secret is NEVER present
    assert "client_secret" not in config
    assert "GOOGLE_CLIENT_SECRET" not in str(config)


def test_verify_google_id_token_validation_rules():
    client_id = "822220189205-test.apps.googleusercontent.com"

    # 1. Invalid or malformed token string raises 401
    with pytest.raises(HTTPException) as exc_invalid:
        verify_google_id_token("malformed.jwt.token", client_id)
    assert exc_invalid.value.status_code == 401

    # 2. Issuer mismatch
    with patch("app.auth.id_token.verify_oauth2_token") as mock_verify:
        mock_verify.return_value = {
            "iss": "untrusted-issuer.com",
            "aud": client_id,
            "sub": "google-12345",
            "email": "test@gmail.com",
            "email_verified": True
        }
        with pytest.raises(HTTPException) as exc_iss:
            verify_google_id_token("mock-token", client_id)
        assert exc_iss.value.status_code == 401
        assert "issuer" in exc_iss.value.detail.lower()

    # 3. Audience mismatch
    with patch("app.auth.id_token.verify_oauth2_token") as mock_verify:
        mock_verify.return_value = {
            "iss": "https://accounts.google.com",
            "aud": "wrong-client-id.apps.googleusercontent.com",
            "sub": "google-12345",
            "email": "test@gmail.com",
            "email_verified": True
        }
        with pytest.raises(HTTPException) as exc_aud:
            verify_google_id_token("mock-token", client_id)
        assert exc_aud.value.status_code == 401
        assert "audience" in exc_aud.value.detail.lower() or "different" in exc_aud.value.detail.lower()

    # 4. Unverified email
    with patch("app.auth.id_token.verify_oauth2_token") as mock_verify:
        mock_verify.return_value = {
            "iss": "https://accounts.google.com",
            "aud": client_id,
            "sub": "google-12345",
            "email": "unverified@gmail.com",
            "email_verified": False
        }
        with pytest.raises(HTTPException) as exc_unver:
            verify_google_id_token("mock-token", client_id)
        assert exc_unver.value.status_code == 400
        assert "not been verified" in exc_unver.value.detail.lower()


def test_google_sign_in_new_user_flow(fake_request):
    db = SessionLocal()
    try:
        client_id = "822220189205-test.apps.googleusercontent.com"
        os.environ["GOOGLE_CLIENT_ID"] = client_id

        mock_payload = {
            "iss": "https://accounts.google.com",
            "aud": client_id,
            "sub": "google_sub_998877",
            "email": "grandmaster.magnus@gmail.com",
            "email_verified": True,
            "name": "Magnus Carlsen",
            "picture": "https://lh3.googleusercontent.com/photo.jpg"
        }

        with patch("app.auth.id_token.verify_oauth2_token", return_value=mock_payload):
            req = GoogleAuthRequest(credential="valid.google.id_token")
            res = google_token_login(req, fake_request, authorization=None, db=db)

            assert res["success"] is True
            assert "access_token" in res
            profile = res["profile"]
            assert profile["email"] == "grandmaster.magnus@gmail.com"
            assert profile["full_name"] == "Magnus Carlsen"
            assert profile["auth_provider"] == "google"
            assert profile["is_registered"] is True

            # Subsequent login with same google_sub finds existing profile
            res_repeat = google_token_login(req, fake_request, authorization=None, db=db)
            assert res_repeat["success"] is True
            assert res_repeat["profile"]["id"] == profile["id"]

    finally:
        db.close()


def test_google_sign_in_anonymous_profile_upgrade(fake_request):
    db = SessionLocal()
    try:
        # Create an anonymous guest profile with game stats
        import uuid, secrets
        from datetime import datetime, timezone
        from app.auth import create_user_session
        from app.profiles import _token_hash

        guest_token = secrets.token_urlsafe(48)
        guest_profile = PlayerProfileModel(
            id=str(uuid.uuid4()),
            username="GuestCommander101",
            username_key="guestcommander101",
            avatar="knight",
            token_hash=_token_hash(guest_token),
            created_at=datetime.now(timezone.utc),
            xp=250,
            classic_rating=1550,
            four_player_rating=1420,
            timezone="UTC"
        )
        db.add(guest_profile)
        db.commit()

        client_id = "822220189205-test.apps.googleusercontent.com"
        os.environ["GOOGLE_CLIENT_ID"] = client_id

        mock_payload = {
            "iss": "https://accounts.google.com",
            "aud": client_id,
            "sub": "google_sub_guest_upgrade_443",
            "email": "upgraded.commander@gmail.com",
            "email_verified": True,
            "name": "Hikaru Nakamura"
        }

        with patch("app.auth.id_token.verify_oauth2_token", return_value=mock_payload):
            req = GoogleAuthRequest(credential="guest.upgrade.token")
            # Pass guest token in authorization header to upgrade
            res = google_token_login(req, fake_request, authorization=f"Bearer {guest_token}", db=db)

            assert res["success"] is True
            upgraded = res["profile"]
            # Verify profile ID and stats are preserved!
            assert upgraded["id"] == guest_profile.id
            assert upgraded["email"] == "upgraded.commander@gmail.com"
            assert upgraded["ratings"]["classic"] == 1550
            assert upgraded["ratings"]["four_player"] == 1420
            assert upgraded["total_xp"] == 250
            assert upgraded["auth_provider"] == "google"

    finally:
        db.close()


def test_google_sign_in_prevents_insecure_linking(fake_request):
    db = SessionLocal()
    try:
        # Register a local password user
        local_user = RegisterRequest(
            full_name="Target User",
            username="target_user_sec",
            email="target@example.com",
            password="StrongPassword2026!",
            confirm_password="StrongPassword2026!"
        )
        register_account(local_user, fake_request, authorization=None, db=db)

        client_id = "822220189205-test.apps.googleusercontent.com"
        os.environ["GOOGLE_CLIENT_ID"] = client_id

        mock_payload = {
            "iss": "https://accounts.google.com",
            "aud": client_id,
            "sub": "unauthorized_google_sub_999",
            "email": "target@example.com",
            "email_verified": True,
            "name": "Attacker Trying Takeover"
        }

        with patch("app.auth.id_token.verify_oauth2_token", return_value=mock_payload):
            req = GoogleAuthRequest(credential="unauthorized.takeover.token")
            # Without being authenticated as target user, unauthenticated Google login matching this email must fail with 409
            with pytest.raises(HTTPException) as exc_takeover:
                google_token_login(req, fake_request, authorization=None, db=db)
            assert exc_takeover.value.status_code == 409
            assert "already exists with password" in exc_takeover.value.detail.lower()

    finally:
        db.close()


def test_oauth_url_generation(fake_request):
    # Google OAuth with env variable set
    os.environ["GOOGLE_CLIENT_ID"] = "test-client-id.apps.googleusercontent.com"
    g_res = google_oauth_url(fake_request)
    assert g_res["configured"] is True
    assert "https://accounts.google.com/o/oauth2/v2/auth" in g_res["url"]
    assert "test-client-id.apps.googleusercontent.com" in g_res["url"]

    # Facebook OAuth with env variable set
    os.environ["FACEBOOK_CLIENT_ID"] = "test-fb-app-id"
    fb_res = facebook_oauth_url(fake_request)
    assert fb_res["configured"] is True
    assert "https://www.facebook.com/v19.0/dialog/oauth" in fb_res["url"]
    assert "test-fb-app-id" in fb_res["url"]
