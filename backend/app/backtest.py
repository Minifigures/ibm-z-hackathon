"""Backtest harness for the calibration badge.

Runs the Monte Carlo SEIR simulator on a known scenario (Wuhan, January 2020)
and reports what fraction of holdout regions had their JHU CSSE confirmed-case
count contained inside the simulator's 95% prediction interval at day 30.

The simulator tracks infections, not confirmed cases, so we deflate projected
counts by a fixed reporting-fraction multiplier (rho ~ 0.1 for early-2020
surveillance ramp-up, sourced from Imperial College and CDC retrospectives)
before comparing to JHU CSSE numbers. Limitation noted in
`backend/app/data/backtest_wuhan_2020.json` and surfaced in the calibration
response.

Result is computed once on first call and cached in-process via lru_cache so
the simulator's per-request /simulate response can include the real coverage
number without paying the full backtest cost on every request.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .simulate import SimParams, run

DATA_FILE = Path(__file__).parent / "data" / "backtest_wuhan_2020.json"


@dataclass(frozen=True)
class BacktestResult:
    scenario_id: str
    holdout_count: int
    coverage_p95: float  # fraction in [0, 1]
    coverage_p50: float
    reporting_fraction: float
    note: str


def _load() -> dict:
    return json.loads(DATA_FILE.read_text())


def _interval_at_horizon(quantiles: dict, horizon_days: int) -> tuple[float, float, float, float]:
    """Return (p2_5, p25, p75, p97_5) at the horizon-end day."""
    return (
        quantiles["p2_5"][horizon_days],
        quantiles["p25"][horizon_days],
        quantiles["p75"][horizon_days],
        quantiles["p97_5"][horizon_days],
    )


@lru_cache(maxsize=1)
def compute_wuhan_coverage() -> BacktestResult:
    cfg = _load()
    horizon = int(cfg["horizon_days"])
    rho = float(cfg["reporting_fraction"])
    seed_iso = str(cfg["seed_iso3"])
    truth: dict[str, float] = {iso: float(v) for iso, v in cfg["ground_truth"].items()}
    seed_infected = int(cfg.get("seed_infected", 50))

    sim = run(
        SimParams(
            disease_id="covid19",
            start_iso3=seed_iso,
            r0=2.5,
            incubation_days=5.0,
            infectious_days=6.0,
            cfr_pct=1.0,
            air_weight=1.0,
            port_weight=0.3,
            travel_restriction=0.0,
            mask_intervention=0.0,
            horizon_days=horizon,
            n_runs=300,
            seed_infected=seed_infected,
        )
    )

    region_by_iso = {r["iso3"]: r for r in sim["regions"]}
    holdout = [iso for iso in truth if iso in region_by_iso]
    if not holdout:
        return BacktestResult(
            scenario_id=str(cfg.get("scenario_id", "wuhan_2020")),
            holdout_count=0,
            coverage_p95=0.0,
            coverage_p50=0.0,
            reporting_fraction=rho,
            note="no overlap between ground-truth and modeled regions",
        )

    hit_p95 = 0
    hit_p50 = 0
    for iso in holdout:
        q = region_by_iso[iso]["quantiles"]
        p2_5, p25, p75, p97_5 = _interval_at_horizon(q, horizon)
        # Deflate the simulator's projected infections by the reporting fraction
        # so we compare like for like against confirmed cases.
        lo95, hi95 = rho * p2_5, rho * p97_5
        lo50, hi50 = rho * p25, rho * p75
        observed = truth[iso]
        if lo95 <= observed <= hi95:
            hit_p95 += 1
        if lo50 <= observed <= hi50:
            hit_p50 += 1

    return BacktestResult(
        scenario_id=str(cfg.get("scenario_id", "wuhan_2020")),
        holdout_count=len(holdout),
        coverage_p95=hit_p95 / len(holdout),
        coverage_p50=hit_p50 / len(holdout),
        reporting_fraction=rho,
        note=str(cfg.get("description", "")),
    )


def reset_cache() -> None:
    """For tests that want to re-run the backtest after monkeypatching."""
    compute_wuhan_coverage.cache_clear()
