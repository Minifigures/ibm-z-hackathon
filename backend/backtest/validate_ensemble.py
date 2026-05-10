"""Same as validate.py but uses the production 4-model ensemble run().

This is the apples-to-apples comparison against the API: every metric
computed here is what /simulate would return.
"""

from __future__ import annotations

import math
import numpy as np

from app.simulate import SimParams, run as ensemble_run
from .validate import (
    H1N1_DAY30_TRUTH, H1N1_CMP_DATE, H1N1_SEED_INITIAL,
    MPOX_CMP_DATE,
    SARS_DAY30_TRUTH, SARS_CMP_DATE, SARS_SEED_INITIAL,
    _load_owid_mpox_truth, _load_jhu_covid_truth,
    _spearman, _pearson, _top_precision,
)


def _validate_ensemble(scenario: str, params: SimParams, truth: dict[str, int]) -> dict:
    print(f"\n{'='*78}\n{scenario}\n{'='*78}")
    print(f"  seed: {params.start_iso3} with {params.seed_infected}, R0={params.r0}, "
          f"horizon={params.horizon_days}d, runs={params.n_runs} (4-variant ensemble)")
    res = ensemble_run(params)

    # Pull per-region terminal cumulative infected quantile bands.
    # res["regions"][i] has: iso3, cumulative_p50_final, prevalence_*, quantiles{p2_5,...,p97_5}
    # quantiles are time series; we want the LAST timestep.
    pairs = []
    for region in res["regions"]:
        iso = region["iso3"]
        if iso not in truth: continue
        q = region["quantiles"]
        # quantiles are arrays over time; cumulative_p50_final is the final p50
        # but for p2.5 / p97.5 at horizon end we need to pull from the time series.
        # However the q values are I/N (prevalence), not cumulative. We need
        # cumulative final from the response: there isn't a per-region cum p2.5.
        # Workaround: use cumulative_p50_final (median) and approximate bands
        # via a Poisson-ish factor — this is rough. Better: use the regions'
        # cumulative quantiles if exposed.
        # The response exposes cumulative_p50_final but no cumulative_p2_5_final.
        # To stay rigorous we'll compare median + use prevalence_p95 to estimate
        # band width as a sanity check; coverage will be approximate.
        med = float(region.get("cumulative_p50_final", 0))
        prev_p50 = float(region.get("prevalence_p50_per_100k", 0))
        prev_p95 = float(region.get("prevalence_p95_per_100k", prev_p50))
        upper_ratio = (prev_p95 / prev_p50) if prev_p50 > 0 else 1.0
        hi = med * max(upper_ratio, 1.0)
        lo = med / max(upper_ratio, 1.0)
        pairs.append({
            "iso3": iso, "actual": float(truth[iso]),
            "p2_5": lo, "p50": med, "p97_5": hi, "mean": med,
        })

    if not pairs:
        print("  no overlap"); return {}

    covered = sum(1 for p in pairs if p["p2_5"] - 1e-6 <= p["actual"] <= p["p97_5"] + 1e-6
                  or (p["actual"] == 0 and p["p97_5"] < 1.0))
    coverage = covered / len(pairs)
    log_errs = [abs(math.log10(p["p50"] + 1) - math.log10(p["actual"] + 1)) for p in pairs]
    med_log_mae = float(np.median(log_errs))

    actual_log = [math.log10(p["actual"] + 1) for p in pairs]
    model_log  = [math.log10(p["mean"]  + 1) for p in pairs]
    rho   = _spearman(model_log, actual_log)
    r_log = _pearson(model_log, actual_log)

    model_rank = sorted(
        [(p["iso3"], p["mean"]) for p in pairs if p["iso3"] != params.start_iso3],
        key=lambda x: -x[1])
    truth_rank = sorted(
        [(p["iso3"], p["actual"]) for p in pairs if p["iso3"] != params.start_iso3],
        key=lambda x: -x[1])
    model_iso = [iso for iso, _ in model_rank]
    truth_iso = [iso for iso, _ in truth_rank]
    p5  = _top_precision(model_iso, truth_iso, 5)
    p10 = _top_precision(model_iso, truth_iso, 10)

    print(f"  countries compared: {len(pairs)}")
    print(f"  coverage_95pi (approx): {coverage*100:5.1f}%")
    print(f"  spearman_rho_log : {rho:+.3f}")
    print(f"  pearson_r_log    : {r_log:+.3f}")
    print(f"  top5_precision   : {p5*100:5.1f}%   model={model_iso[:5]}")
    print(f"                                truth={truth_iso[:5]}")
    print(f"  top10_precision  : {p10*100:5.1f}%")
    print(f"  median_log_mae   : {med_log_mae:.3f}")

    return {
        "scenario": scenario, "n": len(pairs),
        "coverage_95pi": coverage, "spearman_rho_log": rho, "pearson_r_log": r_log,
        "top5_precision": p5, "top10_precision": p10, "median_log_mae": med_log_mae,
    }


def _params(disease, iso, r0, inc, inf, port, seed, horizon=30, n_runs=800):
    return SimParams(
        disease_id=disease, start_iso3=iso,
        r0=r0, incubation_days=inc, infectious_days=inf,
        cfr_pct=1.0, air_weight=1.0, port_weight=port,
        travel_restriction=0.0, mask_intervention=0.0,
        horizon_days=horizon, n_runs=n_runs, seed_infected=seed,
    )


if __name__ == "__main__":
    results = []

    covid_truth, covid_seed = _load_jhu_covid_truth()
    results.append(_validate_ensemble(
        "COVID-19 / CHN / 2020-01-22 (ensemble)",
        _params("covid19", "CHN", 2.5, 5.0, 6.0, 0.3, covid_seed),
        covid_truth))

    mpox_truth, mpox_seed = _load_owid_mpox_truth()
    results.append(_validate_ensemble(
        "Mpox 2022 / GBR / 2022-05-13 (ensemble)",
        _params("mpox", "GBR", 1.6, 9.0, 14.0, 0.3, mpox_seed),
        mpox_truth))

    h1n1_truth = dict(H1N1_DAY30_TRUTH)
    results.append(_validate_ensemble(
        "2009 H1N1 / MEX / 2009-04-26 (ensemble)",
        _params("flu", "MEX", 1.5, 2.0, 4.0, 0.3, H1N1_SEED_INITIAL),
        h1n1_truth))

    sars_truth = dict(SARS_DAY30_TRUTH)
    results.append(_validate_ensemble(
        "2003 SARS / CHN / 2003-03-12 (ensemble)",
        _params("sars", "CHN", 2.7, 6.0, 8.0, 0.3, SARS_SEED_INITIAL),
        sars_truth))

    print(f"\n{'='*78}\nSUMMARY (4-model ensemble + UN migrants + BTS + corridors)\n{'='*78}")
    print(f"{'scenario':<55} {'n':>4} {'cov95':>6} {'rho':>6} {'r':>6} {'top5':>5} {'top10':>6} {'logMAE':>7}")
    for r in results:
        if not r: continue
        print(f"{r['scenario']:<55} {r['n']:>4} "
              f"{r['coverage_95pi']*100:>5.1f}% "
              f"{r['spearman_rho_log']:+.3f} {r['pearson_r_log']:+.3f} "
              f"{r['top5_precision']*100:>4.0f}% {r['top10_precision']*100:>5.0f}% "
              f"{r['median_log_mae']:>7.3f}")
