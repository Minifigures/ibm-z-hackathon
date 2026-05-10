# Research Papers — Disease Outflow Forecaster

This folder contains **13 research papers** covering how world-scale pandemic simulations are actually built, validated, and operated. Each entry below states what the paper is, *how* world simulations are done in it, and which piece of our four-equation stack it underwrites.

Our stack (from `PRD.md` §7.1):
- **(a)** Airport gravity with exponential decay → `F^air_ij = K_a · P_i^α · P_j^β · exp(-γ d_ij) · R_ij`
- **(b)** Port-call mobility → `F^sea_ij = K_p · V_i · V_j · exp(-γ_s τ_ij)`
- **(c)** Region-indexed SEIR with mobility-coupled force of infection → `λ_i(t) = β_i(t)[(1-θ) I_i/N_i + θ Σ_j ω_ji I_j/N_j]`
- **(d)** Monte Carlo uncertainty → `q̂_p(t+h) = Quantile_p({Y^(m)_{t+h}})`

The papers are grouped into three layers:
1. **Foundations** (files 01, 02, 07) — where the formulas come from.
2. **Methods reviews** (files 03, 08) — the field's accepted taxonomy of approaches.
3. **Live applications and calibrations** (files 04, 05, 06, 09–13) — how these models actually got run during real outbreaks, what they predicted, what worked.

---

## 01 — Guo et al. 2026, "Distilling human mobility models with symbolic regression"
**File:** `01_Guo2026_mobility_symbolic_regression.pdf` · arXiv 2501.05684

**What it is.** Uses symbolic regression to *rediscover* the mathematical form of human-mobility laws from data, validating the classical gravity model and an exponential-power-law decay. This is the paper our PRD already cites as the justification for using simple exponential gravity instead of a hand-tuned ad-hoc expression.

**How simulations work in this paper.** Empirical OD (origin–destination) flows are fed into symbolic regression; the model searches an expression space for compact formulas. The "winners" are forms like `F_ij ∝ P_i^α P_j^β exp(-γ d_ij)` — exactly our equation (a).

**Use in our project.**
- **Equation (a) defense.** When a judge asks "why this functional form?", point at this paper. We don't have to re-fit anything; we just use the literature-anchored exponents (α≈β≈1, γ≈0.5/1000 km).
- **Optional calibration target.** If we have time to fit `α, β, γ, K_a` from BTS T-100, this paper's exponential-power-law variant is the form to fit.

---

## 02 — Balcan et al. 2009, "Multiscale mobility networks and the spatial spreading of infectious diseases" (PNAS)
**File:** `02_Balcan2009_multiscale_mobility_networks_PNAS.pdf` · arXiv 0907.3304

**What it is.** The foundational paper for global metapopulation epidemic simulators (the GLEAM family). Authors include Vespignani's group at Northeastern — the same team behind GLEAM and the Chinazzi 2020 COVID paper.

**How world simulations are done in this paper.**
1. Partition the world into ~3,300 sub-populations centered on major airports (Voronoi tessellation).
2. Build two mobility layers: **long-range air travel** (IATA OAG schedules) and **short-range commuting** (gravity/radiation model fit on 29-country census data).
3. Run a **stochastic compartmental model (SLIR / SEIR-style)** in each sub-population with discrete individuals.
4. At each time step, perform a *binomial mobility step*: travelers between patches are sampled from the OD matrix, infection state preserved.
5. Repeat across thousands of stochastic realizations → Monte Carlo ensemble.
6. Aggregate to generate global incidence curves and arrival-time distributions.

**Use in our project.** This is the *reference architecture* for everything we're doing.
- **Equation (c) (metapopulation SEIR with mobility coupling)** is exactly their framework, simplified. Cite this paper any time someone questions whether an ODE-coupled SEIR over a mobility graph is a real method.
- **The two-layer mobility idea** (long-range + short-range) maps to our air + sea split.
- **Monte Carlo across realizations** is the logical parent of our equation (d).
- **Pitfall they document:** commuting flows are an order of magnitude larger than airline flows but *don't* dominate the global pattern. Translation for us: getting air right matters more than getting sea right; spend optimization budget accordingly.

---

## 03 — Lu et al. 2025, "Human Mobility in Epidemic Modeling" (review)
**File:** `03_Lu2025_human_mobility_in_epidemic_modeling_review.pdf` · arXiv 2507.22799

**What it is.** A comprehensive 2025 review article surveying every major approach to coupling mobility with epidemic models — compartmental, network, agent-based, ML.

**How simulations are done (taxonomy this paper provides).**
- **Compartmental + mobility (our approach)**: SIR/SEIR per region, OD matrix couples them. Pros: fast, interpretable. Cons: assumes well-mixed within regions.
- **Network/contact models**: every individual is a node; edges are contacts. Pros: heterogeneity. Cons: massive state.
- **Agent-based**: each agent has a schedule, location, contacts. Pros: most realistic. Cons: slow, hard to calibrate.
- **ML/GNN-based**: learn dynamics from data. Pros: pattern-matching. Cons: black-box, doesn't generalize to novel pathogens.

**Use in our project.**
- **Lit-review crib sheet for the demo / writeup.** When asked "why didn't you use deep learning?", cite §[ML section] of this paper: ML approaches don't extrapolate to novel pathogens, which is the whole use case.
- **Ammunition for the "why metapopulation SEIR" choice in PRD §7.2.** The review explicitly lists trade-offs between approaches — our PRD's argument lines up with theirs.

---

## 04 — Tizzoni et al. 2014, "On the use of human mobility proxies for the modeling of epidemics"
**File:** `04_Tizzoni2014_mobility_proxies_for_epidemics.pdf` · arXiv 1309.7272

**What it is.** Compares three different sources of mobility data — census surveys, mobile-phone CDRs, and the **radiation model** — for use in metapopulation SEIR simulations. Same group as Balcan 2009, plus Marta González.

**How world simulations are stress-tested in this paper.** Run the same SEIR metapopulation model with three different OD matrices as the only difference. Compare arrival times, peak heights, and infection ordering across regions. Result: phone data captures ~87% of true commuting flux but overestimates; radiation model performs differently in central vs. peripheral patches; **importantly, the *ordering* of infection across regions is robust across all three proxies**.

**Use in our project.**
- **Justifies our gravity-model approach.** We don't need ground-truth phone-CDR data to get the *ranking* right. Top-import-hub rankings (a primary product output) are the most robust thing to mobility-data choice — exactly what this paper proves.
- **Calibration sanity check.** We can use the BTS T-100 fit on US-anchored routes (literature priors elsewhere) and not feel bad about it; this paper shows worse data choices than ours still produce robust qualitative results.

---

## 05 — Apolloni et al. 2014, "Metapopulation epidemic models with heterogeneous mixing and travel behaviour"
**File:** `05_Apolloni2014_metapopulation_heterogeneous_mixing.pdf` · arXiv 1401.5021

**What it is.** Analytical paper deriving the **basic reproduction number `R*`** in metapopulation models with two population classes that mix and travel differently. Closed-form expressions, no simulation needed for the headline result.

**How simulations are framed mathematically.** Two classes (e.g. social vs. less-social, or commuters vs. non-commuters), each with its own mixing rate and travel rate. They derive how the global `R*` decomposes into within-patch transmission, between-patch mobility, and class mixing — and find non-monotonic effects (e.g. travel restrictions can *increase* R* under some heterogeneous-mixing regimes).

**Use in our project.**
- **Defends our θ parameter** in the force-of-infection term `λ_i(t) = β_i(t)[(1-θ) I_i/N_i + θ Σ_j ω_ji I_j/N_j]`. The θ split between local and imported infection pressure is the simplest case of the heterogeneous mixing this paper formalizes.
- **Counterintuitive intervention insights for the demo.** When we move the "travel restriction" slider and the result is *not* a clean monotone reduction in everything, this paper explains why ("optimal across-groups mixing maximises pandemic potential"). Good defensive cite if a judge asks why interventions don't always help.

---

## 06 — Chinazzi et al. 2020, "The effect of travel restrictions on the spread of the 2019 novel coronavirus" (Science)
**File:** `06_Chinazzi2020_travel_restrictions_COVID19.pdf`

**What it is.** *The* paper that the entire industry of "global pandemic simulator" is benchmarked against. Used the GLEAM model in real time during the COVID-19 outbreak to project global spread under various travel-restriction scenarios.

**How world simulations are done in this paper.**
1. **Seed**: one infected person in Wuhan on a known date.
2. **Mobility data**: full IATA + commuting layer (the GLEAM matrix).
3. **Pathogen parameters**: literature priors with explicit ranges for R₀ (1.5–2.5), generation time, reporting fraction ρ. **Each Monte Carlo run draws a parameter triple from these priors.**
4. **Run**: stochastic SLIR per metapopulation, synchronized across the global graph.
5. **Intervention layer**: travel restrictions modeled as a multiplicative reduction `(1 - r)` on every airline edge to/from China. Mask/distancing modeled as a reduction in `β`.
6. **Output**: per-region case-importation distributions, with quantile bands across ~10,000 stochastic runs.

**Use in our project.** This is the *exact use case our product is a stripped-down version of.*
- **Equation (d) (Monte Carlo uncertainty)**: same shape — perturb R₀, generation time, ρ over priors; quantile across runs. Our PRD spec calls for ≥200 runs; their published runs were 10K. The methodology is identical.
- **Intervention multipliers**: our travel-restriction and mask sliders implement the exact two interventions Chinazzi quantifies. The paper's headline result ("90% travel restriction modestly affects trajectory unless combined with 50%+ transmission reduction") is the *kind of insight* our slider UI lets a judge discover live.
- **Demo storytelling**: opening line "Wuhan, January 2020" → set R₀=2.5, drag travel-restriction slider, observe modest delay, drag mask slider, observe flattening. This *is* the Chinazzi finding, reproducible on stage.
- **Backtest opportunity (PRD §12 Q4)**: if we want a calibration slide, seed the model in Wuhan on Jan 1 2020 and compare 30-day spread vs. their published projections. They publish all parameters → reproducible.

---

## 07 — Colizza et al. 2006, "The role of the airline transportation network in the prediction and predictability of global epidemics" (PNAS)
**File:** `07_Colizza2006_airline_network_global_epidemics_PNAS.pdf` · arXiv q-bio/0507029

**What it is.** The pre-GLEAM stochastic global-epidemic simulator. First serious paper to argue that **the airline network is the dominant driver of global spread** and that the network's heterogeneity (a few mega-hubs, many small airports) *makes* outbreaks predictable.

**How world simulations are done.** Stochastic SIR in each airport's catchment area; airline edges weighted by IATA passenger-trip volumes; Langevin (continuous-time stochastic) dynamics on the bipartite "patches × travelers" graph. Run thousands of times to compute ensemble mean and variance of arrival times.

**Use in our project.**
- **Foundational defense for using OpenFlights routes as the mobility scaffolding.** This paper proved that the air network's structure is *informative enough by itself* to predict global spread — supporting our decision to start with air mobility before sea.
- **"Predictability" framing for the demo.** They formalize predictability as low ensemble variance: epidemics that go through hubs are *more* predictable than ones that don't. Useful talking point when explaining why our 95% bands narrow on hub destinations and widen elsewhere.

---

## 08 — Pastor-Satorras, Castellano, Van Mieghem, Vespignani 2015, "Epidemic processes in complex networks" (Reviews of Modern Physics)
**File:** `08_PastorSatorras2015_epidemic_processes_complex_networks_review.pdf` · arXiv 1408.2701

**What it is.** The definitive 50-page review of how compartmental epidemic models behave on networks. Covers SIS, SIR, SIRS, metapopulation, contact-tracing, and the connection between network topology and epidemic thresholds.

**How simulations are framed in this paper.**
- **Mean-field on heterogeneous networks**: closed-form expressions for the epidemic threshold `λ_c` in terms of degree distribution moments `<k²>/<k>`. Power-law networks → vanishing threshold (any disease can go global).
- **Metapopulation reaction-diffusion**: each node = a sub-population; reaction = local SEIR; diffusion = mobility on the network. This is *our equation (c).*
- **Stochastic Markov chain** vs. **continuous-time mean-field**: trade-offs spelled out clearly. Our deterministic ODE-with-Monte-Carlo-over-parameters is a defensible middle ground.

**Use in our project.**
- **The reference textbook** for any epidemic-modeling theory question a judge throws. If they ask "what's the epidemic threshold for your network?", it's `1/<k²>/<k> · 1/γ` per this paper, evaluated on the OpenFlights graph.
- **Justifies why our model handles heterogeneous airport degrees fine** — the paper proves heterogeneity doesn't break the simulation, it just lowers thresholds.

---

## 09 — Kraemer et al. 2020, "The effect of human mobility and control measures on the COVID-19 epidemic in China" (Science)
**File:** `09_Kraemer2020_human_mobility_control_measures_COVID19_China.pdf`

**What it is.** Used **Baidu real-time mobility data** to show that the spatial distribution of COVID-19 cases across Chinese cities was strongly correlated with mobility from Wuhan — and that the correlation collapsed once travel restrictions kicked in.

**How world simulations are done.** Negative-binomial regression of city-level cases against Wuhan-outflow mobility, with structural-break testing on the date Wuhan was locked down. Effectively a *data-driven validation* of mobility-based simulators rather than a forward simulator itself.

**Use in our project.**
- **Empirical justification for why mobility-driven models work.** This is the "ground truth" sanity check that says: yes, mobility data *predicts* spatial spread; no, you don't need pathogen-specific tuning to get directional accuracy.
- **For the calibration badge in PRD §6 output #6.** When we claim "intervals contained truth in 92% of holdouts", this paper supplies the methodology for computing that — regress observed cases against your simulator's output, look at residuals.

---

## 10 — Tian et al. 2020, "An investigation of transmission control measures during the first 50 days of the COVID-19 epidemic in China" (Science)
**File:** `10_Tian2020_transmission_control_measures_first50days_China.pdf`

**What it is.** Quantitative breakdown of which interventions actually worked during the first 50 days in China — Wuhan shutdown, intra-city transit suspension, entertainment-venue closure, public-gathering ban.

**How simulations are done.** Counterfactual modeling: build the baseline metapopulation simulation, then re-run with each intervention turned on/off, measure the case-trajectory difference. Each intervention is implemented as a multiplier on either mobility (`m_ij → (1-r) m_ij`) or transmission rate (`β → (1-r)β`).

**Use in our project.** **This is the playbook for our intervention sliders.**
- **PRD inputs "travel restriction" and "mask/distancing"** are exactly the two intervention classes Tian decomposes. Their intervention-multiplier framework is what we copy.
- **Demo headline:** "Wuhan shutdown delayed dispersal by 2.91 days" — a quotable, judge-friendly result that we can reproduce live.
- **Validation target:** if we want to show our model's interventions agree with empirical estimates, this paper supplies the numbers.

---

## 11 — Davis, Chinazzi, Perra et al. 2021, "Cryptic transmission of SARS-CoV-2 and the first COVID-19 wave" (Nature)
**File:** `11_Davis2021_cryptic_transmission_first_COVID19_wave.pdf`

**What it is.** GLEAM-based reconstruction of the *undetected* spread of COVID-19 across Europe and the US in early 2020, finding that surveillance was missing 96–99% of infections and that transmission was already widespread by January.

**How world simulations are done.** Same GLEAM stochastic metapopulation engine as Chinazzi 2020, but run *backwards* — given observed case counts in late February, what unseeded chains of transmission must have existed in January? This is the mobility-aware version of a particle filter.

**Use in our project.**
- **Justifies the "reporting fraction `ρ`" parameter in our Monte Carlo loop** (PRD §7.1 (d)). This paper shows ρ values of 0.01–0.04 for early COVID — those are the priors to draw from. Without them, our case-count outputs are off by 25–100× and our calibration is broken.
- **Demo extension**: "What did we miss?" mode — if we want a stretch feature, run the model with low ρ and overlay "what surveillance saw" vs. "what was actually there". Visually striking.

---

## 12 — Rapti et al. 2022, "The role of mobility in the dynamics of the COVID-19 epidemic in Andalusia"
**File:** `12_Rapti2022_mobility_COVID19_Andalusia.pdf` · arXiv 2207.01958

**What it is.** Province-level metapopulation SEIR for Spain's Andalusia region during the COVID summer-fall 2020 wave, validating that **time-varying mobility data beats static priors** for predicting second-wave geography.

**How world simulations are done.** SEIR per province, mobility matrix `m_ij(t)` updated weekly from anonymized cell-phone data. Compare: (a) no mobility, (b) static gravity-model mobility, (c) time-varying empirical mobility. The third option wins.

**Use in our project.**
- **Sanity check for our static mobility assumption.** Our PRD uses a static OD matrix. This paper quantifies how much accuracy we lose by doing so — useful disclaimer for the limitations slide.
- **Stretch goal:** if we get a real-time mobility data feed, this is the recipe for plugging it in (just swap `m_ij` with `m_ij(t)`).

---

## 13 — Kisselev & Seshaiyer 2025, "Modeling COVID-19 spread in the USA using metapopulation SIR models coupled with graph convolutional neural networks"
**File:** `13_Kisselev2025_metapopulation_SIR_GCN_USA_COVID19.pdf` · arXiv 2501.02043

**What it is.** Hybrid model: metapopulation SIR provides the structure, a graph convolutional neural network learns time-varying parameters from data. State-of-the-art for US state-level COVID forecasting in 2025.

**How world simulations are done.** Standard metapopulation SIR ODEs, but the per-state β(t) and γ(t) are *outputs of a GCN* trained on case time-series + a state-adjacency graph. Forecasts come from rolling the trained ODEs forward.

**Use in our project.**
- **Talking point for the "why no deep learning?" question.** This paper shows that SIR-with-learned-β can match black-box ML on COVID forecasting *while remaining interpretable*. We have the SIR core (and could plug GCN learning in later) — but for a hackathon scoring on speed and explainability, fixed literature β is the right call.
- **Future direction slide.** If we ship and want to extend, this is one of the better-defined hybrid-ML upgrade paths.

---

## What's missing (and why we're OK)

- **Hufnagel, Brockmann, Geisel 2004** ("Forecast and control of epidemics in a globalized world" — PNAS). The first influential air-traffic-driven simulator. PMC and PNAS PDFs are CAPTCHA-gated. Conceptually subsumed by Colizza 2006 (file 07) and Balcan 2009 (file 02) — same idea, more refinement.
- **Brockmann & Helbing 2013** ("Hidden geometry of complex network-driven contagion phenomena" — Science). Defines the *effective distance* metric on the air-route graph. Useful for our top-import-hubs ranking but not load-bearing — gravity already approximates the same intuition. Cite the abstract if it comes up: `science.org/doi/10.1126/science.1245200`.
- **Reich et al. 2019** (CDC FluSight multimodel forecast assessment — PNAS). Best cite for the "how good are our calibration intervals?" question. Cite by reference if a judge probes calibration methodology: `pnas.org/doi/10.1073/pnas.1812594116`.
- **Funk et al. 2018** (Real-time stochastic semi-mechanistic forecasting — *Epidemics*). Renewal-equation forecasting; covered conceptually in Lu 2025 review (file 03).
- **Original Kermack-McKendrick 1927 SIR** — textbook material; not needed.
- **The 2010 GLEAM Journal of Computational Science paper** — gated, but Balcan 2009 (file 02) covers the same model from the same authors.

---

## Recommended reading order for a teammate

**Tier 1 (must-read, 2–3 hours total):**
1. **Lu 2025 review (file 03)** — 30 min. Lay of the land.
2. **Balcan 2009 PNAS (file 02)** — 1 hour. Reference architecture.
3. **Chinazzi 2020 (file 06)** — 1 hour. The exact thing we're a hackathon version of.
4. **Tian 2020 (file 10)** — 30 min. Intervention slider playbook.

**Tier 2 (nice-to-have, skim):**
5. **Guo 2026 (file 01)** — why our gravity formula is defensible.
6. **Colizza 2006 (file 07)** — why the airline network is enough.
7. **Kraemer 2020 (file 09)** — empirical mobility-spread validation.
8. **Tizzoni 2014 (file 04)** — why imperfect mobility data is OK.

**Tier 3 (consult on demand):**
9. **Pastor-Satorras 2015 (file 08)** — theory-question backstop.
10. **Apolloni 2014 (file 05)** — counterintuitive intervention defenses.
11. **Davis 2021 (file 11)** — reporting-fraction priors.
12. **Rapti 2022 (file 12)** — static-mobility limitations.
13. **Kisselev 2025 (file 13)** — ML upgrade path.

---

## How each paper supports each PRD equation

| PRD equation / feature | Primary source(s) | Supporting source(s) |
|---|---|---|
| (a) Air gravity + exp decay | Guo 2026 (01) | Balcan 2009 (02), Colizza 2006 (07) |
| (b) Port-call gravity | — *(analogous form to (a))* | Tizzoni 2014 (04), Rapti 2022 (12) |
| (c) Metapopulation SEIR | Balcan 2009 (02), Pastor-Satorras 2015 (08) | Apolloni 2014 (05), Lu 2025 (03), Kisselev 2025 (13) |
| (d) Monte Carlo uncertainty bands | Chinazzi 2020 (06) | Balcan 2009 (02), Davis 2021 (11) |
| Travel-restriction slider | Tian 2020 (10), Chinazzi 2020 (06) | Apolloni 2014 (05), Kraemer 2020 (09) |
| Mask / distancing slider | Tian 2020 (10), Chinazzi 2020 (06) | — |
| Calibration / coverage badge | Kraemer 2020 (09) | Davis 2021 (11) |
| Top import-hub ranking | Colizza 2006 (07) | Balcan 2009 (02), Tizzoni 2014 (04) |
| "Why not deep learning?" defense | Lu 2025 (03), Kisselev 2025 (13) | — |
| Live-demo storytelling | Chinazzi 2020 (06), Tian 2020 (10) | Kraemer 2020 (09), Davis 2021 (11) |
