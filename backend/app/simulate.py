"""Region-indexed SEIR with mobility coupling and Monte Carlo uncertainty.

Implements equations (c) and (d) from the PRD. State per region: [S, E, I, R].
The integrator is a vectorized forward-Euler with sub-day steps so that all
Monte Carlo runs advance in lockstep over a single set of numpy operations.

Computational profile: with n_regions ~= 70 and n_runs = 200, a 30-day forecast
runs in well under a second on commodity hardware. The PRD's < 1s slider
target is comfortable.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .mobility import combined_mobility, country_index, load_countries

SUB_STEPS_PER_DAY = 4
QUANTILES = (0.025, 0.25, 0.5, 0.75, 0.975)
THETA_IMPORT_COUPLING = 0.05  # weight on imported infectious pressure in lambda


def _calibration_block(n_runs: int) -> dict:
    """Build the calibration sub-response. Imported lazily to avoid a circular
    dependency (backtest -> simulate.run -> _calibration_block -> backtest)."""
    try:
        from . import backtest  # local import is the cycle break
        result = backtest.compute_wuhan_coverage()
        return {
            "monte_carlo_runs": n_runs,
            "interval_coverage_holdout": float(result.coverage_p95),
            "interval_coverage_p50": float(result.coverage_p50),
            "holdout_count": result.holdout_count,
            "scenario_id": result.scenario_id,
            "reporting_fraction": result.reporting_fraction,
            "note": (
                "Coverage measured against JHU CSSE confirmed cases per country at "
                "day 30 of the Wuhan-2020 backtest, deflated by the early-2020 "
                "reporting-fraction prior."
            ),
        }
    except Exception as exc:  # noqa: BLE001 - calibration should never break /simulate
        return {
            "monte_carlo_runs": n_runs,
            "interval_coverage_holdout": None,
            "note": f"Backtest harness unavailable: {exc}",
        }


@dataclass
class SimParams:
    disease_id: str
    start_iso3: str
    r0: float
    incubation_days: float
    infectious_days: float
    cfr_pct: float
    air_weight: float
    port_weight: float
    travel_restriction: float
    mask_intervention: float
    horizon_days: int
    n_runs: int = 200
    seed_infected: int = 50


def _seed_state(n_regions: int, n_runs: int, start_idx: int, seed_infected: int, populations: np.ndarray):
    S = np.tile(populations.astype(np.float64), (n_runs, 1))
    E = np.zeros((n_runs, n_regions))
    I = np.zeros((n_runs, n_regions))
    R = np.zeros((n_runs, n_regions))
    I[:, start_idx] = float(seed_infected)
    S[:, start_idx] -= float(seed_infected)
    return S, E, I, R


def _normalized_inflow_weights(m: np.ndarray) -> np.ndarray:
    """omega[j, i] = m[j, i] / sum_k m[k, i] so that columns sum to 1.

    Used to form the bracketed weighted-average imported-prevalence term in
    lambda_i. Columns with no inflow get a clean zero column instead of a
    divide-by-zero.
    """
    col_sums = m.sum(axis=0)
    safe = np.where(col_sums > 0, col_sums, 1.0)
    omega = m / safe
    omega[:, col_sums == 0] = 0.0
    return omega


def run(params: SimParams) -> dict:
    countries = load_countries()
    iso_to_idx = country_index()
    if params.start_iso3 not in iso_to_idx:
        raise ValueError(f"Unknown start country: {params.start_iso3}")
    start_idx = iso_to_idx[params.start_iso3]

    n = len(countries)
    populations = np.array([c.population for c in countries], dtype=np.float64)
    iso3_list = [c.iso3 for c in countries]
    name_list = [c.name for c in countries]

    m = combined_mobility(
        air_weight=params.air_weight,
        port_weight=params.port_weight,
        travel_restriction=params.travel_restriction,
    )
    omega = _normalized_inflow_weights(m)
    out_rate = m.sum(axis=1)  # per-region per-day outflow

    rng = np.random.default_rng(42)
    # Monte Carlo perturbations on key biological parameters (eq. d).
    r0_samples = np.clip(rng.normal(params.r0, 0.15 * max(params.r0, 0.5), params.n_runs), 0.1, 8.0)
    inf_days_samples = np.clip(rng.normal(params.infectious_days, 0.15 * params.infectious_days, params.n_runs), 1.0, 30.0)
    inc_days_samples = np.clip(rng.normal(params.incubation_days, 0.15 * params.incubation_days, params.n_runs), 0.5, 30.0)
    intervention = 1.0 - params.mask_intervention

    sigma = 1.0 / inc_days_samples            # E -> I rate, shape (n_runs,)
    gamma = 1.0 / inf_days_samples            # I -> R rate, shape (n_runs,)
    beta = r0_samples * gamma * intervention  # transmission rate, shape (n_runs,)

    sigma = sigma[:, None]
    gamma = gamma[:, None]
    beta = beta[:, None]

    S, E, I, R = _seed_state(n, params.n_runs, start_idx, params.seed_infected, populations)
    N = populations[None, :]

    n_steps = params.horizon_days * SUB_STEPS_PER_DAY
    dt = 1.0 / SUB_STEPS_PER_DAY

    # We record one snapshot per day of [S, E, I, R].
    snapshots = np.zeros((params.horizon_days + 1, params.n_runs, n, 4), dtype=np.float32)
    snapshots[0, :, :, 0] = S
    snapshots[0, :, :, 1] = E
    snapshots[0, :, :, 2] = I
    snapshots[0, :, :, 3] = R

    for step in range(n_steps):
        I_per_cap = I / N
        local_pressure = (1.0 - THETA_IMPORT_COUPLING) * I_per_cap
        imported_pressure = THETA_IMPORT_COUPLING * (I_per_cap @ omega)
        lam = beta * (local_pressure + imported_pressure)

        new_exposed = lam * S
        new_infectious = sigma * E
        new_recovered = gamma * I

        # Mobility flux for each compartment: -X * out_rate + (X @ m)
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

        if (step + 1) % SUB_STEPS_PER_DAY == 0:
            day = (step + 1) // SUB_STEPS_PER_DAY
            snapshots[day, :, :, 0] = S
            snapshots[day, :, :, 1] = E
            snapshots[day, :, :, 2] = I
            snapshots[day, :, :, 3] = R

    # Cumulative infected = N - S over time (works because mobility is
    # population-conserving, so any drop in S is from infection).
    cumulative_infected = populations[None, None, :] - snapshots[:, :, :, 0]
    cumulative_infected = np.clip(cumulative_infected, 0.0, None)

    # Active prevalence per 100k for choropleth coloring at horizon end.
    final = snapshots[-1]
    active = final[:, :, 1] + final[:, :, 2]  # E + I
    prevalence_per_100k = (active / populations[None, :]) * 100_000.0
    prevalence_p50 = np.quantile(prevalence_per_100k, 0.5, axis=0)
    prevalence_p95 = np.quantile(prevalence_per_100k, 0.95, axis=0)

    cumulative_p50_final = np.quantile(cumulative_infected[-1], 0.5, axis=0)

    # Per-region time series with quantile bands.
    qbands = np.quantile(cumulative_infected, QUANTILES, axis=1)  # (5, T+1, n)
    region_series = []
    for i, iso3 in enumerate(iso3_list):
        region_series.append({
            "iso3": iso3,
            "name": name_list[i],
            "population": int(populations[i]),
            "prevalence_p50_per_100k": float(prevalence_p50[i]),
            "prevalence_p95_per_100k": float(prevalence_p95[i]),
            "cumulative_p50_final": float(cumulative_p50_final[i]),
            "quantiles": {
                "p2_5":  qbands[0, :, i].tolist(),
                "p25":   qbands[1, :, i].tolist(),
                "p50":   qbands[2, :, i].tolist(),
                "p75":   qbands[3, :, i].tolist(),
                "p97_5": qbands[4, :, i].tolist(),
            },
        })

    # Hub rankings: import = cumulative cases imported by horizon end (excludes seed).
    cum_final_p50 = cumulative_p50_final.copy()
    cum_final_p50[start_idx] = 0.0
    import_order = np.argsort(-cum_final_p50)[:10]
    top_imports = [
        {
            "iso3": iso3_list[i],
            "name": name_list[i],
            "expected_cases": float(cum_final_p50[i]),
            "per_100k": float(cum_final_p50[i] / populations[i] * 100_000.0),
        }
        for i in import_order
    ]

    # Export = total outbound mobility flux from each region weighted by I (active
    # infectious). Aggregate over the full horizon to surface the routes doing
    # most of the importing.
    I_over_time = snapshots[:, :, :, 2]  # (T+1, runs, n)
    I_per_cap = I_over_time / populations[None, None, :]
    I_per_cap_p50 = np.quantile(I_per_cap, 0.5, axis=1)  # (T+1, n)
    # Outbound infectious flux per source: I_per_cap[i] * sum_j(F_ij)
    # F_ij is flow in absolute people; m * pop = flow.
    flow = m * populations[:, None]  # (n, n)
    out_flux_total = flow.sum(axis=1)  # absolute outbound per day from each source
    export_score = (I_per_cap_p50 * out_flux_total[None, :]).sum(axis=0)
    export_score[start_idx] = 0.0  # seed already credited as origin
    export_order = np.argsort(-export_score)[:10]
    top_exports = [
        {
            "iso3": iso3_list[i],
            "name": name_list[i],
            "score": float(export_score[i]),
        }
        for i in export_order
    ]

    # Top OD pairs starting from the seed (used for the spread-arc layer).
    seed_pop = populations[start_idx]
    seed_outflow = flow[start_idx]
    arc_order = np.argsort(-seed_outflow)[:8]
    spread_arcs = [
        {
            "from_iso3": iso3_list[start_idx],
            "to_iso3": iso3_list[j],
            "from_name": name_list[start_idx],
            "to_name": name_list[j],
            "weight": float(seed_outflow[j]),
            "weight_normalized": float(seed_outflow[j] / max(seed_outflow.max(), 1.0)),
        }
        for j in arc_order if j != start_idx
    ]

    return {
        "horizon_days": params.horizon_days,
        "regions": region_series,
        "top_imports": top_imports,
        "top_exports": top_exports,
        "spread_arcs": spread_arcs,
        "calibration": _calibration_block(params.n_runs),
        "params_used": {
            "disease_id": params.disease_id,
            "start_iso3": params.start_iso3,
            "r0_median": float(np.median(r0_samples)),
            "infectious_days_median": float(np.median(inf_days_samples)),
            "incubation_days_median": float(np.median(inc_days_samples)),
            "intervention_multiplier": intervention,
            "air_weight": params.air_weight,
            "port_weight": params.port_weight,
            "travel_restriction": params.travel_restriction,
            "cfr_pct": params.cfr_pct,
        },
    }
