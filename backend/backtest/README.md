# Backtest harness

A measured replacement for the placeholder
`"interval_coverage_holdout": 0.93` value baked into
`app/simulate.py`'s response.

## What it does

1. Downloads the JHU CSSE *confirmed global* time series
   (`time_series_covid19_confirmed_global.csv`) and caches it under
   `backend/backtest/data/`.
2. Aggregates province-level rows to country totals, maps JHU country names
   to the ISO-3 codes already present in `app/data/countries.json`, and
   splits Hong Kong out of mainland China to match the model's region set.
3. Seeds the production simulator (`app.simulate`) with COVID-19 in **CHN**
   on **2020-01-22** (the first JHU date) using the day-0 JHU case count
   (547) so the model's initial condition matches reality.
4. Runs **1000** Monte Carlo iterations over a **30-day** horizon with the
   COVID-19 preset from `app/data/diseases.json`
   (R₀ = 2.5, incubation = 5 d, infectious = 6 d).
5. On day +30 (**2020-02-21**) compares the model's per-country cumulative
   infected band against actual JHU confirmed cases and reports:
   * `coverage_95pi` — fraction of countries whose actual count fell inside
     the model's [p2.5, p97.5] interval.
   * `median_log_mae` — median absolute error in `log10(cases + 1)` between
     model median and JHU truth (cases span ~6 orders of magnitude, so a
     log scale is the only honest one).

## How to run

From `backend/`:

```
python -m backtest.run_backtest
```

The script writes `backend/backtest/results.json`. The cached CSV lives in
`backend/backtest/data/time_series_covid19_confirmed_global.csv` after the
first run; delete it to force a fresh download.

If GitHub is unreachable, the script fails loudly with the URL it tried.

## Headline number from the canonical run

```
seed_iso3            CHN
seed_date            2020-01-22
comparison_date      2020-02-21
horizon_days         30
n_monte_carlo_runs   1000
n_countries_compared 71
coverage_95pi        0.394   (39.4%)
median_log_mae       0.346
```

So the **95% prediction-interval coverage is roughly 39%**, not 93%. The
README and PRD claim was a placeholder; this is the measured number with
the model as currently configured.

## Caveats / what this does not say

* **Synthetic mobility.** The model's gravity OD matrix is built from
  population × hub-index × distance-decay (see `app/mobility.py`). The
  hub-index column in `countries.json` is hand-tuned, not calibrated to any
  IATA passenger figure. Countries that JHU shows getting hit early via
  air-travel (Singapore, Hong Kong, Iran) are systematically under-shot
  because the mobility weights don't replicate their actual travel volume
  to/from Wuhan. Coverage would likely improve substantially with real
  OpenFlights / IATA seat-capacity data.
* **JHU vs. modelled "infected".** JHU's "confirmed" includes only tested
  positives. The model's cumulative-infected (= N − S) is true infections
  including untested cases. For the early-2020 window the testing rate was
  much lower than 100%, so the model is being scored against an undercount
  in most countries — it should generally over-predict, but with these
  mobility weights it tends to under-predict outside CHN.
* **Single seed window.** This is one holdout, not a cross-validated
  rolling window. The PRD's "93% of holdouts" framing implies a
  multi-window study; we deliberately did not invent that here. If you want
  a proper rolling backtest, slide `SEED_DATE` and re-aggregate.
* **CHN seed parameter.** We start with 547 infected in CHN (the JHU
  day-0 number) rather than the simulator's library default of 50. With 50
  the seed compartment is itself outside the [p2.5, p97.5] band on day +30,
  which would tank the coverage further. Using the JHU day-0 truth is what
  a real-time forecaster would actually do.
* **JHU's pre-Jan 22 data does not exist.** The CSV starts on 2020-01-22,
  which is why we use that as the seed date. There's no earlier window we
  could shift the test to.

## Per-country diagnostic

`results.json[*].per_country` is a list of records:

| field         | meaning                                              |
| ------------- | ---------------------------------------------------- |
| `iso3`        | ISO-3 country code                                   |
| `actual`      | JHU confirmed cases on `comparison_date`             |
| `model_median`| simulator p50 cumulative-infected                    |
| `model_p2_5`  | simulator 2.5th percentile                           |
| `model_p97_5` | simulator 97.5th percentile                          |
| `covered`     | did `actual` fall inside [p2.5, p97.5]?              |
| `log_abs_error` | abs(log10(median+1) − log10(actual+1))             |

Countries with no JHU row at all (a handful of the 72 modelled, none with
meaningful 2020-02-21 cases) are dropped from the count, leaving 71.

## Replacing the placeholder

The placeholder lives at `backend/app/simulate.py` line ~241:

```python
"calibration": {
    "monte_carlo_runs": params.n_runs,
    "interval_coverage_holdout": 0.93,  # placeholder until backtest lands
    ...
}
```

Once this harness is wired in, swap in the value from
`results.json["coverage_95pi"]` (currently **0.394**). Be honest about it.
