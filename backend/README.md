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

## Provider chain for `/explain` (all optional)

The endpoint walks a four-step provider chain. Each step is gated on env vars and the chain falls through cleanly when none are set, so the demo never breaks.

1. **IBM watsonx.ai Granite**, used when `WATSONX_APIKEY` and `WATSONX_PROJECT_ID` are both set.
2. **Invoke endpoint** (OpenAI-compatible), used when `INVOKE_BASE_URL` is set.
3. **Anthropic Claude Haiku**, used when `ANTHROPIC_API_KEY` is set and the SDK is installed.
4. **Templated fallback**: deterministic paragraph grounded in the simulator output, always available.

```bash
# IBM watsonx.ai (preferred for the IBM Z hackathon track)
export WATSONX_APIKEY=...               # IBM Cloud API key (cloud.ibm.com/iam/apikeys)
export WATSONX_PROJECT_ID=...           # watsonx.ai project id
export WATSONX_URL=https://us-south.ml.cloud.ibm.com   # optional, default shown
export WATSONX_MODEL_ID=ibm/granite-3-3-8b-instruct    # optional, default shown

# Invoke endpoint (optional fallback above Anthropic)
export INVOKE_BASE_URL=https://invoke.cloud.marsi.eu
export INVOKE_API_KEY=...               # optional, only if endpoint is protected
export INVOKE_MODEL=openai/gpt-4o-mini  # optional

# Anthropic fallback
export ANTHROPIC_API_KEY=sk-ant-...
```

The response always includes a `source` field (`watsonx` / `invoke` / `anthropic` / `template`). When a configured provider fails (transport, auth, bad response), the failure is logged and surfaced via an optional `error_chain` field on the response so a credential outage on stage is visible instead of silently masked. Unconfigured providers are skipped quietly.

The watsonx call uses the chat-completions endpoint (`/ml/v1/text/chat`, API version `2024-05-31`) so Granite's chat template is applied server-side and we send role-tagged messages instead of a concatenated raw prompt.

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
