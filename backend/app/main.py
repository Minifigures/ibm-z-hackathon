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
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

load_dotenv()

from .disease_lookup import lookup as disease_lookup
from .explain import explain
from .mobility import load_countries
from .nowcast import NowcastObservation, NowcastParams, run_nowcast
from .simulate import SimParams, run

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
    disease_id: Literal["covid19", "flu", "mpox", "sars", "pathogenx"] = "covid19"
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
    observations: list[NowcastObservationModel]
    n_particles: int = Field(400, ge=50, le=2000)
    rho_min: float = Field(0.02, gt=0.0, lt=1.0)
    rho_max: float = Field(0.5, gt=0.0, le=1.0)


class DiseaseLookupRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


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
def explain_endpoint(req: ExplainRequest) -> dict[str, str]:
    return explain(req.simulation, focus_iso3=req.focus_iso3)


@app.post("/nowcast")
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


@app.post("/disease-params")
def disease_params_endpoint(req: DiseaseLookupRequest) -> dict[str, Any]:
    result = disease_lookup(req.name)
    status = result.get("status")
    if status == "unconfigured":
        raise HTTPException(status_code=503, detail=result)
    if status == "rejected":
        raise HTTPException(status_code=422, detail=result)
    return result
