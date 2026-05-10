"""Grid search across (theta, seed_multiplier) for all three diseases.

Looks for a single (theta, seed_mult) pair that improves all three scenarios
versus the literature defaults. If such a pair exists, the change is a
generalizable model improvement; if each disease prefers different settings,
that's overfitting and we should leave the defaults alone.

Run from backend/::
    python -m backtest.grid
"""

from __future__ import annotations

import math
from dataclasses import asdict

import numpy as np

from app import simulate as sim
from app.simulate import SimParams
from .run_backtest import _full_simulation
from .validate import (
    H1N1_DAY30_TRUTH, H1N1_CMP_DATE,
    MPOX_CMP_DATE,
    _load_owid_mpox_truth, _load_jhu_covid_truth,
    _spearman, _pearson, _top_precision,
)


def _eval(params: SimParams, truth: dict[str, int]) -> dict:
    cum, iso3 = _full_simulation(params)
    p2_5  = np.quantile(cum, 0.025, axis=0)
    p50   = np.quantile(cum, 0.5,   axis=0)
    p97_5 = np.quantile(cum, 0.975, axis=0)
    means = cum.mean(axis=0)

    pairs = []
    for i, iso in enumerate(iso3):
        if iso not in truth: continue
        pairs.append((iso, float(truth[iso]), float(p2_5[i]),
                      float(p50[i]), float(p97_5[i]), float(means[i])))
    if not pairs: return {}

    covered = sum(
        1 for _, a, lo, _, hi, _ in pairs
        if lo - 1e-6 <= a <= hi + 1e-6 or (a == 0 and hi < 1.0)
    )
    coverage = covered / len(pairs)

    a_log = [math.log10(p[1] + 1) for p in pairs]
    m_log = [math.log10(p[5] + 1) for p in pairs]
    rho = _spearman(m_log, a_log)
    r   = _pearson(m_log, a_log)
    log_errs = [abs(math.log10(p[3] + 1) - math.log10(p[1] + 1)) for p in pairs]
    med_mae = float(np.median(log_errs))

    others = [p for p in pairs if p[0] != params.start_iso3]
    others_truth = sorted(others, key=lambda p: -p[1])
    others_model = sorted(others, key=lambda p: -p[5])
    truth_iso = [p[0] for p in others_truth]
    model_iso = [p[0] for p in others_model]

    return {
        "n": len(pairs),
        "coverage": coverage,
        "rho": rho, "r": r, "med_log_mae": med_mae,
        "p5":  _top_precision(model_iso, truth_iso, 5),
        "p10": _top_precision(model_iso, truth_iso, 10),
    }


def _params(disease, iso, r0, inc, inf, port, seed, n_runs=500):
    return SimParams(
        disease_id=disease, start_iso3=iso,
        r0=r0, incubation_days=inc, infectious_days=inf,
        cfr_pct=1.0, air_weight=1.0, port_weight=port,
        travel_restriction=0.0, mask_intervention=0.0,
        horizon_days=30, n_runs=n_runs, seed_infected=seed,
    )


SCENARIOS = []  # filled in main


def main():
    covid_truth, covid_seed = _load_jhu_covid_truth()
    mpox_truth,  mpox_seed  = _load_owid_mpox_truth()
    h1n1_truth = dict(H1N1_DAY30_TRUTH)

    base = [
        ("COVID/CHN", covid_truth, covid_seed,
         dict(disease="covid19", iso="CHN", r0=2.5, inc=5.0, inf=6.0, port=0.3)),
        ("Mpox/GBR",  mpox_truth,  max(mpox_seed, 4),
         dict(disease="mpox",    iso="GBR", r0=1.6, inc=9.0, inf=14.0, port=0.3)),
        ("H1N1/MEX",  h1n1_truth,  50,
         dict(disease="flu",     iso="MEX", r0=1.5, inc=2.0, inf=4.0,  port=0.3)),
    ]

    thetas       = [0.05, 0.15, 0.25, 0.40]
    seed_mults   = [1, 5, 10, 25]

    print(f"\nGrid: theta in {thetas}, seed_mult in {seed_mults}")
    print(f"Each row: 3 scenarios x 1 model run = 3 sims, 500 MC each.\n")

    results = {}  # (theta, seed_mult) -> {scenario: metrics}

    from . import run_backtest as rb
    for theta in thetas:
        sim.THETA_IMPORT_COUPLING = theta
        rb.THETA_IMPORT_COUPLING = theta  # rb captured the binding at import time
        for sm in seed_mults:
            cell = {}
            for label, truth, base_seed, kw in base:
                p = _params(seed=int(base_seed * sm), **kw)
                cell[label] = _eval(p, truth)
            results[(theta, sm)] = cell

    # Restore default
    sim.THETA_IMPORT_COUPLING = 0.05

    # Print table
    print(f"\n{'theta':>5} {'seedX':>5} | {'COVID/CHN':<28}  {'Mpox/GBR':<28}  {'H1N1/MEX':<28}")
    print(f"{'':>5} {'':>5} | {'cov  rho   r    p5  logMAE':<28}  {'cov  rho   r    p5  logMAE':<28}  {'cov  rho   r    p5  logMAE':<28}")
    print("-" * 105)
    for (theta, sm), cell in results.items():
        row = f"{theta:>5.2f} {sm:>5d} | "
        for label in ["COVID/CHN", "Mpox/GBR", "H1N1/MEX"]:
            m = cell[label]
            row += (f"{m['coverage']*100:>3.0f}% {m['rho']:+.2f} {m['r']:+.2f} "
                    f"{m['p5']*100:>3.0f}% {m['med_log_mae']:>5.2f}  ")
        print(row)

    # Composite score: average rho across 3 scenarios (rank corr is the most
    # robust signal; coverage and log MAE shift with seed scale).
    print(f"\n{'='*78}\nGeneralizable settings (avg Spearman rho across all 3 diseases):")
    print(f"{'='*78}")
    scored = []
    for (theta, sm), cell in results.items():
        rhos = [cell[lbl]["rho"] for lbl in cell]
        avg_rho = sum(rhos) / len(rhos)
        avg_p5  = sum(cell[lbl]["p5"] for lbl in cell) / 3
        avg_cov = sum(cell[lbl]["coverage"] for lbl in cell) / 3
        avg_mae = sum(cell[lbl]["med_log_mae"] for lbl in cell) / 3
        scored.append((avg_rho, avg_p5, avg_cov, avg_mae, theta, sm))
    scored.sort(reverse=True)
    print(f"  {'rank':>4}  theta seedX | avg_rho avg_p5 avg_cov avg_logMAE")
    for i, (rho, p5, cov, mae, theta, sm) in enumerate(scored[:8], 1):
        print(f"  {i:>4}  {theta:>5.2f} {sm:>5d} |   {rho:+.3f}   {p5*100:>4.1f}% {cov*100:>5.1f}%    {mae:>5.3f}")

    print(f"\n  default (theta=0.05, seedX=1) ranks #{next(i for i,t in enumerate(scored,1) if t[4]==0.05 and t[5]==1)}/{len(scored)}")


if __name__ == "__main__":
    main()
