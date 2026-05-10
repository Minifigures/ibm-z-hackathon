# Disease Outflow Forecaster (Backend)

FastAPI service that runs the SEIR + gravity-mobility + Monte Carlo pipeline.

## Run locally

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

API: <http://localhost:8000/docs>

## Endpoints

- `GET  /health`
- `GET  /countries`  list of modelled regions
- `GET  /presets`  disease parameter presets
- `POST /simulate`  run the full pipeline; returns per-region quantile bands, top hubs, spread arcs
- `POST /explain`  LLM narrative for the simulation result

## Anthropic key (optional)

Set `ANTHROPIC_API_KEY` to enable the Claude-Haiku explainer. Without it, `/explain` returns a deterministic templated paragraph so the demo never breaks.

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

## File map

```
app/
  main.py         FastAPI entry, request/response schemas
  simulate.py     SEIR ODE integrator + Monte Carlo loop
  mobility.py     Gravity OD matrix (air + sea), distance utilities
  explain.py      Anthropic call + templated fallback
  data/
    countries.json   ~70 countries, lat/lng/population/hub index
    diseases.json    presets for COVID-19, Flu, Mpox, Pathogen X
```

## Tests

```bash
pip install -r requirements-dev.txt
pytest -v
```

35 tests covering mobility math (haversine, gravity decay, mass conservation, intervention multipliers), the SEIR + Monte Carlo simulator (schema, ordered quantiles, intervention efficacy, isolation under full travel restriction, no-negatives invariant), the FastAPI endpoints (health, countries, presets, simulate happy/sad paths, request validation), and the explainer (templated fallback paths).

## Performance

Default config (70 regions, 200 Monte Carlo runs, 30-day horizon, 4 sub-steps/day) finishes in well under 1 second on a laptop. The integrator is fully vectorized over runs, so the 1000-run stretch target only roughly 5x's the cost.
