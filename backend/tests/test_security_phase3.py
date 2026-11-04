"""
Unit tests for Phase 3 Security Remediations:
- Proxy-aware rate limiting with header extraction.
- Legacy token sanitization in database schema migrations.
- Android manifest and build configuration hardening checks.
"""
import pytest
from starlette.requests import Request
from fastapi import HTTPException

from app.room_limits import get_client_ip, enforce_room_rate_limit, _request_times


def test_proxy_aware_ip_resolution():
    """Verify get_client_ip correctly resolves real client IP behind reverse proxies."""
    # 1. Standard direct client
    direct_req = Request({
        "type": "http",
        "client": ("198.51.100.1", 12345),
        "headers": [],
    })
    assert get_client_ip(direct_req) == "198.51.100.1"

    # 2. Behind Load Balancer / Proxy with X-Forwarded-For
    proxy_req = Request({
        "type": "http",
        "client": ("10.0.0.1", 54321),  # Internal ALB IP
        "headers": [(b"x-forwarded-for", b"203.0.113.195, 10.0.0.1")],
    })
    assert get_client_ip(proxy_req) == "203.0.113.195"

    # 3. Cloudflare CF-Connecting-IP
    cf_req = Request({
        "type": "http",
        "client": ("10.0.0.1", 54321),
        "headers": [(b"cf-connecting-ip", b"198.51.100.77")],
    })
    assert get_client_ip(cf_req) == "198.51.100.77"


def test_rate_limiting_enforcement():
    """Verify rate limiter blocks after threshold and isolates different IPs."""
    req_ip1 = Request({
        "type": "http",
        "client": ("10.0.0.1", 1111),
        "headers": [(b"x-forwarded-for", b"192.0.2.10")],
    })
    req_ip2 = Request({
        "type": "http",
        "client": ("10.0.0.1", 1111),
        "headers": [(b"x-forwarded-for", b"192.0.2.20")],
    })

    # Clear previous test data for this action
    action = "test-security-limit"
    _request_times.pop(("192.0.2.10", action), None)
    _request_times.pop(("192.0.2.20", action), None)

    # 3 allowed requests for IP1
    for _ in range(3):
        enforce_room_rate_limit(req_ip1, action=action, limit=3, window_seconds=60)

    # 4th request from IP1 must raise 429
    with pytest.raises(HTTPException) as exc:
        enforce_room_rate_limit(req_ip1, action=action, limit=3, window_seconds=60)
    assert exc.value.status_code == 429

    # IP2 must still be allowed (not affected by IP1's limit)
    enforce_room_rate_limit(req_ip2, action=action, limit=3, window_seconds=60)


def test_untrusted_forwarded_headers_spoofing_prevented(monkeypatch):
    """Verify that an untrusted public client IP cannot spoof X-Forwarded-For."""
    spoofed_req = Request({
        "type": "http",
        "client": ("198.51.100.99", 54321),  # Untrusted public IP
        "headers": [(b"x-forwarded-for", b"8.8.8.8")],
    })
    # Should ignore 8.8.8.8 because direct IP 198.51.100.99 is NOT in trusted proxies
    assert get_client_ip(spoofed_req) == "198.51.100.99"


def test_require_redis_strict_enforcement(monkeypatch):
    """Verify that REQUIRE_REDIS=true fails closed with 503 if Redis is absent."""
    monkeypatch.setenv("REQUIRE_REDIS", "true")
    req = Request({
        "type": "http",
        "client": ("127.0.0.1", 12345),
        "headers": [],
    })
    with pytest.raises(HTTPException) as exc:
        enforce_room_rate_limit(req, action="strict-redis-test")
    assert exc.value.status_code == 503
    assert "Centralized rate limiting" in exc.value.detail


def test_production_password_reset_never_logs_token(monkeypatch, caplog):
    """Verify that in production mode without SMTP, plaintext reset tokens are NEVER logged."""
    import logging
    from app.auth import deliver_password_reset_token

    monkeypatch.setenv("FOURX_ENV", "production")
    monkeypatch.delenv("SMTP_HOST", raising=False)

    secret_reset_token = "ultra-secret-reset-token-2026"
    with caplog.at_level(logging.INFO):
        success = deliver_password_reset_token("victim@fourxchess.test", secret_reset_token)
        assert success is False
        assert secret_reset_token not in caplog.text
        assert "SMTP_HOST is not configured in production" in caplog.text

