import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

_lock = threading.Lock()
_request_times: dict[tuple[str, str], deque[float]] = defaultdict(deque)


def enforce_room_rate_limit(
    request: Request,
    action: str,
    limit: int = 30,
    window_seconds: int = 60,
) -> None:
    now = time.monotonic()
    key = (request.client.host if request.client else "unknown", action)
    with _lock:
        attempts = _request_times[key]
        while attempts and now - attempts[0] >= window_seconds:
            attempts.popleft()
        if len(attempts) >= limit:
            raise HTTPException(
                status_code=429,
                detail="Too many room requests. Please try again shortly.",
            )
        attempts.append(now)
