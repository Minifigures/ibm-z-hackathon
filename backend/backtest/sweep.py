"""Calibration sweep across diseases, origins, and parameters.

Three scenarios, each with a small literature-defensible parameter grid:

  1. COVID-19 / CHN / 2020-01-22  -> JHU CSSE ground truth, real coverage metric
  2. H1N1 2009 / MEX / 2009-04-17 -> qualitative ranking vs WHO situation reports
  3. Mpox 2022  / GBR / 2022-05-13 -> qualitative ranking vs ECDC weekly bulletins

Run from ``backend/``::

    python -m backtest.sweep

Prints a compact table per scenario; does NOT overwrite ``results.json``.
"""

from __future__ import annotations

import math
from typing import Iterable

import numpy as np

from app.simulate import SimParams
from .run_backtest import _full_simulation
from .jhu_data import load_country_counts


# ---------------------------------------------------------------------------
# Real-world day-+30 ground truth (or top imports from contemporaneous reports)
# ---------------------------------------------------------------------------

# COVID-19: pulled at runtime from JHU.

# 2009 H1N1: pulled from WHO situation reports + ECDC archive. By the end of
# the first month after the late-April detection, lab-confirmed cases were
# concentrated in: USA (the largest by far due to extensive testing), CAN,
# ESP (Spain - first European cases), GBR, GTM, CRI, NZL, ISR, DEU, FRA.
# Source: WHO H1N1 situation update No. 4 (29 Apr 2009) and No. 28 (28 May
# 2009). We compare the model's top imports (excluding seed MEX) to this set.
H1N1_TOP_IMPORTS = ["USA", "CAN", "ESP", "GBR", "NZL", "ISR", "DEU", "FRA"]

# Mpox 2022: ECDC weekly outbreak surveillance, week 24 (mid June 2022),
# the first ~30 days after the UK cluster was detected. Cumulative confirmed
# cases ranked: GBR (470) - the seed itself, then ESP (168), PRT (138),
# DEU (130), FRA (91), NLD (71), USA (49), CAN (25), ITA (20), BEL (19).
# Source: ECDC mpox dashboard archive.
MPOX_TOP_IMPORTS = ["ESP", "PRT", "DEU", "FRA", "NLD", "USA", "CAN", "ITA", "BEL"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _quantiles(cum_final: np.ndarray, iso3_list: list[str]):
    p2_5 = np.quantile(cum_final, 0.025, axis=0)
    p50 = np.quantile(cum_final, 0.5, axis=0)
    p97_5 = np.quantile(cum_final, 0.975, axis=0)
    return {iso: (p2_5[i], p50[i], p97_5[i]) for i, iso in enumerate(iso3_list)}


def _top_imports(cum_final: np.ndarray, iso3_list: list[str], seed_iso3: str, k: int = 10):
    p50 = np.quantile(cum_final, 0.5, axis=0)
    pairs = [(iso, float(p50[i])) for i, iso in enumerate(iso3_list) if iso != seed_iso3]
    pairs.sort(key=lambda x: -x[1])
    return pairs[:k]


def _ranking_overlap(model_top: list[str], truth_top: list[str], k: int = 10) -> tuple[int, int]:
    model_set = set(m for m, _ in model_top[:k]) if model_top and isinstance(model_top[0], tuple) else set(model_top[:k])
    truth_set = set(truth_top[:k])
    return len(model_set & truth_set), len(truth_set)


def _make_params(**kw) -> SimParams:
    base = dict(
        disease_id="covid19",
        start_iso3="CHN",
        r0=2.5,
        incubation_days=5.0,
        infectious_days=6.0,
        cfr_pct=1.0,
        air_weight=1.0,
        port_weight=0.3,
        travel_restriction=0.0,
        mask_intervention=0.0,
        horizon_days=30,
        n_runs=500,
        seed_infected=50,
    )
    base.update(kw)
    return SimParams(**base)


# ---------------------------------------------------------------------------
# Scenario 1: COVID-19, China seed, vs JHU
# ---------------------------------------------------------------------------


def covid_sweep():
    print("=" * 78)
    print("Scenario 1: COVID-19, CHN seed, day +30, vs JHU CSSE")
    print("=" * 78)

    jhu_dates, jhu_by_iso = load_country_counts()
    seed_actual = jhu_by_iso["CHN"]["2020-01-22"]
    cmp_date = "2020-02-21"

    grid = []
    # R0 sweep at literature port_weight=0.3
    for r0 in [2.5, 3.0, 3.5]:
        grid.append({"r0": r0, "port_weight": 0.3, "label": f"R0={r0:.1f} port=0.3"})
    # Tighter mobility coupling via port_weight (proxy for total mobility scale)
    for pw in [0.0, 1.0]:
        grid.append({"r0": 3.0, "port_weight": pw, "label": f"R0=3.0 port={pw:.1f}"})

    print(f"\n{'Config':<22} {'cov95':>7} {'med_log_MAE':>12}  CHN p50 (truth={seed_actual+0:>5})  notable")
    print("-" * 78)

    best = None
    for cfg in grid:
        params = _make_params(
            start_iso3="CHN", r0=cfg["r0"], port_weight=cfg["port_weight"],
            seed_infected=int(seed_actual),
        )
        cum, iso3_list = _full_simulation(params)
        q = _quantiles(cum, iso3_list)

        compared = 0
        covered = 0
        log_errs: list[float] = []
        for iso, (lo, med, hi) in q.items():
            actual = jhu_by_iso.get(iso, {}).get(cmp_date)
            if actual is None: continue
            compared += 1
            in_band = lo - 1e-6 <= actual <= hi + 1e-6 or (actual == 0 and hi < 1.0)
            covered += 1 if in_band else 0
            log_errs.append(abs(math.log10(med + 1.0) - math.log10(actual + 1.0)))

        coverage = covered / compared
        med_mae = float(np.median(log_errs))
        chn_med = q["CHN"][1]
        chn_actual = jhu_by_iso["CHN"][cmp_date]

        # Notable mismatches
        notes = []
        for iso in ["JPN", "KOR", "SGP", "ITA", "USA"]:
            actual = jhu_by_iso.get(iso, {}).get(cmp_date)
            if actual is None: continue
            lo, med, hi = q[iso]
            if not (lo - 1e-6 <= actual <= hi + 1e-6) and actual > 0:
                direction = "low" if med < actual else "hi"
                notes.append(f"{iso}({actual}->{int(med)},{direction})")

        print(f"{cfg['label']:<22} {coverage*100:>6.1f}% {med_mae:>11.3f}  {int(chn_med):>5} (true={chn_actual})       {' '.join(notes[:3])}")

        score = (coverage, -med_mae)
        if best is None or score > best[0]: best = (score, cfg, coverage, med_mae)

    print(f"\nBest config: {best[1]['label']}  -> coverage {best[2]*100:.1f}%, med_log_MAE {best[3]:.3f}")


# ---------------------------------------------------------------------------
# Scenario 2: 2009 H1N1, Mexico seed, ranking-overlap metric
# ---------------------------------------------------------------------------


def flu_sweep():
    print("\n" + "=" * 78)
    print("Scenario 2: 2009 H1N1, MEX seed, day +30, vs WHO sit-rep top imports")
    print("=" * 78)
    print(f"  Truth (top 8 outside MEX, WHO Apr-May 2009): {H1N1_TOP_IMPORTS}\n")

    grid = []
    for r0 in [1.4, 1.6, 1.8]:
        for pw in [0.0, 0.3]:
            grid.append({"r0": r0, "port_weight": pw, "label": f"R0={r0:.1f} port={pw:.1f}"})

    print(f"{'Config':<24} {'top10 model':<70}  hits/8")
    print("-" * 110)

    for cfg in grid:
        params = _make_params(
            disease_id="flu", start_iso3="MEX",
            r0=cfg["r0"], port_weight=cfg["port_weight"],
            incubation_days=2.0, infectious_days=4.0,
            seed_infected=200,  # WHO confirmed ~22 by Apr 24, true infections were larger
        )
        cum, iso3_list = _full_simulation(params)
        top = _top_imports(cum, iso3_list, "MEX", k=10)
        top_iso = [iso for iso, _ in top]
        hits = len(set(top_iso) & set(H1N1_TOP_IMPORTS))
        top_str = ", ".join(f"{iso}({int(v):>4})" for iso, v in top[:6])
        print(f"{cfg['label']:<24} {top_str:<70}  {hits}/{len(H1N1_TOP_IMPORTS)}")


# ---------------------------------------------------------------------------
# Scenario 3: 2022 Mpox, UK seed, ranking-overlap metric
# ---------------------------------------------------------------------------


def mpox_sweep():
    print("\n" + "=" * 78)
    print("Scenario 3: 2022 Mpox, GBR seed, day +30, vs ECDC week-24 top imports")
    print("=" * 78)
    print(f"  Truth (top 9 outside GBR, ECDC June 2022): {MPOX_TOP_IMPORTS}\n")

    grid = []
    for r0 in [1.2, 1.6, 2.0]:
        for pw in [0.0, 0.3]:
            grid.append({"r0": r0, "port_weight": pw, "label": f"R0={r0:.1f} port={pw:.1f}"})

    print(f"{'Config':<24} {'top10 model':<70}  hits/9")
    print("-" * 110)

    for cfg in grid:
        params = _make_params(
            disease_id="mpox", start_iso3="GBR",
            r0=cfg["r0"], port_weight=cfg["port_weight"],
            incubation_days=9.0, infectious_days=14.0,
            seed_infected=20,
        )
        cum, iso3_list = _full_simulation(params)
        top = _top_imports(cum, iso3_list, "GBR", k=10)
        top_iso = [iso for iso, _ in top]
        hits = len(set(top_iso) & set(MPOX_TOP_IMPORTS))
        top_str = ", ".join(f"{iso}({int(v):>4})" for iso, v in top[:6])
        print(f"{cfg['label']:<24} {top_str:<70}  {hits}/{len(MPOX_TOP_IMPORTS)}")


def _detail_run(disease_id, start_iso3, r0, inc, inf, port_w, seed_n, truth_top, label):
    print("\n" + "-" * 78)
    print(f"DETAIL: {label}")
    print("-" * 78)
    params = _make_params(
        disease_id=disease_id, start_iso3=start_iso3,
        r0=r0, incubation_days=inc, infectious_days=inf,
        port_weight=port_w, seed_infected=seed_n, n_runs=1000,
    )
    cum, iso3_list = _full_simulation(params)
    top = _top_imports(cum, iso3_list, start_iso3, k=15)
    print(f"  truth top: {truth_top}")
    print(f"  model top 15:")
    for rank, (iso, p50) in enumerate(top, 1):
        in_truth = "<--" if iso in truth_top else ""
        print(f"    {rank:>2}. {iso}  p50={int(p50):>6}  {in_truth}")


if __name__ == "__main__":
    covid_sweep()
    flu_sweep()
    mpox_sweep()
    print("\n" + "=" * 78)
    print("DETAIL VIEW: top-15 ranking for each disease at literature defaults")
    print("=" * 78)
    _detail_run("flu", "MEX", 1.6, 2.0, 4.0, 0.3, 200, H1N1_TOP_IMPORTS, "H1N1 R0=1.6 port=0.3")
    _detail_run("mpox", "GBR", 1.6, 9.0, 14.0, 0.3, 20, MPOX_TOP_IMPORTS, "Mpox R0=1.6 port=0.3")
