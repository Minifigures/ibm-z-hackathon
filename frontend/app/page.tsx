"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ForecastChart } from "@/components/forecast-chart";
import { ExplainPanel } from "@/components/explain-panel";
import { HubList } from "@/components/hub-list";
import { SliderRow } from "@/components/slider-row";
import {
  api,
  type Country,
  type DiseasePreset,
  type SimulateRequest,
  type SimulationResult,
} from "@/lib/api";

const WorldMap = dynamic(() => import("@/components/world-map").then((m) => m.WorldMap), {
  ssr: false,
});

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
  const [countries, setCountries] = useState<Country[]>([]);
  const [presets, setPresets] = useState<Record<string, DiseasePreset>>({});
  const [req, setReq] = useState<SimulateRequest>(DEFAULT_REQ);
  const [result, setResult] = useState<SimulationResult | null>(null);
  const [selectedIso3, setSelectedIso3] = useState<string | null>(null);
  const [lockedIso3, setLockedIso3] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [latencyMs, setLatencyMs] = useState<number | null>(null);
  const [explainText, setExplainText] = useState<string | null>(null);
  const [explainSource, setExplainSource] = useState<string | null>(null);
  const [explainLoading, setExplainLoading] = useState(false);
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

  // Hover preview: only updates selection while nothing is locked.
  const handleHover = useCallback((iso3: string) => {
    setSelectedIso3((prev) => (lockedIso3 ? prev : iso3));
  }, [lockedIso3]);
  // Click locks (or clicking empty / passing null clears the lock).
  const handlePick = useCallback((iso3: string | null) => {
    setLockedIso3(iso3);
    setSelectedIso3(iso3);
  }, []);

  const onPickPreset = (id: string) => {
    const p = presets[id];
    if (!p) return;
    update({
      disease_id: id,
      r0: p.r0,
      incubation_days: p.incubation_days,
      infectious_days: p.infectious_days,
      cfr_pct: p.cfr_pct,
    });
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

  const allHubs = useMemo(() => {
    if (!result) return [];
    return result.regions
      .map((r) => ({
        iso3: r.iso3,
        name: r.name,
        expected_cases: r.cumulative_p50_final,
      }))
      .sort((a, b) => b.expected_cases - a.expected_cases);
  }, [result]);

  const focusName = focusRegion?.name ?? null;
  const calibration = result?.calibration;

  return (
    <main className="grid grid-cols-[360px_1fr] grid-rows-[auto_1fr] h-screen w-screen overflow-hidden bg-ink-900 text-slate-100">
      <header className="col-span-2 border-b border-ink-600 bg-ink-800 px-4 py-2 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-2 h-2 rounded-full bg-accent shadow-[0_0_8px_2px_rgba(124,242,200,0.6)]" />
          <h1 className="text-sm font-semibold tracking-wide">Disease Outflow Forecaster</h1>
          <span className="text-[11px] text-slate-500">
            SEIR + gravity mobility + Monte Carlo · IBM Z hackathon prototype
          </span>
        </div>
        <div className="flex items-center gap-3 text-[11px] text-slate-400">
          <span>
            sim: <span className="font-mono text-slate-200">{busy ? "…" : `${latencyMs?.toFixed(0) ?? "..."} ms`}</span>
          </span>
          {calibration ? (
            <span className="rounded border border-accent/40 px-2 py-0.5 text-accent">
              {(calibration.interval_coverage_holdout * 100).toFixed(0)}% coverage on holdout
            </span>
          ) : null}
        </div>
      </header>

      <aside className="row-start-2 overflow-y-auto border-r border-ink-600 bg-ink-800 p-4 space-y-4">
        <section>
          <h2 className="text-xs uppercase tracking-wider text-slate-400 mb-2">Scenario</h2>
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
            hint="Basic reproduction number"
            value={req.r0}
            min={0.5}
            max={5}
            step={0.1}
            format={(v) => v.toFixed(1)}
            onChange={(r0) => update({ r0 })}
          />
          <SliderRow
            label="Incubation (days)"
            value={req.incubation_days}
            min={1}
            max={21}
            step={0.5}
            format={(v) => v.toFixed(1)}
            onChange={(incubation_days) => update({ incubation_days })}
          />
          <SliderRow
            label="Infectious period (days)"
            value={req.infectious_days}
            min={1}
            max={21}
            step={0.5}
            format={(v) => v.toFixed(1)}
            onChange={(infectious_days) => update({ infectious_days })}
          />
          <SliderRow
            label="CFR (%)"
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
            value={req.air_weight}
            min={0}
            max={2}
            step={0.05}
            format={(v) => v.toFixed(2) + "×"}
            onChange={(air_weight) => update({ air_weight })}
          />
          <SliderRow
            label="Port weight"
            value={req.port_weight}
            min={0}
            max={2}
            step={0.05}
            format={(v) => v.toFixed(2) + "×"}
            onChange={(port_weight) => update({ port_weight })}
          />
          <SliderRow
            label="Travel restriction"
            value={req.travel_restriction}
            min={0}
            max={1}
            step={0.05}
            format={(v) => `${(v * 100).toFixed(0)}%`}
            onChange={(travel_restriction) => update({ travel_restriction })}
          />
          <SliderRow
            label="Mask / distancing"
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
            value={req.horizon_days}
            min={7}
            max={120}
            step={1}
            format={(v) => `${v} days`}
            onChange={(horizon_days) => update({ horizon_days })}
          />
          <SliderRow
            label="Monte Carlo runs"
            value={req.n_runs}
            min={50}
            max={1000}
            step={50}
            format={(v) => `${v}`}
            onChange={(n_runs) => update({ n_runs })}
          />
        </section>
      </aside>

      <section className="row-start-2 relative">
        <div className="absolute inset-0">
          <WorldMap
            countries={countries}
            regions={result?.regions ?? []}
            arcs={result?.spread_arcs ?? []}
            startIso3={req.start_iso3}
            selectedIso3={selectedIso3}
            lockedIso3={lockedIso3}
            onHover={handleHover}
            onPick={handlePick}
          />
        </div>

        <div className="absolute bottom-0 left-0 right-0 grid grid-cols-3 gap-3 p-3 pointer-events-none">
          <div className="pointer-events-auto">
            <HubList
              title="All countries (median cumulative cases)"
              rows={allHubs}
              valueKey="expected_cases"
              onHover={handleHover}
              onPick={handlePick}
              selectedIso3={selectedIso3}
              maxHeight="260px"
            />
          </div>
          <div className="pointer-events-auto">
            {focusRegion ? (
              <ForecastChart
                title={`Forecast · ${focusRegion.name}`}
                quantiles={focusRegion.quantiles}
              />
            ) : (
              <div className="rounded-md border border-ink-600 bg-ink-800 p-3 text-xs text-slate-500">
                Click a country on the map (or in the hub list) to see its forecast curve with
                50% / 95% intervals.
              </div>
            )}
          </div>
          <div className="pointer-events-auto">
            <ExplainPanel
              text={explainText}
              source={explainSource}
              loading={explainLoading}
              onRequest={onExplain}
              focusName={focusName}
            />
          </div>
        </div>
      </section>
    </main>
  );
}
