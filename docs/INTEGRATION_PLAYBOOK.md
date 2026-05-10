# Integration Playbook
## Turning the 16 Research Papers Into Concrete Features

Companion to `RESEARCH_PAPERS.md`, which mapped each paper to the four PRD equations. **This document goes the other direction:** for each paper, what's the *most ambitious feature* we could realistically ship that pulls something the PRD doesn't currently have?

Each section gives:
- **The single most surprising / useful idea** in the paper.
- **Easy wins** — features we could add with hours of work.
- **Stretch ideas** — features that would re-rank us in the demo if we hit them.
- **Risk** — what could go wrong.

Features are tagged:
- 🟢 **Hours of work**, low risk, ship it.
- 🟡 **Half-day**, moderate risk, judge candy.
- 🔴 **Day+**, high risk, demo-defining if it works.

---

## 14 — Brockmann & Helbing 2013, "Hidden Geometry of Complex, Network-Driven Contagion Phenomena"
**File:** `14_BrockmannHelbing2013_hidden_geometry_effective_distance.pdf` · *Science* 342, 1337–1342

### The big idea
Geographic distance is the wrong coordinate for predicting epidemic arrival. Replace it with **effective distance** along the air-route graph:
$$d^{\text{eff}}(s, t) = \min_{\text{path } s \to t} \sum (1 - \log p_{ij})$$
where `p_ij` is the fraction of outbound flights from i that go to j. With this redefinition, **arrival time becomes a linear function of effective distance** with R² > 0.9 across the SARS, H1N1, and EHEC outbreaks.

This is *not* a model — it's a re-coordinatization. It costs nothing to compute (Dijkstra on the OpenFlights graph, ~50 ms for 200 airports) but changes how everything looks.

### Easy wins
- 🟢 **Effective-distance arrival-time annotation.** When user clicks a country, in addition to our SEIR forecast curve, show "predicted arrival: day X" derived from `d^eff(seed, country)` and a slope fit. One extra line on the chart, costs ~50 ms.
- 🟢 **Color the spread arcs by effective-distance rank.** Currently arcs are weighted by raw flow. Re-rank by effective distance from the seed city — the *first 10 arrivals* are the visually meaningful set.
- 🟢 **LLM explainer hook.** Pipe `d^eff(seed, region)` into the explanation prompt. Madrid example becomes: *"Madrid is at effective distance 1.8 from São Paulo through 4 daily direct routes — predicted arrival around day 18, ahead of Lagos at d^eff = 3.1."*

### Stretch ideas
- 🟡 **"Effective Distance" map view toggle.** Add a button next to the Mercator projection: switch the world map to a **radial polar plot** centered on the seed city, with countries placed at radius = effective distance and angle = original longitude. The outbreak literally radiates outward in concentric rings. This is the single most striking visualization we could ship.
- 🔴 **Reverse mode: outbreak source localization.** Given any case distribution (e.g. "current cases in 12 countries"), invert the effective-distance map to *find the most likely seed city*. The seed is the location that minimizes the variance of `arrival_time(country) − d^eff(seed, country)` across all observed countries. Wire this into a "Source Detective" demo tab: paste in current case counts, get back a heatmap of likely origins. Brockmann's paper shows this works on real outbreaks.

### Risk
- The linearity result was fitted on 3 outbreaks, all heavy-tailed-degree air networks. For sea-only or mixed-mode pathogens, recompute effective distance on the combined graph — usually still linear but slope changes.
- Polar projection breaks visually for very long-haul routes (effective distance compresses). Cap radius and let users hover for actual values.

---

## 15 — Reich et al. 2019, "A collaborative multiyear, multimodel assessment of seasonal influenza forecasting in the United States"
**File:** `15_Reich2019_multimodel_influenza_forecast_assessment_PNAS.pdf` · PNAS 116(8)

### The big idea
22 different forecasting models from 5 institutions submitted real-time forecasts to the CDC FluSight challenge over 7 seasons. **The ensemble of all 22 models beat every single individual model in 80%+ of weeks.** And the ensemble was simple: equal-weighted average of probability distributions.

The standard scoring metric is the **multibin log score**: bin the prediction interval into 1% buckets, log-score the truth's bucket. Robust, calibrated, and what every public-health forecasting team uses.

### Easy wins
- 🟢 **Multibin log score in the calibration corner.** PRD §6 already has a "calibration badge". Compute the multibin log score on backtests and display it next to coverage %. Two numbers: coverage (interpretable to public) and log score (interpretable to epidemiologists). Both speak to a different judge.
- 🟢 **Naive-baseline comparison toggle.** Reich finds *many* submitted models lose to a "historical average" baseline. Add a "vs. baseline" toggle that overlays a no-mobility flat-prior forecast next to ours. Honesty signal — and we *will* beat it for novel pathogens because there's no historical average.

### Stretch ideas
- 🟡 **Internal ensemble: 4 models, 1 mean.** Run our pipeline as four parallel Monte Carlo ensembles with different structural assumptions:
  - **M1**: SEIR + air gravity only (no sea, no commuting)
  - **M2**: SEIR + air + sea
  - **M3**: SEIR + air + radiation-model commuting *(file 04 supports this)*
  - **M4**: Renewal equation with effective-distance-based importation *(files 14 + 16 support this)*
  
  Display each model's quantile band in a faint color, the equal-weighted ensemble in bold. **Talk track:** "Reich 2019 PNAS proved equal-weight ensembles beat any single model. We do the same."
- 🟡 **Per-horizon confidence bar.** Reich shows accuracy decays with forecast horizon. Add a small bar above the forecast curve: `[●●●●○○○○○○]` showing model skill at each forecast week (1-week=4 dots, 8-week=1 dot). Visually communicates *when to trust us*.
- 🔴 **Live "leaderboard" panel.** Show all 4 sub-models' coverage scores live, updating as the user moves sliders. The "winning" model varies by scenario. This is great storytelling: *the right model depends on the disease.*

### Risk
- Multibin scoring needs ground truth. We can compute it on **synthetic backtests** (seed Wuhan Jan 2020 → check vs. Chinazzi-published projections), or on H1N1 2009 if we want to be ambitious.
- Ensemble of 4 models doubles compute. Cap each model at 50 Monte Carlo runs; ensemble still has 200 effective samples.

---

## 16 — Funk et al. 2018, "Real-time forecasting of infectious disease dynamics with a stochastic semi-mechanistic model"
**File:** `16_Funk2018_realtime_forecasting_semi_mechanistic.pdf` · *Epidemics* 22

### The big idea
Use a **renewal equation** (`I_t = R_t · Σ_τ w_τ I_{t-τ}`) coupled with a **particle filter** that updates `R_t` from observed case counts as they come in. The "semi-mechanistic" tag means the structure is mechanistic (renewal) but `R_t` is a stochastic process, not a fixed parameter. This is what real-time epidemic forecasters actually run during outbreaks.

The connection to our SEIR-based what-if simulator: **renewal and SEIR are mathematically equivalent in continuous time** (Champredon et al. 2018). So the same model can run two ways:
- **What-if mode** (current PRD): set R₀, simulate forward.
- **Nowcast mode** (this paper): observe cases, infer R_t, project forward.

### Easy wins
- 🟢 **Add CRPS (Continuous Ranked Probability Score) to the calibration badge.** Funk uses CRPS as a probabilistic accuracy metric. It's `~10 lines of numpy` to compute. Pair with the multibin log score from Reich.
- 🟢 **"Generation interval" slider.** Funk shows generation-interval uncertainty dominates short-horizon forecasts. The PRD has incubation period; add a generation-interval slider (defaulting to incubation + 0.5/γ). Useful Monte Carlo perturbation, plus realistic.

### Stretch ideas
- 🟡 **"I have data" upload mode.** Give the user a CSV upload widget: paste 5–30 days of observed case counts for the seed city. Run a particle filter (~200 particles) over our Monte Carlo SEIR ensemble, weighting each particle by likelihood of the observed data. Then forecast forward from the *posterior* particle weights. **The model goes from a what-if simulator to a real-time forecaster, which is the actual job public-health people need done.** This is a tier-1 demo upgrade.
- 🟡 **R_t inversion display.** When in "I have data" mode, show an inferred-R_t time series alongside the user's R₀ slider. The slider keeps moving; the inferred R_t holds. Demonstrates the difference between assumed-pathogen-character (slider) and observed-real-world-behavior (data).
- 🔴 **Live data hook to JHU CSSE / WHO.** PRD lists JHU CSSE archive as optional. If we hit it: pre-load the COVID-19 Wuhan time series, run particle filter, show our model converging to Chinazzi's published R_t over the first 30 days. *On stage, this is unbeatable.*

### Risk
- Particle filter at 200 particles × 200 Monte Carlo runs = 40K state updates. At 30-day horizon × 5-region forecast, that's 6M operations. Feasible in numpy but requires care — vectorize aggressively.
- "I have data" mode increases scope. Wall it off behind a single button so the simple UX stays simple.

---

## Cross-cutting integration ideas

These are features that combine 2+ papers in ways no single paper offers:

### 🔴 "Pathogen Detective" mode (papers 11, 14, 16)
**Inputs**: a partial outbreak — e.g., "as of today, these 8 countries report cases at these levels."
**Outputs**: 
1. The most likely seed city (from Brockmann inverse, file 14).
2. The most likely R₀ and reporting fraction ρ (from Funk particle filter, file 16).
3. The most likely *cryptic spread already in progress* (from Davis 2021's reporting-fraction reasoning, file 11).
4. A 30-day forward forecast with full uncertainty bands.

This single feature reframes the product: from a *teaching toy* into a *plausible early-outbreak triage tool*. The kind of thing that gets a hackathon demo a "wait, is this actually useful?" reaction from a public-health judge.

### 🟡 "Why this disease behaves this way" LLM grounding (papers 14, 03, 06)
Build a structured fact-table that the LLM explainer fills in for every region:
- Effective distance from seed (file 14)
- Top 3 connecting routes (PRD output)
- Predicted arrival window (file 14 linear fit)
- R₀ × generation-interval implied doubling time (file 03 review)
- "Compare to a known outbreak" (file 06 — Wuhan baseline)

The LLM stops hallucinating because the facts are pre-computed; explanations cite specific routes and arrival windows. Cuts LLM cost and improves quality.

### 🟡 "Confidence-stratified map view" (papers 15, 04, 07)
Don't just color the choropleth by predicted infection density. Add a **second layer (toggleable)** that colors by *forecast precision*: tight bands → solid color, wide bands → hatched/transparent. Reich (file 15) frames the metric, Tizzoni (file 04) and Colizza (file 07) explain why hubs are predictable and peripheries aren't. Visually honest about where to trust the model.

### 🟢 "Model assumptions" badge (papers 03, 05, 08)
A small "ⓘ" button in the corner that opens a model card listing every assumption (well-mixed within metapopulation, no age structure, deterministic ODE within Monte Carlo run, ...) and what each citation in this folder addresses. Great for serious technical judges, fast to build, signals depth.

---

## Recommended build order under tight time

If we have 12 hours of integration work to spend, ranked by ROI:

1. **🟢 Effective-distance arrival annotation + LLM ground-truthing** (file 14). 2 hours. Demo *and* explainer get sharper.
2. **🟢 Multi-metric calibration badge** (CRPS + multibin log score + coverage %). 2 hours. Stops the "your bands are made up" question dead.
3. **🟡 Internal 4-model ensemble** (file 15). 3 hours. Single biggest credibility unlock.
4. **🟡 Effective-distance polar map view** (file 14). 3 hours. The visual everyone screenshots.
5. **🔴 "I have data" particle-filter mode** (file 16). 4+ hours. Stretch — but if it works, it changes what the product *is*.

Total ~14 hours. Drop item 5 if we're behind.

---

## What this folder is NOT

A literature review. We have `RESEARCH_PAPERS.md` for that. **This document is a feature backlog disguised as a research summary.** Every section is a thing we could choose to build, with the citation pre-loaded for the demo Q&A.
