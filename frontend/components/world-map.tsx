"use client";

import { useEffect, useRef, useState } from "react";
import maplibregl, { type Map as MapLibreMap, type StyleSpecification } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import type { Country, RegionResult, SpreadArc } from "@/lib/api";
import {
  joinRegionsToFeatures,
  loadCountryGeoJSON,
  type CountryFeatureCollection,
} from "@/lib/world-data";

const BASEMAP: StyleSpecification = {
  version: 8,
  glyphs: "https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf",
  sources: {
    carto: {
      type: "raster",
      tiles: [
        "https://a.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png",
        "https://b.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png",
        "https://c.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png",
        "https://d.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png",
      ],
      tileSize: 256,
      attribution: "(c) OpenStreetMap contributors, (c) CARTO",
    },
  },
  layers: [
    { id: "background", type: "background", paint: { "background-color": "#0a0e14" } },
    { id: "carto", type: "raster", source: "carto" },
  ],
};

type Props = {
  countries: Country[];
  regions: RegionResult[];
  arcs: SpreadArc[];
  selectedIso3: string | null;
  startIso3: string;
  onSelect: (iso3: string) => void;
};

const EMPTY_FC: CountryFeatureCollection = {
  type: "FeatureCollection",
  features: [],
};

function buildArcGeoJSON(arcs: SpreadArc[], countries: Country[]) {
  const idx = new Map(countries.map((c) => [c.iso3, c]));
  const features = arcs
    .map((arc) => {
      const a = idx.get(arc.from_iso3);
      const b = idx.get(arc.to_iso3);
      if (!a || !b) return null;
      // Sample a great-circle as a polyline of N points so the line curves on the map.
      const N = 48;
      const φ1 = (a.lat * Math.PI) / 180;
      const λ1 = (a.lng * Math.PI) / 180;
      const φ2 = (b.lat * Math.PI) / 180;
      const λ2 = (b.lng * Math.PI) / 180;
      const d = 2 * Math.asin(
        Math.sqrt(
          Math.sin((φ2 - φ1) / 2) ** 2 +
            Math.cos(φ1) * Math.cos(φ2) * Math.sin((λ2 - λ1) / 2) ** 2,
        ),
      );
      const coords: Array<[number, number]> = [];
      for (let i = 0; i <= N; i++) {
        const f = i / N;
        if (d === 0) {
          coords.push([a.lng, a.lat]);
          continue;
        }
        const A = Math.sin((1 - f) * d) / Math.sin(d);
        const B = Math.sin(f * d) / Math.sin(d);
        const x = A * Math.cos(φ1) * Math.cos(λ1) + B * Math.cos(φ2) * Math.cos(λ2);
        const y = A * Math.cos(φ1) * Math.sin(λ1) + B * Math.cos(φ2) * Math.sin(λ2);
        const z = A * Math.sin(φ1) + B * Math.sin(φ2);
        const φ = Math.atan2(z, Math.sqrt(x * x + y * y));
        const λ = Math.atan2(y, x);
        coords.push([(λ * 180) / Math.PI, (φ * 180) / Math.PI]);
      }
      return {
        type: "Feature" as const,
        geometry: { type: "LineString" as const, coordinates: coords },
        properties: {
          weight: arc.weight_normalized,
          from: arc.from_iso3,
          to: arc.to_iso3,
        },
      };
    })
    .filter((f): f is NonNullable<typeof f> => Boolean(f));
  return { type: "FeatureCollection" as const, features };
}

export function WorldMap({ countries, regions, arcs, selectedIso3, startIso3, onSelect }: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const onSelectRef = useRef(onSelect);
  const [worldGeo, setWorldGeo] = useState<CountryFeatureCollection | null>(null);

  // Keep the click handler reference current without rebinding the listener.
  useEffect(() => {
    onSelectRef.current = onSelect;
  }, [onSelect]);

  // Lazily fetch Natural Earth admin-0 country polygons once per session.
  useEffect(() => {
    let cancelled = false;
    loadCountryGeoJSON()
      .then((fc) => {
        if (!cancelled) setWorldGeo(fc);
      })
      .catch((err) => {
        // Non-fatal: the map still renders the basemap and arcs/markers.
        // eslint-disable-next-line no-console
        console.error("Failed to load Natural Earth GeoJSON", err);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    // Defer init by one frame so the container has resolved its CSS dimensions
    const frame = requestAnimationFrame(() => {
      if (!containerRef.current) return;
      const map = new maplibregl.Map({
        container: containerRef.current,
        style: BASEMAP,
        center: [10, 20],
        zoom: 1.4,
        attributionControl: { compact: true },
      });
      map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
      // Suppress tile fetch errors from bubbling to Next.js dev overlay,
      // but keep a dev-mode breadcrumb so a broken basemap is debuggable.
      map.on("error", (e) => {
        if (process.env.NODE_ENV !== "production") console.warn("[maplibre]", e);
      });
      // Force MapLibre to recalculate its canvas size after the style loads
      map.once("load", () => map.resize());
      mapRef.current = map;
    });
    return () => {
      cancelAnimationFrame(frame);
      mapRef.current?.remove();
      mapRef.current = null;
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    const apply = () => {
      // --- Country choropleth -------------------------------------------------
      const joined = worldGeo ? joinRegionsToFeatures(worldGeo, regions) : EMPTY_FC;

      const countriesSource = map.getSource("countries") as maplibregl.GeoJSONSource | undefined;
      if (countriesSource) {
        countriesSource.setData(joined);
      } else {
        map.addSource("countries", { type: "geojson", data: joined });

        // Sequential ramp keyed on prevalence per 100k, with a muted "no data"
        // colour for any country we couldn't join. The ramp matches the
        // original circle-colour stops so the legend stays consistent.
        map.addLayer({
          id: "countries-fill",
          type: "fill",
          source: "countries",
          paint: {
            "fill-color": [
              "case",
              ["==", ["get", "hasData"], 0],
              "#1a2230",
              [
                "interpolate",
                ["linear"],
                ["get", "prevalence"],
                0,
                "#28384f",
                1,
                "#3c82b4",
                10,
                "#50c8c8",
                50,
                "#f0c850",
                200,
                "#f06446",
                1000,
                "#dc3246",
              ],
            ],
            "fill-opacity": [
              "case",
              ["==", ["get", "hasData"], 0],
              0.25,
              0.7,
            ],
          },
        });

        map.addLayer({
          id: "countries-line",
          type: "line",
          source: "countries",
          paint: {
            "line-color": [
              "case",
              ["==", ["get", "iso3"], ["literal", startIso3]],
              "#7cf2c8",
              ["==", ["get", "iso3"], ["literal", selectedIso3 ?? ""]],
              "#ffffff",
              "rgba(255, 255, 255, 0.18)",
            ],
            "line-width": [
              "case",
              ["==", ["get", "iso3"], ["literal", startIso3]],
              2.4,
              ["==", ["get", "iso3"], ["literal", selectedIso3 ?? ""]],
              2,
              0.4,
            ],
          },
        });

        map.on("click", "countries-fill", (ev) => {
          const f = ev.features?.[0];
          if (!f) return;
          const iso3 = (f.properties?.iso3 as string | undefined) ?? "";
          if (iso3) onSelectRef.current(iso3);
        });
        map.on(
          "mouseenter",
          "countries-fill",
          () => (map.getCanvas().style.cursor = "pointer"),
        );
        map.on(
          "mouseleave",
          "countries-fill",
          () => (map.getCanvas().style.cursor = ""),
        );
      }

      // Refresh the highlight expression when the selection or origin changes.
      if (map.getLayer("countries-line")) {
        map.setPaintProperty("countries-line", "line-color", [
          "case",
          ["==", ["get", "iso3"], ["literal", startIso3]],
          "#7cf2c8",
          ["==", ["get", "iso3"], ["literal", selectedIso3 ?? ""]],
          "#ffffff",
          "rgba(255, 255, 255, 0.18)",
        ]);
        map.setPaintProperty("countries-line", "line-width", [
          "case",
          ["==", ["get", "iso3"], ["literal", startIso3]],
          2.4,
          ["==", ["get", "iso3"], ["literal", selectedIso3 ?? ""]],
          2,
          0.4,
        ]);
      }

      // --- Spread arcs (unchanged behaviour) ---------------------------------
      const arcData = buildArcGeoJSON(arcs, countries);
      const arcSource = map.getSource("arcs") as maplibregl.GeoJSONSource | undefined;
      if (arcSource) {
        arcSource.setData(arcData);
      } else {
        map.addSource("arcs", { type: "geojson", data: arcData });
        map.addLayer({
          id: "arcs-line",
          type: "line",
          source: "arcs",
          layout: { "line-cap": "round", "line-join": "round" },
          paint: {
            "line-color": "#7cf2c8",
            "line-width": ["interpolate", ["linear"], ["get", "weight"], 0, 0.4, 1, 2.5],
            "line-opacity": ["interpolate", ["linear"], ["get", "weight"], 0, 0.3, 1, 0.9],
          },
        });
      }
    };

    if (map.loaded()) apply();
    else map.once("load", apply);
  }, [countries, regions, arcs, startIso3, selectedIso3, worldGeo]);

  return <div ref={containerRef} className="absolute inset-0" style={{ width: "100%", height: "100%" }} />;
}
