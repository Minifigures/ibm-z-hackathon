"""In-memory per-IP sliding-window rate limit, exposed as a FastAPI dependency.

Minimal, single-process, intentionally not distributed; enough to keep a hackathon
demo from being abused by a tight loop on the watsonx-backed endpoints.
For production deploys move to slowapi/Redis or a reverse-proxy rate limit.

Usage:

    from .rate_limit import rate_limit
    nowcast_limiter = rate_limit(max_calls=10, window_seconds=60)

    @app.post("/nowcast", dependencies=[Depends(nowcast_limiter)])
    def nowcast_endpoint(...): ...
"""

import time
from collections import deque
from threading import Lock
from typing import Callable

from fastapi import HTTPException
from starlette.requests import Request


def _client_ip(request: Request) -> str:
    # Honour X-Forwarded-For when nginx fronts uvicorn. Take the first hop
    # because that is the original client.
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def rate_limit(max_calls: int, window_seconds: float) -> Callable[[Request], None]:
    """Build a FastAPI dependency that enforces a sliding-window per-IP cap.

    The returned function takes the FastAPI Request and either returns None
    (allowed) or raises HTTPException(429) with a Retry-After header.

    A function-factory closure is used instead of a class with __call__ because
    FastAPI's `typing.get_type_hints` introspection treats annotated parameters
    on instance __call__ as query parameters rather than auto-resolving Request.
    A plain function with `request: Request` is reliably auto-injected.
    """
    if max_calls <= 0 or window_seconds <= 0:
        raise ValueError("max_calls and window_seconds must be positive")

    hits: dict[str, deque] = {}
    lock = Lock()

    def dep(request: Request) -> None:
        ip = _client_ip(request)
        now = time.monotonic()
        cutoff = now - window_seconds
        with lock:
            bucket = hits.setdefault(ip, deque())
            while bucket and bucket[0] < cutoff:
                bucket.popleft()
            if len(bucket) >= max_calls:
                retry_after = max(1, int(window_seconds - (now - bucket[0])))
                raise HTTPException(
                    status_code=429,
                    detail={
                        "error": "rate_limited",
                        "message": (
                            f"Too many requests from {ip}. "
                            f"Limit: {max_calls}/{int(window_seconds)}s."
                        ),
                        "retry_after_seconds": retry_after,
                    },
                    headers={"Retry-After": str(retry_after)},
                )
            bucket.append(now)

    # Expose internal state for tests and inspection.
    dep.hits = hits  # type: ignore[attr-defined]
    dep.max_calls = max_calls  # type: ignore[attr-defined]
    dep.window_seconds = window_seconds  # type: ignore[attr-defined]
    return dep
