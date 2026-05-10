"""Mobility model: gravity OD matrix with exponential distance decay.

Implements equation (a) from the PRD:

    F_air[i, j] = K_a * P_i^alpha * P_j^beta * exp(-gamma * d_ij) * R_ij

where d_ij is great-circle distance in thousands of km. Without the OpenFlights
routes table the route indicator R_ij is approximated by combining each
country's hub index with a connectivity threshold. Sea mobility is stubbed as
a coastal-pair indicator that scales with hub indices.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np

DATA_DIR = Path(__file__).parent / "data"

# Literature priors from the PRD (Section 7.1)
ALPHA = 1.0
BETA = 1.0
GAMMA_AIR = 0.5  # per 1000 km
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
    """Daily air-passenger proxy F_air[i, j]. Symmetric in this MVP."""
    countries = load_countries()
    pop = np.array([c.population for c in countries], dtype=np.float64)
    hub = np.array([c.hub for c in countries], dtype=np.float64)
    d = distance_matrix_km()

    # Combine population with hub index to act as effective traveler-generating mass.
    effective = pop * (0.5 + 0.5 * hub / hub.max())
    raw = _gravity(effective, effective, d, GAMMA_AIR)

    # Normalize so the global row-sum is comparable to a sane daily-traveler scale.
    # Target ~5 million daily international air passengers across the modeled set.
    if raw.sum() > 0:
        raw *= 5_000_000.0 / raw.sum()
    return raw


@lru_cache(maxsize=1)
def sea_flow_matrix() -> np.ndarray:
    """Coarse port-call proxy F_sea[i, j]. The PRD treats this as a multiplier-tuned
    secondary channel; we use a hub-weighted gravity with slower decay. Inland
    countries get a small attenuation factor."""
    countries = load_countries()
    landlocked = {"AFG", "KAZ", "UZB", "HUN", "CZE", "AUT", "CHE", "ETH", "UGA"}
    coastal = np.array([0.2 if c.iso3 in landlocked else 1.0 for c in countries])
    pop = np.array([c.population for c in countries], dtype=np.float64)
    hub = np.array([c.hub for c in countries], dtype=np.float64)
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
