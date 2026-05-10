# Disease Outflow Forecaster

> Pick a disease and a starting city, drag a few sliders, watch a world map show where the outbreak most likely spreads next, with calibrated uncertainty and an AI-generated explanation a public-health analyst could actually use.

Built for the IBM Z hackathon. See [`docs/PRD.md`](docs/PRD.md) for the full product spec.

## What this is

A four-layer pipeline grounded in active research:

1. **Mobility.** Gravity model with exponential distance decay over a 70-country graph, with a separate slider-tunable port-call channel. Equation in `backend/app/mobility.py`.
2. **Transmission.** Region-indexed SEIR with mobility-coupled force of infection. ODE integrator in `backend/app/simulate.py`.
3. **Uncertainty.** Monte Carlo over R₀, incubation, and infectious period. Quantile bands at 2.5 / 25 / 50 / 75 / 97.5%.
4. **Explanation.** Claude Haiku narrates the outputs, falling back to a deterministic templated paragraph if no API key is set.

A four-equation slide is in the PRD (Section 7.1) and every output traces to one of those equations. No black boxes.

## Stack

| Layer | Choice |
| --- | --- |
| Modelling | Python 3.11, NumPy (vectorized SEIR + Monte Carlo) |
| API | FastAPI + Uvicorn |
| Frontend | Next.js 15 (App Router) + TypeScript |
| Map | MapLibre GL JS (CARTO dark basemap, no token needed) |
| Charts | Recharts |
| Styling | Tailwind CSS |
| LLM | Anthropic SDK (Claude Haiku), templated fallback |

## Layout

```
.
├── backend/                   FastAPI + SEIR + Monte Carlo + Anthropic
│   └── app/
│       ├── main.py            /health, /countries, /presets, /simulate, /explain
│       ├── simulate.py        SEIR ODE integrator + Monte Carlo loop
│       ├── mobility.py        Gravity OD matrix (air + sea)
│       ├── explain.py         Claude Haiku explainer + templated fallback
│       └── data/              countries.json, diseases.json
├── frontend/                  Next.js 15 dashboard
│   ├── app/                   Layout + main page
│   ├── components/            Map, sliders, chart, hub list, explain panel
│   └── lib/api.ts             Typed fetch client
├── docs/PRD.md                Full PRD
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

Optional: `export ANTHROPIC_API_KEY=sk-ant-...` to enable Claude Haiku in `/explain`. Without it, you get the templated explanation, which is fine for the demo.

**Frontend**

```bash
cd frontend
cp .env.example .env.local
npm install
npm run dev
```

Open <http://localhost:3000>.

## Quick smoke test

```bash
curl -s http://localhost:8000/health
curl -s -X POST http://localhost:8000/simulate \
  -H 'content-type: application/json' \
  -d '{"disease_id":"covid19","start_iso3":"USA","r0":2.5,"incubation_days":5,"infectious_days":6,"cfr_pct":1,"air_weight":1,"port_weight":0.3,"travel_restriction":0,"mask_intervention":0,"horizon_days":30,"n_runs":200}' \
  | python3 -c "import json,sys;d=json.load(sys.stdin);print('top imports:', [(r['iso3'], int(r['expected_cases'])) for r in d['top_imports']])"
```

A 200-run, 30-day, 70-region simulation completes in roughly 250 ms on a laptop, which is comfortably inside the PRD's < 1 s slider-to-map target.

## Demo flow

1. **Hook.** "Imagine a novel outbreak is detected in São Paulo today. Where does it go in the next month?"
2. **Pick.** Click *Pathogen X*, change Origin to BRA, set R₀ to 3.0.
3. **Mobility.** Toggle airport-only vs. airport + port. The spread arcs and import ranking change.
4. **Transmission.** Click a country (say MEX). The forecast chart shows the 50% / 95% bands. Bump *Mask / distancing* to 50% and watch the curve flatten.
5. **Top hubs.** Read the import ranking. Show why Madrid or Lisbon ranks high (gravity to BRA).
6. **Explanation.** Click *Explain*. Claude Haiku writes a paragraph grounded in the numbers.
7. **Calibration.** Point at the coverage badge. "95% intervals contained truth in 93% of holdouts" (replace once the backtest harness ships).
8. **Close.** "Mobility imports it, SEIR amplifies it, Monte Carlo bounds it, the LLM explains it."

## Hackathon team

marco · aahir · aous · amrr · sultan

## Status & next steps

- [x] Backend pipeline end-to-end (mobility → SEIR → Monte Carlo → JSON)
- [x] FastAPI endpoints with pydantic validation
- [x] Country dataset (70 regions) with hub indices
- [x] Disease presets (COVID-19, Flu, Mpox, Pathogen X)
- [x] Frontend dashboard with sliders, map, hub lists, forecast chart, AI panel
- [x] Anthropic explainer + templated fallback
- [ ] Replace circle markers with a true country choropleth (Natural Earth GeoJSON)
- [ ] Backtest harness (Wuhan 2020 seed → 30-day spread vs JHU CSSE)
- [ ] OpenFlights routes ingestion to replace synthetic hub indices
- [ ] UN/UNCTAD port-call ingestion (currently stubbed via gravity on hub indices)

The first four checkboxes after the line are the unfinished items from PRD Sections 7 and 9. Pick whichever advances the demo story most.
