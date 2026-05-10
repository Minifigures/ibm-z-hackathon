"use client";

import {
  Area,
  AreaChart,
  CartesianGrid,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { Quantiles } from "@/lib/api";

type Props = {
  title: string;
  quantiles: Quantiles;
};

export function ForecastChart({ title, quantiles }: Props) {
  const series = quantiles.p50.map((_, i) => ({
    day: i,
    band95_lo: quantiles.p2_5[i],
    band95_hi: quantiles.p97_5[i],
    band80_lo: quantiles.p25[i],
    band80_hi: quantiles.p75[i],
    median: quantiles.p50[i],
  }));

  // Recharts area takes a single value, so we use stacked areas keyed off the
  // delta between bounds. Render the wide band first, then the narrow band.
  const display = series.map((row) => ({
    ...row,
    band95_floor: row.band95_lo,
    band95_height: Math.max(row.band95_hi - row.band95_lo, 0),
    band80_floor: row.band80_lo,
    band80_height: Math.max(row.band80_hi - row.band80_lo, 0),
  }));

  return (
    <div className="rounded-md border border-ink-600 bg-ink-800 p-3">
      <div className="flex items-baseline justify-between">
        <h3 className="text-xs uppercase tracking-wide text-slate-400">{title}</h3>
        <span className="text-[10px] text-slate-500">95% / 50% intervals + median</span>
      </div>
      <div className="h-44 mt-2">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={display} margin={{ top: 4, right: 6, bottom: 0, left: 0 }}>
            <CartesianGrid strokeDasharray="2 4" stroke="#1f2632" vertical={false} />
            <XAxis dataKey="day" stroke="#475569" tick={{ fontSize: 10 }} />
            <YAxis stroke="#475569" tick={{ fontSize: 10 }} width={40} />
            <Tooltip
              contentStyle={{
                background: "#0f141c",
                border: "1px solid #1f2632",
                borderRadius: 6,
                fontSize: 11,
              }}
              labelFormatter={(d) => `Day ${d}`}
              formatter={(v: number, k: string) => {
                if (k === "median") return [Math.round(v).toLocaleString(), "median"];
                return null;
              }}
            />
            <Area type="monotone" dataKey="band95_floor" stackId="95" stroke="none" fill="transparent" />
            <Area
              type="monotone"
              dataKey="band95_height"
              stackId="95"
              stroke="none"
              fill="#7cf2c8"
              fillOpacity={0.12}
            />
            <Area type="monotone" dataKey="band80_floor" stackId="80" stroke="none" fill="transparent" />
            <Area
              type="monotone"
              dataKey="band80_height"
              stackId="80"
              stroke="none"
              fill="#7cf2c8"
              fillOpacity={0.28}
            />
            <Line type="monotone" dataKey="median" stroke="#7cf2c8" strokeWidth={1.6} dot={false} />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
