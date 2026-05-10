"""Offline calibration metrics against the Wuhan-2020 frozen JHU snapshot.

Runs the Monte Carlo SEIR with the Wuhan seed and scores the ensemble at day
30 against `data/backtest_wuhan_2020.json`, a frozen snapshot of JHU CSSE
country-level confirmed cases as of 2020-01-30. Three calibration scores per
holdout country, averaged into a single number per metric:

- 95% interval coverage: fraction of holdout countries whose JHU truth lies
  inside the deflated 2.5%/97.5% band of the ensemble. Well-calibrated ~ 0.95.
- 50% interval coverage: same against the 25%/75% band. Well-calibrated ~ 0.50.
- CRPS (Funk et al. 2018, Epidemics): proper score for the ensemble vs scalar
  truth, averaged over holdouts. Normalised per 100k population so it is
  dimensionless and comparable across runs.
- Multibin log score (Reich et al. 2019, PNAS FluSight): log probability of
  the 20-bin quantile bucket containing the truth, averaged over holdouts.

The simulator tracks infections, not confirmed cases, so projected counts are
deflated by a fixed reporting fraction (rho = 0.10 for early-2020 surveillance
ramp-up, sourced from Imperial College and CDC retrospectives) before scoring
against JHU CSSE confirmed counts.

Frozen ground truth means the harness runs offline with no network calls,
keeping the demo deterministic and reproducible. Result is cached via
lru_cache so /simulate pays the backtest cost once per process.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np

from .calibration import _ensemble_crps, _multibin_log_score
from .effective_distance import effective_distance_from
from .mobility import air_flow_matrix, combined_mobility, country_index, load_countries

DATA_FILE = Path(__file__).parent / "data" / "backtest_wuhan_2020.json"


@dataclass(frozen=True)
class BacktestResult:
    scenario_id: str
    holdout_count: int
    coverage_95: float
    coverage_50: float
    crps_norm_per_100k: float
    multibin_log_score: float
    reporting_fraction: float
    note: str

    def to_dict(self) -> dict:
        return asdict(self)


def _load_config() -> dict:
    return json.loads(DATA_FILE.read_text())


@lru_cache(maxsize=1)
def compute_wuhan_calibration() -> BacktestResult:
    cfg = _load_config()
    horizon = int(cfg["horizon_days"])
    rho = float(cfg["reporting_fraction"])
    seed_iso = str(cfg["seed_iso3"]).upper()
    seed_infected = int(cfg.get("seed_infected", 500))
    truth: dict[str, float] = {iso.upper(): float(v) for iso, v in cfg["ground_truth"].items()}
    scenario_id = str(cfg.get("scenario_id", "wuhan_2020"))

    # Lazy imports to avoid `simulate -> backtest -> simulate` import cycle.
    from .simulate import SimParams, _seed_distribution, _seir_ensemble

    countries = load_countries()
    iso_to_idx = country_index()
    n_regions = len(countries)
    populations = np.array([c.population for c in countries], dtype=np.float64)

    if seed_iso not in iso_to_idx:
        return BacktestResult(
            scenario_id=scenario_id,
            holdout_count=0,
            coverage_95=float("nan"),
            coverage_50=float("nan"),
            crps_norm_per_100k=float("nan"),
            multibin_log_score=float("nan"),
            reporting_fraction=rho,
            note=f"seed iso3 {seed_iso} not in modeled regions",
        )
    seed_idx = iso_to_idx[seed_iso]

    # Match the canonical run() pipeline: combined air+sea mobility, fixed
    # theta, point-source seeding for a single-city outbreak.
    base = SimParams(
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

    m = combined_mobility(
        air_weight=base.air_weight,
        port_weight=base.port_weight,
        travel_restriction=base.travel_restriction,
    )
    air_flow = air_flow_matrix()
    d_eff_seed = effective_distance_from(air_flow, seed_idx)
    seed_dist = _seed_distribution(n_regions, seed_idx, seed_infected, "point", d_eff_seed)

    _snapshots, cum = _seir_ensemble(
        base,
        mobility_matrix=m,
        theta=0.05,
        seed_distribution=seed_dist,
        populations=populations,
        n_runs=base.n_runs,
        rng_seed=2026,
    )
    # cum shape: (T+1, n_runs, n_regions). Take terminal-day infections.
    terminal = cum[horizon]  # (n_runs, n_regions)

    # Filter holdout to regions we actually model.
    holdout = [iso for iso in truth if iso in iso_to_idx and iso != seed_iso]
    if not holdout:
        return BacktestResult(
            scenario_id=scenario_id,
            holdout_count=0,
            coverage_95=float("nan"),
            coverage_50=float("nan"),
            crps_norm_per_100k=float("nan"),
            multibin_log_score=float("nan"),
            reporting_fraction=rho,
            note="no overlap between ground truth and modeled regions",
        )

    cov_95 = 0
    cov_50 = 0
    crps_vals: list[float] = []
    log_scores: list[float] = []
    for iso in holdout:
        col = terminal[:, iso_to_idx[iso]] * rho  # deflate to confirmed-case scale
        truth_val = truth[iso]
        lo95, hi95 = np.quantile(col, [0.025, 0.975])
        lo50, hi50 = np.quantile(col, [0.25, 0.75])
        cov_95 += int(lo95 <= truth_val <= hi95)
        cov_50 += int(lo50 <= truth_val <= hi50)
        scale = max(populations[iso_to_idx[iso]], 1.0)
        crps_vals.append(_ensemble_crps(col, truth_val) / scale * 100_000.0)
        log_scores.append(_multibin_log_score(col, truth_val))

    n = len(holdout)
    return BacktestResult(
        scenario_id=scenario_id,
        holdout_count=n,
        coverage_95=cov_95 / n,
        coverage_50=cov_50 / n,
        crps_norm_per_100k=float(np.mean(crps_vals)),
        multibin_log_score=float(np.mean(log_scores)),
        reporting_fraction=rho,
        note=(
            "CRPS, multibin log score, and 50%/95% coverage measured against the "
            "JHU CSSE confirmed-case snapshot at day 30 of the Wuhan-2020 backtest, "
            "deflated by the early-2020 reporting-fraction prior. Frozen JSON ground "
            "truth; runs offline."
        ),
    )


def reset_cache() -> None:
    """Clear the lru_cache so a fresh backtest is computed on next call.

    Used by tests that want to re-run the harness after monkeypatching.
    """
    compute_wuhan_calibration.cache_clear()
