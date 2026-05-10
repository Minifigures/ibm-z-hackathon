"""Ingest OpenFlights routes.dat + airports.dat to produce per-country route counts.

Source:
    https://raw.githubusercontent.com/jpatokal/openflights/master/data/routes.dat
    https://raw.githubusercontent.com/jpatokal/openflights/master/data/airports.dat

Schema reference: https://openflights.org/data.html
    routes.dat columns:
        airline, airline_id, src_iata, src_id, dst_iata, dst_id,
        codeshare, stops, equipment
    airports.dat columns:
        id, name, city, country, iata, icao, lat, lng, altitude,
        timezone, dst, tz, type, source

Output: backend/app/data/airport_routes.json
    [
        {"iso3": "USA", "airport_routes": <int>, "airport_unique_destinations": <int>},
        ...
    ]
    where:
        airport_routes = inbound + outbound route legs touching the country
        airport_unique_destinations = number of distinct destination ISO3 codes
                                      reachable via direct flights from the
                                      country's airports (route degree proxy)

Run:
    python -m backend.scripts.ingest_openflights
or, from the backend dir:
    python scripts/ingest_openflights.py

Last-refreshed timestamp is written into the output JSON header for traceability.
"""

from __future__ import annotations

import csv
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

logger = logging.getLogger("ingest_openflights")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

ROUTES_URL = "https://raw.githubusercontent.com/jpatokal/openflights/master/data/routes.dat"
AIRPORTS_URL = "https://raw.githubusercontent.com/jpatokal/openflights/master/data/airports.dat"

SCRIPT_DIR = Path(__file__).resolve().parent
RAW_DIR = SCRIPT_DIR / "data"
APP_DATA_DIR = SCRIPT_DIR.parent / "app" / "data"

# Country-name -> ISO3 mapping that covers every country in
# backend/app/data/countries.json. OpenFlights' airports.dat uses these
# spellings (verified against the upstream file). Anything not in this map is
# logged and skipped — the simulator falls back to the synthetic hub_index for
# unmapped countries.
NAME_TO_ISO3: dict[str, str] = {
    "United States": "USA",
    "Canada": "CAN",
    "Mexico": "MEX",
    "Brazil": "BRA",
    "Argentina": "ARG",
    "Colombia": "COL",
    "Chile": "CHL",
    "Peru": "PER",
    "Venezuela": "VEN",
    "Cuba": "CUB",
    "United Kingdom": "GBR",
    "France": "FRA",
    "Germany": "DEU",
    "Spain": "ESP",
    "Italy": "ITA",
    "Portugal": "PRT",
    "Netherlands": "NLD",
    "Belgium": "BEL",
    "Switzerland": "CHE",
    "Austria": "AUT",
    "Poland": "POL",
    "Sweden": "SWE",
    "Norway": "NOR",
    "Denmark": "DNK",
    "Finland": "FIN",
    "Ireland": "IRL",
    "Greece": "GRC",
    "Turkey": "TUR",
    "Russia": "RUS",
    "Ukraine": "UKR",
    "Egypt": "EGY",
    "Morocco": "MAR",
    "Algeria": "DZA",
    "Nigeria": "NGA",
    "South Africa": "ZAF",
    "Kenya": "KEN",
    "Ethiopia": "ETH",
    "Ghana": "GHA",
    "Senegal": "SEN",
    "Tanzania": "TZA",
    "Saudi Arabia": "SAU",
    "United Arab Emirates": "ARE",
    "Qatar": "QAT",
    "Israel": "ISR",
    "Iran": "IRN",
    "Iraq": "IRQ",
    "Pakistan": "PAK",
    "India": "IND",
    "Bangladesh": "BGD",
    "Sri Lanka": "LKA",
    "Nepal": "NPL",
    "Burma": "MMR",          # OpenFlights still uses "Burma" for Myanmar.
    "Myanmar": "MMR",
    "Thailand": "THA",
    "Vietnam": "VNM",
    "Malaysia": "MYS",
    "Singapore": "SGP",
    "Indonesia": "IDN",
    "Philippines": "PHL",
    "China": "CHN",
    "Hong Kong": "HKG",
    "Hong Kong SAR of China": "HKG",
    "Taiwan": "TWN",
    "Japan": "JPN",
    "South Korea": "KOR",
    "Korea, Republic of": "KOR",
    "Australia": "AUS",
    "New Zealand": "NZL",
    "Kazakhstan": "KAZ",
    "Uzbekistan": "UZB",
    "Afghanistan": "AFG",
    "Romania": "ROU",
    "Czech Republic": "CZE",
    "Czechia": "CZE",
    "Hungary": "HUN",
}


def _download(url: str, dest: Path) -> None:
    """Download URL to dest. Fails loudly if the network isn't reachable."""
    logger.info("Downloading %s -> %s", url, dest)
    try:
        resp = requests.get(url, timeout=60)
    except requests.RequestException as exc:
        logger.error("Network error fetching %s: %s", url, exc)
        raise SystemExit(2) from exc
    if resp.status_code != 200:
        logger.error("Bad HTTP status %s for %s", resp.status_code, url)
        raise SystemExit(2)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(resp.content)
    logger.info("Wrote %d bytes", len(resp.content))


def _ensure_raw_files() -> tuple[Path, Path]:
    routes_path = RAW_DIR / "routes.dat"
    airports_path = RAW_DIR / "airports.dat"
    if not routes_path.exists():
        _download(ROUTES_URL, routes_path)
    else:
        logger.info("Using cached %s", routes_path)
    if not airports_path.exists():
        _download(AIRPORTS_URL, airports_path)
    else:
        logger.info("Using cached %s", airports_path)
    return routes_path, airports_path


def _load_airport_to_iso3(airports_path: Path) -> dict[str, str]:
    """Return {IATA -> ISO3} for airports whose country we can map.

    OpenFlights' airports.dat has 14 fields per row, comma-separated, with
    string fields wrapped in double quotes and "\\N" for missing values.
    """
    iata_to_iso3: dict[str, str] = {}
    skipped_countries: dict[str, int] = {}
    n_rows = 0
    with airports_path.open(encoding="utf-8") as fp:
        reader = csv.reader(fp)
        for row in reader:
            n_rows += 1
            # Defensive: rows can rarely be malformed; require at least 8 cols.
            if len(row) < 8:
                continue
            country = row[3].strip()
            iata = row[4].strip()
            if not iata or iata == "\\N":
                continue
            iso3 = NAME_TO_ISO3.get(country)
            if iso3 is None:
                skipped_countries[country] = skipped_countries.get(country, 0) + 1
                continue
            iata_to_iso3[iata] = iso3
    logger.info(
        "Parsed %d airport rows; %d IATA->ISO3 entries kept; %d distinct unmapped countries",
        n_rows,
        len(iata_to_iso3),
        len(skipped_countries),
    )
    if skipped_countries:
        # Show the most-common unmapped countries so you can extend NAME_TO_ISO3.
        top = sorted(skipped_countries.items(), key=lambda kv: -kv[1])[:10]
        logger.info("Top skipped countries (count): %s", top)
    return iata_to_iso3


def _aggregate_routes(routes_path: Path, iata_to_iso3: dict[str, str]) -> dict[str, dict]:
    """Walk routes.dat and aggregate per-ISO3 stats."""
    # per ISO3: total leg count (each route contributes to both src and dst)
    leg_count: dict[str, int] = {}
    # per ISO3: set of distinct destination ISO3 codes reached from this country
    unique_dests: dict[str, set[str]] = {}
    rows = 0
    skipped = 0
    with routes_path.open(encoding="utf-8") as fp:
        reader = csv.reader(fp)
        for row in reader:
            rows += 1
            # routes.dat has 9 fields. Some entries use "\\N" for missing IDs.
            if len(row) < 9:
                skipped += 1
                continue
            src_iata = row[2].strip()
            dst_iata = row[4].strip()
            if not src_iata or not dst_iata:
                skipped += 1
                continue
            src_iso3 = iata_to_iso3.get(src_iata)
            dst_iso3 = iata_to_iso3.get(dst_iata)
            if src_iso3 is None and dst_iso3 is None:
                skipped += 1
                continue
            if src_iso3 is not None:
                leg_count[src_iso3] = leg_count.get(src_iso3, 0) + 1
                if dst_iso3 is not None:
                    unique_dests.setdefault(src_iso3, set()).add(dst_iso3)
            if dst_iso3 is not None:
                leg_count[dst_iso3] = leg_count.get(dst_iso3, 0) + 1
                if src_iso3 is not None:
                    unique_dests.setdefault(dst_iso3, set()).add(src_iso3)
    logger.info("Walked %d route rows; %d skipped (no mappable endpoint)", rows, skipped)
    out: dict[str, dict] = {}
    all_iso3 = set(leg_count) | set(unique_dests)
    for iso3 in sorted(all_iso3):
        # unique_dests stores the set including the country itself only if a
        # route returns to its origin; subtract self-loops to keep "destination
        # countries other than self" the conservative interpretation.
        dests = unique_dests.get(iso3, set()).copy()
        dests.discard(iso3)
        out[iso3] = {
            "airport_routes": leg_count.get(iso3, 0),
            "airport_unique_destinations": len(dests),
        }
    return out


def main() -> int:
    routes_path, airports_path = _ensure_raw_files()
    iata_to_iso3 = _load_airport_to_iso3(airports_path)
    if not iata_to_iso3:
        logger.error("No airports mapped to ISO3 - check NAME_TO_ISO3 and source file.")
        return 2
    aggregated = _aggregate_routes(routes_path, iata_to_iso3)
    if not aggregated:
        logger.error("Aggregation produced no rows - aborting.")
        return 2

    APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
    out_path = APP_DATA_DIR / "airport_routes.json"
    payload = {
        "_meta": {
            "source": "OpenFlights routes.dat + airports.dat",
            "source_urls": [ROUTES_URL, AIRPORTS_URL],
            "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "n_countries": len(aggregated),
            "fields": {
                "airport_routes": "Total inbound + outbound route legs touching the country",
                "airport_unique_destinations": (
                    "Distinct destination ISO3 codes reachable via direct flights "
                    "from the country's airports (route-degree proxy)"
                ),
            },
        },
        "countries": aggregated,
    }
    out_path.write_text(json.dumps(payload, indent=2, sort_keys=True))
    logger.info("Wrote %s (%d countries)", out_path, len(aggregated))
    # Human-friendly preview of the top 5.
    top = sorted(aggregated.items(), key=lambda kv: -kv[1]["airport_unique_destinations"])[:5]
    logger.info("Top 5 by airport_unique_destinations: %s", top)
    return 0


if __name__ == "__main__":
    sys.exit(main())
