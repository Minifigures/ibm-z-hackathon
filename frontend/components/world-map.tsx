"use client";

import { useEffect, useRef } from "react";
import maplibregl, { type Map as MapLibreMap, type StyleSpecification } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import type { Country, RegionResult, SpreadArc } from "@/lib/api";

const BASEMAP: StyleSpecification = {
  version: 8,
  glyphs: "https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf",
  sources: {
    carto: {
      type: "raster",
      // Stadia Maps free tier works without a key on localhost; deployments
      // need ?api_key=... (see README "Production deploy" note).
      // Use 1x .png so the tileSize: 256 declaration matches the actual tile
      // pixel dimensions — pairing @2x (512px tiles) with tileSize: 256 makes
      // MapLibre treat 512px tiles as 256px and inflate label sizes.
      tiles: [
        "https://tiles.stadiamaps.com/tiles/alidade_smooth_dark/{z}/{x}/{y}.png",
      ],
      tileSize: 256,
      attribution: "(c) Stadia Maps, (c) OpenMapTiles, (c) OpenStreetMap contributors",
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
  /** When non-null, hover events do not override the selection. */
  lockedIso3?: string | null;
  startIso3: string;
  /** Cursor entered a country — preview only; parent decides whether to honor it. */
  onHover: (iso3: string) => void;
  /** Click on a country (iso3) or empty ocean (null). Parent typically locks/unlocks. */
  onPick: (iso3: string | null) => void;
};

function colorForPrevalence(p: number): string {
  // Stops chosen so that p=0 stays muted while p>=200/100k saturates.
  const stops: Array<[number, [number, number, number]]> = [
    [0, [40, 60, 80]],
    [1, [60, 130, 180]],
    [10, [80, 200, 200]],
    [50, [240, 200, 80]],
    [200, [240, 100, 70]],
    [1000, [220, 50, 70]],
  ];
  const v = Math.max(0, p);
  for (let i = 1; i < stops.length; i++) {
    const [lo, c0] = stops[i - 1];
    const [hi, c1] = stops[i];
    if (v <= hi) {
      const t = (v - lo) / Math.max(hi - lo, 1e-6);
      const r = c0[0] + (c1[0] - c0[0]) * t;
      const g = c0[1] + (c1[1] - c0[1]) * t;
      const b = c0[2] + (c1[2] - c0[2]) * t;
      return `rgb(${r.toFixed(0)}, ${g.toFixed(0)}, ${b.toFixed(0)})`;
    }
  }
  return "rgb(220, 50, 70)";
}

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

export function WorldMap({
  countries,
  regions,
  arcs,
  selectedIso3,
  lockedIso3,
  startIso3,
  onHover,
  onPick,
}: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const onHoverRef = useRef(onHover);
  const onPickRef = useRef(onPick);
  const lastHoveredRef = useRef<string | null>(null);
  // Tracks the last point where we ran queryRenderedFeatures. Cursor jitters
  // of a few pixels short-circuit before doing any picking work. With 71
  // features and a 14px hit radius the query itself is cheap, but skipping it
  // entirely keeps mousemove hot-path under a microsecond when the cursor is
  // effectively still.
  const lastQueryPointRef = useRef<{ x: number; y: number } | null>(null);
  const HOVER_QUERY_THRESHOLD_PX = 3;
  // Mirror parent lock state into a ref so the imperative MapLibre handlers
  // always see the latest value without needing to be re-registered.
  const lockedRef = useRef<string | null>(lockedIso3 ?? null);
  useEffect(() => {
    onHoverRef.current = onHover;
    onPickRef.current = onPick;
  }, [onHover, onPick]);
  useEffect(() => {
    lockedRef.current = lockedIso3 ?? null;
  }, [lockedIso3]);

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
      const regionByIso3 = new Map(regions.map((r) => [r.iso3, r]));
      const features = countries.map((c) => {
        const r = regionByIso3.get(c.iso3);
        const prevalence = r?.prevalence_p50_per_100k ?? 0;
        const cumulative = r?.cumulative_p50_final ?? 0;
        return {
          type: "Feature" as const,
          id: c.iso3,
          geometry: { type: "Point" as const, coordinates: [c.lng, c.lat] },
          properties: {
            iso3: c.iso3,
            name: c.name,
            population: c.population,
            prevalence,
            cumulative,
            color: colorForPrevalence(prevalence),
            radius: 6 + Math.min(28, Math.sqrt(Math.max(prevalence, 0)) * 2.2),
            isStart: c.iso3 === startIso3 ? 1 : 0,
          },
        };
      });
      const fc = { type: "FeatureCollection" as const, features };

      const existing = map.getSource("regions") as maplibregl.GeoJSONSource | undefined;
      if (existing) {
        existing.setData(fc);
      } else {
        map.addSource("regions", { type: "geojson", data: fc, promoteId: "iso3" });
        map.addLayer({
          id: "regions-glow",
          type: "circle",
          source: "regions",
          paint: {
            "circle-radius": ["get", "radius"],
            "circle-color": ["get", "color"],
            "circle-opacity": [
              "interpolate", ["linear"], ["get", "prevalence"],
              0, 0,
              1, 0.12,
              50, 0.22,
            ],
            "circle-blur": 0.4,
          },
        });
        map.addLayer({
          id: "regions-fill",
          type: "circle",
          source: "regions",
          paint: {
            "circle-radius": [
              "case",
              ["==", ["get", "isStart"], 1], 8,
              ["interpolate", ["linear"], ["get", "prevalence"],
                0, 5,
                1, 7,
                10, 10,
                50, 13,
                200, 16,
              ],
            ],
            "circle-color": ["get", "color"],
            "circle-opacity": [
              "case",
              ["==", ["get", "isStart"], 1], 0.95,
              ["interpolate", ["linear"], ["get", "prevalence"],
                0, 0.7,
                1, 0.85,
                10, 0.95,
              ],
            ],
            "circle-stroke-width": [
              "case",
              ["==", ["get", "isStart"], 1], 2.5,
              ["boolean", ["feature-state", "selected"], false], 2,
              0.5,
            ],
            "circle-stroke-color": [
              "case",
              ["==", ["get", "isStart"], 1], "#7cf2c8",
              ["boolean", ["feature-state", "selected"], false], "#ffffff",
              "rgba(255, 255, 255, 0.4)",
            ],
          },
        });
        // Invisible larger hit target for reliable hover/click detection.
        map.addLayer({
          id: "regions-hit",
          type: "circle",
          source: "regions",
          paint: {
            "circle-radius": 14,
            "circle-color": "#000",
            "circle-opacity": 0,
          },
        });

        // Click anywhere on the map. The parent owns the lock state — we just
        // tell it what was picked (iso3 or null for empty ocean).
        map.on("click", (ev) => {
          const feats = map.queryRenderedFeatures(ev.point, { layers: ["regions-hit"] });
          if (feats.length) {
            const iso3 = feats[0].properties?.iso3 as string;
            onPickRef.current(iso3);
          } else {
            onPickRef.current(null);
          }
        });
        map.on("mousemove", (ev) => {
          // Short-circuit when the cursor barely moved — avoids ~60 picks/sec
          // when the user is just resting their hand on the trackpad.
          const prev = lastQueryPointRef.current;
          if (
            prev &&
            Math.abs(ev.point.x - prev.x) < HOVER_QUERY_THRESHOLD_PX &&
            Math.abs(ev.point.y - prev.y) < HOVER_QUERY_THRESHOLD_PX
          ) {
            return;
          }
          lastQueryPointRef.current = { x: ev.point.x, y: ev.point.y };
          const feats = map.queryRenderedFeatures(ev.point, { layers: ["regions-hit"] });
          map.getCanvas().style.cursor = feats.length ? "pointer" : "";
          // Local short-circuit: skip hover events when the parent has locked
          // selection. Parent also enforces this, but skipping here avoids
          // a needless render trip per mouse pixel.
          if (lockedRef.current) return;
          if (!feats.length) {
            lastHoveredRef.current = null;
            return;
          }
          const iso3 = feats[0].properties?.iso3 as string;
          if (iso3 && iso3 !== lastHoveredRef.current) {
            lastHoveredRef.current = iso3;
            onHoverRef.current(iso3);
          }
        });
      }

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
  }, [countries, regions, arcs, startIso3]);

  // Lightweight selection effect: just toggles feature-state, no GeoJSON rebuild.
  const prevSelectedRef = useRef<string | null>(null);
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const apply = () => {
      if (!map.getSource("regions")) return;
      const prev = prevSelectedRef.current;
      if (prev && prev !== selectedIso3) {
        map.setFeatureState({ source: "regions", id: prev }, { selected: false });
      }
      if (selectedIso3) {
        map.setFeatureState({ source: "regions", id: selectedIso3 }, { selected: true });
      }
      prevSelectedRef.current = selectedIso3;
    };
    if (map.loaded()) apply();
    else map.once("load", apply);
  }, [selectedIso3]);

  return <div ref={containerRef} className="absolute inset-0" style={{ width: "100%", height: "100%" }} />;
}
