"""Aggregate a static Top-50 container ports snapshot to per-country TEU.

Source:
    Lloyd's List "One Hundred Ports 2023" (calendar-year 2022 throughput) and
    World Shipping Council "Top 50 World Container Ports" rankings, both of
    which publish the same underlying numbers from each port authority. TEU =
    twenty-foot-equivalent unit, the standard container-throughput unit.

    https://lloydslist.maritimeintelligence.informa.com/one-hundred-container-ports-2023
    https://www.worldshipping.org/top-50-ports

Snapshot year: 2022 (the 2023 rankings report 2022 throughput). This is a
hackathon-grade static snapshot - we do NOT pretend to be live data; the
README documents this clearly. The values are ports' annual TEU in millions,
from publicly reported port-authority figures rounded to the published
precision.

Output: backend/app/data/port_calls.json
    {
        "_meta": {...},
        "countries": {
            "CHN": {"port_teu_millions": <float>, "port_count": <int>},
            ...
        }
    }

We aggregate per ISO3 by summing TEU across that country's ports in the
top-50 list. Countries without a top-50 port are absent; mobility.py falls
back to the synthetic hub_index for those.

Run:
    python scripts/ingest_ports.py
"""

from __future__ import annotations

import csv
import io
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("ingest_ports")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

SCRIPT_DIR = Path(__file__).resolve().parent
APP_DATA_DIR = SCRIPT_DIR.parent / "app" / "data"

SOURCE_YEAR = 2022
SOURCE_LABEL = (
    "Lloyd's List One Hundred Ports 2023 / World Shipping Council Top 50 "
    "(reported 2022 throughput)"
)

# Top-50 container ports by 2022 TEU throughput, in millions of TEU.
# Each row: rank, port_name, country_iso3, teu_millions.
# Numbers rounded to the precision published by Lloyd's List / WSC.
TOP_PORTS_CSV = """rank,port,iso3,teu_millions
1,Shanghai,CHN,47.30
2,Singapore,SGP,37.29
3,Ningbo-Zhoushan,CHN,33.35
4,Shenzhen,CHN,30.04
5,Qingdao,CHN,25.67
6,Guangzhou,CHN,24.60
7,Busan,KOR,22.07
8,Tianjin,CHN,21.02
9,Hong Kong,HKG,16.69
10,Rotterdam,NLD,14.45
11,Dubai (Jebel Ali),ARE,13.97
12,Port Klang,MYS,13.22
13,Antwerp-Bruges,BEL,13.50
14,Xiamen,CHN,12.43
15,Tanjung Pelepas,MYS,10.51
16,Kaohsiung,TWN,9.49
17,Los Angeles,USA,9.91
18,Hamburg,DEU,8.30
19,Long Beach,USA,9.13
20,Laem Chabang,THA,8.74
21,New York/New Jersey,USA,9.49
22,Tanger Med,MAR,7.59
23,Ho Chi Minh City,VNM,7.86
24,Colombo,LKA,6.86
25,Jakarta (Tanjung Priok),IDN,6.57
26,Algeciras,ESP,4.76
27,Valencia,ESP,5.08
28,Piraeus,GRC,5.06
29,Mundra,IND,7.17
30,Manila,PHL,5.04
31,Jeddah,SAU,4.54
32,Cartagena,COL,3.51
33,Yokohama,JPN,2.88
34,Bremerhaven,DEU,4.61
35,Mersin,TUR,2.06
36,Tokyo,JPN,4.27
37,Felixstowe,GBR,3.50
38,Salalah,OMN,4.50
39,Le Havre,FRA,3.04
40,Karachi (Qasim/KICT),PAK,3.30
41,Savannah,USA,5.89
42,Houston,USA,3.97
43,Norfolk (Virginia),USA,3.72
44,Seattle/Tacoma (NWSA),USA,3.38
45,Buenos Aires,ARG,1.45
46,Santos,BRA,5.20
47,Durban,ZAF,2.51
48,Chittagong,BGD,3.21
49,Haifa,ISR,1.50
50,Sydney (Port Botany),AUS,2.66
"""


def _aggregate(csv_text: str) -> dict[str, dict]:
    out: dict[str, dict] = {}
    reader = csv.DictReader(io.StringIO(csv_text))
    for row in reader:
        iso3 = row["iso3"].strip()
        teu = float(row["teu_millions"])
        bucket = out.setdefault(iso3, {"port_teu_millions": 0.0, "port_count": 0})
        bucket["port_teu_millions"] += teu
        bucket["port_count"] += 1
    # Round to two decimals to match published precision.
    for v in out.values():
        v["port_teu_millions"] = round(v["port_teu_millions"], 3)
    return out


def main() -> int:
    aggregated = _aggregate(TOP_PORTS_CSV)
    if not aggregated:
        logger.error("Empty aggregation - source CSV is malformed.")
        return 2

    APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
    out_path = APP_DATA_DIR / "port_calls.json"
    payload = {
        "_meta": {
            "source": SOURCE_LABEL,
            "source_year": SOURCE_YEAR,
            "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "n_countries": len(aggregated),
            "fields": {
                "port_teu_millions": (
                    "Sum of TEU (millions, annual) across this country's ports "
                    "in the published Top-50 ranking. Used as a port-call volume "
                    "proxy in the gravity model."
                ),
                "port_count": "How many of the country's ports appear in the Top-50",
            },
            "notes": (
                "Static snapshot; refresh manually when the next ranking publishes. "
                "Countries absent here fall back to the synthetic hub_index in mobility.py."
            ),
        },
        "countries": aggregated,
    }
    out_path.write_text(json.dumps(payload, indent=2, sort_keys=True))
    logger.info("Wrote %s (%d countries)", out_path, len(aggregated))
    top = sorted(aggregated.items(), key=lambda kv: -kv[1]["port_teu_millions"])[:5]
    logger.info("Top 5 by port_teu_millions: %s", top)
    return 0


if __name__ == "__main__":
    sys.exit(main())
