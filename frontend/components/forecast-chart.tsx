"use client";

import {
  Area,
  AreaChart,
  CartesianGrid,
  Line,
  ReferenceDot,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { ModelVariant, NowcastObservation, Quantiles } from "@/lib/api";

type Props = {
  title: string;
  quantiles: Quantiles;
  predictedArrivalDay?: number | null;
  effectiveDistance?: number | null;
  variantsTerminalP50?: number[];
  variantMeta?: ModelVariant[];
  posteriorQuantiles?: Quantiles | null;
  observations?: NowcastObservation[] | null;
};

const VARIANT_COLORS = ["#fbbf24", "#7cf2c8", "#a78bfa", "#f472b6"];

export function ForecastChart({
  title,
  quantiles,
  predictedArrivalDay,
  effectiveDistance,
  variantsTerminalP50,
  variantMeta,
  posteriorQuantiles,
  observations,
}: Props) {
  const series = quantiles.p50.map((_, i) => ({
    day: i,
    band95_lo: quantiles.p2_5[i],
    band95_hi: quantiles.p97_5[i],
    band80_lo: quantiles.p25[i],
    band80_hi: quantiles.p75[i],
    median: quantiles.p50[i],
    posterior_median:
      posteriorQuantiles && i < posteriorQuantiles.p50.length ? posteriorQuantiles.p50[i] : null,
  }));

  const display = series.map((row) => ({
    ...row,
    band95_floor: row.band95_lo,
    band95_height: Math.max(row.band95_hi - row.band95_lo, 0),
    band80_floor: row.band80_lo,
    band80_height: Math.max(row.band80_hi - row.band80_lo, 0),
  }));

  const showArrival =
    typeof predictedArrivalDay === "number" &&
    predictedArrivalDay > 0 &&
    predictedArrivalDay < display.length;

  const horizon = display.length - 1;
  const showVariants =
    Array.isArray(variantsTerminalP50) &&
    Array.isArray(variantMeta) &&
    variantsTerminalP50.length === variantMeta.length &&
    variantsTerminalP50.length > 0;

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
            {posteriorQuantiles ? (
              <Line
                type="monotone"
                dataKey="posterior_median"
                stroke="#fb923c"
                strokeWidth={1.6}
                strokeDasharray="4 3"
                dot={false}
              />
            ) : null}
            {observations
              ? observations.map((obs, i) => (
                  <ReferenceDot
                    key={`obs-${i}`}
                    x={obs.day}
                    y={obs.cumulative_cases}
                    r={3.5}
                    fill="#fb923c"
                    stroke="#0f141c"
                    strokeWidth={1}
                  />
                ))
              : null}
            {showArrival ? (
              <ReferenceLine
                x={predictedArrivalDay}
                stroke="#fbbf24"
                strokeDasharray="3 3"
                label={{
                  value: `arrival ~day ${predictedArrivalDay}`,
                  position: "top",
                  fill: "#fbbf24",
                  fontSize: 10,
                }}
              />
            ) : null}
            {showVariants
              ? variantsTerminalP50!.map((v, i) => (
                  <ReferenceDot
                    key={i}
                    x={horizon}
                    y={v}
                    r={3}
                    fill={VARIANT_COLORS[i % VARIANT_COLORS.length]}
                    stroke="#0f141c"
                    strokeWidth={1}
                  />
                ))
              : null}
          </AreaChart>
        </ResponsiveContainer>
      </div>
      {showVariants ? (
        <div className="mt-1 flex flex-wrap gap-2 text-[10px] text-slate-500">
          {variantMeta!.map((m, i) => (
            <span
              key={m.id}
              className="inline-flex items-center gap-1"
              title={`${m.label} — ${m.citation}`}
            >
              <span
                className="inline-block h-2 w-2 rounded-full"
                style={{ background: VARIANT_COLORS[i % VARIANT_COLORS.length] }}
              />
              <span className="text-slate-400">{m.label}</span>
              <span className="font-mono text-slate-300">
                {Math.round(variantsTerminalP50![i]).toLocaleString()}
              </span>
            </span>
          ))}
          <span className="text-slate-600">
            · ensemble of 4 models · Reich 2019 PNAS
          </span>
        </div>
      ) : null}
      {posteriorQuantiles ? (
        <div className="mt-1 flex items-center gap-2 text-[10px]">
          <span
            className="inline-block h-0.5 w-4"
            style={{
              background:
                "repeating-linear-gradient(to right, #fb923c 0 4px, transparent 4px 7px)",
            }}
          />
          <span className="text-orange-300">posterior median</span>
          <span className="text-slate-500">· data-conditioned (Funk 2018)</span>
        </div>
      ) : null}
      {effectiveDistance != null ? (
        <div className="mt-1 flex items-center gap-2 text-[10px] text-slate-500">
          <span className="rounded bg-ink-700 px-1.5 py-0.5 font-mono text-slate-300">
            d_eff = {effectiveDistance.toFixed(2)}
          </span>
          <span>
            effective distance on air-route graph (Brockmann &amp; Helbing 2013); arrival day is the
            first day median active prevalence crosses 1/100k.
          </span>
        </div>
      ) : null}
    </div>
  );
}
