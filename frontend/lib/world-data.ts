import type { RegionResult } from "@/lib/api";

/**
 * Natural Earth admin-0 countries at 1:110m. Roughly 250 KB, suitable for a
 * world overview. Loaded at runtime so we don't bloat the JS bundle.
 */
export const NATURAL_EARTH_URL =
  "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_110m_admin_0_countries.geojson";

/**
 * Subset of the Natural Earth admin-0 properties that we rely on. Natural
 * Earth uses several different ISO3-style fields and not all of them are
 * populated for every feature (disputed territories often have `-99`).
 */
export type NaturalEarthProps = {
  ISO_A3?: string;
  ADM0_A3?: string;
  ADM0_A3_US?: string;
  SOV_A3?: string;
  ADMIN?: string;
  NAME?: string;
  NAME_LONG?: string;
};

export type CountryFeature = GeoJSON.Feature<GeoJSON.Geometry, NaturalEarthProps>;
export type CountryFeatureCollection = GeoJSON.FeatureCollection<
  GeoJSON.Geometry,
  NaturalEarthProps
>;

export type JoinedProps = NaturalEarthProps & {
  iso3: string;
  name: string;
  prevalence: number;
  cumulative: number;
  hasData: 0 | 1;
};

export type JoinedFeatureCollection = GeoJSON.FeatureCollection<GeoJSON.Geometry, JoinedProps>;

/**
 * Pick the best ISO3 code from a Natural Earth feature. Some features carry
 * `-99` as a sentinel for disputed/unrecognized states; in that case we fall
 * back to the next-most-specific code so the country still gets joined to a
 * region result if one exists.
 */
export function pickIso3(props: NaturalEarthProps): string | null {
  const candidates = [props.ISO_A3, props.ADM0_A3, props.ADM0_A3_US, props.SOV_A3];
  for (const c of candidates) {
    if (typeof c === "string" && c.length === 3 && c !== "-99") return c.toUpperCase();
  }
  return null;
}

export function pickName(props: NaturalEarthProps): string {
  return props.ADMIN ?? props.NAME_LONG ?? props.NAME ?? "Unknown";
}

/**
 * Annotate every feature with a stable `iso3` / `name` property and the
 * matching simulation metric so MapLibre data-driven styling can read it
 * directly via `["get", "prevalence"]` etc. Features that don't have a join
 * partner keep `prevalence = 0` and `hasData = 0` so they render in the
 * "no data" colour.
 */
export function joinRegionsToFeatures(
  fc: CountryFeatureCollection,
  regions: RegionResult[],
): JoinedFeatureCollection {
  const byIso3 = new Map(regions.map((r) => [r.iso3, r]));
  const features: JoinedFeatureCollection["features"] = fc.features.map((feature) => {
    const iso3 = pickIso3(feature.properties ?? {});
    const region = iso3 ? byIso3.get(iso3) : undefined;
    return {
      ...feature,
      properties: {
        ...(feature.properties ?? {}),
        iso3: iso3 ?? "",
        name: pickName(feature.properties ?? {}),
        prevalence: region?.prevalence_p50_per_100k ?? 0,
        cumulative: region?.cumulative_p50_final ?? 0,
        hasData: region ? 1 : 0,
      },
    };
  });
  return { ...fc, features };
}

/**
 * Lazily fetch the Natural Earth GeoJSON. The result is memoised so multiple
 * simulation updates don't re-download it. Failures bubble up so the caller
 * can degrade gracefully.
 */
let geojsonPromise: Promise<CountryFeatureCollection> | null = null;
export function loadCountryGeoJSON(
  fetchImpl: typeof fetch = fetch,
): Promise<CountryFeatureCollection> {
  if (!geojsonPromise) {
    geojsonPromise = fetchImpl(NATURAL_EARTH_URL)
      .then((res) => {
        if (!res.ok) throw new Error(`Natural Earth fetch failed: ${res.status}`);
        return res.json() as Promise<CountryFeatureCollection>;
      })
      .catch((err) => {
        // Reset so a later retry can succeed (e.g. transient network blip).
        geojsonPromise = null;
        throw err;
      });
  }
  return geojsonPromise;
}

/** Test seam: drop the cached promise so unit tests start from scratch. */
export function __resetCountryGeoJSONCache(): void {
  geojsonPromise = null;
}
