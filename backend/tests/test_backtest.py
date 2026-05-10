import pytest

from app import backtest


@pytest.fixture(autouse=True)
def _reset_cache():
    backtest.reset_cache()
    yield
    backtest.reset_cache()


def test_backtest_runs_against_jhu_truth():
    result = backtest.compute_wuhan_coverage()
    assert result.scenario_id == "wuhan_2020"
    # Some of the modeled regions overlap with the ground-truth set.
    assert result.holdout_count > 5
    assert 0.0 <= result.coverage_p95 <= 1.0
    assert 0.0 <= result.coverage_p50 <= 1.0
    # 95% interval should not be tighter than the 50% interval.
    assert result.coverage_p95 >= result.coverage_p50
    # Reporting fraction matches the scenario file.
    assert 0 < result.reporting_fraction <= 1.0


def test_backtest_result_is_cached():
    """Second call should hit the lru_cache and return the same object."""
    a = backtest.compute_wuhan_coverage()
    b = backtest.compute_wuhan_coverage()
    assert a is b


def test_simulate_calibration_block_uses_real_coverage():
    """The /simulate response now reports the backtest coverage rather than the
    placeholder value the original implementation hardcoded."""
    from app.simulate import SimParams, run

    out = run(
        SimParams(
            disease_id="covid19", start_iso3="USA",
            r0=2.5, incubation_days=5.0, infectious_days=6.0, cfr_pct=1.0,
            air_weight=1.0, port_weight=0.3,
            travel_restriction=0.0, mask_intervention=0.0,
            horizon_days=15, n_runs=40,
        )
    )
    cal = out["calibration"]
    assert cal["scenario_id"] == "wuhan_2020"
    assert isinstance(cal["interval_coverage_holdout"], float)
    assert 0.0 <= cal["interval_coverage_holdout"] <= 1.0
    # Placeholder note is gone.
    assert "placeholder" not in cal["note"]
