"""
Unit tests for Phase 1 Security Remediations:
- No password reset token leakage in forgot-password API responses.
- HTTP Security Headers & Content Security Policy (CSP) enforcement.
- DOM and chat sanitization validation.
"""
import pytest
from unittest.mock import patch
from starlette.requests import Request
from starlette.datastructures import Headers
from fastapi import Response

from app.db import init_db, SessionLocal
from app.auth import (
    forgot_password, reset_password, register_account,
    ForgotPasswordRequest, ResetPasswordRequest, RegisterRequest
)
from app.main import app, apply_security_headers
from fastapi.responses import JSONResponse


@pytest.fixture(scope="module", autouse=True)
def setup_db():
    init_db()


@pytest.fixture
def fake_request():
    return Request({
        "type": "http",
        "client": ("127.0.0.1", 54321),
        "headers": [(b"user-agent", b"Pytest-Security-Agent/1.0")],
        "server": ("localhost", 8000),
        "scheme": "http",
        "path": "/api/auth/forgot-password",
    })


def test_forgot_password_never_leaks_reset_token(fake_request):
    """VULN-01 verification: API response must not contain reset_token."""
    db = SessionLocal()
    try:
        # Register a test account
        reg = RegisterRequest(
            full_name="Security Auditor",
            username="sec_auditor",
            email="auditor@fourxchess.test",
            password="StrongPassword2026!",
            confirm_password="StrongPassword2026!"
        )
        register_account(reg, fake_request, authorization=None, db=db)

        # Call forgot-password
        with patch("app.auth.deliver_password_reset_token") as mock_deliver:
            res = forgot_password(ForgotPasswordRequest(email="auditor@fourxchess.test"), fake_request, db=db)
            assert res["success"] is True
            assert "reset_token" not in res or res.get("reset_token") is None
            assert "If an account with that email exists" in res["message"]
            assert mock_deliver.called
            email, token = mock_deliver.call_args[0]
            assert email == "auditor@fourxchess.test"
            assert isinstance(token, str) and len(token) > 16

        # Call forgot-password with unknown email (must have identical response to prevent user enumeration)
        with patch("app.auth.deliver_password_reset_token") as mock_deliver_unknown:
            res_unknown = forgot_password(ForgotPasswordRequest(email="unknown@doesnotexist.test"), fake_request, db=db)
            assert res_unknown["success"] is True
            assert "reset_token" not in res_unknown or res_unknown.get("reset_token") is None
            assert res_unknown["message"] == res["message"]
            assert not mock_deliver_unknown.called
    finally:
        db.close()


def test_security_headers_and_csp_enforcement():
    """VULN-04 & CSP verification: response headers must include nosniff, frame-options and CSP."""
    raw_response = JSONResponse(content={"status": "online"})
    res = apply_security_headers(raw_response)
    assert res.headers["X-Content-Type-Options"] == "nosniff"
    assert res.headers["X-Frame-Options"] == "SAMEORIGIN"
    assert res.headers["X-XSS-Protection"] == "1; mode=block"
    assert "Content-Security-Policy" in res.headers
    csp = res.headers["Content-Security-Policy"]
    assert "default-src 'self'" in csp
    assert "https://accounts.google.com" in csp
    assert "connect-src 'self' ws: wss: https://accounts.google.com" in csp
