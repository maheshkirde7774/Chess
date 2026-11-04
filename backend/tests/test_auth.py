import pytest
import os
from starlette.requests import Request
from fastapi import HTTPException

from app.db import init_db, SessionLocal, PlayerProfileModel, ActiveSessionModel
from app.auth import (
    hash_password, verify_password,
    register_account, login_account, logout_account,
    forgot_password, reset_password, auth_status,
    google_oauth_url, facebook_oauth_url,
    RegisterRequest, LoginRequest, ForgotPasswordRequest, ResetPasswordRequest
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
