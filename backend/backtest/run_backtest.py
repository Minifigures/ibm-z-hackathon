"""Backtest the SEIR + mobility + Monte Carlo simulator against JHU CSSE data.

Seeds COVID-19 in CHN on 2020-01-22 (first JHU observation date) and runs the
production model with literature defaults. On day +30 (2020-02-21) we compare
each modelled country's cumulative-infected quantile band against the actual
JHU confirmed-case count and record:

    coverage_95pi    fraction of countries whose actual fell inside [p2.5, p97.5]
    median_log_mae   median |log10(model_p50 + 1) - log10(actual + 1)|

Run from ``backend/``::

    python -m backtest.run_backtest

Writes ``backend/backtest/results.json`` and prints headline metrics to stdout.
"""

from __future__ import annotations

import json
import math
from datetime import date, timedelta
from pathlib import Path

import numpy as np

# We intentionally import via ``app.*`` (not ``backend.app.*``) because the
# project's tests, fastapi entry point, and PRD all assume the working
# directory is ``backend/``.
from app.mobility import country_index, load_countries
from app.simulate import SUB_STEPS_PER_DAY, THETA_IMPORT_COUPLING_DEFAULT as THETA_IMPORT_COUPLING, SimParams, combined_mobility  # type: ignore
from app.simulate import _normalized_inflow_weights, _seed_state  # type: ignore

from .jhu_data import load_country_counts

# ---------------------------------------------------------------------------
# Backtest configuration
# ---------------------------------------------------------------------------
SEED_ISO3 = "CHN"
SEED_DATE = "2020-01-22"            # first day in JHU file
COMPARISON_DATE = "2020-02-21"      # SEED_DATE + 30 days
HORIZON_DAYS = 30
N_MONTE_CARLO = 1000

# Literature COVID-19 defaults from app/data/diseases.json
R0 = 2.5
INCUBATION_DAYS = 5.0
INFECTIOUS_DAYS = 6.0
CFR_PCT = 1.0

# We mirror the /simulate request defaults that match a realistic 2020-Q1
# scenario: no travel restriction or mask intervention yet at day 0.
AIR_WEIGHT = 1.0
PORT_WEIGHT = 0.3
TRAVEL_RESTRICTION = 0.0
MASK_INTERVENTION = 0.0

# JHU's mainland-China case count on 2020-01-22 was already 548 (ramping from
# the late-December cluster). We seed the model with this number rather than
# the standard 50 to give the simulator a fair starting condition; otherwise
# we are asking a 50-case start to match a 548-case truth. Seeding from the
# actual day-0 truth is what a real-time forecaster would do.
SEED_INFECTED_OVERRIDE: int | None = None  # filled in from JHU at runtime

OUTPUT_PATH = Path(__file__).parent / "results.json"


def _full_simulation(params: SimParams) -> tuple[np.ndarray, list[str]]:
    """Run the model and return raw cumulative-infected samples.

    Re-implements ``app.simulate.run`` only as far as collecting the per-run
    cumulative-infected array at the end of the horizon. Doing this rather
    than calling ``run()`` and reading back its quantiles lets us compute the
    band ourselves with whatever percentiles we want, and avoids the JSON
    round-trip that ``run()`` does for the API response.

    Returns
    -------
    cum_final : np.ndarray, shape (n_runs, n_regions)
        Cumulative infected (= N - S) per Monte Carlo run, per region, on
        the last simulated day.
    iso3_list : list[str]
        Region ISO-3 codes in column order.
    """
    countries = load_countries()
    iso_to_idx = country_index()
    if params.start_iso3 not in iso_to_idx:
        raise ValueError(f"Unknown start country: {params.start_iso3}")
    start_idx = iso_to_idx[params.start_iso3]

    n = len(countries)
    populations = np.array([c.population for c in countries], dtype=np.float64)
    iso3_list = [c.iso3 for c in countries]

    m = combined_mobility(
        air_weight=params.air_weight,
        port_weight=params.port_weight,
        travel_restriction=params.travel_restriction,
    )
    omega = _normalized_inflow_weights(m)
    out_rate = m.sum(axis=1)

    rng = np.random.default_rng(42)
    r0_samples = np.clip(
        rng.normal(params.r0, 0.15 * max(params.r0, 0.5), params.n_runs), 0.1, 8.0
    )
    inf_days_samples = np.clip(
        rng.normal(params.infectious_days, 0.15 * params.infectious_days, params.n_runs),
        1.0, 30.0,
    )
    inc_days_samples = np.clip(
        rng.normal(params.incubation_days, 0.15 * params.incubation_days, params.n_runs),
        0.5, 30.0,
    )
    intervention = 1.0 - params.mask_intervention

    sigma = (1.0 / inc_days_samples)[:, None]
    gamma = (1.0 / inf_days_samples)[:, None]
    beta = (r0_samples * (1.0 / inf_days_samples) * intervention)[:, None]

    seed_distribution = np.zeros(n, dtype=np.float64)
    seed_distribution[start_idx] = float(params.seed_infected)
    S, E, I, R = _seed_state(n, params.n_runs, seed_distribution, populations)
    N = populations[None, :]

    n_steps = params.horizon_days * SUB_STEPS_PER_DAY
    dt = 1.0 / SUB_STEPS_PER_DAY

    for _ in range(n_steps):
        I_per_cap = I / N
        local_pressure = (1.0 - THETA_IMPORT_COUPLING) * I_per_cap
        imported_pressure = THETA_IMPORT_COUPLING * (I_per_cap @ omega)
        lam = beta * (local_pressure + imported_pressure)

        new_exposed = lam * S
        new_infectious = sigma * E
        new_recovered = gamma * I

        S_in = S @ m
        E_in = E @ m
        I_in = I @ m
        R_in = R @ m

        dS = -new_exposed - S * out_rate + S_in
        dE = new_exposed - new_infectious - E * out_rate + E_in
        dI = new_infectious - new_recovered - I * out_rate + I_in
        dR = new_recovered - R * out_rate + R_in

        S = np.maximum(S + dt * dS, 0.0)
        E = np.maximum(E + dt * dE, 0.0)
        I = np.maximum(I + dt * dI, 0.0)
        R = np.maximum(R + dt * dR, 0.0)

    # Cumulative infected at horizon end = pop - S.
    cum_final = np.clip(populations[None, :] - S, 0.0, None)  # (n_runs, n)
    return cum_final, iso3_list


def _date_plus(d: str, days: int) -> str:
    y, m, dd = (int(x) for x in d.split("-"))
    return (date(y, m, dd) + timedelta(days=days)).isoformat()


def run_backtest() -> dict:
    print(f"Loading JHU CSSE data...")
    jhu_dates, jhu_by_iso = load_country_counts()
    if SEED_DATE not in jhu_dates:
        raise RuntimeError(f"JHU file does not contain seed date {SEED_DATE}.")
    if COMPARISON_DATE not in jhu_dates:
        raise RuntimeError(f"JHU file does not contain comparison date {COMPARISON_DATE}.")

    seed_actual = jhu_by_iso.get(SEED_ISO3, {}).get(SEED_DATE, 0)
    if seed_actual <= 0:
        raise RuntimeError(
            f"JHU has no {SEED_ISO3} cases on {SEED_DATE}; cannot seed the simulator."
        )
    print(f"Seeding {SEED_ISO3} with {seed_actual} infected (JHU value on {SEED_DATE}).")

    params = SimParams(
        disease_id="covid19",
        start_iso3=SEED_ISO3,
        r0=R0,
        incubation_days=INCUBATION_DAYS,
        infectious_days=INFECTIOUS_DAYS,
        cfr_pct=CFR_PCT,
        air_weight=AIR_WEIGHT,
        port_weight=PORT_WEIGHT,
        travel_restriction=TRAVEL_RESTRICTION,
        mask_intervention=MASK_INTERVENTION,
        horizon_days=HORIZON_DAYS,
        n_runs=N_MONTE_CARLO,
        seed_infected=int(seed_actual),
    )

    print(f"Running model: {N_MONTE_CARLO} runs x {HORIZON_DAYS} days...")
    cum_final, iso3_list = _full_simulation(params)
    print(f"  shape: {cum_final.shape}")

    # Per-country quantiles at horizon end.
    p2_5 = np.quantile(cum_final, 0.025, axis=0)
    p50 = np.quantile(cum_final, 0.5, axis=0)
    p97_5 = np.quantile(cum_final, 0.975, axis=0)

    per_country = []
    covered_count = 0
    compared_count = 0
    log_errors: list[float] = []

    for i, iso3 in enumerate(iso3_list):
        # Drop iso3s where we have no JHU data at all (very few on 2020-01-22).
        if iso3 not in jhu_by_iso:
            continue
        actual = jhu_by_iso[iso3].get(COMPARISON_DATE)
        if actual is None:
            continue

        lo = float(p2_5[i])
        med = float(p50[i])
        hi = float(p97_5[i])

        # Coverage: did the actual fall inside [p2.5, p97.5]?
        # Tolerate the both-near-zero case explicitly: if both model and truth
        # round to 0, count as covered.
        if actual <= hi + 1e-6 and actual >= lo - 1e-6:
            covered = True
        elif actual == 0 and hi < 1.0:
            covered = True
        else:
            covered = False

        log_err = abs(math.log10(med + 1.0) - math.log10(actual + 1.0))

        per_country.append({
            "iso3": iso3,
            "actual": int(actual),
            "model_median": med,
            "model_p2_5": lo,
            "model_p97_5": hi,
            "covered": covered,
            "log_abs_error": log_err,
        })
        compared_count += 1
        covered_count += int(covered)
        log_errors.append(log_err)

    coverage = covered_count / compared_count if compared_count else float("nan")
    median_log_mae = float(np.median(log_errors)) if log_errors else float("nan")

    # Sort per_country: seed first, then by descending actual.
    per_country.sort(key=lambda r: (0 if r["iso3"] == SEED_ISO3 else 1, -r["actual"]))

    result = {
        "seed_iso3": SEED_ISO3,
        "seed_date": SEED_DATE,
        "horizon_days": HORIZON_DAYS,
        "comparison_date": COMPARISON_DATE,
        "n_monte_carlo_runs": N_MONTE_CARLO,
        "n_countries_compared": compared_count,
        "coverage_95pi": coverage,
        "median_log_mae": median_log_mae,
        "seed_infected_initial": int(seed_actual),
        "params": {
            "r0": R0,
            "incubation_days": INCUBATION_DAYS,
            "infectious_days": INFECTIOUS_DAYS,
            "cfr_pct": CFR_PCT,
            "air_weight": AIR_WEIGHT,
            "port_weight": PORT_WEIGHT,
            "travel_restriction": TRAVEL_RESTRICTION,
            "mask_intervention": MASK_INTERVENTION,
        },
        "per_country": per_country,
    }

    OUTPUT_PATH.write_text(json.dumps(result, indent=2))
    print(f"\nBacktest complete. Headline metrics:")
    print(f"  countries compared: {compared_count}")
    print(f"  95% PI coverage   : {coverage*100:.1f}%")
    print(f"  median log10 MAE  : {median_log_mae:.3f}")
    print(f"  results written to: {OUTPUT_PATH}")
    return result


if __name__ == "__main__":
    run_backtest()
