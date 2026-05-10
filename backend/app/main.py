"""FastAPI entry point for the Disease Outflow Forecaster.

Endpoints
- GET  /health
- GET  /countries     -> list of modelled regions (id, name, lat, lng, population)
- GET  /presets       -> disease parameter presets
- POST /simulate      -> run SEIR + Monte Carlo, return per-region quantile bands
- POST /explain       -> LLM-generated narrative for the latest simulation
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

load_dotenv()

from .data_sources import manifest as data_sources_manifest
from .disease_lookup import lookup as disease_lookup
from .explain import explain
from .mobility import load_countries
from .nowcast import NowcastObservation, NowcastParams, run_nowcast
from .rate_limit import rate_limit
from .simulate import SimParams, run

# Per-IP sliding-window rate limit applied to the watsonx/CPU-heavy endpoints.
# The numbers are demo-friendly: a real interactive user will not exceed 10
# nowcasts per minute, but a tight loop hitting the backend will get 429'd.
nowcast_limiter = rate_limit(max_calls=10, window_seconds=60)
disease_lookup_limiter = rate_limit(max_calls=20, window_seconds=60)

DATA_DIR = Path(__file__).parent / "data"

app = FastAPI(
    title="Disease Outflow Forecaster API",
    description="SEIR + gravity-mobility + Monte Carlo simulator for the IBM Z hackathon.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class SimulateRequest(BaseModel):
    disease_id: Literal["covid19", "flu", "mpox", "sars", "ebola", "pathogenx", "dengue2050"] = "covid19"
    start_iso3: str = Field("USA", min_length=3, max_length=3)
    r0: float = Field(2.5, ge=0.1, le=8.0)
    incubation_days: float = Field(5.0, ge=0.5, le=30.0)
    infectious_days: float = Field(6.0, ge=1.0, le=30.0)
    cfr_pct: float = Field(1.0, ge=0.0, le=50.0)
    air_weight: float = Field(1.0, ge=0.0, le=2.0)
    port_weight: float = Field(0.3, ge=0.0, le=2.0)
    travel_restriction: float = Field(0.0, ge=0.0, le=1.0)
    mask_intervention: float = Field(0.0, ge=0.0, le=1.0)
    horizon_days: int = Field(30, ge=7, le=180)
    n_runs: int = Field(200, ge=20, le=1000)


class ExplainRequest(BaseModel):
    simulation: dict[str, Any]
    focus_iso3: str | None = None


class NowcastObservationModel(BaseModel):
    day: int = Field(..., ge=0, le=365)
    cumulative_cases: float = Field(..., ge=0.0)


class NowcastRequest(SimulateRequest):
    # Cap the observation list so a malicious payload cannot blow up memory
    # or CPU. 365 is generous: a year of daily counts for a single seed.
    observations: list[NowcastObservationModel] = Field(..., min_length=1, max_length=365)
    n_particles: int = Field(400, ge=50, le=2000)
    rho_min: float = Field(0.02, gt=0.0, lt=1.0)
    rho_max: float = Field(0.5, gt=0.0, le=1.0)


class DiseaseLookupRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/data-sources")
def data_sources() -> dict[str, Any]:
    """Manifest of real-world mobility datasets feeding the simulator."""
    return data_sources_manifest()


@app.get("/countries")
def countries() -> list[dict[str, Any]]:
    return [
        {
            "iso3": c.iso3,
            "name": c.name,
            "lat": c.lat,
            "lng": c.lng,
            "population": c.population,
            "hub": c.hub,
        }
        for c in load_countries()
    ]


@app.get("/presets")
def presets() -> dict[str, Any]:
    return json.loads((DATA_DIR / "diseases.json").read_text())


@app.post("/simulate")
def simulate(req: SimulateRequest) -> dict[str, Any]:
    try:
        result = run(
            SimParams(
                disease_id=req.disease_id,
                start_iso3=req.start_iso3.upper(),
                r0=req.r0,
                incubation_days=req.incubation_days,
                infectious_days=req.infectious_days,
                cfr_pct=req.cfr_pct,
                air_weight=req.air_weight,
                port_weight=req.port_weight,
                travel_restriction=req.travel_restriction,
                mask_intervention=req.mask_intervention,
                horizon_days=req.horizon_days,
                n_runs=req.n_runs,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return result


@app.post("/explain")
def explain_endpoint(req: ExplainRequest) -> dict[str, Any]:
    # explain() should always return a dict, never raise — but template fallback
    # currently dereferences top_imports[0] without guarding for the empty case
    # (will be fixed properly in a follow-up). Wrap so the front-end gets a
    # readable error string instead of a 500 with no JSON.
    try:
        return explain(req.simulation, focus_iso3=req.focus_iso3)
    except Exception as exc:  # noqa: BLE001 - explainer is best-effort; surface the error
        import traceback as _tb
        return {
            "text": "Explainer crashed; using fallback.",
            "source": "error",
            "error": f"{type(exc).__name__}: {exc}",
            "trace": _tb.format_exc()[-600:],
        }


@app.post("/nowcast", dependencies=[Depends(nowcast_limiter)])
def nowcast_endpoint(req: NowcastRequest) -> dict[str, Any]:
    if req.rho_min >= req.rho_max:
        raise HTTPException(status_code=400, detail="rho_min must be < rho_max")
    base = SimParams(
        disease_id=req.disease_id,
        start_iso3=req.start_iso3.upper(),
        r0=req.r0,
        incubation_days=req.incubation_days,
        infectious_days=req.infectious_days,
        cfr_pct=req.cfr_pct,
        air_weight=req.air_weight,
        port_weight=req.port_weight,
        travel_restriction=req.travel_restriction,
        mask_intervention=req.mask_intervention,
        horizon_days=req.horizon_days,
        n_runs=req.n_particles,
    )
    try:
        return run_nowcast(
            NowcastParams(
                base=base,
                observations=[
                    NowcastObservation(day=o.day, cumulative_cases=o.cumulative_cases)
                    for o in req.observations
                ],
                n_particles=req.n_particles,
                rho_min=req.rho_min,
                rho_max=req.rho_max,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/disease-params", dependencies=[Depends(disease_lookup_limiter)])
def disease_params_endpoint(req: DiseaseLookupRequest) -> dict[str, Any]:
    result = disease_lookup(req.name)
    status = result.get("status")
    if status == "unconfigured":
        raise HTTPException(status_code=503, detail=result)
    if status == "rejected":
        raise HTTPException(status_code=422, detail=result)
    return result
