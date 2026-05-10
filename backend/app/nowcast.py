"""Particle-filter nowcast: re-weight the Monte Carlo ensemble against observed
case counts.

Implements an importance-sampling variant of the Funk et al. 2018 (Epidemics)
real-time forecasting recipe. Each particle is one realisation of the SEIR
ensemble with its own (R0, infectious period, incubation period, reporting
fraction rho) parameter draw. The likelihood of the user-supplied observed
cumulative-case time series under each particle is

    log L_p = sum_t  Poisson( y_t | rho_p * cumulative_p[t, seed_idx] )

where cumulative_p[t, seed_idx] is the model's cumulative infections in the
seed region on day t. We then form posterior weights w_p ~ exp(log L_p),
normalise, and report posterior-weighted quantile bands for the seed region
(and any other region we want to inspect). No resampling is needed because
the ensemble trajectories are deterministic given each particle's parameter
draw.

The function is a single-model nowcast running the canonical air+sea SEIR
variant (Balcan 2009 / Chinazzi 2020 architecture) at higher particle count.
The 4-model ensemble lives in `simulate.run`; here we want a clean single
posterior to report against the data.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .effective_distance import effective_distance_from
from .mobility import air_flow_matrix, combined_mobility, country_index, load_countries
from .simulate import SimParams, _seed_distribution, _seir_ensemble


@dataclass
class NowcastObservation:
    day: int
    cumulative_cases: float


@dataclass
class NowcastParams:
    base: SimParams
    observations: list[NowcastObservation]
    n_particles: int = 400
    rho_min: float = 0.02
    rho_max: float = 0.5
    # Log-space Gaussian width on cumulative cases. Wide because cumulative
    # epidemic data is heavily over-dispersed (under-reporting + delayed
    # reporting). 1.2 ~ e^1.2 = 3.3x multiplicative SD per observation, which
    # avoids weight collapse to a single particle while still concentrating
    # mass on plausible trajectories.
    obs_sigma: float = 1.2


def _log_gaussian_log_pmf(lam: np.ndarray, k: float, sigma: float) -> np.ndarray:
    """Log-space Gaussian likelihood: y ~ LogNormal(log(rho * cum), sigma).

    Returns log p(y | mu, sigma) up to additive constants that cancel under
    weight normalisation. We use this instead of a strict Poisson because
    cumulative-case data spans several orders of magnitude during exponential
    growth and a Poisson likelihood collapses all posterior mass onto a
    single particle (effective sample size -> 1). The log-Normal handles
    multiplicative deviations gracefully and is the standard choice in
    epidemic nowcasting (Funk et al. 2018, Eqn. 3).

    `lam` is the model-predicted observed count (P-vector); `k` is the truth.
    """
    lam = np.maximum(lam, 1e-3)
    k_safe = max(float(k), 1e-3)
    diff = np.log(lam) - np.log(k_safe)
    return -0.5 * (diff / sigma) ** 2


def run_nowcast(params: NowcastParams) -> dict:
    if not params.observations:
        raise ValueError("nowcast requires at least one observation")

    countries = load_countries()
    iso_to_idx = country_index()
    if params.base.start_iso3 not in iso_to_idx:
        raise ValueError(f"Unknown start country: {params.base.start_iso3}")
    seed_idx = iso_to_idx[params.base.start_iso3]
    n = len(countries)
    populations = np.array([c.population for c in countries], dtype=np.float64)

    # Validate observations against the simulation horizon.
    max_day = max(o.day for o in params.observations)
    if max_day < 0 or max_day > params.base.horizon_days:
        raise ValueError(
            f"observations day range [0, {max_day}] exceeds simulation horizon "
            f"{params.base.horizon_days}"
        )

    # Canonical air+sea mobility (variant M2).
    m = combined_mobility(
        air_weight=params.base.air_weight,
        port_weight=params.base.port_weight,
        travel_restriction=params.base.travel_restriction,
    )

    air_flow = air_flow_matrix()
    d_eff_seed = effective_distance_from(air_flow, seed_idx)
    seed_dist = _seed_distribution(n, seed_idx, params.base.seed_infected, "point", d_eff_seed)

    # Run the SEIR ensemble at the requested particle count.
    snapshots, cum = _seir_ensemble(
        params.base,
        mobility_matrix=m,
        theta=0.05,
        seed_distribution=seed_dist,
        populations=populations,
        n_runs=params.n_particles,
        rng_seed=2026,
    )
    # cum shape: (T+1, n_particles, n)

    # Per-particle reporting-fraction draw, independent of SEIR perturbations.
    rng = np.random.default_rng(2027)
    rho = rng.uniform(params.rho_min, params.rho_max, size=params.n_particles)

    # Particle log-likelihoods. Log-space Gaussian on cumulative reported
    # cases so the posterior degrades gracefully when the prior R0 is far
    # from the data (avoids ESS -> 1 collapse seen with strict Poisson).
    log_lik = np.zeros(params.n_particles, dtype=np.float64)
    for obs in params.observations:
        lam = rho * cum[obs.day, :, seed_idx]
        log_lik += _log_gaussian_log_pmf(lam, float(obs.cumulative_cases), params.obs_sigma)

    # Normalise to weights, robust to large negative log-liks.
    log_lik -= log_lik.max()
    weights = np.exp(log_lik)
    w_sum = weights.sum()
    if w_sum <= 0 or not np.isfinite(w_sum):
        # Pathological likelihood surface; fall back to uniform weights.
        weights = np.ones_like(weights)
        w_sum = weights.sum()
    weights /= w_sum

    # Effective sample size: 1 / sum(w^2). High = data is non-informative,
    # low = the prior is far from the observations.
    ess = float(1.0 / np.sum(weights**2))

    # Weighted quantile bands for the seed region trajectory.
    seed_traj = cum[:, :, seed_idx]  # (T+1, n_particles)
    quantiles = (0.025, 0.25, 0.5, 0.75, 0.975)
    posterior_bands: dict[str, list[float]] = {}
    for q, key in zip(quantiles, ("p2_5", "p25", "p50", "p75", "p97_5")):
        posterior_bands[key] = [
            float(_weighted_quantile(seed_traj[t], weights, q)) for t in range(seed_traj.shape[0])
        ]

    # Posterior summaries on the parameter draws. R0 is encoded in the SEIR
    # ensemble's per-particle perturbations (matching the rng_seed used in
    # _seir_ensemble); reconstruct it the same way for consistent reporting.
    sample_rng = np.random.default_rng(2026)
    r0_samples = np.clip(
        sample_rng.normal(params.base.r0, 0.15 * max(params.base.r0, 0.5), params.n_particles),
        0.1, 8.0,
    )

    r0_post_median = float(_weighted_quantile(r0_samples, weights, 0.5))
    r0_post_lo = float(_weighted_quantile(r0_samples, weights, 0.025))
    r0_post_hi = float(_weighted_quantile(r0_samples, weights, 0.975))
    rho_post_median = float(_weighted_quantile(rho, weights, 0.5))
    rho_post_lo = float(_weighted_quantile(rho, weights, 0.025))
    rho_post_hi = float(_weighted_quantile(rho, weights, 0.975))

    return {
        "horizon_days": params.base.horizon_days,
        "seed_iso3": params.base.start_iso3,
        "posterior_quantiles": posterior_bands,
        "observations": [
            {"day": o.day, "cumulative_cases": o.cumulative_cases}
            for o in params.observations
        ],
        "posterior_summary": {
            "n_particles": params.n_particles,
            "effective_sample_size": ess,
            "r0_prior_median": float(params.base.r0),
            "r0_posterior_median": r0_post_median,
            "r0_posterior_95": [r0_post_lo, r0_post_hi],
            "rho_prior_range": [params.rho_min, params.rho_max],
            "rho_posterior_median": rho_post_median,
            "rho_posterior_95": [rho_post_lo, rho_post_hi],
        },
        "note": (
            "Importance-sampled posterior over (R0, infectious period, "
            "incubation period, rho) given the user-supplied observed seed-region "
            "cumulative cases. Methodology: Funk et al. 2018 (Epidemics). "
            "Effective sample size below ~50 means the data lie far from the prior."
        ),
    }


def _weighted_quantile(values: np.ndarray, weights: np.ndarray, q: float) -> float:
    """Cumulative-weight inverse-CDF quantile. Stable for w that sum to 1."""
    order = np.argsort(values)
    v = values[order]
    w = weights[order]
    cw = np.cumsum(w)
    idx = int(np.searchsorted(cw, q))
    idx = min(max(idx, 0), len(v) - 1)
    return float(v[idx])
