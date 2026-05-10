import { describe, expect, it, vi, beforeEach } from "vitest";
import {
  __resetCountryGeoJSONCache,
  joinRegionsToFeatures,
  loadCountryGeoJSON,
  pickIso3,
  type CountryFeatureCollection,
} from "@/lib/world-data";
import type { RegionResult } from "@/lib/api";

const SAMPLE_FC: CountryFeatureCollection = {
  type: "FeatureCollection",
  features: [
    {
      type: "Feature",
      geometry: { type: "Polygon", coordinates: [[[0, 0], [1, 0], [1, 1], [0, 0]]] },
      properties: { ISO_A3: "USA", ADMIN: "United States" },
    },
    {
      type: "Feature",
      geometry: { type: "Polygon", coordinates: [[[0, 0], [1, 0], [1, 1], [0, 0]]] },
      properties: { ISO_A3: "BRA", ADMIN: "Brazil" },
    },
    {
      type: "Feature",
      geometry: { type: "Polygon", coordinates: [[[0, 0], [1, 0], [1, 1], [0, 0]]] },
      // Disputed territory: ISO_A3 sentinel, but ADM0_A3 is meaningful.
      properties: { ISO_A3: "-99", ADM0_A3: "KOS", ADMIN: "Kosovo" },
    },
  ],
};

const REGIONS: RegionResult[] = [
  {
    iso3: "USA",
    name: "United States",
    population: 331_000_000,
    prevalence_p50_per_100k: 42,
    prevalence_p95_per_100k: 80,
    cumulative_p50_final: 1_000_000,
    effective_distance_from_seed: null,
    predicted_arrival_day: null,
    quantiles: { p2_5: [], p25: [], p50: [], p75: [], p97_5: [] },
  },
];

describe("pickIso3", () => {
  it("prefers ISO_A3 when it is a real 3-letter code", () => {
    expect(pickIso3({ ISO_A3: "USA", ADM0_A3: "OTH" })).toBe("USA");
  });

  it("falls back to ADM0_A3 when ISO_A3 is the -99 sentinel", () => {
    expect(pickIso3({ ISO_A3: "-99", ADM0_A3: "KOS" })).toBe("KOS");
  });

  it("returns null when no usable code exists", () => {
    expect(pickIso3({ ISO_A3: "-99" })).toBeNull();
    expect(pickIso3({})).toBeNull();
  });
});

describe("joinRegionsToFeatures", () => {
  it("annotates joined features with the simulation prevalence", () => {
    const joined = joinRegionsToFeatures(SAMPLE_FC, REGIONS);
    const usa = joined.features.find((f) => f.properties?.iso3 === "USA");
    expect(usa).toBeDefined();
    expect(usa?.properties).toMatchObject({
      iso3: "USA",
      name: "United States",
      prevalence: 42,
      cumulative: 1_000_000,
      hasData: 1,
    });
  });

  it("zeroes out countries that have no simulation data", () => {
    const joined = joinRegionsToFeatures(SAMPLE_FC, REGIONS);
    const bra = joined.features.find((f) => f.properties?.iso3 === "BRA");
    expect(bra?.properties).toMatchObject({ prevalence: 0, hasData: 0 });
  });

  it("still tags features whose ISO_A3 is the disputed sentinel", () => {
    const joined = joinRegionsToFeatures(SAMPLE_FC, REGIONS);
    const kos = joined.features.find((f) => f.properties?.name === "Kosovo");
    expect(kos?.properties?.iso3).toBe("KOS");
  });

  it("preserves the input feature count", () => {
    const joined = joinRegionsToFeatures(SAMPLE_FC, REGIONS);
    expect(joined.features).toHaveLength(SAMPLE_FC.features.length);
  });
});

describe("loadCountryGeoJSON", () => {
  beforeEach(() => {
    __resetCountryGeoJSONCache();
  });

  it("memoises successful fetches across calls", async () => {
    const fetchImpl = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(SAMPLE_FC),
    } as unknown as Response);
    const a = await loadCountryGeoJSON(fetchImpl as unknown as typeof fetch);
    const b = await loadCountryGeoJSON(fetchImpl as unknown as typeof fetch);
    expect(a).toBe(b);
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });

  it("rethrows non-OK responses and clears the cache so a retry can succeed", async () => {
    const failing = vi.fn().mockResolvedValue({ ok: false, status: 503 } as Response);
    await expect(
      loadCountryGeoJSON(failing as unknown as typeof fetch),
    ).rejects.toThrow(/503/);

    const ok = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(SAMPLE_FC),
    } as unknown as Response);
    const fc = await loadCountryGeoJSON(ok as unknown as typeof fetch);
    expect(fc.features).toHaveLength(SAMPLE_FC.features.length);
  });
});
