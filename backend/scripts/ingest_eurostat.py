"""Extract 2019 bilateral passenger volumes from Eurostat avia_paocc.

Source: Eurostat dataset AVIA_PAOCC, "Air passenger transport between
reporting and partner countries by type of schedule." JSON-stat 2.0 format,
gzip-compressed, ~55 MB.

Filters to: freq=A (annual), unit=PAS (passengers), tra_meas=PAS_CRD
(passengers carried, both directions), schedule=TOT (all schedules),
time=2019 (last full pre-pandemic year).

Output: backend/app/data/eurostat_passenger_flows.json with the schema::

    {
        "_meta": { ... },
        "year": 2019,
        "pairs": { "GBR_ESP": 18000000, ... }   # ISO3 pair, sorted alphabetically
    }

Run from backend/::
    python -m scripts.ingest_eurostat
"""

from __future__ import annotations

import gzip
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

REPO_BACKEND = Path(__file__).resolve().parent.parent
SRC = REPO_BACKEND / "scripts" / "data" / "eurostat" / "avia_paocc_2019.json"
OUT = REPO_BACKEND / "app" / "data" / "eurostat_passenger_flows.json"

# Eurostat country codes (mostly ISO2 but with some EU aggregates) -> ISO3.
# We drop EU aggregates (EU27_2020, EU28, EA, etc.) and keep only individual
# countries. Codes that map to nothing get skipped.
EUROSTAT_TO_ISO3 = {
    "AT": "AUT", "BE": "BEL", "BG": "BGR", "CY": "CYP", "CZ": "CZE",
    "DE": "DEU", "DK": "DNK", "EE": "EST", "EL": "GRC", "ES": "ESP",
    "FI": "FIN", "FR": "FRA", "HR": "HRV", "HU": "HUN", "IE": "IRL",
    "IS": "ISL", "IT": "ITA", "LT": "LTU", "LU": "LUX", "LV": "LVA",
    "MT": "MLT", "NL": "NLD", "NO": "NOR", "PL": "POL", "PT": "PRT",
    "RO": "ROU", "SE": "SWE", "SI": "SVN", "SK": "SVK", "TR": "TUR",
    "UK": "GBR",
    # Aggregates we want to skip
    "EU27_2020": None, "EU28": None, "EU27_2007": None,
    "EA19": None, "EA20": None, "EFTA": None, "EEA": None,
}


def linear_to_coords(idx: int, sizes: list[int]) -> list[int]:
    """JSON-stat row-major linearization."""
    coords = []
    for s in reversed(sizes):
        idx, rem = divmod(idx, s)
        coords.append(rem)
    return list(reversed(coords))


def main():
    if not SRC.exists():
        raise SystemExit(f"Source not found: {SRC}. Download it first.")
    logger.info("Loading %s ...", SRC.name)
    with gzip.open(SRC, "rt", encoding="utf-8") as f:
        d = json.load(f)

    sizes = d["size"]
    dim_ids = d["id"]
    logger.info("dims: %s, sizes: %s, values: %d", dim_ids, sizes, len(d["value"]))

    # Build inverse indices for the dims we care about
    cat = lambda dim: d["dimension"][dim]["category"]["index"]
    target = {
        "freq":     cat("freq")["A"],
        "unit":     cat("unit")["PAS"],
        "tra_meas": cat("tra_meas")["PAS_CRD"],
        "schedule": cat("schedule")["TOT"],
        "time":     cat("time")["2019"],
    }
    partner_inv = {v: k for k, v in cat("partner").items()}
    geo_inv     = {v: k for k, v in cat("geo").items()}

    pos_of = {dim: dim_ids.index(dim) for dim in dim_ids}

    # Iterate. For each value, decode coords, filter to our targets, capture
    # geo-partner symmetrized total.
    pair_totals: dict[tuple[str, str], float] = {}
    n_kept = 0
    skipped_aggregate = 0
    skipped_unmapped = 0
    for k_str, val in d["value"].items():
        coords = linear_to_coords(int(k_str), sizes)
        if (
            coords[pos_of["freq"]]     != target["freq"]     or
            coords[pos_of["unit"]]     != target["unit"]     or
            coords[pos_of["tra_meas"]] != target["tra_meas"] or
            coords[pos_of["schedule"]] != target["schedule"] or
            coords[pos_of["time"]]     != target["time"]
        ):
            continue
        partner_code = partner_inv[coords[pos_of["partner"]]]
        geo_code     = geo_inv[coords[pos_of["geo"]]]

        partner_iso = EUROSTAT_TO_ISO3.get(partner_code)
        geo_iso     = EUROSTAT_TO_ISO3.get(geo_code)
        if partner_iso is None or geo_iso is None:
            if partner_code in EUROSTAT_TO_ISO3 or geo_code in EUROSTAT_TO_ISO3:
                skipped_aggregate += 1
            else:
                skipped_unmapped += 1
            continue
        if partner_iso == geo_iso:
            continue

        # Symmetrize: store as alphabetically-sorted pair so each pair gets
        # a single entry summing both reporters.
        pair = tuple(sorted([geo_iso, partner_iso]))
        pair_totals[pair] = pair_totals.get(pair, 0) + float(val)
        n_kept += 1

    logger.info(
        "kept=%d, skipped_aggregate=%d, skipped_unmapped=%d, unique_pairs=%d",
        n_kept, skipped_aggregate, skipped_unmapped, len(pair_totals),
    )

    # Symmetric data: when both reporters report the same pair, we summed
    # twice. Halve to get the actual passenger total per pair.
    pair_totals = {p: v / 2 for p, v in pair_totals.items()}

    # Sort by descending volume
    pairs_sorted = sorted(pair_totals.items(), key=lambda x: -x[1])
    pairs_dict = {f"{a}_{b}": int(v) for (a, b), v in pairs_sorted}

    payload = {
        "_meta": {
            "source": "Eurostat AVIA_PAOCC (JSON-stat 2.0 via Eurostat REST API)",
            "url": "https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/data/avia_paocc",
            "year": 2019,
            "filters": "freq=A unit=PAS tra_meas=PAS_CRD schedule=TOT",
            "n_pairs": len(pairs_dict),
            "note": "Bilateral passengers-carried between reporting EU countries and partner countries. Pairs are alphabetically-sorted ISO3 keys (e.g. ESP_GBR). Summed across both reporter directions and halved to avoid double-counting.",
        },
        "year": 2019,
        "pairs": pairs_dict,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2))
    logger.info("Wrote %s", OUT)

    print("\nTop 15 EU bilateral corridors by 2019 passengers carried:")
    for k, v in list(pairs_dict.items())[:15]:
        print(f"  {k:<10} {v:>12,d}")


if __name__ == "__main__":
    main()
