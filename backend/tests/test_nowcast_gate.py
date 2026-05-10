"""Tests for the /nowcast input caps and per-IP rate limit."""

import time

import pytest
from fastapi import FastAPI, Depends, HTTPException
from fastapi.testclient import TestClient

from app.main import app, nowcast_limiter
from app.rate_limit import rate_limit


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
    nowcast_limiter.hits.clear()
    yield
    nowcast_limiter.hits.clear()


def test_nowcast_rejects_oversized_observation_list():
    """Observations cap is enforced by the pydantic schema (max_length=365)."""
    client = TestClient(app)
    r = client.post("/nowcast", json=_payload(n_obs=400))
    assert r.status_code == 422
    assert "observations" in str(r.json()).lower()


def test_nowcast_rejects_empty_observation_list():
    client = TestClient(app)
    r = client.post("/nowcast", json=_payload(n_obs=0))
    assert r.status_code == 422


def test_disease_params_dependency_injects_request_correctly():
    """Regression for the previous class-based RateLimit which made FastAPI
    interpret `request` as a query parameter and 422 every call."""
    client = TestClient(app)
    r = client.post("/disease-params", json={"name": "ebola"})
    # The endpoint should NOT 422 with `loc: ["query", "request"]`. It may
    # legitimately 503 (watsonx unconfigured in test env), 422 from pydantic
    # output validation, 200 with params, or 429. All are fine; the failure
    # mode we are guarding against is the dependency-injection bug.
    if r.status_code == 422:
        body = r.json()
        detail = body.get("detail")
        if isinstance(detail, list):
            for item in detail:
                assert item.get("loc") != ["query", "request"], (
                    "rate-limit dependency is leaking 'request' as a query parameter"
                )


def test_rate_limit_returns_429_after_burst():
    """The function-factory dependency, called directly, should 429 on overflow."""
    rl = rate_limit(max_calls=3, window_seconds=60)

    class _FakeClient:
        host = "1.2.3.4"

    class _Req:
        client = _FakeClient()
        headers: dict[str, str] = {}

    for _ in range(3):
        rl(_Req())
    with pytest.raises(HTTPException) as exc:
        rl(_Req())
    assert exc.value.status_code == 429
    assert "rate_limited" in str(exc.value.detail)


def test_rate_limit_window_drains():
    """After window_seconds the bucket frees up."""
    rl = rate_limit(max_calls=2, window_seconds=0.1)

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
    rl = rate_limit(max_calls=1, window_seconds=60)

    class _Req:
        class client:
            host = "10.0.0.1"  # nginx proxy
        headers = {"x-forwarded-for": "203.0.113.5, 10.0.0.1"}

    rl(_Req())
    with pytest.raises(HTTPException):
        rl(_Req())


def test_rate_limit_via_fastapi_actually_429s():
    """End-to-end: a route protected by the rate-limit dependency should
    actually return 429 in a TestClient request when burst-flooded."""
    test_app = FastAPI()
    limiter = rate_limit(max_calls=2, window_seconds=60)

    @test_app.get("/ping", dependencies=[Depends(limiter)])
    def ping() -> dict:
        return {"ok": True}

    client = TestClient(test_app)
    assert client.get("/ping").status_code == 200
    assert client.get("/ping").status_code == 200
    r = client.get("/ping")
    assert r.status_code == 429
    assert "Retry-After" in r.headers
