"""Multi-disease, multi-metric model validation.

Tests the SEIR + gravity + Monte Carlo model against real day-+30 case counts
for three historical outbreaks, using only literature-default parameters
(no per-scenario tuning):

  COVID-19 / CHN seed / 2020-01-22 -> JHU CSSE day +30 confirmed cases
  Mpox 2022 / GBR seed / 2022-05-13 -> OWID monkeypox dataset day +30
  2009 H1N1 / MEX seed / 2009-04-26 -> WHO Sit-Rep No. 28 day +30

For each, computes:

  coverage_95pi        fraction of countries whose actual is in [p2.5, p97.5]
  spearman_rho_log     Spearman rho on log10(actual+1) vs log10(model_mean+1)
  pearson_r_log        Pearson  r  on the same
  top5_precision       |model_top5 ∩ truth_top5| / 5
  top10_precision      |model_top10 ∩ truth_top10| / 10
  median_log_mae       median |log10(model_p50+1) - log10(actual+1)|

Run from backend/::
    python -m backtest.validate
"""

from __future__ import annotations

import csv
import math
from pathlib import Path

import numpy as np

from app.simulate import SimParams
from .run_backtest import _full_simulation
from .jhu_data import load_country_counts


# ---------------------------------------------------------------------------
# Real-world day-+30 truth tables
# ---------------------------------------------------------------------------

# COVID-19: pulled from cached JHU CSSE file.

# 2009 H1N1 (Influenza A H1N1pdm09)
# Source: WHO Pandemic (H1N1) 2009 Situation Update No. 28 (28 May 2009).
# The first lab-confirmed case in Mexico was 2009-04-26 (US CDC ascertained
# 2009-04-21). Day +30 from 2009-04-26 is 2009-05-26. The May 28 sit-rep is
# the closest published archive snapshot. These are CONFIRMED LAB cases
# only; true infections were 10-100x larger due to extensive undertesting.
H1N1_DAY30_TRUTH = {
    "MEX":  4910,  # seed
    "USA":  6764,
    "CAN":   805,
    "ESP":   138,
    "GBR":   137,
    "JPN":     4,
    "DEU":    14,
    "FRA":    16,
    "NZL":    9,
    "ISR":    9,
    "ITA":    19,
    "AUS":    7,
    "KOR":    21,
    "CHN":    7,
    "BRA":     8,
    "ARG":     1,
    "CHL":    24,
    "COL":    11,
    "CRI":    33,
    "GTM":     3,
    "PER":     1,
    "SWE":     2,
    "NLD":     3,
    "BEL":    12,
    "AUT":     1,
    "POL":     1,
    "CHE":     1,
    "NOR":     2,
    "DNK":     1,
    "PRT":     1,
    "IRL":     1,
}
H1N1_SEED_DATE = "2009-04-26"
H1N1_CMP_DATE  = "2009-05-26"
H1N1_SEED_INITIAL = 1500  # Lipsitch 2009 (Influenza Other Respir Viruses): true infections in Mexico were ~30x lab-confirmed by Apr 24, 2009. WHO confirmed 26 cases; literature estimate ~1000-5000 true.

# Mpox 2022 day-+30 truth: extracted at runtime from OWID monkeypox CSV.
MPOX_SEED_DATE = "2022-05-13"
MPOX_CMP_DATE  = "2022-06-13"

# SARS 2003 day-+30 truth: WHO Sit-Rep 24 (April 11, 2003), ~30 days after
# the WHO global alert on March 12, 2003. Probable case counts; the WHO
# archive is the canonical source. Riley et al. 2003 Science estimated true
# infections in mainland China were larger but officially reported counts
# are what the disease forecasting community benchmarks against.
SARS_DAY30_TRUTH = {
    "CHN": 1290,  # mainland China (Guangdong + Beijing + others)
    "HKG":  988,
    "SGP":  153,
    "CAN":  100,  # Toronto cluster
    "VNM":   62,
    "TWN":   23,
    "USA":   35,
    "DEU":    6,
    "GBR":    5,
    "FRA":    5,
    "ITA":    3,
    "ROU":    1,
    "IRL":    1,
    "CHE":    1,
}
SARS_SEED_DATE     = "2003-03-12"
SARS_CMP_DATE      = "2003-04-11"
# By WHO global alert (Mar 12, 2003), Chinese mainland had ~150 reported
# cases, but Riley et al. 2003 (Science) and CDC retrospective analyses
# put true infections at ~800 by then (cryptic spread within Guangdong
# before international notification).
SARS_SEED_INITIAL  = 800

# Ebola 2014 West Africa day-+30 truth: cmrivers/ebola country_timeseries.
# WHO formal notification was 2014-03-23. The next 30 days saw spread within
# Guinea + first crossings into Liberia (overland through Lofa County). Source
# CSV has gaps per country/per day; we use the closest available datapoint
# in the [Apr 16, Apr 23] window for each country. This is a known-hard test
# for an air-mobility-only model: Ebola moved via porous land borders, and
# the model's air gravity does not capture it.
EBOLA_DAY30_TRUTH = {
    "GIN": 218,   # 2014-04-23 (WHO Sit-Rep)
    "LBR":  27,   # 2014-04-17 (most recent populated entry pre-day+30)
    "SLE":   0,   # 2014-04-23 — first SLE confirmed case was May 25
}
EBOLA_SEED_DATE    = "2014-03-23"
EBOLA_CMP_DATE     = "2014-04-22"
# WHO Ebola Response Team 2014 NEJM backcalculated true infections in Guinea
# at ~2x to 3x the lab-confirmed. Lab-confirmed on Mar 23 was ~50; use 100.
EBOLA_SEED_INITIAL = 100


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


def _spearman(x: list[float], y: list[float]) -> float:
    """Spearman rank correlation. Returns nan if degenerate."""
    if len(x) < 3: return float("nan")
    n = len(x)
    rx = _ranks(x)
    ry = _ranks(y)
    return _pearson(rx, ry)


def _ranks(arr: list[float]) -> list[float]:
    """Average-rank for ties."""
    indexed = sorted(enumerate(arr), key=lambda p: p[1])
    ranks = [0.0] * len(arr)
    i = 0
    while i < len(indexed):
        j = i
        while j + 1 < len(indexed) and indexed[j + 1][1] == indexed[i][1]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[indexed[k][0]] = avg
        i = j + 1
    return ranks


def _pearson(x: list[float], y: list[float]) -> float:
    if len(x) < 2: return float("nan")
    mx = sum(x) / len(x); my = sum(y) / len(y)
    num = sum((a - mx) * (b - my) for a, b in zip(x, y))
    dx = math.sqrt(sum((a - mx) ** 2 for a in x))
    dy = math.sqrt(sum((b - my) ** 2 for b in y))
    if dx == 0 or dy == 0: return float("nan")
    return num / (dx * dy)


def _top_precision(model_rank: list[str], truth_rank: list[str], k: int) -> float:
    return len(set(model_rank[:k]) & set(truth_rank[:k])) / k


# ---------------------------------------------------------------------------
# Validation runner
# ---------------------------------------------------------------------------


def _validate(scenario: str, params: SimParams, truth: dict[str, int], cmp_date: str):
    """Run model, compute metrics, return dict."""
    print(f"\n{'='*78}\n{scenario}\n{'='*78}")
    print(f"  seed: {params.start_iso3} with {params.seed_infected} infected, R0={params.r0}, "
          f"horizon={params.horizon_days}d, runs={params.n_runs}, port_w={params.port_weight}")
    print(f"  truth: day +30 ({cmp_date}), {len(truth)} countries with data")

    cum, iso3_list = _full_simulation(params)  # (n_runs, n_regions)
    p2_5  = np.quantile(cum, 0.025, axis=0)
    p50   = np.quantile(cum, 0.5,   axis=0)
    p97_5 = np.quantile(cum, 0.975, axis=0)
    means = cum.mean(axis=0)

    # Build joined arrays (only countries present in BOTH truth and model)
    pairs = []
    for i, iso in enumerate(iso3_list):
        if iso not in truth: continue
        pairs.append({
            "iso3": iso,
            "actual": float(truth[iso]),
            "p2_5": float(p2_5[i]),
            "p50":  float(p50[i]),
            "p97_5": float(p97_5[i]),
            "mean": float(means[i]),
        })
    if not pairs:
        print("  NO OVERLAP between truth and model regions"); return {}

    # Coverage (actual in [p2.5, p97.5])
    covered = sum(1 for p in pairs if p["p2_5"] - 1e-6 <= p["actual"] <= p["p97_5"] + 1e-6
                  or (p["actual"] == 0 and p["p97_5"] < 1.0))
    coverage = covered / len(pairs)

    # Log-space MAE on median
    log_errs = [abs(math.log10(p["p50"] + 1) - math.log10(p["actual"] + 1)) for p in pairs]
    med_log_mae = float(np.median(log_errs))

    # Rank metrics: use mean (robust when p50 is 0 for many countries)
    actual_log = [math.log10(p["actual"] + 1) for p in pairs]
    model_log  = [math.log10(p["mean"]  + 1) for p in pairs]
    rho   = _spearman(model_log, actual_log)
    r_log = _pearson(model_log, actual_log)

    # Top-K precision (excluding seed)
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

    # Print
    print(f"  countries compared      : {len(pairs)}")
    print(f"  coverage_95pi           : {coverage*100:5.1f}%")
    print(f"  spearman_rho_log        : {rho:+.3f}")
    print(f"  pearson_r_log           : {r_log:+.3f}")
    print(f"  top5_precision          : {p5*100:5.1f}%   model={model_iso[:5]}  truth={truth_iso[:5]}")
    print(f"  top10_precision         : {p10*100:5.1f}%")
    print(f"  median_log_mae          : {med_log_mae:.3f}")

    # Show worst over/under predictions
    pairs_for_residual = [p for p in pairs if p["iso3"] != params.start_iso3]
    pairs_for_residual.sort(
        key=lambda p: math.log10(p["p50"] + 1) - math.log10(p["actual"] + 1))
    under = pairs_for_residual[:3]
    over  = pairs_for_residual[-3:]
    print(f"  most UNDER-predicted    : {[(p['iso3'], int(p['actual']), int(p['p50'])) for p in under]}")
    print(f"  most  OVER-predicted    : {[(p['iso3'], int(p['actual']), int(p['p50'])) for p in over]}")

    return {
        "scenario": scenario, "n": len(pairs),
        "coverage_95pi": coverage, "spearman_rho_log": rho, "pearson_r_log": r_log,
        "top5_precision": p5, "top10_precision": p10, "median_log_mae": med_log_mae,
    }


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------


def _load_owid_mpox_truth() -> tuple[dict[str, int], int]:
    """Read OWID mpox CSV; return (day-+30 dict, seed-day GBR count).

    Pulls from the VSI mirror first, then from owid/monkeypox on github.
    """
    csv_path = Path(__file__).parent / "data" / "owid_mpox.csv"
    if not csv_path.exists():
        from scripts._data_source import fetch
        fetch(
            local=csv_path,
            vsi_path="owid/owid_mpox.csv",
            public_url="https://raw.githubusercontent.com/owid/monkeypox/main/owid-monkeypox-data.csv",
        )
    truth: dict[str, int] = {}
    seed_count = 0
    with csv_path.open() as f:
        for row in csv.DictReader(f):
            if not row["iso_code"] or row["iso_code"].startswith("OWID"): continue
            try: cases = int(float(row["total_cases"] or 0))
            except: continue
            if row["date"] == MPOX_CMP_DATE and cases > 0:
                truth[row["iso_code"]] = cases
            if row["date"] == MPOX_SEED_DATE and row["iso_code"] == "GBR":
                seed_count = cases
    # Endo et al. 2022 (Lancet ID) backcalculated ~50-100 true mpox cases in
    # GBR by 2022-05-13 from clinical onset data, vs ECDC's ~4 confirmed by
    # then. Use 75 as a defensible mid-literature seed; the OWID confirmed
    # count badly under-represents the actual circulating infections.
    return truth, max(seed_count, 75)


def _load_jhu_covid_truth() -> tuple[dict[str, int], int]:
    _, jhu = load_country_counts()
    seed = jhu["CHN"]["2020-01-22"]
    truth = {iso: jhu[iso]["2020-02-21"] for iso in jhu if "2020-02-21" in jhu[iso]}
    return truth, int(seed)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def _params(disease, iso, r0, inc, inf, port, seed, horizon=30, n_runs=1000):
    return SimParams(
        disease_id=disease, start_iso3=iso,
        r0=r0, incubation_days=inc, infectious_days=inf,
        cfr_pct=1.0, air_weight=1.0, port_weight=port,
        travel_restriction=0.0, mask_intervention=0.0,
        horizon_days=horizon, n_runs=n_runs, seed_infected=seed,
    )


if __name__ == "__main__":
    results = []

    # --- COVID-19 ---
    covid_truth, covid_seed = _load_jhu_covid_truth()
    results.append(_validate(
        "COVID-19 / CHN / 2020-01-22 -> 2020-02-21 (vs JHU CSSE)",
        _params("covid19", "CHN", 2.5, 5.0, 6.0, 0.3, covid_seed),
        covid_truth, "2020-02-21"))

    # --- Mpox 2022 ---
    mpox_truth, mpox_seed = _load_owid_mpox_truth()
    results.append(_validate(
        "Mpox 2022 / GBR / 2022-05-13 -> 2022-06-13 (vs OWID)",
        _params("mpox", "GBR", 1.6, 9.0, 14.0, 0.3, mpox_seed),
        mpox_truth, MPOX_CMP_DATE))

    # --- 2009 H1N1 ---
    h1n1_truth = {k: v for k, v in H1N1_DAY30_TRUTH.items()}
    results.append(_validate(
        "2009 H1N1 / MEX / 2009-04-26 -> 2009-05-26 (vs WHO Sit-Rep No. 28)",
        _params("flu", "MEX", 1.5, 2.0, 4.0, 0.3, H1N1_SEED_INITIAL),
        h1n1_truth, H1N1_CMP_DATE))

    # --- 2003 SARS ---
    sars_truth = {k: v for k, v in SARS_DAY30_TRUTH.items()}
    results.append(_validate(
        "2003 SARS / CHN / 2003-03-12 -> 2003-04-11 (vs WHO Sit-Rep 24)",
        _params("sars", "CHN", 2.7, 6.0, 8.0, 0.3, SARS_SEED_INITIAL),
        sars_truth, SARS_CMP_DATE))

    # --- 2014 Ebola (West Africa) ---
    ebola_truth = {k: v for k, v in EBOLA_DAY30_TRUTH.items()}
    results.append(_validate(
        "2014 Ebola / GIN / 2014-03-23 -> 2014-04-22 (vs cmrivers/ebola)",
        _params("ebola", "GIN", 1.51, 9.7, 7.5, 0.3, EBOLA_SEED_INITIAL),
        ebola_truth, EBOLA_CMP_DATE))

    # --- summary ---
    print(f"\n{'='*78}\nSUMMARY (literature defaults, no scenario-specific tuning)\n{'='*78}")
    print(f"{'scenario':<60} {'n':>4} {'cov95':>6} {'rho':>6} {'r':>6} {'top5':>5} {'top10':>6} {'logMAE':>7}")
    for r in results:
        if not r: continue
        print(f"{r['scenario']:<60} {r['n']:>4} "
              f"{r['coverage_95pi']*100:>5.1f}% "
              f"{r['spearman_rho_log']:+.3f} {r['pearson_r_log']:+.3f} "
              f"{r['top5_precision']*100:>4.0f}% {r['top10_precision']*100:>5.0f}% "
              f"{r['median_log_mae']:>7.3f}")
