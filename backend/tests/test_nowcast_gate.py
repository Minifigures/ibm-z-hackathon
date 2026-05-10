"""Tests for the /nowcast input caps and per-IP rate limit."""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from app.main import app, nowcast_limiter
from app.rate_limit import RateLimit


def _payload(n_obs: int = 3) -> dict:
    return {
        "disease_id": "covid19",
        "start_iso3": "USA",
        "r0": 2.5,
        "incubation_days": 5.0,
        "infectious_days": 6.0,
        "cfr_pct": 1.0,
        "air_weight": 1.0,
        "port_weight": 0.3,
        "travel_restriction": 0.0,
        "mask_intervention": 0.0,
        "horizon_days": 15,
        "n_runs": 50,
        "observations": [
            {"day": i, "cumulative_cases": 100 * (i + 1)} for i in range(n_obs)
        ],
        "n_particles": 60,
        "rho_min": 0.05,
        "rho_max": 0.4,
    }


@pytest.fixture(autouse=True)
def _reset_limiter():
    """Each test gets a clean rate-limit bucket."""
    nowcast_limiter._hits.clear()
    yield
    nowcast_limiter._hits.clear()


def test_nowcast_rejects_oversized_observation_list():
    """Observations cap is enforced by the pydantic schema (max_length=365)."""
    client = TestClient(app)
    r = client.post("/nowcast", json=_payload(n_obs=400))
    assert r.status_code == 422  # pydantic validation
    body = r.json()
    # The error shape varies by pydantic version; just confirm "observations"
    # is mentioned somewhere in the validation detail.
    assert "observations" in str(body).lower()


def test_nowcast_rejects_empty_observation_list():
    client = TestClient(app)
    r = client.post("/nowcast", json=_payload(n_obs=0))
    assert r.status_code == 422


def test_rate_limit_returns_429_after_burst():
    """Direct test of the RateLimit dependency, isolated from FastAPI."""
    rl = RateLimit(max_calls=3, window_seconds=60)

    class _FakeClient:
        host = "1.2.3.4"

    class _Req:
        client = _FakeClient()
        headers: dict[str, str] = {}

    # First three calls succeed.
    for _ in range(3):
        rl(_Req())
    # Fourth raises 429.
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        rl(_Req())
    assert exc.value.status_code == 429
    assert "rate_limited" in str(exc.value.detail)


def test_rate_limit_window_drains():
    """After window_seconds the bucket frees up."""
    rl = RateLimit(max_calls=2, window_seconds=0.1)

    class _Req:
        class client:
            host = "9.9.9.9"
        headers: dict[str, str] = {}

    rl(_Req())
    rl(_Req())
    time.sleep(0.15)
    rl(_Req())  # should not raise


def test_rate_limit_honours_x_forwarded_for():
    """First IP in X-Forwarded-For is treated as the client."""
    rl = RateLimit(max_calls=1, window_seconds=60)

    class _Req:
        class client:
            host = "10.0.0.1"  # nginx proxy
        headers = {"x-forwarded-for": "203.0.113.5, 10.0.0.1"}

    rl(_Req())
    # Same forwarded IP gets blocked even though uvicorn sees the proxy IP.
    from fastapi import HTTPException

    with pytest.raises(HTTPException):
        rl(_Req())
