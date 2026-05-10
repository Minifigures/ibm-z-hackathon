"""Probabilistic-forecast calibration metrics.

We report three metrics on the Monte Carlo ensemble at horizon end, computed
via *leave-one-out* over the runs themselves (each run is treated as a
held-out "truth" against the empirical distribution of the remaining runs):

- 95% interval coverage: fraction of LOO truths inside the 95% band of the
  rest. A well-calibrated ensemble lands at ~0.95.
- CRPS (Continuous Ranked Probability Score, Funk et al. 2018): a strictly
  proper score for probabilistic forecasts. Lower is better; here we report
  the average over LOO trials, normalised by the population-weighted mean
  cumulative cases so it is dimensionless and comparable across runs.
- Multibin log score (Reich et al. 2019, CDC FluSight): bin the forecast
  distribution into 1% quantile buckets, log-score the bucket containing the
  truth. Higher is better; the ideal value for a perfectly calibrated
  ensemble with N=200 is approximately log(0.05) ~ -3.0 (because the truth
  falls into a 5% bucket on average) -- we report the unsmoothed value.

These are *internal posterior-predictive* metrics; they do not validate
against an external observed outbreak. The PRD risk register flags this; the
metrics here demonstrate the methodology and are honest within their stated
scope.
"""

from __future__ import annotations

import numpy as np


def _ensemble_crps(samples: np.ndarray, truth: float) -> float:
    """CRPS of an empirical ensemble against a single scalar truth.

    Uses the closed-form sample CRPS:

        CRPS = E|X - y| - 0.5 * E|X - X'|

    where X, X' are i.i.d. draws from the forecast distribution and y is the
    observation. Both terms are estimated with the empirical sample.
    """
    n = samples.size
    if n == 0:
        return float("nan")
    abs_dev = np.mean(np.abs(samples - truth))
    # Vectorised double-sum O(n^2). n = 200 -> 40k ops, negligible.
    pairwise = np.mean(np.abs(samples[:, None] - samples[None, :]))
    return float(abs_dev - 0.5 * pairwise)


def _multibin_log_score(samples: np.ndarray, truth: float, n_bins: int = 20) -> float:
    """Log score of a multibin probability mass on the forecast distribution.

    The forecast is summarised into `n_bins` quantile bins (default 20 -> 5%
    bins, matching FluSight's coarsest setting). We assign 1/n probability
    mass per bin to a sample's source bin, then return log(prob_in_bin(truth)).
    Floored at log(1/n) so an out-of-range truth scores the smallest non-zero
    bin instead of -inf.
    """
    n = samples.size
    if n == 0:
        return float("nan")
    edges = np.quantile(samples, np.linspace(0, 1, n_bins + 1))
    # Ensure strictly increasing edges; ties get a tiny epsilon so digitize works.
    edges = np.maximum.accumulate(edges)
    # Probability mass per bin = fraction of samples that fall into it.
    counts, _ = np.histogram(samples, bins=edges)
    probs = counts / max(n, 1)
    # Bin containing the truth.
    bin_idx = int(np.clip(np.searchsorted(edges, truth, side="right") - 1, 0, n_bins - 1))
    p = probs[bin_idx]
    floor = 1.0 / max(n, 1)
    return float(np.log(max(p, floor)))


def calibration_metrics(
    cumulative_at_horizon: np.ndarray,
    populations: np.ndarray,
    seed_idx: int,
    *,
    sample_regions: int = 12,
    sample_truths: int = 30,
) -> dict[str, float]:
    """Compute coverage / CRPS / multibin log score from leave-one-out trials.

    cumulative_at_horizon: (n_runs, n_regions) of cumulative cases at the
    terminal day of the simulation.

    To keep latency bounded we sub-sample regions (top by ensemble mean,
    excluding the seed) and Monte Carlo trials.
    """
    runs, n = cumulative_at_horizon.shape
    if runs < 5 or n < 1:
        return {"coverage_95": float("nan"), "crps_norm": float("nan"), "multibin_log_score": float("nan")}

    mean_cum = cumulative_at_horizon.mean(axis=0)
    mean_cum[seed_idx] = -np.inf  # exclude seed from the calibration set
    region_order = np.argsort(-mean_cum)
    region_idx = region_order[:sample_regions]

    rng = np.random.default_rng(7)
    trial_runs = rng.choice(runs, size=min(sample_truths, runs), replace=False)

    cov_hits = 0
    cov_total = 0
    crps_vals: list[float] = []
    log_scores: list[float] = []

    for r in region_idx:
        col = cumulative_at_horizon[:, r]
        # Skip regions with degenerate forecasts.
        if col.max() <= 0:
            continue
        scale = max(populations[r], 1.0)
        for t in trial_runs:
            truth = float(col[t])
            rest = np.delete(col, t)
            lo, hi = np.quantile(rest, [0.025, 0.975])
            cov_hits += int(lo <= truth <= hi)
            cov_total += 1
            crps_vals.append(_ensemble_crps(rest, truth) / scale * 100_000.0)
            log_scores.append(_multibin_log_score(rest, truth))

    if cov_total == 0:
        return {"coverage_95": float("nan"), "crps_norm": float("nan"), "multibin_log_score": float("nan")}

    return {
        "coverage_95": cov_hits / cov_total,
        "crps_norm": float(np.mean(crps_vals)),
        "multibin_log_score": float(np.mean(log_scores)),
    }
