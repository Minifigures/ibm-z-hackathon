"""Mobility model: gravity OD matrix with exponential distance decay.

Implements equation (a) from the PRD:

    F_air[i, j] = K_a * P_i^alpha * P_j^beta * exp(-gamma * d_ij) * R_ij

where d_ij is great-circle distance in thousands of km. Where the OpenFlights
routes table provides per-country route degree we use the real number
(`airport_unique_destinations`). Where a static port-call snapshot provides
TEU we use that for the sea channel. Anything missing falls back to the
hand-tuned `hub` index in countries.json so the system never breaks.
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data"

# Literature priors from the PRD (Section 7.1)
ALPHA = 1.0
BETA = 1.0
GAMMA_AIR = 0.482  # per 1000 km, empirically fit from 55 BTS US-anchored + 190 Eurostat EU bilateral pairs (R^2=0.52); literature prior was 0.5 (Guo 2026)
GAMMA_SEA = 0.3  # per 1000 km, longer effective range


@dataclass(frozen=True)
class Country:
    iso3: str
    name: str
    lat: float
    lng: float
    population: int
    hub: float


@lru_cache(maxsize=1)
def load_countries() -> list[Country]:
    raw = json.loads((DATA_DIR / "countries.json").read_text())
    return [Country(**row) for row in raw]


@lru_cache(maxsize=1)
def country_index() -> dict[str, int]:
    return {c.iso3: i for i, c in enumerate(load_countries())}


def _load_json_safely(path: Path) -> dict | None:
    """Best-effort loader. Returns None on any failure and logs a warning."""
    try:
        if not path.exists():
            logger.warning(
                "Real mobility data file %s not found; falling back to synthetic hub_index.",
                path.name,
            )
            return None
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning(
            "Failed to load %s (%s); falling back to synthetic hub_index.",
            path.name,
            exc,
        )
        return None


def _rescaled_hub_array(metric_by_iso3: dict[str, float]) -> np.ndarray:
    """Build a per-country array where countries with real data use the
    rescaled metric and the rest fall back to their synthetic hub value.

    The metric values are rescaled so that the *mean of the resulting hybrid
    array* matches the mean of the original synthetic hub array. This keeps
    the scale of the gravity output (and the downstream normalization
    targets) comparable to the previous behavior so the existing Monte Carlo
    bands and tests don't drift.
    """
    countries = load_countries()
    hub = np.array([c.hub for c in countries], dtype=np.float64)
    if not metric_by_iso3:
        return hub

    have_real = np.array(
        [c.iso3 in metric_by_iso3 for c in countries], dtype=bool
    )
    if not have_real.any():
        return hub

    raw = np.array(
        [float(metric_by_iso3.get(c.iso3, 0.0)) for c in countries],
        dtype=np.float64,
    )
    # Scale the real values so their mean (over the countries that have data)
    # matches the synthetic hub mean over the same countries; that keeps
    # cross-country relative ratios from the real source while preserving the
    # absolute scale of the hub index.
    real_mean = raw[have_real].mean()
    hub_mean_over_real = hub[have_real].mean()
    if real_mean <= 0:
        return hub
    scaled = raw * (hub_mean_over_real / real_mean)

    out = hub.copy()
    out[have_real] = scaled[have_real]
    return out


@lru_cache(maxsize=1)
def real_air_hub() -> np.ndarray:
    """Per-country air hub index, preferring the real OpenFlights route-degree
    where available and falling back to the synthetic `hub` otherwise.
    """
    payload = _load_json_safely(DATA_DIR / "airport_routes.json")
    if payload is None:
        return np.array([c.hub for c in load_countries()], dtype=np.float64)
    rows = payload.get("countries", {}) if isinstance(payload, dict) else {}
    metric = {
        iso3: float(v.get("airport_unique_destinations", 0.0))
        for iso3, v in rows.items()
        if isinstance(v, dict)
    }
    return _rescaled_hub_array(metric)


@lru_cache(maxsize=1)
def un_migrant_multiplier_matrix() -> np.ndarray:
    """N x N symmetric multiplier built from UN DESA 2020 bilateral migrant
    stocks. For each pair, sum stock(a->b) + stock(b->a) (= total diaspora
    population on that corridor) and apply a log-clipped multiplier:

        mult = clip(1 + (log10(total_stock+1) - 3), 1.0, 5.0)

    so a corridor with 1k migrants gets ~1x, 100k gets ~3x, 10M+ gets 5x.
    The cutoff at 1k is a noise floor; the cap at 5x prevents MEX-USA
    (~11M migrants) from dominating the matrix. Empirical literature
    (Beine et al. 2014; Docquier & Lodigiani 2010) finds approximately
    linear-in-log relationships between diaspora size and bilateral travel.

    Defaults to all-1s if the file is missing.
    """
    n = len(load_countries())
    mult = np.ones((n, n), dtype=np.float64)
    payload = _load_json_safely(DATA_DIR / "un_migrant_stock.json")
    if not isinstance(payload, dict):
        return mult
    iso_to_idx = country_index()
    raw_stocks = payload.get("stocks", {})

    # Aggregate symmetric totals
    pair_totals: dict[tuple[int, int], float] = {}
    for k, v in raw_stocks.items():
        try:
            a, b = k.split("_")
        except ValueError:
            continue
        i = iso_to_idx.get(a)
        j = iso_to_idx.get(b)
        if i is None or j is None or i == j:
            continue
        key = (min(i, j), max(i, j))
        pair_totals[key] = pair_totals.get(key, 0.0) + float(v)

    applied = 0
    for (i, j), total in pair_totals.items():
        if total <= 0:
            continue
        m = 1.0 + (math.log10(total + 1.0) - 3.0)
        m = max(1.0, min(5.0, m))
        if m > 1.001:
            mult[i, j] = m
            mult[j, i] = m
            applied += 1
    logger.info("un_migrant_multiplier_matrix: %d pairs amplified", applied)
    return mult


@lru_cache(maxsize=1)
def eurostat_eu_pair_flows() -> dict[tuple[str, str], int] | None:
    """2019 Eurostat avia_paocc passengers-carried for EU bilateral country
    pairs. Returns {(iso3_a, iso3_b): annual_passengers} with alphabetically
    sorted keys, or None if the file is missing.
    """
    payload = _load_json_safely(DATA_DIR / "eurostat_passenger_flows.json")
    if not isinstance(payload, dict):
        return None
    pairs = payload.get("pairs", {})
    out: dict[tuple[str, str], int] = {}
    for k, v in pairs.items():
        try:
            a, b = k.split("_")
        except ValueError:
            continue
        if v > 0:
            out[(a, b)] = int(v)
    return out


@lru_cache(maxsize=1)
def bts_us_anchored_flows() -> dict[str, int] | None:
    """2019 BTS T-100 international passenger volumes on US-anchored corridors.

    Returns {iso3: annual_passengers} for foreign countries with US-anchored
    routes, or None if the file is missing. Annual totals are bidirectional
    aggregates per BTS row semantics; we treat them as a relative-volume
    proxy for the USA row of the gravity matrix.
    """
    payload = _load_json_safely(DATA_DIR / "bts_passenger_flows.json")
    if not isinstance(payload, dict):
        return None
    flows = payload.get("from_us_to_country", {})
    return {iso: int(v) for iso, v in flows.items() if v > 0}


@lru_cache(maxsize=1)
def bilateral_corridor_matrix() -> np.ndarray:
    """Symmetric N x N multiplier on the gravity output for known high-volume
    or culturally-tied corridors that pure population-x-distance gravity
    systematically under-predicts (Hispanophone, Lusophone, Sinosphere
    diaspora, intra-EU tourism, etc.). Defaults to 1.0 (no change) for any
    pair not explicitly listed.
    """
    n = len(load_countries())
    mult = np.ones((n, n), dtype=np.float64)
    payload = _load_json_safely(DATA_DIR / "bilateral_corridors.json")
    if payload is None:
        return mult
    iso_to_idx = country_index()
    rows = payload.get("corridors", []) if isinstance(payload, dict) else []
    applied = 0
    for entry in rows:
        if not isinstance(entry, list) or len(entry) < 3:
            continue
        a, b, factor = entry[0], entry[1], float(entry[2])
        if a in iso_to_idx and b in iso_to_idx and factor > 0:
            i, j = iso_to_idx[a], iso_to_idx[b]
            mult[i, j] = factor
            mult[j, i] = factor
            applied += 1
    logger.info("bilateral_corridor_matrix: applied %d/%d entries", applied, len(rows))
    return mult


@lru_cache(maxsize=1)
def real_port_hub() -> np.ndarray:
    """Per-country sea hub index, preferring the static Top-50 port TEU
    snapshot where available and falling back to the synthetic `hub`.
    """
    payload = _load_json_safely(DATA_DIR / "port_calls.json")
    if payload is None:
        return np.array([c.hub for c in load_countries()], dtype=np.float64)
    rows = payload.get("countries", {}) if isinstance(payload, dict) else {}
    metric = {
        iso3: float(v.get("port_teu_millions", 0.0))
        for iso3, v in rows.items()
        if isinstance(v, dict)
    }
    return _rescaled_hub_array(metric)


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


@lru_cache(maxsize=1)
def distance_matrix_km() -> np.ndarray:
    countries = load_countries()
    n = len(countries)
    d = np.zeros((n, n), dtype=np.float64)
    for i, ci in enumerate(countries):
        for j, cj in enumerate(countries):
            if i == j:
                continue
            d[i, j] = haversine_km(ci.lat, ci.lng, cj.lat, cj.lng)
    return d


def _gravity(p_i: np.ndarray, p_j: np.ndarray, d_km: np.ndarray, gamma_per_1000km: float) -> np.ndarray:
    """Vectorized gravity intensity, before route filtering or normalization."""
    d_thousands = d_km / 1000.0
    p_outer = np.outer(p_i ** ALPHA, p_j ** BETA)
    decay = np.exp(-gamma_per_1000km * d_thousands)
    np.fill_diagonal(decay, 0.0)
    return p_outer * decay


@lru_cache(maxsize=1)
def air_flow_matrix() -> np.ndarray:
    """Daily air-passenger proxy F_air[i, j]. Symmetric in this MVP.

    Uses the OpenFlights route-degree (`airport_unique_destinations`) as the
    per-country hub multiplier when available, falling back to the synthetic
    hub_index. The hybrid array is rescaled so its mean matches the synthetic
    hub mean, preserving the post-normalization 5M daily-traveler target.
    """
    countries = load_countries()
    pop = np.array([c.population for c in countries], dtype=np.float64)
    hub = real_air_hub()
    d = distance_matrix_km()

    # Combine population with hub index to act as effective traveler-generating mass.
    effective = pop * (0.5 + 0.5 * hub / hub.max())
    raw = _gravity(effective, effective, d, GAMMA_AIR)

    # Bilateral corridor multipliers: hand-curated cultural/colonial ties
    # (ESP-MEX, PRT-BRA, CHN-SGP, etc.) AND data-driven diaspora multipliers
    # from UN DESA 2020 bilateral migrant stocks. Both apply multiplicatively
    # before normalization, so they reshape the matrix without changing total
    # mass.
    raw = raw * bilateral_corridor_matrix() * un_migrant_multiplier_matrix()

    # NOTE: Eurostat avia_paocc overlay was tested here and rolled back. It
    # is empirically net-negative on rank correlation across the COVID/Mpox/
    # H1N1 backtest (avg rho 0.573 -> 0.537) because pathogens don't follow
    # aggregate passenger flows uniformly: mpox propagated through
    # MSM-network ties, not the high-volume tourism corridors Eurostat
    # captures. The data file `eurostat_passenger_flows.json` is retained
    # for reference, and the loader `eurostat_eu_pair_flows()` is still
    # available if a future model wants to use it (e.g. weighted by
    # transmission-mode prior).

    # Replace the USA row+column with real BTS T-100 passenger volumes where
    # available. We rescale so the USA-row sum is preserved (no change to
    # USA's total outbound mobility), only the within-USA distribution is
    # corrected to match reality. Pairs without BTS data keep their gravity
    # value; pairs with BTS data become proportional to actual 2019 passenger
    # counts. Symmetric: USA->X and X->USA both updated.
    bts = bts_us_anchored_flows()
    iso_to_idx = country_index()
    if bts and "USA" in iso_to_idx:
        usa = iso_to_idx["USA"]
        usa_row_orig_sum = float(raw[usa].sum())
        new_row = np.zeros_like(raw[usa])
        for iso3, vol in bts.items():
            j = iso_to_idx.get(iso3)
            if j is not None and j != usa:
                new_row[j] = float(vol)
        new_row_sum = float(new_row.sum())
        if new_row_sum > 0 and usa_row_orig_sum > 0:
            new_row *= usa_row_orig_sum / new_row_sum
            # For pairs WITHOUT BTS data, keep gravity value; for pairs WITH BTS,
            # use the rescaled value. Mix them.
            for iso3 in bts:
                j = iso_to_idx.get(iso3)
                if j is not None and j != usa:
                    raw[usa, j] = new_row[j]
                    raw[j, usa] = new_row[j]  # symmetric

    # Normalize so the global row-sum is comparable to a sane daily-traveler scale.
    # Target ~5 million daily international air passengers across the modeled set.
    if raw.sum() > 0:
        raw *= 5_000_000.0 / raw.sum()
    return raw


@lru_cache(maxsize=1)
def sea_flow_matrix() -> np.ndarray:
    """Coarse port-call proxy F_sea[i, j]. The PRD treats this as a multiplier-tuned
    secondary channel; we use a hub-weighted gravity with slower decay.

    Where the static Top-50 container ports snapshot covers a country we use
    `port_teu_millions` (rescaled to hub-index magnitude) as the hub
    multiplier; otherwise we fall back to the synthetic hub_index. Inland
    countries still get a coastal attenuation factor.
    """
    countries = load_countries()
    landlocked = {"AFG", "KAZ", "UZB", "HUN", "CZE", "AUT", "CHE", "ETH", "UGA"}
    coastal = np.array([0.2 if c.iso3 in landlocked else 1.0 for c in countries])
    pop = np.array([c.population for c in countries], dtype=np.float64)
    hub = real_port_hub()
    mass = pop * (0.4 + 0.6 * hub / hub.max()) * coastal
    d = distance_matrix_km()
    raw = _gravity(mass, mass, d, GAMMA_SEA)
    if raw.sum() > 0:
        raw *= 200_000.0 / raw.sum()
    return raw


def combined_mobility(
    air_weight: float = 1.0,
    port_weight: float = 0.3,
    travel_restriction: float = 0.0,
) -> np.ndarray:
    """Build the per-day fractional mobility matrix m[i, j] used by SEIR.

    travel_restriction in [0, 1] is applied multiplicatively to the absolute
    flows. The result is the fraction of region i's population that moves to
    region j per simulation day; m[i, i] is zero.
    """
    air = air_flow_matrix() * air_weight
    sea = sea_flow_matrix() * port_weight
    flow = (air + sea) * (1.0 - travel_restriction)

    pop = np.array([c.population for c in load_countries()], dtype=np.float64)
    m = flow / pop[:, None]
    np.fill_diagonal(m, 0.0)
    # Cap the per-day fraction: real out-mobility for a country rarely exceeds 0.5%.
    return np.clip(m, 0.0, 0.005)
