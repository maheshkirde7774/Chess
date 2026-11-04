import os
import threading
import time
from collections import defaultdict, deque
from typing import Optional

from fastapi import HTTPException, Request

_lock = threading.Lock()
_request_times: dict[tuple[str, str], deque[float]] = defaultdict(deque)
_redis_client = None
_redis_checked = False
_last_cleanup = 0.0


def get_client_ip(request: Request) -> str:
    """Extracts client IP, trusting forwarded headers ONLY from configured reverse proxies."""
    direct_ip = request.client.host if request.client else "unknown"
    trusted_proxy_enabled = os.getenv("TRUSTED_PROXY_ENABLED", "true").lower() in ("true", "1", "yes")
    if not trusted_proxy_enabled:
        return direct_ip

    # Validate whether direct upstream connection originates from a trusted proxy
    trusted_proxies_raw = os.getenv(
        "TRUSTED_PROXIES",
        "127.0.0.1,::1,localhost,testclient,10.,172.16.,172.17.,172.18.,172.19.,172.20.,172.21.,172.22.,172.23.,172.24.,172.25.,172.26.,172.27.,172.28.,172.29.,172.30.,172.31.,192.168."
    )
    trusted_prefixes = tuple(p.strip() for p in trusted_proxies_raw.split(",") if p.strip())
    is_trusted = any(direct_ip == prefix or direct_ip.startswith(prefix) for prefix in trusted_prefixes)
    if not is_trusted:
        # Untrusted direct connection: reject spoofed client headers
        return direct_ip

    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        client_ip = forwarded.split(",")[0].strip()
        if client_ip:
            return client_ip
    cf_ip = request.headers.get("cf-connecting-ip")
    if cf_ip:
        return cf_ip.strip()

    return direct_ip


def _get_redis():
    global _redis_client, _redis_checked
    if not _redis_checked:
        _redis_checked = True
        redis_url = os.getenv("REDIS_URL")
        if redis_url:
            try:
                import redis
                _redis_client = redis.from_url(redis_url, socket_timeout=1.0)
            except Exception:
                _redis_client = None
    return _redis_client


def enforce_room_rate_limit(
    request: Request,
    action: str,
    limit: int = 30,
    window_seconds: int = 60,
) -> None:
    client_ip = get_client_ip(request)
    
    # Check if centralized Redis is available for multi-worker clusters
    require_redis = os.getenv("REQUIRE_REDIS", "").lower() in ("true", "1", "yes")
    redis = _get_redis()
    if redis is not None:
        try:
            key = f"fourx:ratelimit:{client_ip}:{action}"
            current = redis.incr(key)
            if current == 1:
                redis.expire(key, window_seconds)
            if current > limit:
                raise HTTPException(
                    status_code=429,
                    detail="Rate limit exceeded. Please try again shortly.",
                )
            return
        except HTTPException:
            raise
        except Exception:
            if require_redis:
                raise HTTPException(
                    status_code=503,
                    detail="Centralized rate limiting service is currently unavailable.",
                )
    elif require_redis:
        raise HTTPException(
            status_code=503,
            detail="Centralized rate limiting service is required in multi-worker production.",
        )

    # In-memory thread-safe sliding window rate limiting
    now = time.monotonic()
    key = (client_ip, action)
    with _lock:
        global _last_cleanup
        # Periodic cleanup of expired keys every 300 seconds
        if now - _last_cleanup > 300:
            _last_cleanup = now
            stale_keys = [k for k, q in _request_times.items() if not q or now - q[-1] >= window_seconds]
            for k in stale_keys:
                del _request_times[k]

        attempts = _request_times[key]
        while attempts and now - attempts[0] >= window_seconds:
            attempts.popleft()
        if len(attempts) >= limit:
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded. Please try again shortly.",
            )
        attempts.append(now)
