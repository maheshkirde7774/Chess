"""
Unit tests for Phase 2 Security Remediations:
- WebSocket connection limits per IP.
- Handshake flooding prevention.
- Verification of required dependencies in requirements.txt.
"""
import pytest
from app.ws_manager import ConnectionManager


def test_ws_connection_limits_per_ip():
    """VULN-04 verification: Per-IP limits must prevent connection exhaustion."""
    mgr = ConnectionManager()
    mgr.max_total_connections_per_ip = 5
    mgr.max_pending_handshakes_per_ip = 3
    test_ip = "198.51.100.42"

    # 1. IP is initially allowed
    assert mgr.can_accept_ip(test_ip) is True

    # 2. Track 3 pending handshakes -> should hit pending limit
    mgr.track_pending(test_ip)
    mgr.track_pending(test_ip)
    mgr.track_pending(test_ip)
    assert mgr.can_accept_ip(test_ip) is False

    # 3. Release pending handshakes -> should be accepted again
    mgr.release_pending(test_ip)
    assert mgr.can_accept_ip(test_ip) is True

    # 4. Fill active connections up to threshold
    mgr.track_active(test_ip)
    mgr.track_active(test_ip)
    mgr.track_active(test_ip)
    mgr.track_active(test_ip)
    mgr.track_active(test_ip)
    assert mgr.can_accept_ip(test_ip) is False

    # 5. Release active connection -> should allow connection again
    mgr.release_active(test_ip)
    assert mgr.can_accept_ip(test_ip) is True


def test_required_production_dependencies():
    """Verify that google-auth and python-dotenv are declared in requirements.txt."""
    with open("backend/requirements.txt", "r", encoding="utf-8") as f:
        reqs = f.read()
    assert "google-auth" in reqs, "google-auth must be declared in backend/requirements.txt"
    assert "python-dotenv" in reqs, "python-dotenv must be declared in backend/requirements.txt"
    assert "requests" in reqs, "requests must be declared in backend/requirements.txt"

    # Verify import works directly
    import google.oauth2.id_token
    import dotenv
    import requests
    assert google.oauth2.id_token is not None
    assert dotenv is not None
    assert requests is not None

