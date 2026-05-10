"""In-memory per-IP sliding-window rate limit used as a FastAPI dependency.

This is intentionally minimal. It is not production-grade, multi-process,
or distributed; it is enough to keep a hackathon demo from being abused by
a single attacker hitting the watsonx-backed endpoints in a tight loop.
For production deploys move to slowapi/Redis or a reverse-proxy rate limit.

Usage:

    from .rate_limit import RateLimit
    nowcast_limit = RateLimit(max_calls=10, window_seconds=60)

    @app.post("/nowcast", dependencies=[Depends(nowcast_limit)])
    def nowcast_endpoint(...): ...
"""

from __future__ import annotations

import time
from collections import deque
from threading import Lock

from fastapi import HTTPException, Request


class RateLimit:
    """Sliding-window counter keyed by the requesting client IP."""

    def __init__(self, max_calls: int, window_seconds: float) -> None:
        if max_calls <= 0 or window_seconds <= 0:
            raise ValueError("max_calls and window_seconds must be positive")
        self.max_calls = max_calls
        self.window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = {}
        self._lock = Lock()

    def _client_ip(self, request: Request) -> str:
        # Honour X-Forwarded-For when nginx is in front of uvicorn. Take the
        # first hop because that is the original client.
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def __call__(self, request: Request) -> None:
        ip = self._client_ip(request)
        now = time.monotonic()
        cutoff = now - self.window_seconds
        with self._lock:
            bucket = self._hits.setdefault(ip, deque())
            while bucket and bucket[0] < cutoff:
                bucket.popleft()
            if len(bucket) >= self.max_calls:
                retry_after = max(1, int(self.window_seconds - (now - bucket[0])))
                raise HTTPException(
                    status_code=429,
                    detail={
                        "error": "rate_limited",
                        "message": (
                            f"Too many requests from {ip}. "
                            f"Limit: {self.max_calls}/{int(self.window_seconds)}s."
                        ),
                        "retry_after_seconds": retry_after,
                    },
                    headers={"Retry-After": str(retry_after)},
                )
            bucket.append(now)
