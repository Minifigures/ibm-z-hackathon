# Mobility data ingestion scripts

These scripts produce the per-country JSON files that
`backend/app/mobility.py` reads at module load. If the JSON files are missing
the simulator falls back to the synthetic `hub_index` field on every country
in `backend/app/data/countries.json`, so the system still runs without them.

## Files produced

- `backend/app/data/airport_routes.json` — produced by `ingest_openflights.py`
- `backend/app/data/port_calls.json` — produced by `ingest_ports.py`

Each output file contains a `_meta` block (with the source URL/citation, the
`generated_utc` timestamp, and a description of every metric field) and a
`countries` map keyed by ISO3.

## Setup

```
pip install -r scripts/requirements.txt
```

The only new runtime dependency is `requests`. We keep it in this
sub-requirements file rather than `backend/requirements.txt` so the API
service image doesn't carry the ingest tooling.

## Running

From the `backend/` directory:

```
python scripts/ingest_openflights.py
python scripts/ingest_ports.py
```

Both scripts are idempotent. The OpenFlights script caches the raw
`routes.dat` and `airports.dat` under `backend/scripts/data/`; delete the
cached files to force a fresh download on the next run.

## Sources

### OpenFlights (`ingest_openflights.py`)

- `https://raw.githubusercontent.com/jpatokal/openflights/master/data/routes.dat`
- `https://raw.githubusercontent.com/jpatokal/openflights/master/data/airports.dat`
- Schema reference: <https://openflights.org/data.html>

For each ISO3 country in `countries.json` we compute:

- `airport_routes` — total inbound + outbound route legs touching the country
- `airport_unique_destinations` — distinct destination ISO3 codes reachable
  via a direct flight from the country's airports. This is the route-degree
  proxy `mobility.py` consumes.

`OpenFlights` country names are mapped to ISO3 via a hand-curated dict in
`ingest_openflights.py::NAME_TO_ISO3`. Countries not in that dict (mostly
small islands like French Polynesia and the like) are logged and skipped —
they're not in `countries.json` either, so this is harmless.

### Ports (`ingest_ports.py`)

- Source: Lloyd's List "One Hundred Ports 2023" + World Shipping Council
  "Top 50 World Container Ports", reporting calendar-year **2022**
  throughput (TEU = twenty-foot-equivalent units).
- Lloyd's List: <https://lloydslist.maritimeintelligence.informa.com/one-hundred-container-ports-2023>
- WSC: <https://www.worldshipping.org/top-50-ports>

The Top-50 list is embedded in the script as a CSV constant. Each row is one
port; we sum TEU per ISO3 to produce the country-level snapshot. This is a
deliberate static snapshot — there is no clean live port-call API suitable
for a hackathon. Refresh by editing the `TOP_PORTS_CSV` constant when the
next-year ranking publishes (typically every August).

## Last refresh

| Script                 | Last run    | Source year |
|------------------------|-------------|-------------|
| `ingest_openflights.py` | 2026-05-10 | OpenFlights master (rolling) |
| `ingest_ports.py`       | 2026-05-10 | 2022 (Lloyd's List 2023 ranking) |

## What `mobility.py` does with this data

At module import:

1. Loads both JSON files. If a file is missing or malformed, logs a warning
   and uses the synthetic `hub_index` array exclusively.
2. Builds two hybrid arrays — `real_air_hub()` and `real_port_hub()` — where
   countries with real data use the rescaled metric and the rest fall back
   to their `hub_index`. The rescaling matches the *mean* of the real
   subset to the synthetic hub mean over the same subset, which keeps the
   absolute scale of the gravity output (and the downstream 5M / 200k
   normalization targets) comparable to the previous behavior. Tests around
   mobility scale (`test_air_flow_normalized_to_target_total` etc.) pass
   unchanged.
