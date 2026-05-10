export type Country = {
  iso3: string;
  name: string;
  lat: number;
  lng: number;
  population: number;
  hub: number;
};

export type DiseasePreset = {
  id: string;
  label: string;
  r0: number;
  incubation_days: number;
  infectious_days: number;
  cfr_pct: number;
  notes: string;
  citations: string[];
};

export type Quantiles = {
  p2_5: number[];
  p25: number[];
  p50: number[];
  p75: number[];
  p97_5: number[];
};

export type RegionResult = {
  iso3: string;
  name: string;
  population: number;
  prevalence_p50_per_100k: number;
  prevalence_p95_per_100k: number;
  cumulative_p50_final: number;
  quantiles: Quantiles;
};

export type HubRow = {
  iso3: string;
  name: string;
  expected_cases?: number;
  per_100k?: number;
  score?: number;
};

export type SpreadArc = {
  from_iso3: string;
  to_iso3: string;
  from_name: string;
  to_name: string;
  weight: number;
  weight_normalized: number;
};

export type SimulationResult = {
  horizon_days: number;
  regions: RegionResult[];
  top_imports: HubRow[];
  top_exports: HubRow[];
  spread_arcs: SpreadArc[];
  calibration: {
    monte_carlo_runs: number;
    interval_coverage_holdout: number;
    note: string;
  };
  params_used: Record<string, number | string>;
};

export type SimulateRequest = {
  disease_id: string;
  start_iso3: string;
  r0: number;
  incubation_days: number;
  infectious_days: number;
  cfr_pct: number;
  air_weight: number;
  port_weight: number;
  travel_restriction: number;
  mask_intervention: number;
  horizon_days: number;
  n_runs: number;
};

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

async function jsonFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!res.ok) throw new Error(`${path} ${res.status}: ${await res.text()}`);
  return res.json() as Promise<T>;
}

export const api = {
  countries: () => jsonFetch<Country[]>("/countries"),
  presets: () => jsonFetch<Record<string, DiseasePreset>>("/presets"),
  simulate: (req: SimulateRequest) =>
    jsonFetch<SimulationResult>("/simulate", { method: "POST", body: JSON.stringify(req) }),
  explain: (simulation: SimulationResult, focus_iso3: string | null) =>
    jsonFetch<{ text: string; source: string }>("/explain", {
      method: "POST",
      body: JSON.stringify({ simulation, focus_iso3 }),
    }),
};
