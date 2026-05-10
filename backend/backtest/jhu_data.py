"""Download + parse the JHU CSSE confirmed-cases global time series.

The CSV lives in the archived `CSSEGISandData/COVID-19` repo on GitHub. We
cache it locally in ``backend/backtest/data/`` so re-runs are offline-safe.

Only the columns we need are returned: a mapping from ISO-3 country code to a
dict ``{date_iso: cumulative_confirmed}``. Province-level rows are summed up
to a single country total so that, e.g., all 30+ US state rows collapse to a
single ``USA`` series.

JHU country names are not ISO-3 codes; we apply a lookup table for the names
that appear in the file. Anything not in the table (or not in the model's
``countries.json``) is dropped silently — the backtest only scores countries
the model can actually simulate.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Iterator

import requests

JHU_URL = (
    "https://raw.githubusercontent.com/CSSEGISandData/COVID-19/master/"
    "csse_covid_19_data/csse_covid_19_time_series/"
    "time_series_covid19_confirmed_global.csv"
)

CACHE_DIR = Path(__file__).parent / "data"
CACHE_FILE = CACHE_DIR / "time_series_covid19_confirmed_global.csv"

# JHU country/region label -> ISO-3 code present in countries.json.
# Anything not in this map (e.g. "Andorra", "Holy See", small islands) is
# dropped because the model does not simulate them.
JHU_TO_ISO3: dict[str, str] = {
    "US": "USA",
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
    "Burma": "MMR",            # JHU uses Burma; countries.json uses MMR
    "Thailand": "THA",
    "Vietnam": "VNM",
    "Malaysia": "MYS",
    "Singapore": "SGP",
    "Indonesia": "IDN",
    "Philippines": "PHL",
    "China": "CHN",             # mainland China; HK/Macau/Taiwan are separate JHU rows
    # Hong Kong appears as a province under "China" in JHU; handled below
    "Taiwan*": "TWN",           # JHU literally writes "Taiwan*"
    "Japan": "JPN",
    "Korea, South": "KOR",
    "Australia": "AUS",
    "New Zealand": "NZL",
    "Kazakhstan": "KAZ",
    "Uzbekistan": "UZB",
    "Afghanistan": "AFG",
    "Romania": "ROU",
    "Czechia": "CZE",
    "Hungary": "HUN",
}

# Hong Kong appears as a Province/State under Country/Region "China" in JHU.
# We split it out so the model's HKG entry can be scored separately, and so
# the CHN total excludes HK/Macau (as countries.json treats them as distinct).
HK_PROVINCE_LABEL = "Hong Kong"
MACAU_PROVINCE_LABEL = "Macau"


def fetch_jhu_csv(force_download: bool = False) -> str:
    """Return the JHU confirmed-cases CSV body, downloading if not cached."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    if CACHE_FILE.exists() and not force_download:
        return CACHE_FILE.read_text(encoding="utf-8")

    try:
        resp = requests.get(JHU_URL, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise RuntimeError(
            f"Failed to download JHU CSSE data from {JHU_URL!r}. "
            "If you are offline, place a copy of the CSV at "
            f"{CACHE_FILE} and re-run."
        ) from exc

    CACHE_FILE.write_text(resp.text, encoding="utf-8")
    return resp.text


def _iter_rows(csv_text: str) -> Iterator[list[str]]:
    return csv.reader(io.StringIO(csv_text))


def parse_jhu(csv_text: str) -> tuple[list[str], dict[str, dict[str, int]]]:
    """Parse JHU CSV.

    Returns
    -------
    dates : list[str]
        Date column headers in ISO format (``YYYY-MM-DD``).
    by_iso3 : dict[str, dict[str, int]]
        ``iso3 -> {date_iso: cumulative_confirmed}``. Provinces are summed
        into the country total. Hong Kong is split out as ``HKG``.
    """
    rows = list(_iter_rows(csv_text))
    if not rows:
        raise RuntimeError("JHU CSV appears to be empty.")

    header = rows[0]
    # Header layout: Province/State, Country/Region, Lat, Long, m/d/yy, m/d/yy, ...
    raw_dates = header[4:]
    dates_iso = [_jhu_date_to_iso(d) for d in raw_dates]

    by_iso3: dict[str, dict[str, int]] = {}

    for row in rows[1:]:
        if len(row) < 5:
            continue
        province = row[0].strip()
        country = row[1].strip()
        # Special case: Hong Kong province under China -> HKG
        if country == "China" and province == HK_PROVINCE_LABEL:
            iso3 = "HKG"
        elif country == "China" and province == MACAU_PROVINCE_LABEL:
            # Not in countries.json, drop.
            continue
        else:
            iso3 = JHU_TO_ISO3.get(country)
            if iso3 is None:
                continue

        series = by_iso3.setdefault(iso3, {d: 0 for d in dates_iso})
        for date_iso, val_str in zip(dates_iso, row[4:]):
            try:
                v = int(val_str) if val_str else 0
            except ValueError:
                # Some early rows have floats, e.g. "0.0".
                try:
                    v = int(float(val_str))
                except ValueError:
                    v = 0
            series[date_iso] += v

    return dates_iso, by_iso3


def _jhu_date_to_iso(jhu_date: str) -> str:
    """Convert ``M/D/YY`` (e.g. ``1/22/20``) to ISO ``YYYY-MM-DD``."""
    parts = jhu_date.strip().split("/")
    if len(parts) != 3:
        raise ValueError(f"Unrecognized JHU date format: {jhu_date!r}")
    m, d, y = parts
    year = int(y)
    year += 2000 if year < 100 else 0
    return f"{year:04d}-{int(m):02d}-{int(d):02d}"


def load_country_counts() -> tuple[list[str], dict[str, dict[str, int]]]:
    """Convenience wrapper: download (or read cache) + parse."""
    csv_text = fetch_jhu_csv()
    return parse_jhu(csv_text)


if __name__ == "__main__":
    dates, data = load_country_counts()
    print(f"Loaded JHU series: {len(dates)} dates, {len(data)} countries.")
    print(f"First date: {dates[0]}  Last date: {dates[-1]}")
    sample = ["CHN", "USA", "ITA", "KOR", "JPN", "HKG"]
    for iso in sample:
        if iso in data:
            print(f"  {iso} on 2020-02-21: {data[iso].get('2020-02-21', 'n/a')}")
