"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ForecastChart } from "@/components/forecast-chart";
import { ExplainPanel } from "@/components/explain-panel";
import { HubList } from "@/components/hub-list";
import { Landing } from "@/components/landing";
import { NowcastPanel } from "@/components/nowcast-panel";
import { SliderRow } from "@/components/slider-row";
import { DiseaseSearch } from "@/components/disease-search";
import {
  api,
  type Country,
  type DiseaseParams,
  type DiseasePreset,
  type NowcastObservation,
  type NowcastResult,
  type SimulateRequest,
  type SimulationResult,
} from "@/lib/api";

const WorldMap = dynamic(() => import("@/components/world-map").then((m) => m.WorldMap), {
  ssr: false,
});
const PolarMap = dynamic(() => import("@/components/polar-map").then((m) => m.PolarMap), {
  ssr: false,
});

type MapView = "geo" | "polar";

const DEFAULT_REQ: SimulateRequest = {
  disease_id: "covid19",
  start_iso3: "USA",
  r0: 2.5,
  incubation_days: 5.0,
  infectious_days: 6.0,
  cfr_pct: 1.0,
  air_weight: 1.0,
  port_weight: 0.3,
  travel_restriction: 0.0,
  mask_intervention: 0.0,
  horizon_days: 30,
  n_runs: 200,
};

export default function Page() {
  const [showLanding, setShowLanding] = useState(true);
  const [countries, setCountries] = useState<Country[]>([]);
  const [presets, setPresets] = useState<Record<string, DiseasePreset>>({});
  const [req, setReq] = useState<SimulateRequest>(DEFAULT_REQ);
  const [result, setResult] = useState<SimulationResult | null>(null);
  const [selectedIso3, setSelectedIso3] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [latencyMs, setLatencyMs] = useState<number | null>(null);
  const [explainText, setExplainText] = useState<string | null>(null);
  const [explainSource, setExplainSource] = useState<string | null>(null);
  const [explainLoading, setExplainLoading] = useState(false);
  const [mapView, setMapView] = useState<MapView>("geo");
  const [nowcastResult, setNowcastResult] = useState<NowcastResult | null>(null);
  const [nowcastLoading, setNowcastLoading] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [hubsCollapsed, setHubsCollapsed] = useState(false);
  const [forecastCollapsed, setForecastCollapsed] = useState(false);
  const [explainCollapsed, setExplainCollapsed] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    api.countries().then(setCountries).catch(console.error);
    api.presets().then(setPresets).catch(console.error);
  }, []);

  const runSimulation = useCallback(async (next: SimulateRequest) => {
    setBusy(true);
    const t0 = performance.now();
    try {
      const r = await api.simulate(next);
      setResult(r);
      setLatencyMs(performance.now() - t0);
    } catch (err) {
      console.error(err);
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => runSimulation(req), 120);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [req, runSimulation]);

  const update = (patch: Partial<SimulateRequest>) => setReq((cur) => ({ ...cur, ...patch }));

  const onPickPreset = (id: string) => {
    const p = presets[id];
    if (!p) return;
    const patch: Partial<SimulateRequest> = {
      disease_id: id,
      r0: p.r0,
      incubation_days: p.incubation_days,
      infectious_days: p.infectious_days,
      cfr_pct: p.cfr_pct,
    };
    // If the preset declares a historical origin and we model it, snap the
    // origin selector to it. Pathogen X intentionally leaves origin null so
    // it preserves the user's last-touched country.
    if (p.likely_origin_iso3 && countries.some((c) => c.iso3 === p.likely_origin_iso3)) {
      patch.start_iso3 = p.likely_origin_iso3;
    }
    update(patch);
  };

  const onAutoFill = (p: DiseaseParams) => {
    const patch: Partial<SimulateRequest> = {
      disease_id: "pathogenx",
      r0: p.r0,
      incubation_days: p.incubation_days,
      infectious_days: p.infectious_days,
      cfr_pct: p.cfr_pct,
    };
    if (p.likely_origin_iso3 && countries.some((c) => c.iso3 === p.likely_origin_iso3)) {
      patch.start_iso3 = p.likely_origin_iso3;
    }
    update(patch);
  };

  const onExplain = async () => {
    if (!result) return;
    setExplainLoading(true);
    try {
      const r = await api.explain(result, selectedIso3);
      setExplainText(r.text);
      setExplainSource(r.source);
    } catch (err) {
      setExplainText(`Explainer error: ${(err as Error).message}`);
      setExplainSource(null);
    } finally {
      setExplainLoading(false);
    }
  };

  const focusRegion = useMemo(() => {
    if (!result || !selectedIso3) return null;
    return result.regions.find((r) => r.iso3 === selectedIso3) ?? null;
  }, [result, selectedIso3]);

  const runNowcast = async (observations: NowcastObservation[]) => {
    setNowcastLoading(true);
    try {
      const r = await api.nowcast({ ...req, observations });
      setNowcastResult(r);
    } catch (err) {
      console.error(err);
    } finally {
      setNowcastLoading(false);
    }
  };

  // Invalidate any prior posterior whenever the user moves a slider or
  // changes origin -- otherwise we'd be overlaying stale posteriors on a
  // freshly re-simulated prior.
  useEffect(() => {
    setNowcastResult(null);
  }, [
    req.disease_id,
    req.start_iso3,
    req.r0,
    req.incubation_days,
    req.infectious_days,
    req.air_weight,
    req.port_weight,
    req.travel_restriction,
    req.mask_intervention,
    req.horizon_days,
  ]);

  const showPosteriorOnFocus =
    nowcastResult !== null && focusRegion?.iso3 === req.start_iso3;

  const focusName = focusRegion?.name ?? null;
  const calibration = result?.calibration;

  return (
    <>
    {showLanding ? <Landing onLaunch={() => setShowLanding(false)} /> : null}
    <main
      className="grid grid-rows-[auto_1fr] h-screen w-screen overflow-hidden bg-ink-900 text-slate-100"
      style={{ gridTemplateColumns: `${sidebarCollapsed ? 36 : 360}px 1fr` }}
    >
      <header className="col-span-2 border-b border-ink-600 bg-ink-800 px-4 py-2 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-2 h-2 rounded-full bg-accent shadow-[0_0_8px_2px_rgba(124,242,200,0.6)]" />
          <h1 className="text-sm font-semibold tracking-wide">Pandexis · Disease Outflow Forecaster</h1>
          <span className="text-[11px] text-slate-500">
            SEIR + gravity mobility + Monte Carlo · IBM Z hackathon prototype
          </span>
        </div>
        <div className="flex items-center gap-3 text-[11px] text-slate-400">
          <span>
            sim: <span className="font-mono text-slate-200">{busy ? "…" : `${latencyMs?.toFixed(0) ?? "..."} ms`}</span>
          </span>
          {calibration ? (
            <div
              className="flex items-center gap-1 text-[11px]"
              title={calibration.note}
            >
              <span className="rounded border border-accent/40 px-2 py-0.5 text-accent">
                {(calibration.interval_coverage_holdout * 100).toFixed(0)}% cov₉₅
              </span>
              {typeof calibration.crps_norm_per_100k === "number" &&
              Number.isFinite(calibration.crps_norm_per_100k) ? (
                <span
                  className="rounded border border-slate-600 px-2 py-0.5 text-slate-200"
                  title="CRPS per 100k (Funk 2018) — lower is better"
                >
                  CRPS {calibration.crps_norm_per_100k.toFixed(2)}/100k
                </span>
              ) : null}
              {typeof calibration.multibin_log_score === "number" &&
              Number.isFinite(calibration.multibin_log_score) ? (
                <span
                  className="rounded border border-slate-600 px-2 py-0.5 text-slate-200"
                  title="Multibin log score (Reich 2019 / FluSight) — higher is better"
                >
                  log {calibration.multibin_log_score.toFixed(2)}
                </span>
              ) : null}
            </div>
          ) : null}
        </div>
      </header>

      {sidebarCollapsed ? (
        <aside className="row-start-2 border-r border-ink-600 bg-ink-800 flex flex-col items-center pt-3">
          <button
            type="button"
            aria-label="Expand scenario panel"
            aria-expanded={false}
            onClick={() => setSidebarCollapsed(false)}
            className="w-6 h-6 inline-flex items-center justify-center rounded border border-ink-600 text-slate-400 hover:border-slate-400 hover:text-slate-200 text-[14px] leading-none"
          >
            +
          </button>
          <div
            className="mt-3 text-[10px] uppercase tracking-wider text-slate-500"
            style={{ writingMode: "vertical-rl" }}
          >
            Scenario
          </div>
        </aside>
      ) : (
      <aside className="row-start-2 overflow-y-auto border-r border-ink-600 bg-ink-800 p-4 space-y-4">
        <section>
          <div className="flex items-center justify-between mb-2">
            <h2 className="text-xs uppercase tracking-wider text-slate-400">Scenario</h2>
            <button
              type="button"
              aria-label="Minimize scenario panel"
              aria-expanded={true}
              onClick={() => setSidebarCollapsed(true)}
              className="w-5 h-5 inline-flex items-center justify-center rounded border border-ink-600 text-slate-400 hover:border-slate-400 hover:text-slate-200 text-[12px] leading-none"
            >
              −
            </button>
          </div>
          <div className="mb-3">
            <DiseaseSearch onApply={onAutoFill} />
          </div>
          <div className="grid grid-cols-2 gap-2 mb-3">
            {Object.values(presets).map((p) => (
              <button
                key={p.id}
                onClick={() => onPickPreset(p.id)}
                className={`text-xs px-2 py-1.5 rounded border ${
                  req.disease_id === p.id
                    ? "border-accent text-accent bg-accent/10"
                    : "border-ink-600 text-slate-300 hover:border-slate-400"
                }`}
              >
                {p.label}
              </button>
            ))}
          </div>
          <label className="block text-xs uppercase tracking-wide text-slate-400 mb-1">
            Origin
          </label>
          <select
            className="w-full bg-ink-700 border border-ink-600 rounded px-2 py-1.5 text-sm"
            value={req.start_iso3}
            onChange={(e) => update({ start_iso3: e.target.value })}
          >
            {countries.map((c) => (
              <option key={c.iso3} value={c.iso3}>
                {c.name} ({c.iso3})
              </option>
            ))}
          </select>
        </section>

        <section className="space-y-3">
          <SliderRow
            label="R₀"
            info="Basic reproduction number — the average number of new infections a single infected person causes in a fully susceptible population."
            value={req.r0}
            min={0.5}
            max={5}
            step={0.1}
            format={(v) => v.toFixed(1)}
            onChange={(r0) => update({ r0 })}
          />
          <SliderRow
            label="Incubation (days)"
            info="Average time from exposure to becoming infectious. Longer incubation means slower onset but more silent spread."
            value={req.incubation_days}
            min={1}
            max={21}
            step={0.5}
            format={(v) => v.toFixed(1)}
            onChange={(incubation_days) => update({ incubation_days })}
          />
          <SliderRow
            label="Infectious period (days)"
            info="Average number of days an infected person can transmit the disease to others before recovering or being isolated."
            value={req.infectious_days}
            min={1}
            max={21}
            step={0.5}
            format={(v) => v.toFixed(1)}
            onChange={(infectious_days) => update({ infectious_days })}
          />
          <SliderRow
            label="CFR (%)"
            info="Case fatality rate — the percentage of confirmed cases that result in death."
            value={req.cfr_pct}
            min={0.01}
            max={30}
            step={0.05}
            format={(v) => v.toFixed(2) + "%"}
            onChange={(cfr_pct) => update({ cfr_pct })}
          />
        </section>

        <section className="space-y-3 pt-3 border-t border-ink-600">
          <h2 className="text-xs uppercase tracking-wider text-slate-400">Mobility</h2>
          <SliderRow
            label="Air weight"
            info="Multiplier on air-travel flow between countries. Higher values amplify spread along flight routes."
            value={req.air_weight}
            min={0}
            max={2}
            step={0.05}
            format={(v) => v.toFixed(2) + "×"}
            onChange={(air_weight) => update({ air_weight })}
          />
          <SliderRow
            label="Port weight"
            info="Multiplier on maritime / port-based flow. Higher values amplify spread through shipping and cruise routes."
            value={req.port_weight}
            min={0}
            max={2}
            step={0.05}
            format={(v) => v.toFixed(2) + "×"}
            onChange={(port_weight) => update({ port_weight })}
          />
          <SliderRow
            label="Travel restriction"
            info="Fraction of cross-border mobility removed by policies (border closures, quarantines). 0% = open borders, 100% = no travel."
            value={req.travel_restriction}
            min={0}
            max={1}
            step={0.05}
            format={(v) => `${(v * 100).toFixed(0)}%`}
            onChange={(travel_restriction) => update({ travel_restriction })}
          />
          <SliderRow
            label="Mask / distancing"
            info="Reduction in per-contact transmission from masks, distancing, and hygiene measures. 0% = no effect, 100% = transmission fully blocked."
            value={req.mask_intervention}
            min={0}
            max={1}
            step={0.05}
            format={(v) => `${(v * 100).toFixed(0)}% transmission cut`}
            onChange={(mask_intervention) => update({ mask_intervention })}
          />
        </section>

        <section className="space-y-3 pt-3 border-t border-ink-600">
          <SliderRow
            label="Forecast horizon"
            info="How many days into the future the simulation projects. Longer horizons compound uncertainty."
            value={req.horizon_days}
            min={7}
            max={120}
            step={1}
            format={(v) => `${v} days`}
            onChange={(horizon_days) => update({ horizon_days })}
          />
          <SliderRow
            label="Monte Carlo runs"
            info="Number of stochastic simulation trajectories. More runs give tighter confidence intervals at the cost of compute time."
            value={req.n_runs}
            min={50}
            max={1000}
            step={50}
            format={(v) => `${v}`}
            onChange={(n_runs) => update({ n_runs })}
          />
        </section>
      </aside>
      )}

      <section className="row-start-2 grid grid-rows-[1fr_auto] overflow-hidden">
        <div className="relative overflow-hidden">
          <div className="absolute inset-0">
            {mapView === "geo" ? (
              <WorldMap
                countries={countries}
                regions={result?.regions ?? []}
                arcs={result?.spread_arcs ?? []}
                startIso3={req.start_iso3}
                selectedIso3={selectedIso3}
                onSelect={setSelectedIso3}
              />
            ) : (
              <PolarMap
                countries={countries}
                regions={result?.regions ?? []}
                arcs={result?.spread_arcs ?? []}
                startIso3={req.start_iso3}
                selectedIso3={selectedIso3}
                onSelect={setSelectedIso3}
              />
            )}
          </div>

          <div className="absolute right-3 top-3 z-10 flex gap-1 rounded border border-ink-600 bg-ink-800/90 p-0.5 text-[11px] backdrop-blur">
            <button
              onClick={() => setMapView("geo")}
              className={`rounded px-2 py-1 ${
                mapView === "geo" ? "bg-accent/20 text-accent" : "text-slate-300 hover:text-slate-100"
              }`}
            >
              Geo
            </button>
            <button
              onClick={() => setMapView("polar")}
              className={`rounded px-2 py-1 ${
                mapView === "polar" ? "bg-accent/20 text-accent" : "text-slate-300 hover:text-slate-100"
              }`}
              title="Effective-distance polar projection (Brockmann & Helbing 2013)"
            >
              Polar (d_eff)
            </button>
          </div>
        </div>

        <div className="grid grid-cols-3 gap-3 max-h-[42vh] overflow-y-auto border-t border-ink-600 bg-ink-900 p-3">
          <HubList
            title="Top import hubs (median expected cases)"
            rows={result?.top_imports ?? []}
            valueKey="expected_cases"
            onSelect={setSelectedIso3}
            collapsed={hubsCollapsed}
            onToggleCollapse={() => setHubsCollapsed((v) => !v)}
          />
          {focusRegion ? (
            <ForecastChart
              title={`Forecast · ${focusRegion.name}`}
              quantiles={focusRegion.quantiles}
              predictedArrivalDay={focusRegion.predicted_arrival_day}
              effectiveDistance={focusRegion.effective_distance_from_seed}
              variantsTerminalP50={focusRegion.variants_terminal_p50}
              variantMeta={result?.model_variants}
              posteriorQuantiles={showPosteriorOnFocus ? nowcastResult!.posterior_quantiles : null}
              observations={showPosteriorOnFocus ? nowcastResult!.observations : null}
              collapsed={forecastCollapsed}
              onToggleCollapse={() => setForecastCollapsed((v) => !v)}
            />
          ) : (
            <div className="rounded-md border border-ink-600 bg-ink-800 p-3 text-xs text-slate-500">
              Click a country on the map (or in the hub list) to see its forecast curve with
              50% / 95% intervals.
            </div>
          )}
          <div className="space-y-2">
            <ExplainPanel
              text={explainText}
              source={explainSource}
              loading={explainLoading}
              onRequest={onExplain}
              focusName={focusName}
              collapsed={explainCollapsed}
              onToggleCollapse={() => setExplainCollapsed((v) => !v)}
            />
            <NowcastPanel
              loading={nowcastLoading}
              result={nowcastResult}
              onRun={runNowcast}
              onClear={() => setNowcastResult(null)}
              seedIso3={req.start_iso3}
            />
          </div>
        </div>
      </section>
    </main>
    </>
  );
}
