# Disease Outflow Forecaster (Frontend)

Next.js 15 (App Router) + MapLibre GL + Recharts. Connects to the FastAPI backend via `NEXT_PUBLIC_API_BASE`.

## Run locally

```bash
cd frontend
cp .env.example .env.local   # edit if backend isn't on localhost:8000
npm install
npm run dev
```

Open <http://localhost:3000>.

## File map

```
app/
  layout.tsx           Root layout, dark theme, fonts
  page.tsx             Main dashboard: sliders, map, hubs, chart, explainer
  globals.css          Tailwind layers + slider/popup styling
components/
  world-map.tsx        MapLibre map with circle layer + great-circle spread arcs
  slider-row.tsx       Labeled range slider with live value readout
  forecast-chart.tsx   Recharts area chart with 50% / 95% interval bands
  hub-list.tsx         Ranked top-imports / top-exports list with mini bars
  explain-panel.tsx    AI explanation drawer with regenerate + source badge
lib/
  api.ts               Typed fetch client for the FastAPI service
```

## Tests

```bash
npm test          # one-shot
npm run test:watch
npm run typecheck
```

Vitest + jsdom + Testing Library, with 12 component tests across the slider row, hub list, and explanation panel.

## Slider redraw target

The PRD targets sub-second slider-to-map redraw. The frontend debounces slider changes by 120ms then issues a single `/simulate` POST. With the default 200 Monte Carlo runs over ~70 regions the round-trip lands in ~250-400ms on a laptop.
