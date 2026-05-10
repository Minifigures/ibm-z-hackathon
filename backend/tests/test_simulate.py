import numpy as np
import pytest

from app.mobility import country_index, load_countries
from app.simulate import SimParams, run


def _params(**overrides):
    base = dict(
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
        horizon_days=20,
        n_runs=60,
    )
    base.update(overrides)
    return SimParams(**base)


def test_run_returns_expected_schema():
    result = run(_params())
    assert set(result.keys()) >= {
        "horizon_days",
        "regions",
        "top_imports",
        "top_exports",
        "spread_arcs",
        "calibration",
        "params_used",
    }
    assert result["horizon_days"] == 20
    assert len(result["regions"]) == len(load_countries())

    region = result["regions"][0]
    assert {"iso3", "name", "population", "quantiles"} <= region.keys()
    q = region["quantiles"]
    for key in ("p2_5", "p25", "p50", "p75", "p97_5"):
        assert key in q
        assert len(q[key]) == 21  # horizon_days + 1 snapshots


def test_quantiles_are_ordered():
    result = run(_params(start_iso3="BRA"))
    for r in result["regions"]:
        q = r["quantiles"]
        for t in range(len(q["p50"])):
            assert q["p2_5"][t] <= q["p25"][t] + 1e-6
            assert q["p25"][t] <= q["p50"][t] + 1e-6
            assert q["p50"][t] <= q["p75"][t] + 1e-6
            assert q["p75"][t] <= q["p97_5"][t] + 1e-6


def test_top_imports_excludes_seed():
    result = run(_params(start_iso3="USA"))
    assert all(row["iso3"] != "USA" for row in result["top_imports"])


def test_full_travel_restriction_isolates_seed():
    result = run(_params(travel_restriction=1.0, horizon_days=30))
    idx = country_index()
    seed_idx = idx["USA"]
    # Every non-seed region should have ~zero cumulative cases at horizon.
    for i, r in enumerate(result["regions"]):
        if i == seed_idx:
            continue
        assert r["cumulative_p50_final"] < 1.0, f"{r['iso3']} should be isolated"


def test_full_mask_suppresses_growth():
    no_mask = run(_params(mask_intervention=0.0, horizon_days=40))
    full_mask = run(_params(mask_intervention=1.0, horizon_days=40))
    seed_idx = country_index()["USA"]
    seed_no = no_mask["regions"][seed_idx]["cumulative_p50_final"]
    seed_full = full_mask["regions"][seed_idx]["cumulative_p50_final"]
    # 100% transmission cut means R = 0; the seeded pool shouldn't grow far past
    # the initial 50 infected before they recover.
    assert seed_full < 200
    assert seed_no > seed_full * 5


def test_state_remains_nonnegative():
    # Pull cumulative arrays directly to confirm no negatives leaked through.
    result = run(_params())
    for r in result["regions"]:
        for key in ("p2_5", "p25", "p50", "p75", "p97_5"):
            arr = np.array(r["quantiles"][key])
            assert (arr >= -1e-3).all(), f"{r['iso3']} {key} went negative"


def test_unknown_seed_iso_raises():
    with pytest.raises(ValueError):
        run(_params(start_iso3="ZZZ"))


def test_horizon_zero_or_short_does_not_crash():
    result = run(_params(horizon_days=7))
    assert len(result["regions"][0]["quantiles"]["p50"]) == 8


def test_higher_r0_yields_more_seed_cases():
    low = run(_params(r0=1.2, horizon_days=30))
    high = run(_params(r0=3.5, horizon_days=30))
    seed_idx = country_index()["USA"]
    assert (
        high["regions"][seed_idx]["cumulative_p50_final"]
        > low["regions"][seed_idx]["cumulative_p50_final"]
    )


def test_spread_arcs_originate_from_seed():
    result = run(_params(start_iso3="BRA"))
    assert len(result["spread_arcs"]) > 0
    for arc in result["spread_arcs"]:
        assert arc["from_iso3"] == "BRA"
        assert arc["to_iso3"] != "BRA"
        assert arc["weight_normalized"] >= 0
