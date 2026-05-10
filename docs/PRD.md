# Product Requirements Document
## Disease Outflow Forecaster

**Owner:** Marco Anthony Ayuste
**Date:** May 10, 2026
**Status:** Draft v0.2
**Source materials:**
- Technical brief: *Judge-Friendly Technical Formulas for a Disease Forecasting Prototype*
- Project spec note (Marco, May 10): inputs / data / model / outputs

---

## 1. Vision in one sentence

**Pick a disease and a starting city, drag a few sliders, and watch a world map show where the outbreak most likely spreads next, with calibrated uncertainty and an AI-generated explanation a public-health analyst could actually use.**

## 2. Problem & Opportunity

When a novel outbreak is detected (Wuhan 2019, Mpox 2022, hypothetical X), the question public-health and travel-industry decision makers need answered in the first 72 hours is: *given what we know about this pathogen and where it started, which regions are at highest risk in the next 2 to 6 weeks, and which transport links are doing most of the importing?*

Existing tools fall into two camps. Academic models (Chinazzi 2020, GLEAM, EpiRisk) are excellent but require expert operation and are not interactive. Public dashboards (WHO, CDC) report current state, not forward simulation under user-tunable interventions. There's a gap for a fast, interactive, slider-driven simulator that a non-expert can use in 30 seconds and a judge can audit equation by equation.

This project fills that gap with a four-layer pipeline grounded in active research: **airport-route gravity for air importation, port-call activity for sea importation, region-indexed SEIR for local transmission, and Monte Carlo simulation for honest uncertainty**, topped with an LLM explainer that translates outputs into plain English.

## 3. Users & Use Cases

### 3.1 Personas (priority order)
1. **Hackathon judge** evaluating depth + interactivity + storytelling.
2. **Travel-industry risk analyst** (proxy: an airline ops planner asking "which routes need contingency?").
3. **Public-health communicator** wanting a defensible visual for a press briefing.
4. **Curious public** exploring "what if" scenarios.

### 3.2 Top user stories
- *As a judge*, I drag the R₀ slider from 1.5 to 3.0 and see the world map redraw in under a second.
- *As an analyst*, I switch the starting city from Lagos to São Paulo and immediately see how the top destination ranking changes.
- *As a communicator*, I click "Explain" on a country and get a paragraph linking R₀, route volume, and projected case window.
- *As a teammate*, I add a new disease preset (smallpox, hypothetical X) by editing one JSON file.

## 4. Goals & Success Metrics

### 4.1 Product goals
1. Be visibly interactive. Sliders move, map redraws, no progress bars over 1 second.
2. Be technically defensible. Every output traces to one of the four equations; no black boxes.
3. Be honest about uncertainty. Confidence bands on every forecast curve; calibration check shipped in the app.
4. Tell a story. The demo flows mobility → transmission → outputs → explanation in 4 to 5 minutes.

### 4.2 Quantitative success criteria

| Metric | Target | Stretch |
|---|---|---|
| Slider-to-map redraw latency | < 1.0 s on the demo VSI | < 300 ms |
| Number of regions modelled | ≥ 100 (countries) | ≥ 500 (cities/airports) |
| Diseases preconfigured | ≥ 4 (COVID-19, flu, mpox, generic) | ≥ 8 incl. hypothetical X |
| Monte Carlo simulations per run | ≥ 200 | ≥ 1000 |
| 95% prediction interval coverage on backtest | between 85% and 95% | between 90% and 95% |
| AI explanation latency | < 4 s | < 2 s |

### 4.3 Qualitative
- A judge with a public-health PhD asks a follow-up; we cite arXiv or CDC, not vibes.
- The dashboard works on a phone (responsive map + collapsing slider panel).
- Code is small enough that a teammate can swap the starting city dataset in 30 minutes.

## 5. Inputs (UI)

| Input | Control | Default | Range / values |
|---|---|---|---|
| Disease type | dropdown | COVID-19 | COVID-19, Influenza, Mpox, "Pathogen X" custom |
| Starting city | searchable dropdown | Lagos (LOS) | any IATA airport in dataset |
| R₀ | slider | 2.5 | 0.5 to 5.0, step 0.1 |
| Incubation period (days) | slider | 5 | 1 to 21 |
| Severity (CFR %) | slider | 1.0 | 0.01 to 30 |
| Airport spread weight | slider | 1.0 | 0 to 2.0 (multiplier on air flow) |
| Port spread weight | slider | 0.3 | 0 to 2.0 (multiplier on sea flow) |
| Intervention: travel restriction | slider | 0 | 0 to 100% reduction in flow |
| Intervention: mask/distancing | slider | 0 | 0 to 100% reduction in transmission |
| Forecast horizon | slider | 30 days | 7 to 180 |

Picking a disease preset writes default values into R₀ / incubation / severity but leaves them editable. "Pathogen X" sets all sliders to the user's last-touched values.

## 6. Outputs (UI)

1. **World choropleth map** colored by predicted infections per 100k at horizon end. Click a region to drill in.
2. **Top import hubs** ranked list (top 10): regions receiving the most expected imported infections from the start city.
3. **Top export hubs** ranked list: regions/airports/ports doing the most outflow.
4. **Forecast curve** for the selected region: median + 50% / 80% / 95% bands over time.
5. **Likely spread paths**: animated arcs on the map showing top route flows in the first 14 days.
6. **Confidence indicator**: a calibration badge ("intervals contained truth in 92% of holdouts") displayed in the corner.
7. **AI explanation panel**: 1 to 2 paragraphs of plain-English narrative for the currently selected region or globally, generated on demand.

## 7. Technical Approach

### 7.1 Equation stack (4 equations on a slide)

**(a) Airport mobility, gravity with exponential decay** (per the brief, arXiv 2501.05684):

$$F^{air}_{ij} = K_a \cdot P_i^{\alpha} \cdot P_j^{\beta} \cdot \exp(-\gamma d_{ij}) \cdot R_{ij}$$

where $R_{ij} \in \{0, 1\}$ is whether OpenFlights lists a direct route, $P_i$ is metro-area population, $d_{ij}$ is great-circle distance from airport coordinates. We optionally fit $\alpha,\beta,\gamma,K_a$ to BTS T-100 passenger counts for US-anchored routes; everywhere else uses literature priors ($\alpha \approx \beta \approx 1$, $\gamma \approx 0.5$ per 1000 km).

**(b) Port mobility, port-call activity** (UN/UNCTAD AIS port-call data):

$$F^{sea}_{ij} = K_p \cdot V_i \cdot V_j \cdot \exp(-\gamma_s \tau_{ij})$$

where $V_i$ is annual port-call volume at $i$ and $\tau_{ij}$ is a sea-route transit time proxy (great-circle / 25 knots, or a precomputed shipping-lane distance if we get fancy). Sea import only matters for diseases with long incubation or environmental persistence; the slider lets the user dial it down for short-cycle pathogens.

**(c) Region-indexed SEIR with mobility-adjusted force of infection** (per the brief):

$$\frac{dS_i}{dt} = -\lambda_i(t) S_i + \sum_{j\neq i} m_{ji} S_j - \sum_{j\neq i} m_{ij} S_i$$

$$\frac{dE_i}{dt} = \lambda_i(t) S_i - \sigma E_i + \text{(mobility terms)}$$

$$\frac{dI_i}{dt} = \sigma E_i - \gamma I_i + \text{(mobility terms)}$$

$$\frac{dR_i}{dt} = \gamma I_i + \text{(mobility terms)}$$

with

$$\lambda_i(t) = \beta_i(t)\left[(1-\theta) \frac{I_i}{N_i} + \theta \sum_{j\neq i} \omega_{ji} \frac{I_j}{N_j}\right]$$

where $m_{ij}$ is normalized total mobility ($F^{air}_{ij} + w_p F^{sea}_{ij}$ scaled by population, with travel-restriction slider applied multiplicatively), $\sigma^{-1}$ is incubation period, $\gamma^{-1}$ is mean infectious period, and the mask/distancing slider scales $\beta_i(t)$.

**(d) Monte Carlo uncertainty** (per the brief):

$$\{Y_{t+h}^{(1)}, \ldots, Y_{t+h}^{(M)}\} \sim p(Y_{t+h} | \mathcal{D}_{1:t})$$

$$\hat q_p(t+h) = \text{Quantile}_p(Y_{t+h}^{(1)}, \ldots, Y_{t+h}^{(M)})$$

Each Monte Carlo run perturbs R₀, generation time, and reporting fraction $\rho$ within prior ranges; quantile bands come from $M \geq 200$ runs.

### 7.2 Why SEIR (not renewal) for this product
The brief recommended renewal as the *operational forecaster*, but SEIR is the right fit here because:
- The product is a **what-if simulator**, not a backtest-driven forecaster. SEIR runs forward from a single seeded state, which matches "starting city" UX.
- SEIR exposes the levers the sliders need (β, σ, γ, intervention multipliers).
- Mobility integrates naturally into SEIR via metapopulation coupling; renewal models need a separate import-pressure hack.
- Renewal stays in the back pocket as a fitting tool if we want to estimate $R_t$ from observed COVID data to validate the SEIR run.

### 7.3 Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌──────────────────────┐
│ Static datasets │     │ Mobility builder │     │ SEIR simulator       │
│ - OpenFlights   │ ──> │  air F_ij        │ ──> │  ODE integrator      │
│ - airports.csv  │     │  sea F_ij        │     │  Monte Carlo loop    │
│ - UN port calls │     │  combined m_ij   │     │  per-region S/E/I/R  │
│ - city pops     │     └──────────────────┘     └──────────┬───────────┘
└─────────────────┘                                         │
                                            ┌───────────────▼──────────┐
                                            │ Forecast aggregator      │
                                            │  quantile bands per region│
                                            │  top-k hub ranking        │
                                            └───────────────┬──────────┘
                                                            │
              ┌───────────────────────────┐                 │
              │ FastAPI backend on VSI    │ <───────────────┘
              │  /simulate POST           │
              │  /explain POST  ─────────┐│
              └───────────────────────────│┘
                                          │ ┌──────────────────────────┐
                                          └>│ LLM (Claude / OpenAI)    │
                                            │  explainer over context  │
                                            └──────────────────────────┘
                                                            │
              ┌──────────────────────────────────────────────┘
              ▼
┌─────────────────────────────────────────┐
│ Next.js frontend                         │
│  - Mapbox/MapLibre choropleth + arcs     │
│  - Slider panel (controlled inputs)      │
│  - Forecast chart (Recharts)             │
│  - AI explanation drawer                 │
└─────────────────────────────────────────┘
```

**Tech stack:**
- Modelling core: Python 3.11, `numpy`, `scipy.integrate.solve_ivp`, `pandas`. No ML framework needed; SEIR is ODEs.
- API: FastAPI + uvicorn. `/simulate` returns Monte Carlo quantiles per region; `/explain` calls the LLM.
- Frontend: Next.js (App Router) + MapLibre GL JS (free, no Mapbox token) + Recharts + shadcn/ui.
- LLM: Claude Haiku via Anthropic API for the explainer (cheap, fast). Fallback to a templated explainer if API quota hits.
- Hosting: the IBM Cloud VSI we already provisioned at 163.66.95.111 (Toronto, ca-tor-1, 2 vCPU / 4 GB).

### 7.4 Performance plan to hit < 1s slider response
- Pre-compute the mobility matrix $m_{ij}$ once on data load and cache.
- Use a coarse default resolution (~150 countries / top 200 airports) for live simulation; switch to 500 airports only when "high resolution" toggle is on.
- Run 200 Monte Carlo SEIR sims in parallel via numpy vectorization, target < 800 ms on the 2 vCPU box.
- Stream partial results: render with the first 50 sims while the rest finish.

## 8. Data Plan

| Layer | Source | Acquisition risk | Notes |
|---|---|---|---|
| Airport routes | OpenFlights `routes.dat`, `airports.dat` (open) | Low | Snapshot is a few years old; fine for a model. |
| US passenger flows (calibration) | BTS T-100 segment data | Low | Used only to fit gravity parameters on US-anchored routes. |
| Port calls | UN/UNCTAD AIS port-call dataset | Medium | May need scraping or API key; have a fallback static CSV. |
| City / metro populations | SimpleMaps World Cities, Wikidata | Low | Pair with airport IATA codes via fuzzy match. |
| Country populations | World Bank | Low | For country-level aggregation. |
| Disease params | literature defaults baked into JSON presets | Low | COVID-19, flu, mpox, X. |
| (Optional) historical case data | JHU CSSE archive, WHO | Medium | Only needed if we want a backtest. |

## 9. Milestones (48 hour build, 5-person team)

| Hour | Deliverable | Who |
|---|---|---|
| 0 to 4 | Repo + monorepo skeleton (Python core, Next.js app), data ETL stubs, agree disease presets | Marco + Person A |
| 4 to 12 | OpenFlights → gravity OD matrix; airport coords + populations joined; sanity arc plot | Person A + Person B |
| 12 to 18 | UN port calls ingested; combined mobility matrix; intervention sliders applied as multipliers | Person B |
| 12 to 24 | SEIR ODE per-region runs in numpy; Monte Carlo loop returns quantiles; `/simulate` API live | Marco |
| 18 to 30 | Next.js + MapLibre choropleth wired to API; sliders POST and re-render | Person C + Person D |
| 24 to 36 | Top-hub rankings, forecast curve chart, spread-arc layer | Person C + Person D |
| 30 to 40 | LLM explainer prompt + `/explain` endpoint, drawer in UI | Marco + Person C |
| 36 to 44 | Coverage / calibration backtest harness; "How it works" page; demo polish | Person A + Person B |
| 44 to 48 | Demo dry-runs, freeze code, screenshot fallbacks, deploy to VSI | All |

## 10. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| 200-region SEIR too slow for live sliders | High | High | Vectorize with numpy; cap default resolution; stream partial results |
| OpenFlights data is stale (missing new routes) | Medium | Low | Document the snapshot date; offer "user-added route" override |
| Port data hard to get | Medium | Medium | Fall back to static port-call snapshot; degrade gracefully when port slider is 0 |
| LLM API quota / cost | Low | Low | Haiku is cheap; cache explanations by `(disease, city, slider hash)` |
| Mapbox/MapLibre rendering jank on phone | Medium | Medium | Test on iPhone in hour 36; degrade to a simpler SVG map if needed |
| Mobility-coupled SEIR is unstable for high R₀ | Medium | Medium | Cap step size in `solve_ivp`; clamp inputs; show "model unstable" if NaN appears |
| Judge asks "why not deep learning" | High | Low (good!) | Answer ready: "data quality and explainability constraints, not model complexity, see CDC modelling handbook" |

## 11. Demo Script (5 min)

1. **Hook (30s):** "Imagine a novel outbreak is detected in São Paulo today. Where does it go in the next month?"
2. **Pick disease + city (30s):** Click "Pathogen X", drag start point to São Paulo, set R₀ = 3, severity 2%.
3. **Mobility (45s):** Toggle airport-only vs. airport+port. Show the spread-path arcs change. One slide of the gravity equation.
4. **Transmission (1m):** Hover a country. Show the SEIR forecast curve with 50/80/95 bands. Touch the "mask intervention" slider to 50%; watch the curve flatten.
5. **Top hubs (1m):** Show top 10 import + export rankings. Explain why Madrid ranks high (route degree to São Paulo).
6. **AI explanation (45s):** Click "Explain Madrid". A paragraph appears: "Madrid receives X% of LATAM-origin traffic, R₀ at current setting yields ~Y expected imported cases by day 30, intervention reduces this by Z%."
7. **Calibration check (30s):** Open the calibration badge. "Our 95% intervals contained the truth in 93% of held-out scenarios."
8. **Close (15s):** "Mobility imports it, SEIR amplifies it, Monte Carlo bounds it, the LLM explains it."

## 12. Open Questions (team to answer first)

1. Disease preset list: lock to COVID-19, Flu, Mpox, Pathogen X, or add SARS / Ebola / measles?
2. Map provider: MapLibre + free tiles (no token, possibly slower) vs. Mapbox (token, faster, has limits)?
3. LLM: Claude Haiku via Anthropic API (Marco has access) vs. self-host a small model on the VSI?
4. Do we backtest at all (e.g. seed COVID-19 in Wuhan Jan 1 2020 and check 30-day spread vs. real)? It's high-effort but a killer slide.
5. Hackathon name + theme + judging rubric? Affects which sections we play up.
6. Any required tech sponsor stack (e.g. "must use AWS / Databricks / a specific API")?

## 13. Out of Scope (be explicit so we don't drift)

- Real-time data feeds (we use static snapshots).
- Per-county or per-postal-code resolution (top ~500 airports / ~150 countries is the ceiling).
- Treatment / vaccine pharmacology modelling.
- Native mobile app.
- User accounts, auth, persistence beyond URL-encoded scenarios.
- Multi-pathogen / co-infection dynamics.
- Economic impact modelling (interesting, but a different product).

## 14. Appendix: Pitfalls to Avoid (carried from the brief)

- Do **not** copy a fancy symbolic-regression mobility expression you can't defend. Cite arXiv 2501.05684 as validation for the simpler exponential gravity, then use it.
- Do **not** claim your simulator predicts real outbreaks; frame it as a defensible scenario tool with literature-anchored parameters.
- Do **not** ship intervals from a normal-distribution plus/minus. Always Monte Carlo, always quantile-based.
- Do **not** lead the demo with the architecture diagram. Lead with the slider moving the map.

---

**Next steps after this PRD lands:**
1. Resolve the 6 open questions in Section 12 in a 15-minute team standup.
2. Cut the milestones in Section 9 into a project board (Linear / Notion / GitHub Projects).
3. Provision dev environment using the existing `provision-vsi.sh` (already done; box is at 163.66.95.111).
4. Lock disease preset JSON before hour 4 so modellers and UI can work in parallel.
