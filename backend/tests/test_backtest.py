"""Smoke tests for the offline Wuhan-2020 calibration harness."""

from __future__ import annotations

import math

import pytest

from app import backtest


@pytest.fixture(autouse=True)
def _reset_cache():
    backtest.reset_cache()
    yield
    backtest.reset_cache()


def test_backtest_runs_against_jhu_truth():
    result = backtest.compute_wuhan_calibration()
    assert result.scenario_id == "wuhan_2020"
    assert result.holdout_count > 5
    assert 0.0 <= result.coverage_95 <= 1.0
    assert 0.0 <= result.coverage_50 <= 1.0
    # 95% interval should not be tighter than 50% interval.
    assert result.coverage_95 >= result.coverage_50
    # CRPS is non-negative; multibin log score is non-positive.
    assert result.crps_norm_per_100k >= 0.0
    assert result.multibin_log_score <= 0.0
    assert math.isfinite(result.crps_norm_per_100k)
    assert math.isfinite(result.multibin_log_score)
    assert 0 < result.reporting_fraction <= 1.0


def test_backtest_result_is_cached():
    """Second call hits lru_cache and returns the same object."""
    a = backtest.compute_wuhan_calibration()
    b = backtest.compute_wuhan_calibration()
    assert a is b


def test_simulate_response_contains_offline_backtest():
    """/simulate now embeds the offline backtest under calibration.offline_backtest."""
    from app.simulate import SimParams, run

    out = run(
        SimParams(
            disease_id="covid19",
            start_iso3="USA",
            r0=2.5,
            incubation_days=5.0,
            infectious_days=6.0,
            cfr_pct=1.0,
            air_weight=1.0,
            port_weight=0.3,
            travel_restriction=0.0,
            mask_intervention=0.0,
            horizon_days=15,
            n_runs=40,
        )
    )
    cal = out["calibration"]
    offline = cal.get("offline_backtest")
    assert offline is not None
    assert offline.get("scenario_id") == "wuhan_2020"
    assert isinstance(offline["coverage_95"], float)
    assert isinstance(offline["crps_norm_per_100k"], float)
    assert isinstance(offline["multibin_log_score"], float)
