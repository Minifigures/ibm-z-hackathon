"""Empirically fit gravity exponents from real bilateral passenger data.

Per Guo et al. 2026 (arXiv 2501.05684), the canonical air-mobility law is

    F_ij = K * P_i^alpha * P_j^beta * exp(-gamma * d_ij)

The PRD currently uses literature priors alpha = beta = 1, gamma = 0.5 / 1000km.
This script fits the exponents to real BTS T-100 (USA-anchored) and Eurostat
(EU bilateral) passenger flows by ordinary least squares in log space:

    log F_ij = log K + alpha log P_i + beta log P_j - gamma d_ij

Useful as a sanity check: if the fitted gamma is far from 0.5, the literature
prior is mis-calibrated and we should update GAMMA_AIR in mobility.py.

Run from backend/::
    python -m backtest.fit_gravity
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

REPO_BACKEND = Path(__file__).resolve().parent.parent
COUNTRIES_PATH = REPO_BACKEND / "app" / "data" / "countries.json"
BTS_PATH = REPO_BACKEND / "app" / "data" / "bts_passenger_flows.json"
EUROSTAT_PATH = REPO_BACKEND / "app" / "data" / "eurostat_passenger_flows.json"


def haversine_km(lat1, lng1, lat2, lng2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def load_countries():
    raw = json.loads(COUNTRIES_PATH.read_text())
    return {c["iso3"]: c for c in raw}


def main():
    countries = load_countries()

    # ----- BTS: US-anchored pairs -----
    bts = json.loads(BTS_PATH.read_text())
    bts_pairs = bts.get("from_us_to_country", {})
    usa = countries["USA"]
    rows_bts = []
    for iso, vol in bts_pairs.items():
        if iso not in countries: continue
        c = countries[iso]
        d = haversine_km(usa["lat"], usa["lng"], c["lat"], c["lng"])
        if d <= 0 or vol <= 0: continue
        rows_bts.append((usa["population"], c["population"], d, vol))

    # ----- Eurostat: EU bilateral pairs -----
    es = json.loads(EUROSTAT_PATH.read_text())
    es_pairs = es.get("pairs", {})
    rows_es = []
    for k, vol in es_pairs.items():
        try: a, b = k.split("_")
        except: continue
        if a not in countries or b not in countries: continue
        ca, cb = countries[a], countries[b]
        d = haversine_km(ca["lat"], ca["lng"], cb["lat"], cb["lng"])
        if d <= 0 or vol <= 0: continue
        rows_es.append((ca["population"], cb["population"], d, vol))

    rows = rows_bts + rows_es
    print(f"Fit dataset: {len(rows_bts)} BTS US-anchored + {len(rows_es)} Eurostat EU pairs = {len(rows)} total")

    # OLS in log space:  log F = log K + alpha log P_i + beta log P_j - gamma d
    P_i = np.array([r[0] for r in rows], dtype=np.float64)
    P_j = np.array([r[1] for r in rows], dtype=np.float64)
    d   = np.array([r[2] for r in rows], dtype=np.float64) / 1000.0  # convert to thousands of km
    F   = np.array([r[3] for r in rows], dtype=np.float64)

    y = np.log(F)
    X = np.column_stack([
        np.ones_like(y),       # log K
        np.log(P_i),           # alpha
        np.log(P_j),           # beta
        -d,                    # -gamma (so coefficient is +gamma)
    ])

    coef, residuals, rank, sv = np.linalg.lstsq(X, y, rcond=None)
    log_K, alpha, beta, gamma = coef
    print(f"\nFitted gravity (full model):")
    print(f"  alpha = {alpha:.3f}   (literature prior: 1.0)")
    print(f"  beta  = {beta:.3f}   (literature prior: 1.0)")
    print(f"  gamma = {gamma:.3f} per 1000 km   (literature prior: 0.5)")
    print(f"  K     = {math.exp(log_K):.3e}")

    # R^2
    y_hat = X @ coef
    ss_res = np.sum((y - y_hat) ** 2)
    ss_tot = np.sum((y - y.mean()) ** 2)
    r2 = 1 - ss_res / ss_tot
    print(f"  R^2 = {r2:.3f} on log F")

    # Constrained fit: alpha = beta = 1, only fit log K and gamma
    X2 = np.column_stack([
        np.ones_like(y),
        -d,
    ])
    y2 = y - np.log(P_i) - np.log(P_j)
    coef2, *_ = np.linalg.lstsq(X2, y2, rcond=None)
    log_K2, gamma2 = coef2
    y_hat2 = X2 @ coef2
    r2_constrained = 1 - np.sum((y2 - y_hat2) ** 2) / np.sum((y2 - y2.mean()) ** 2)
    print(f"\nConstrained fit (alpha=beta=1, fit only K and gamma):")
    print(f"  gamma = {gamma2:.3f} per 1000 km")
    print(f"  K     = {math.exp(log_K2):.3e}")
    print(f"  R^2 (on log of population-normalized flow) = {r2_constrained:.3f}")

    # Sanity check: compare BTS-only and Eurostat-only fits
    for name, sub in [("BTS only", rows_bts), ("Eurostat only", rows_es)]:
        if not sub: continue
        Pi = np.array([r[0] for r in sub], dtype=np.float64)
        Pj = np.array([r[1] for r in sub], dtype=np.float64)
        ds = np.array([r[2] for r in sub], dtype=np.float64) / 1000.0
        Fs = np.array([r[3] for r in sub], dtype=np.float64)
        ys = np.log(Fs) - np.log(Pi) - np.log(Pj)
        Xs = np.column_stack([np.ones_like(ys), -ds])
        c, *_ = np.linalg.lstsq(Xs, ys, rcond=None)
        print(f"  {name:<15}: gamma = {c[1]:.3f}, n = {len(sub)}")


if __name__ == "__main__":
    main()
