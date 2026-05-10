"""Manifest of the real-world mobility datasets feeding the simulator.

Surfaced via GET /data-sources so judges and operators can see exactly
which datasets are loaded, how big they are, where they came from, and
whether they currently affect the mobility matrix. Quickest answer to
"is this thing running on real data or stub data".
"""

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"


@dataclass(frozen=True)
class DataSource:
    name: str
    file: str
    source: str
    year: int | None
    n_records: int | None
    active: bool
    note: str
    file_size_bytes: int
    file_mtime_iso: str | None


def _file_stat(path: Path) -> tuple[int, str | None]:
    if not path.exists():
        return 0, None
    st = path.stat()
    mtime = datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat(timespec="seconds")
    return int(st.st_size), mtime


def _read_meta(path: Path) -> tuple[int | None, int | None]:
    """Return (year, n_records) from the file's _meta block, plus a fallback
    record count from common top-level shapes."""
    if not path.exists():
        return None, None
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None, None
    meta = payload.get("_meta") if isinstance(payload, dict) else None
    year = None
    n = None
    if isinstance(meta, dict):
        y = meta.get("year")
        if isinstance(y, (int, float)):
            year = int(y)
        for k in ("n_pairs", "n_country_pairs", "rows", "rows_aggregated"):
            v = meta.get(k)
            if isinstance(v, (int, float)):
                n = int(v)
                break
    if n is None and isinstance(payload, dict):
        # Look at the largest non-meta container as a record-count fallback.
        for k, v in payload.items():
            if k == "_meta":
                continue
            if isinstance(v, (list, dict)):
                m = len(v)
                if n is None or m > n:
                    n = m
    return year, n


def _build(name: str, file_name: str, source: str, *, active: bool, note: str) -> DataSource:
    path = DATA_DIR / file_name
    size, mtime = _file_stat(path)
    year, n = _read_meta(path)
    return DataSource(
        name=name,
        file=file_name,
        source=source,
        year=year,
        n_records=n,
        active=active,
        note=note,
        file_size_bytes=size,
        file_mtime_iso=mtime,
    )


def manifest() -> dict:
    sources = [
        _build(
            "OpenFlights airport routes",
            "airport_routes.json",
            "OpenFlights routes.dat (https://openflights.org/data.html)",
            active=True,
            note="real_air_hub() uses airport_unique_destinations as the per-country hub multiplier in air_flow_matrix; falls back to the synthetic hub when missing.",
        ),
        _build(
            "UN DESA bilateral migrant stock",
            "un_migrant_stock.json",
            "UN DESA Population Division, International Migrant Stock 2020 (Table 1)",
            active=True,
            note="un_migrant_multiplier_matrix() applies a log-shaped diaspora multiplier (~1x at 1k, ~5x at 10M+) symmetrically to the air-flow gravity matrix.",
        ),
        _build(
            "US BTS T-100 international passengers",
            "bts_passenger_flows.json",
            "Kaggle parulpandey/us-international-air-traffic-data (BTS T-100)",
            active=True,
            note="bts_us_anchored_flows() rescales the USA row+column of air_flow_matrix to real 2019 passenger volumes; total USA outbound mass is preserved.",
        ),
        _build(
            "Top-50 container ports (TEU)",
            "port_calls.json",
            "World Shipping Council Top-50 ports snapshot",
            active=True,
            note="real_port_hub() uses port_teu_millions as the per-country sea-hub multiplier in sea_flow_matrix; landlocked countries get a coastal-attenuation factor.",
        ),
        _build(
            "Hand-curated bilateral corridors",
            "bilateral_corridors.json",
            "Authors' compilation (cultural / colonial / commuting ties)",
            active=True,
            note="bilateral_corridor_matrix() amplifies known corridors (ESP-MEX, PRT-BRA, CHN-SGP, etc.) symmetrically before air-flow normalization.",
        ),
        _build(
            "Eurostat AVIA_PAOCC EU passenger flows",
            "eurostat_passenger_flows.json",
            "Eurostat AVIA_PAOCC via the JSON-stat 2.0 SDMX REST API",
            active=False,
            note="Loaded via eurostat_eu_pair_flows() but intentionally not applied: the overlay net-degrades rank correlation on the COVID/Mpox/H1N1 backtest (avg rho 0.573 -> 0.537) because mpox propagated through MSM-network ties, not aggregate tourism corridors. Retained for future use.",
        ),
    ]
    return {
        "sources": [asdict(s) for s in sources],
        "summary": {
            "active_sources": sum(1 for s in sources if s.active),
            "total_sources": len(sources),
            "synthetic_fallback_used_for": "Countries absent from a real dataset transparently fall back to the synthetic hub_index from countries.json.",
        },
    }
