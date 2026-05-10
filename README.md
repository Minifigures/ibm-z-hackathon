# Disease Outflow Forecaster

> Pick a disease and a starting city, drag a few sliders, watch a world map show where the outbreak most likely spreads next, with calibrated uncertainty and an AI-generated explanation a public-health analyst could actually use.

Built for the IBM Z hackathon. See [`docs/PRD.md`](docs/PRD.md) for the full product spec and [`docs/TRACKS.md`](docs/TRACKS.md) for the track-targeting matrix and current coverage.

## What this is

A four-layer pipeline grounded in active research:

1. **Mobility.** Gravity model with exponential distance decay over a 70-country graph, with a separate slider-tunable port-call channel. Equation in `backend/app/mobility.py`.
2. **Transmission.** Region-indexed SEIR with mobility-coupled force of infection. ODE integrator in `backend/app/simulate.py`.
3. **Uncertainty.** Monte Carlo over R₀, incubation, and infectious period. Quantile bands at 2.5 / 25 / 50 / 75 / 97.5%.
4. **Explanation.** A three-step provider chain: IBM watsonx.ai Granite (preferred), Anthropic Claude Haiku (backup), deterministic templated paragraph (always available). The response carries a `source` field (and optional `error_chain` when a configured provider fails) so the UI can show a provenance pill and a judge can audit which provider generated the narrative.

A four-equation slide is in the PRD (Section 7.1) and every output traces to one of those equations. No black boxes.

## Stack

| Layer | Choice |
| --- | --- |
| Modelling | Python 3.11, NumPy (vectorized SEIR + Monte Carlo) |
| API | FastAPI + Uvicorn |
| Frontend | Next.js 15 (App Router) + TypeScript |
| Map | MapLibre GL JS, Stadia Maps `alidade_smooth_dark` raster tiles |
| Charts | Recharts |
| Styling | Tailwind CSS |
| LLM | IBM watsonx.ai Granite (chat completions), Anthropic Claude Haiku, templated fallback |
| Deploy | GitHub Actions, SSH-based pull-and-restart on the IBM VSI |

## Layout

```
.
├── backend/                       FastAPI + SEIR + Monte Carlo + provider chain
│   └── app/
│       ├── main.py                /health, /countries, /presets, /simulate, /explain
│       ├── simulate.py            SEIR ODE integrator + Monte Carlo loop
│       ├── mobility.py            Gravity OD matrix (air + sea)
│       ├── explain.py             Provider chain (watsonx, anthropic, template)
│       ├── watsonx.py             IBM Cloud IAM + watsonx.ai chat completions
│       └── data/                  countries.json, diseases.json
├── frontend/                      Next.js 15 dashboard
│   ├── app/                       Layout + main page (sliders, map area, panels)
│   ├── components/
│   │   ├── world-map.tsx          Interactive bubble map, hover-preview, click-lock
│   │   ├── time-scrubber.tsx      Play/pause + day scrubber that animates prevalence
│   │   ├── hub-list.tsx           Scrollable, ranked country list
│   │   ├── forecast-chart.tsx     Recharts area + line with 50% / 95% bands
│   │   ├── explain-panel.tsx      Narrative drawer + colored provenance pill
│   │   ├── sdg-badge.tsx          UN SDG alignment chip with click-to-expand panel
│   │   └── slider-row.tsx         Labeled slider with live readout
│   └── lib/api.ts                 Typed fetch client
├── docs/
│   ├── PRD.md                     Full product spec
│   └── TRACKS.md                  Track-targeting matrix and gaps
├── .github/workflows/deploy.yml   Auto-deploy main to IBM VSI on push
└── README.md
```

## Run it

Two terminals.

**Backend**

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Optional environment variables for `/explain` (chain falls through cleanly when none are set, demo never breaks):

```bash
# IBM watsonx.ai (preferred, lights up the IBM Granite pill in the UI)
export WATSONX_APIKEY=...                 # https://cloud.ibm.com/iam/apikeys
export WATSONX_PROJECT_ID=...             # watsonx.ai studio Manage > General
export WATSONX_URL=https://us-south.ml.cloud.ibm.com   # optional, default shown
export WATSONX_MODEL_ID=ibm/granite-3-3-8b-instruct    # optional, default shown

# Anthropic backup
export ANTHROPIC_API_KEY=sk-ant-...
```

The watsonx call uses `/ml/v1/text/chat` (API version `2024-05-31`) so Granite's chat template is applied server-side and we send role-tagged `system` + `user` messages. When a configured provider fails, the failure is logged and surfaced via an `error_chain` field on the response.

**Frontend**

```bash
cd frontend
cp .env.example .env.local
npm install
npm run dev
```

Open <http://localhost:3000>.

## Tests

```bash
# Backend (47 tests)
cd backend && pip install -r requirements-dev.txt && pytest -v

# Frontend (20 tests)
cd frontend && npm test
cd frontend && npm run typecheck
```

Backend coverage spans mobility math (haversine, gravity decay, mass conservation, intervention multipliers, landlocked attenuation), the SEIR + Monte Carlo simulator (schema, ordered quantiles, isolation under full travel restriction, mask-suppression, R₀ monotonicity, no-negatives), the FastAPI endpoints (TestClient happy/sad paths and validation), the watsonx provider (config gate, IAM token cache, chat-endpoint URL, role-tagged body, error paths), and the explainer chain (provider precedence, `error_chain` population, downstream-success-after-upstream-failure).

Frontend coverage spans `SliderRow`, `HubList`, `ForecastChart`-adjacent components, `ExplainPanel` (including provenance pill labels), `SDGBadge` (toggle + close), and `TimeScrubber` (play/scrub/auto-advance under fake timers). The `WorldMap` component is exercised manually since jsdom does not provide WebGL.

## Quick smoke test

```bash
curl -s http://localhost:8000/health
curl -s -X POST http://localhost:8000/simulate \
  -H 'content-type: application/json' \
  -d '{"disease_id":"covid19","start_iso3":"USA","r0":2.5,"incubation_days":5,"infectious_days":6,"cfr_pct":1,"air_weight":1,"port_weight":0.3,"travel_restriction":0,"mask_intervention":0,"horizon_days":30,"n_runs":200}' \
  | python3 -c "import json,sys;d=json.load(sys.stdin);print('top imports:', [(r['iso3'], int(r['expected_cases'])) for r in d['top_imports']])"
```

A 200-run, 30-day, 70-region simulation completes in roughly 250 ms on a laptop, comfortably inside the PRD's < 1 s slider-to-map target.

## Basemap and production deploy

The frontend uses Stadia Maps' `alidade_smooth_dark` raster tiles for English labels. The free tier serves anonymous requests on `localhost` without an API key, which covers local dev and hackathon judging. **For any non-localhost deploy** you need to either (a) sign up for a free Stadia API key and append `?api_key=...` to the tile URL in `frontend/components/world-map.tsx`, or (b) self-host the underlying OpenMapTiles via something like `protomaps`. Anonymous deployed origins will get 401/403 from Stadia.

`main` auto-deploys to the IBM VSI via `.github/workflows/deploy.yml`. The action uses three repository secrets (`DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_SSH_KEY`), SSHs into the box, fetches `main`, reinstalls deps only when their lockfile hashes change, rebuilds the frontend, restarts the two systemd units (`disease-outflow-backend.service`, `disease-outflow-frontend.service`), and waits up to 60 s for both health checks to pass.

## Demo flow

1. **Hook.** "Imagine a novel outbreak is detected in São Paulo today. Where does it go in the next month?"
2. **Pick.** Click *Pathogen X*, change Origin to BRA, set R₀ to 3.0.
3. **Mobility.** Toggle airport-only vs. airport + port. The spread arcs and country ranking shift.
4. **Transmission.** Hover or click a country (say MEX). The forecast chart shows the 50% / 95% bands. Click locks the selection so it survives the next hover; clicking empty ocean unlocks. Bump *Mask / distancing* to 50% and watch the curve flatten.
5. **Time scrubber.** Hit play. The map animates through the forecast horizon day by day, derived from the cached Monte Carlo quantiles (no extra `/simulate` calls). Click *Live* to snap back to the horizon view.
6. **All countries.** Scroll the country panel: every region is ranked by median cumulative cases. Skip past the seed to see the next exposed regions. Show why Madrid or Lisbon ranks high (gravity to BRA).
7. **Explanation.** Click *Explain*. The provenance pill identifies the provider: IBM blue for Granite via watsonx.ai, accent for Claude Haiku, slate for the templated fallback. With `WATSONX_APIKEY` set, the live call uses Granite chat completions.
8. **SDG badge.** Top-right chip alongside the calibration badge. Click to expand: SDGs 3, 9, 11, 13, 17 with one-line justifications, locking the UN-track angle into the product itself rather than the docs.
9. **Calibration.** Point at the coverage badge. "95% intervals contained truth in 93% of holdouts" (replace once the backtest harness ships).
10. **Close.** "Mobility imports it, SEIR amplifies it, Monte Carlo bounds it, watsonx explains it."

## Hackathon team

marco · aahir · aous · amrr · sultan

## Status

Done:

- [x] Backend pipeline end-to-end (mobility → SEIR → Monte Carlo → JSON), 47 pytest cases
- [x] FastAPI endpoints with pydantic validation
- [x] Country dataset (70 regions) with hub indices
- [x] Disease presets (COVID-19, Flu, Mpox, Pathogen X)
- [x] Three-provider explain chain (watsonx → anthropic → template) with `error_chain` audit field
- [x] Interactive map: hover-preview, click-lock, scrollable country list, throttled mousemove, GeoJSON-stable selection via feature-state
- [x] Time scrubber: play/pause + day-by-day animation derived from cached Monte Carlo quantiles
- [x] SDG alignment badge + provenance pill in the UI
- [x] Auto-deploy to IBM VSI on push to `main`

Open:

- [ ] Replace circle markers with a true country choropleth (Natural Earth GeoJSON)
- [ ] Backtest harness (seed Wuhan Jan 2020, score 30-day spread vs. JHU CSSE) so the calibration badge stops being a placeholder
- [ ] OpenFlights routes ingestion to replace the synthetic hub indices
- [ ] UN/UNCTAD port-call ingestion (sea channel currently uses gravity on hub indices)
- [ ] Climate-sensitive disease preset (Dengue 2050 under RCP 4.5) for the Sustainability/Climate track

The first four are the unfinished items from PRD Sections 7 and 9. Pick whichever advances the demo story most.
