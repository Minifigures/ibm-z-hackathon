"""Shared helper: fetch a raw data file with VSI mirror first, public fallback.

The hackathon team mirrors all raw upstream data files at
``http://163.66.95.111/data/raw/`` (the IBM Cloud VSI). This is faster, more
stable, and removes auth requirements (BTS Kaggle token, UN CloudFront UA
gymnastics, slow Eurostat queries).

Usage::

    from scripts._data_source import fetch

    fetch(
        local=Path("backend/scripts/data/un_migrant_stock_2020.xlsx"),
        vsi_path="un/un_migrant_stock_2020.xlsx",
        public_url="https://www.un.org/.../undesa_pd_2020_..._origin.xlsx",
        public_headers={"User-Agent": "Mozilla/5.0 ..."},
    )

Returns the local Path (downloads if missing, no-op if already present).
Override the mirror with ``RAW_DATA_BASE=https://...`` if you want to point
the team's pipeline at a different mirror.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

VSI_DEFAULT = "http://163.66.95.111/data/raw"


def vsi_base() -> str:
    """Resolve the mirror base URL. Override with RAW_DATA_BASE env var."""
    return os.environ.get("RAW_DATA_BASE", VSI_DEFAULT).rstrip("/")


def fetch(
    local: Path,
    vsi_path: str | None = None,
    public_url: str | None = None,
    public_headers: dict | None = None,
    timeout: int = 120,
    chunk: int = 1 << 20,
) -> Path:
    """Ensure ``local`` exists. Tries the VSI mirror first, then public_url.

    - If ``local`` already exists and is non-empty, return immediately.
    - Otherwise GET ``{vsi_base()}/{vsi_path}`` (if vsi_path is given).
    - On failure, fall back to ``public_url`` (if given).
    - On failure of both, raise.

    Streams to disk in 1 MB chunks so big files don't blow up memory.
    """
    if local.exists() and local.stat().st_size > 0:
        logger.info("cached: %s (%d bytes)", local, local.stat().st_size)
        return local

    local.parent.mkdir(parents=True, exist_ok=True)
    candidates: list[tuple[str, dict | None]] = []
    if vsi_path:
        candidates.append((f"{vsi_base()}/{vsi_path.lstrip('/')}", None))
    if public_url:
        candidates.append((public_url, public_headers))

    last_err: Exception | None = None
    for url, headers in candidates:
        logger.info("fetching %s -> %s", url, local)
        try:
            with requests.get(url, headers=headers or {}, stream=True, timeout=timeout) as resp:
                resp.raise_for_status()
                with local.open("wb") as f:
                    for c in resp.iter_content(chunk_size=chunk):
                        if c: f.write(c)
            if local.stat().st_size == 0:
                raise RuntimeError(f"empty response from {url}")
            logger.info("got %d bytes from %s", local.stat().st_size, url)
            return local
        except (requests.RequestException, RuntimeError) as e:
            logger.warning("source failed (%s): %s", url, e)
            last_err = e
            local.unlink(missing_ok=True)

    raise RuntimeError(
        f"all sources failed for {local.name}; last error: {last_err}"
    )
