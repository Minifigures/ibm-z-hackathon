"""Region-indexed SEIR with mobility coupling and Monte Carlo uncertainty.

Implements equations (c) and (d) from the PRD. State per region: [S, E, I, R].
The integrator is a vectorized forward-Euler with sub-day steps so that all
Monte Carlo runs advance in lockstep over a single set of numpy operations.

The public `run` function executes a 4-model ensemble (Reich et al. 2019,
PNAS) by calling `_seir_ensemble` four times with different mobility /
coupling / seeding assumptions and concatenating the runs. Equal-weight
averaging of probabilistic forecasts is the headline finding of FluSight:
the ensemble systematically beats every individual model.

Computational profile: with n_regions ~= 70 and n_runs_per_variant = 50
(default; total ensemble = 4 * 50 = 200), a 30-day forecast runs in well
under a second on commodity hardware. The PRD's < 1s slider target is
preserved.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Callable

import numpy as np

from .calibration import calibration_metrics
from .effective_distance import effective_distance_from
from .mobility import air_flow_matrix, combined_mobility, country_index, load_countries

SUB_STEPS_PER_DAY = 4
QUANTILES = (0.025, 0.25, 0.5, 0.75, 0.975)
THETA_IMPORT_COUPLING_DEFAULT = 0.05  # weight on imported infectious pressure in lambda


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


@dataclass(frozen=True)
class ModelVariant:
    """A single model in the 4-member ensemble.

    `mobility_overrides` patches the params used to build the mobility matrix
    for this variant; `theta` is the import-coupling weight; `seed_strategy`
    decides how the initial `seed_infected` cases are distributed across
    regions (default: all in `start_idx`).
    """

    id: str
    label: str
    citation: str
    mobility_overrides: dict
    theta: float
    seed_strategy: str  # "point" or "effective_distance"


@lru_cache(maxsize=1)
def _disease_metadata() -> dict:
    """Load diseases.json once. Used to look up disease-specific flags such
    as `cryptic_preseeding` that toggle which ensemble variants apply.
    """
    return json.loads((Path(__file__).parent / "data" / "diseases.json").read_text())


def _enable_cryptic_preseeding(disease_id: str) -> bool:
    """Whether the Brockmann-2013 / Davis-2021 effective-distance pre-seeding
    variant should fire for this disease. Defaults True (conservative for any
    unknown novel pathogen). Set to False in diseases.json for pathogens
    where cryptic pre-spread is not biologically plausible (e.g. mpox 2022,
    H1N1 2009 — both were caught clinically before significant pre-spread).
    """
    return bool(_disease_metadata().get(disease_id, {}).get("cryptic_preseeding", True))


def _model_variants() -> list[ModelVariant]:
    """The 4-model ensemble we run in `run`. Reich 2019 framing: each variant
    is a structurally different model; equal-weight averaging produces the
    ensemble forecast. Citations are surfaced to the UI tooltip.
    """
    return [
        ModelVariant(
            id="air_only",
            label="Air-only SEIR",
            citation="Colizza et al. 2006, PNAS",
            mobility_overrides={"port_weight": 0.0},
            theta=THETA_IMPORT_COUPLING_DEFAULT,
            seed_strategy="point",
        ),
        ModelVariant(
            id="air_sea",
            label="Air + sea SEIR",
            citation="Balcan et al. 2009, PNAS",
            mobility_overrides={},
            theta=THETA_IMPORT_COUPLING_DEFAULT,
            seed_strategy="point",
        ),
        ModelVariant(
            id="high_import_coupling",
            label="High-coupling SEIR",
            citation="Apolloni et al. 2014, BMC TBMM",
            mobility_overrides={},
            theta=0.15,
            seed_strategy="point",
        ),
        ModelVariant(
            id="effective_distance_seed",
            label="Eff-distance pre-seed",
            citation="Brockmann & Helbing 2013, Science",
            mobility_overrides={},
            theta=THETA_IMPORT_COUPLING_DEFAULT,
            seed_strategy="effective_distance",
        ),
    ]


def _build_calibration(
    cum_terminal: np.ndarray,
    populations: np.ndarray,
    seed_idx: int,
    n_runs: int,
) -> dict:
    metrics = calibration_metrics(cum_terminal, populations, seed_idx)
    return {
        "monte_carlo_runs": n_runs,
        "interval_coverage_holdout": metrics["coverage_95"],
        "crps_norm_per_100k": metrics["crps_norm"],
        "multibin_log_score": metrics["multibin_log_score"],
        "note": (
            "Internal posterior-predictive metrics computed by leave-one-out over the "
            "Monte Carlo runs at horizon end. Methodology: coverage = fraction of LOO "
            "truths inside the 95% band of the rest; CRPS per Funk et al. 2018 (Epidemics, "
            "normalised /100k); multibin log score per Reich et al. 2019 PNAS FluSight."
        ),
    }


def _seed_state(
    n_regions: int,
    n_runs: int,
    seed_distribution: np.ndarray,  # shape (n_regions,) summing to ~seed_total
    populations: np.ndarray,
):
    S = np.tile(populations.astype(np.float64), (n_runs, 1))
    E = np.zeros((n_runs, n_regions))
    I = np.zeros((n_runs, n_regions))
    R = np.zeros((n_runs, n_regions))
    I[:] = seed_distribution[None, :]
    S -= seed_distribution[None, :]
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


def _seed_distribution(
    n_regions: int,
    start_idx: int,
    seed_total: float,
    strategy: str,
    d_eff_from_seed: np.ndarray,
) -> np.ndarray:
    """Convert the scalar `seed_infected` into a per-region initial-I vector.

    - "point": all seed cases land in start_idx (the default, classic GLEAM seeding).
    - "effective_distance": cases distributed across all reachable regions in
       proportion to exp(-0.4 * d_eff). 70% of mass stays at start_idx; the
       remaining 30% is spread by inverse effective distance, simulating the
       Davis 2021 "cryptic pre-seeding" hypothesis.
    """
    out = np.zeros(n_regions, dtype=np.float64)
    if strategy == "effective_distance":
        weights = np.where(np.isfinite(d_eff_from_seed), np.exp(-0.4 * d_eff_from_seed), 0.0)
        weights[start_idx] = 0.0
        total = weights.sum()
        out[start_idx] = 0.7 * seed_total
        if total > 0:
            out += (0.3 * seed_total) * (weights / total)
        else:
            out[start_idx] = seed_total
    else:
        out[start_idx] = seed_total
    return out


def _seir_ensemble(
    params: SimParams,
    *,
    mobility_matrix: np.ndarray,
    theta: float,
    seed_distribution: np.ndarray,
    populations: np.ndarray,
    n_runs: int,
    rng_seed: int,
) -> np.ndarray:
    """Run a single model variant. Returns cumulative_infected of shape
    (T+1, n_runs, n).
    """
    n = mobility_matrix.shape[0]
    omega = _normalized_inflow_weights(mobility_matrix)
    out_rate = mobility_matrix.sum(axis=1)

    rng = np.random.default_rng(rng_seed)
    r0_samples = np.clip(
        rng.normal(params.r0, 0.15 * max(params.r0, 0.5), n_runs), 0.1, 8.0
    )
    inf_days_samples = np.clip(
        rng.normal(params.infectious_days, 0.15 * params.infectious_days, n_runs), 1.0, 30.0
    )
    inc_days_samples = np.clip(
        rng.normal(params.incubation_days, 0.15 * params.incubation_days, n_runs), 0.5, 30.0
    )
    intervention = 1.0 - params.mask_intervention

    sigma = (1.0 / inc_days_samples)[:, None]
    gamma = (1.0 / inf_days_samples)[:, None]
    beta = (r0_samples * (1.0 / inf_days_samples) * intervention)[:, None]

    S, E, I, R = _seed_state(n, n_runs, seed_distribution, populations)
    N = populations[None, :]

    n_steps = params.horizon_days * SUB_STEPS_PER_DAY
    dt = 1.0 / SUB_STEPS_PER_DAY

    snapshots = np.zeros((params.horizon_days + 1, n_runs, n, 4), dtype=np.float32)
    snapshots[0, :, :, 0] = S
    snapshots[0, :, :, 1] = E
    snapshots[0, :, :, 2] = I
    snapshots[0, :, :, 3] = R

    m = mobility_matrix
    one_minus_theta = 1.0 - theta

    for step in range(n_steps):
        I_per_cap = I / N
        local_pressure = one_minus_theta * I_per_cap
        imported_pressure = theta * (I_per_cap @ omega)
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

        if (step + 1) % SUB_STEPS_PER_DAY == 0:
            day = (step + 1) // SUB_STEPS_PER_DAY
            snapshots[day, :, :, 0] = S
            snapshots[day, :, :, 1] = E
            snapshots[day, :, :, 2] = I
            snapshots[day, :, :, 3] = R

    cum = populations[None, None, :] - snapshots[:, :, :, 0]
    cum = np.clip(cum, 0.0, None)
    return snapshots, cum  # snapshots needed for prevalence + arrival downstream


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

    # Effective distance is computed once and reused (a) for the seeding
    # strategy of variant 4 and (b) as a per-region UI affordance.
    air_flow = air_flow_matrix()
    d_eff_from_seed = effective_distance_from(air_flow, start_idx)

    variants = _model_variants()
    # Disease-aware ensemble: drop the effective-distance pre-seeding variant
    # for pathogens where cryptic pre-spread is not biologically plausible.
    # See `cryptic_preseeding` flag in diseases.json.
    if not _enable_cryptic_preseeding(params.disease_id):
        variants = [v for v in variants if v.seed_strategy != "effective_distance"]
    n_runs_per_variant = max(int(round(params.n_runs / len(variants))), 20)

    all_cum_runs: list[np.ndarray] = []      # list of (T+1, runs_v, n)
    all_snapshots_runs: list[np.ndarray] = []  # list of (T+1, runs_v, n, 4)
    variant_terminal_p50 = np.zeros((len(variants), n), dtype=np.float64)
    variant_meta = []

    for vi, variant in enumerate(variants):
        v_params = SimParams(**{**params.__dict__, **variant.mobility_overrides})
        m = combined_mobility(
            air_weight=v_params.air_weight,
            port_weight=v_params.port_weight,
            travel_restriction=v_params.travel_restriction,
        )
        seed_dist = _seed_distribution(
            n, start_idx, params.seed_infected, variant.seed_strategy, d_eff_from_seed
        )
        snapshots_v, cum_v = _seir_ensemble(
            params,
            mobility_matrix=m,
            theta=variant.theta,
            seed_distribution=seed_dist,
            populations=populations,
            n_runs=n_runs_per_variant,
            rng_seed=42 + vi,
        )
        all_cum_runs.append(cum_v)
        all_snapshots_runs.append(snapshots_v)
        # Per-variant median terminal cumulative cases (for chart overlays).
        variant_terminal_p50[vi] = np.quantile(cum_v[-1], 0.5, axis=0)
        variant_meta.append({
            "id": variant.id,
            "label": variant.label,
            "citation": variant.citation,
        })

    # Concatenate Monte Carlo runs across variants -> ensemble (Reich 2019).
    cum_ensemble = np.concatenate(all_cum_runs, axis=1)             # (T+1, total_runs, n)
    snapshots_ensemble = np.concatenate(all_snapshots_runs, axis=1)  # (T+1, total_runs, n, 4)

    # Derived quantities used downstream.
    cumulative_infected = cum_ensemble
    final = snapshots_ensemble[-1]
    active = final[:, :, 1] + final[:, :, 2]
    prevalence_per_100k = (active / populations[None, :]) * 100_000.0
    prevalence_p50 = np.quantile(prevalence_per_100k, 0.5, axis=0)
    prevalence_p95 = np.quantile(prevalence_per_100k, 0.95, axis=0)
    cumulative_p50_final = np.quantile(cumulative_infected[-1], 0.5, axis=0)

    I_over_time = snapshots_ensemble[:, :, :, 2]
    I_per_cap_p50 = np.quantile(I_over_time / populations[None, None, :], 0.5, axis=1)
    THRESHOLD = 1e-5
    crossed = I_per_cap_p50 > THRESHOLD
    arrival_day = np.where(crossed.any(axis=0), crossed.argmax(axis=0), -1)
    arrival_day[start_idx] = 0

    qbands = np.quantile(cumulative_infected, QUANTILES, axis=1)  # (5, T+1, n)
    region_series = []
    for i, iso3 in enumerate(iso3_list):
        d_eff_val = float(d_eff_from_seed[i]) if np.isfinite(d_eff_from_seed[i]) else None
        arrival_val = int(arrival_day[i]) if arrival_day[i] >= 0 else None
        region_series.append({
            "iso3": iso3,
            "name": name_list[i],
            "population": int(populations[i]),
            "prevalence_p50_per_100k": float(prevalence_p50[i]),
            "prevalence_p95_per_100k": float(prevalence_p95[i]),
            "cumulative_p50_final": float(cumulative_p50_final[i]),
            "effective_distance_from_seed": d_eff_val,
            "predicted_arrival_day": arrival_val,
            "variants_terminal_p50": [float(v) for v in variant_terminal_p50[:, i]],
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

    # Export = total outbound mobility flux from each region weighted by I.
    # Use the canonical air+sea mobility (variant M2) for this aggregate so
    # the rankings stay stable across slider moves and don't flip with which
    # variant happens to dominate.
    m_canonical = combined_mobility(
        air_weight=params.air_weight,
        port_weight=params.port_weight,
        travel_restriction=params.travel_restriction,
    )
    flow = m_canonical * populations[:, None]
    out_flux_total = flow.sum(axis=1)
    export_score = (I_per_cap_p50 * out_flux_total[None, :]).sum(axis=0)
    export_score[start_idx] = 0.0
    export_order = np.argsort(-export_score)[:10]
    top_exports = [
        {
            "iso3": iso3_list[i],
            "name": name_list[i],
            "score": float(export_score[i]),
        }
        for i in export_order
    ]

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

    total_runs = sum(c.shape[1] for c in all_cum_runs)
    rng_meta = np.random.default_rng(42)  # deterministic perturbations metadata
    r0_med = params.r0
    inf_med = params.infectious_days
    inc_med = params.incubation_days

    return {
        "horizon_days": params.horizon_days,
        "regions": region_series,
        "top_imports": top_imports,
        "top_exports": top_exports,
        "spread_arcs": spread_arcs,
        "calibration": _build_calibration(cumulative_infected[-1], populations, start_idx, total_runs),
        "model_variants": variant_meta,
        "params_used": {
            "disease_id": params.disease_id,
            "start_iso3": params.start_iso3,
            "r0_median": float(r0_med),
            "infectious_days_median": float(inf_med),
            "incubation_days_median": float(inc_med),
            "intervention_multiplier": 1.0 - params.mask_intervention,
            "air_weight": params.air_weight,
            "port_weight": params.port_weight,
            "travel_restriction": params.travel_restriction,
            "cfr_pct": params.cfr_pct,
        },
    }
