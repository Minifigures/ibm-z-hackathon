"""Aggregate BTS T-100 international passenger CSV into US-anchored country-pair
passenger volumes.

Source: Kaggle "U.S. International Air Traffic data (1990-2020)" — a mirror of
BTS T-100 International Segment data, expected at::

    backend/scripts/data/kaggle/International_Report_Passengers.csv

Joins foreign IATA airports to ISO3 country codes via OpenFlights airports.dat
(already downloaded by ingest_openflights.py).

Output: backend/app/data/bts_passenger_flows.json with the schema::

    {
        "_meta": { ... source, year, n_pairs ... },
        "year": 2019,
        "from_us_to_country": { "MEX": 30000000, "CAN": 25000000, ... },
        "from_country_to_us": { "MEX": 31000000, ... }
    }

Run from backend/::
    python -m scripts.ingest_bts
"""

from __future__ import annotations

import csv
import json
import logging
import sys
from collections import defaultdict
from pathlib import Path

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

REPO_BACKEND = Path(__file__).resolve().parent.parent
BTS_CSV   = REPO_BACKEND / "scripts" / "data" / "kaggle" / "International_Report_Passengers.csv"
AIRPORTS  = REPO_BACKEND / "scripts" / "data" / "airports.dat"
OUT_PATH  = REPO_BACKEND / "app" / "data" / "bts_passenger_flows.json"
COUNTRIES_PATH = REPO_BACKEND / "app" / "data" / "countries.json"

TARGET_YEAR = 2019  # last full pre-pandemic year

# Mapping from OpenFlights country names to ISO3. The OpenFlights file uses
# full common names ("United States"), so we need to convert to ISO3.
NAME_TO_ISO3 = {
    "United States": "USA", "United Kingdom": "GBR", "China": "CHN",
    "Japan": "JPN", "South Korea": "KOR", "Korea": "KOR",
    "France": "FRA", "Germany": "DEU", "Spain": "ESP", "Italy": "ITA",
    "Portugal": "PRT", "Netherlands": "NLD", "Belgium": "BEL",
    "Mexico": "MEX", "Canada": "CAN", "Brazil": "BRA", "Argentina": "ARG",
    "Chile": "CHL", "Colombia": "COL", "Peru": "PER", "Venezuela": "VEN",
    "Cuba": "CUB", "Dominican Republic": "DOM", "Costa Rica": "CRI",
    "Guatemala": "GTM", "El Salvador": "SLV", "Honduras": "HND",
    "Panama": "PAN", "Jamaica": "JAM", "Bahamas": "BHS",
    "India": "IND", "Pakistan": "PAK", "Bangladesh": "BGD",
    "Thailand": "THA", "Vietnam": "VNM", "Philippines": "PHL",
    "Indonesia": "IDN", "Malaysia": "MYS", "Singapore": "SGP",
    "Australia": "AUS", "New Zealand": "NZL",
    "Russia": "RUS", "Russian Federation": "RUS",
    "Turkey": "TUR", "Saudi Arabia": "SAU", "United Arab Emirates": "ARE",
    "Israel": "ISR", "Egypt": "EGY", "Morocco": "MAR", "Algeria": "DZA",
    "Tunisia": "TUN", "South Africa": "ZAF", "Nigeria": "NGA",
    "Kenya": "KEN", "Ethiopia": "ETH", "Ghana": "GHA",
    "Greece": "GRC", "Sweden": "SWE", "Norway": "NOR", "Denmark": "DNK",
    "Finland": "FIN", "Poland": "POL", "Czech Republic": "CZE",
    "Hungary": "HUN", "Austria": "AUT", "Switzerland": "CHE",
    "Ireland": "IRL", "Iceland": "ISL", "Romania": "ROU",
    "Hong Kong": "HKG", "Hong Kong SAR China": "HKG",
    "Taiwan": "TWN",
    "Iran": "IRN", "Iraq": "IRQ", "Lebanon": "LBN", "Jordan": "JOR",
    "Qatar": "QAT", "Kuwait": "KWT", "Bahrain": "BHR", "Oman": "OMN",
    "Yemen": "YEM", "Afghanistan": "AFG", "Kazakhstan": "KAZ",
    "Sri Lanka": "LKA", "Nepal": "NPL", "Myanmar": "MMR", "Cambodia": "KHM",
    "Ecuador": "ECU", "Bolivia": "BOL", "Paraguay": "PRY", "Uruguay": "URY",
    "Trinidad and Tobago": "TTO", "Haiti": "HTI",
}


def build_iata_to_iso3() -> dict[str, str]:
    """Parse OpenFlights airports.dat -> {IATA: ISO3}. Skips airports without IATA."""
    iata_to_iso = {}
    skipped = 0
    with AIRPORTS.open(encoding="utf-8") as f:
        for row in csv.reader(f):
            if len(row) < 5: continue
            iata = row[4].strip('"')
            country_name = row[3].strip('"')
            if not iata or len(iata) != 3 or iata == "\\N":
                continue
            iso3 = NAME_TO_ISO3.get(country_name)
            if iso3:
                iata_to_iso[iata] = iso3
            else:
                skipped += 1
    logger.info(
        "IATA->ISO3 map built: %d airports mapped, %d skipped (country not in mapping)",
        len(iata_to_iso), skipped,
    )
    return iata_to_iso


def build_modeled_iso3() -> set[str]:
    raw = json.loads(COUNTRIES_PATH.read_text())
    return {row["iso3"] for row in raw}


def aggregate(iata_to_iso: dict[str, str]) -> tuple[dict, dict, int]:
    """Sum passenger Totals over the target year, both directions.

    BTS T-100 international has rows tagged with US gateway (usg_apt) and
    foreign airport (fg_apt). Each row covers all flights between that
    airport pair in that month for one carrier. Total can be passengers
    flowing in either direction depending on the report; we treat each row
    as bidirectional aggregate per BTS's documentation, then split into
    US-out and US-in by gateway airport's flag (the dataset doesn't break
    direction at the row level, so we sum into both directions equally
    weighted per row).
    """
    out_to_country: dict[str, int] = defaultdict(int)  # USA -> X
    in_from_country: dict[str, int] = defaultdict(int)  # X -> USA
    rows_processed = 0
    rows_kept = 0

    with BTS_CSV.open(encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            rows_processed += 1
            try:
                year = int(row["Year"])
            except (KeyError, ValueError):
                continue
            if year != TARGET_YEAR:
                continue
            try:
                total = int(row["Total"])
            except (KeyError, ValueError):
                continue
            if total <= 0:
                continue
            fg_iata = row.get("fg_apt", "").strip()
            iso3 = iata_to_iso.get(fg_iata)
            if not iso3:
                continue
            out_to_country[iso3] += total
            in_from_country[iso3] += total
            rows_kept += 1

    logger.info(
        "BTS rows: processed=%d, kept (year=%d, mapped, total>0)=%d",
        rows_processed, TARGET_YEAR, rows_kept,
    )
    return dict(out_to_country), dict(in_from_country), rows_kept


def main():
    # VSI mirror first, then fall through. The Kaggle source needs an API
    # token (parulpandey/us-international-air-traffic-data); the VSI hosts
    # the same files unauthenticated for reproducibility.
    from ._data_source import fetch
    fetch(
        local=BTS_CSV,
        vsi_path="bts/International_Report_Passengers.csv",
        public_url=None,  # Kaggle CSV requires `kaggle datasets download` + auth
    )
    fetch(
        local=AIRPORTS,
        vsi_path="openflights/airports.dat",
        public_url="https://raw.githubusercontent.com/jpatokal/openflights/master/data/airports.dat",
    )

    iata_to_iso = build_iata_to_iso3()
    modeled = build_modeled_iso3()

    out_to, in_from, n_rows = aggregate(iata_to_iso)

    # Restrict output to ISO3s the model knows about.
    out_to = {k: v for k, v in out_to.items() if k in modeled}
    in_from = {k: v for k, v in in_from.items() if k in modeled}

    payload = {
        "_meta": {
            "source": "Kaggle parulpandey/us-international-air-traffic-data (BTS T-100 International Passengers)",
            "year": TARGET_YEAR,
            "rows_aggregated": n_rows,
            "n_country_pairs": len(out_to),
            "note": "Per-country annual passenger totals on US-anchored international routes. Symmetric (BTS row Total is bidirectional aggregate).",
        },
        "year": TARGET_YEAR,
        "from_us_to_country": dict(sorted(out_to.items(), key=lambda x: -x[1])),
        "from_country_to_us": dict(sorted(in_from.items(), key=lambda x: -x[1])),
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(payload, indent=2))
    logger.info("Wrote %s with %d country-pair entries.", OUT_PATH, len(out_to))

    print("\nTop 10 US-anchored corridors by 2019 passengers:")
    for iso3, n in list(payload["from_us_to_country"].items())[:10]:
        print(f"  USA <-> {iso3}: {n:>11,d}")


if __name__ == "__main__":
    main()
