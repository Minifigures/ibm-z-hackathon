"use client";

import type { HubRow } from "@/lib/api";

type Props = {
  title: string;
  rows: HubRow[];
  valueKey: "expected_cases" | "score";
  onSelect?: (iso3: string) => void;
};

export function HubList({ title, rows, valueKey, onSelect }: Props) {
  const max = Math.max(...rows.map((r) => Number(r[valueKey] ?? 0)), 1);

  return (
    <div className="rounded-md border border-ink-600 bg-ink-800">
      <div className="px-3 py-2 border-b border-ink-600">
        <h3 className="text-xs uppercase tracking-wide text-slate-400">{title}</h3>
      </div>
      <ul>
        {rows.map((row, i) => {
          const v = Number(row[valueKey] ?? 0);
          return (
            <li
              key={row.iso3}
              className="flex items-center gap-2 px-3 py-1.5 text-xs hover:bg-ink-700 cursor-pointer"
              onClick={() => onSelect?.(row.iso3)}
            >
              <span className="text-slate-500 w-4 tabular-nums">{i + 1}</span>
              <span className="font-mono text-[11px] text-slate-400 w-9">{row.iso3}</span>
              <span className="flex-1 truncate">{row.name}</span>
              <div className="flex items-center gap-2 w-32">
                <div className="flex-1 h-1.5 rounded-full bg-ink-600 overflow-hidden">
                  <div
                    className="h-full bg-accent"
                    style={{ width: `${(v / max) * 100}%` }}
                  />
                </div>
                <span className="font-mono tabular-nums text-slate-300 w-12 text-right">
                  {valueKey === "expected_cases"
                    ? Math.round(v).toLocaleString()
                    : v.toExponential(1)}
                </span>
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
