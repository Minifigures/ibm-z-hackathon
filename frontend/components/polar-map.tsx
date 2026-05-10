"use client";

import { useMemo } from "react";
import type { Country, RegionResult, SpreadArc } from "@/lib/api";

type Props = {
  countries: Country[];
  regions: RegionResult[];
  arcs: SpreadArc[];
  startIso3: string;
  selectedIso3: string | null;
  onSelect: (iso3: string) => void;
};

// Initial bearing from (lat1, lng1) to (lat2, lng2), in radians [-pi, pi].
// Used to place each country at a stable angle around the polar map. We use
// the great-circle bearing rather than raw longitude so that countries
// near the poles or on the antipode of the seed don't pile up at lng = ±180.
function bearing(lat1: number, lng1: number, lat2: number, lng2: number): number {
  const phi1 = (lat1 * Math.PI) / 180;
  const phi2 = (lat2 * Math.PI) / 180;
  const dl = ((lng2 - lng1) * Math.PI) / 180;
  const y = Math.sin(dl) * Math.cos(phi2);
  const x =
    Math.cos(phi1) * Math.sin(phi2) -
    Math.sin(phi1) * Math.cos(phi2) * Math.cos(dl);
  return Math.atan2(y, x);
}

function prevalenceColor(prev: number): string {
  // Same ramp stops as the choropleth in world-map.tsx.
  if (prev >= 1000) return "#dc3246";
  if (prev >= 200) return "#f06446";
  if (prev >= 50) return "#f0c850";
  if (prev >= 10) return "#50c8c8";
  if (prev >= 1) return "#3c82b4";
  if (prev > 0) return "#28384f";
  return "#1a2230";
}

export function PolarMap({
  countries,
  regions,
  arcs,
  startIso3,
  selectedIso3,
  onSelect,
}: Props) {
  const W = 800;
  const H = 800;
  const cx = W / 2;
  const cy = H / 2;

  const seed = countries.find((c) => c.iso3 === startIso3);
  const regionByIso = useMemo(() => new Map(regions.map((r) => [r.iso3, r])), [regions]);

  const points = useMemo(() => {
    if (!seed) return { items: [], maxDeff: 0 };
    let maxDeff = 0;
    const items = countries
      .map((c) => {
        const r = regionByIso.get(c.iso3);
        const d = r?.effective_distance_from_seed ?? null;
        if (d == null || !Number.isFinite(d)) return null;
        if (d > maxDeff) maxDeff = d;
        return { country: c, region: r, d };
      })
      .filter((x): x is { country: Country; region: RegionResult; d: number } => Boolean(x));
    return { items, maxDeff };
  }, [countries, regionByIso, seed]);

  const radius = (d: number) => {
    if (points.maxDeff <= 0) return 0;
    const norm = d / points.maxDeff;
    // Reserve 8% of half-width for the seed disk + label margin.
    return 0.08 * Math.min(W, H) + norm * 0.42 * Math.min(W, H);
  };

  if (!seed) {
    return (
      <div className="flex h-full items-center justify-center text-xs text-slate-500">
        Polar view requires a valid origin country.
      </div>
    );
  }

  // Concentric reference rings every 25% of max effective distance.
  const ringFractions = [0.25, 0.5, 0.75, 1.0];

  return (
    <div className="relative h-full w-full overflow-hidden bg-ink-900">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="h-full w-full"
        preserveAspectRatio="xMidYMid meet"
      >
        <defs>
          <radialGradient id="bg-rays" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="#13202b" stopOpacity={0.7} />
            <stop offset="100%" stopColor="#0a0e14" stopOpacity={1} />
          </radialGradient>
        </defs>
        <rect width={W} height={H} fill="url(#bg-rays)" />

        {/* Reference rings */}
        {ringFractions.map((f) => {
          const dVal = points.maxDeff * f;
          const r = radius(dVal);
          return (
            <g key={f}>
              <circle
                cx={cx}
                cy={cy}
                r={r}
                fill="none"
                stroke="#1f2632"
                strokeDasharray="2 4"
                strokeWidth={1}
              />
              <text
                x={cx + r + 4}
                y={cy - 2}
                fill="#475569"
                fontSize={9}
                fontFamily="monospace"
              >
                d_eff = {dVal.toFixed(1)}
              </text>
            </g>
          );
        })}

        {/* Spread arcs: straight lines from seed disk outward to top OD destinations */}
        {arcs.map((arc) => {
          const target = points.items.find((p) => p.country.iso3 === arc.to_iso3);
          if (!target) return null;
          const θ = bearing(seed.lat, seed.lng, target.country.lat, target.country.lng);
          const r = radius(target.d);
          const x = cx + r * Math.sin(θ);
          const y = cy - r * Math.cos(θ);
          return (
            <line
              key={`${arc.from_iso3}-${arc.to_iso3}`}
              x1={cx}
              y1={cy}
              x2={x}
              y2={y}
              stroke="#7cf2c8"
              strokeOpacity={0.15 + 0.7 * arc.weight_normalized}
              strokeWidth={0.6 + 1.8 * arc.weight_normalized}
              strokeLinecap="round"
            />
          );
        })}

        {/* Region dots */}
        {points.items.map(({ country, region, d }) => {
          const θ = bearing(seed.lat, seed.lng, country.lat, country.lng);
          const r = radius(d);
          const x = cx + r * Math.sin(θ);
          const y = cy - r * Math.cos(θ);
          const isSelected = selectedIso3 === country.iso3;
          const dotColor = prevalenceColor(region.prevalence_p50_per_100k);
          const radiusPx = 4 + Math.log10(Math.max(country.population, 1)) - 5;
          return (
            <g
              key={country.iso3}
              onClick={() => onSelect(country.iso3)}
              style={{ cursor: "pointer" }}
            >
              <circle
                cx={x}
                cy={y}
                r={Math.max(radiusPx, 3)}
                fill={dotColor}
                stroke={isSelected ? "#ffffff" : "rgba(255, 255, 255, 0.18)"}
                strokeWidth={isSelected ? 1.6 : 0.5}
                opacity={0.92}
              />
              {isSelected || country.iso3 === startIso3 || (region.predicted_arrival_day !== null && region.predicted_arrival_day < 14) ? (
                <text
                  x={x + 6}
                  y={y + 3}
                  fill={country.iso3 === startIso3 ? "#7cf2c8" : "#cbd5e1"}
                  fontSize={9}
                  fontFamily="monospace"
                >
                  {country.iso3}
                </text>
              ) : null}
            </g>
          );
        })}

        {/* Seed marker on top */}
        <g>
          <circle cx={cx} cy={cy} r={7} fill="#7cf2c8" stroke="#0a0e14" strokeWidth={1.5} />
          <text
            x={cx + 10}
            y={cy + 3}
            fill="#7cf2c8"
            fontSize={11}
            fontFamily="monospace"
            fontWeight={600}
          >
            {seed.iso3}
          </text>
        </g>

        {/* Caption */}
        <text x={12} y={H - 14} fill="#475569" fontSize={10}>
          Effective-distance polar projection · radius = d_eff(seed → country) on
          air-route graph · angle = great-circle bearing from seed · Brockmann
          &amp; Helbing 2013, Science.
        </text>
      </svg>
    </div>
  );
}
