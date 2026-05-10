"use client";

import { useState } from "react";
import type { NowcastObservation, NowcastResult } from "@/lib/api";

type Props = {
  loading: boolean;
  result: NowcastResult | null;
  onRun: (obs: NowcastObservation[]) => void;
  onClear: () => void;
  seedIso3: string;
};

const PLACEHOLDER = `# CSV format: day, cumulative_cases
# Example: COVID-19-style early growth in the seed country.
3, 100
7, 350
12, 1500
18, 6500
22, 12000
`;

function parseCSV(text: string): { ok: NowcastObservation[]; errors: string[] } {
  const ok: NowcastObservation[] = [];
  const errors: string[] = [];
  text
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter((l) => l && !l.startsWith("#"))
    .forEach((line, i) => {
      const [a, b] = line.split(",").map((s) => s.trim());
      const day = Number(a);
      const cases = Number(b);
      if (!Number.isFinite(day) || !Number.isFinite(cases) || day < 0 || cases < 0) {
        errors.push(`line ${i + 1}: "${line}" is not "day,cases"`);
        return;
      }
      ok.push({ day, cumulative_cases: cases });
    });
  return { ok, errors };
}

export function NowcastPanel({ loading, result, onRun, onClear, seedIso3 }: Props) {
  const [text, setText] = useState("");
  const [errs, setErrs] = useState<string[]>([]);

  const submit = () => {
    const { ok, errors } = parseCSV(text);
    if (ok.length === 0) {
      setErrs(errors.length ? errors : ["paste at least one (day, cases) row"]);
      return;
    }
    setErrs(errors);
    onRun(ok);
  };

  return (
    <div className="rounded-md border border-ink-600 bg-ink-800">
      <div className="flex items-center justify-between border-b border-ink-600 px-3 py-2">
        <h3 className="text-xs uppercase tracking-wide text-slate-400">
          Nowcast · particle filter
          <span className="ml-1 text-slate-500">(Funk 2018)</span>
        </h3>
        <div className="flex items-center gap-1">
          {result ? (
            <button
              className="rounded px-2 py-1 text-[11px] text-slate-400 hover:text-slate-200"
              onClick={onClear}
            >
              Clear
            </button>
          ) : null}
          <button
            className="rounded bg-accent/20 px-2 py-1 text-[11px] text-accent hover:bg-accent/30 disabled:opacity-50"
            disabled={loading}
            onClick={submit}
          >
            {loading ? "Filtering…" : "Run"}
          </button>
        </div>
      </div>
      <div className="px-3 py-2">
        <p className="text-[10px] text-slate-500 mb-1">
          Paste observed cumulative cases for <span className="text-slate-300">{seedIso3}</span>{" "}
          (one <span className="font-mono">day,cases</span> pair per line). Each particle is
          re-weighted by likelihood of these observations under the SEIR+gravity model.
        </p>
        <textarea
          className="h-20 w-full resize-none rounded border border-ink-600 bg-ink-900 p-2 font-mono text-[11px] text-slate-200 focus:border-accent focus:outline-none"
          placeholder={PLACEHOLDER}
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
        {errs.length > 0 ? (
          <ul className="mt-1 text-[10px] text-amber-400">
            {errs.slice(0, 3).map((e, i) => (
              <li key={i}>{e}</li>
            ))}
          </ul>
        ) : null}
      </div>
      {result ? (
        <div className="border-t border-ink-600 px-3 py-2 text-[11px] text-slate-300">
          <div className="grid grid-cols-2 gap-2">
            <div>
              <div className="text-[10px] text-slate-500">R₀ posterior</div>
              <div className="font-mono">
                {result.posterior_summary.r0_posterior_median.toFixed(2)}{" "}
                <span className="text-slate-500">
                  [{result.posterior_summary.r0_posterior_95[0].toFixed(2)},{" "}
                  {result.posterior_summary.r0_posterior_95[1].toFixed(2)}]
                </span>
              </div>
              <div className="text-[10px] text-slate-500">
                prior median {result.posterior_summary.r0_prior_median.toFixed(2)}
              </div>
            </div>
            <div>
              <div className="text-[10px] text-slate-500">ρ (reporting fraction) posterior</div>
              <div className="font-mono">
                {result.posterior_summary.rho_posterior_median.toFixed(2)}{" "}
                <span className="text-slate-500">
                  [{result.posterior_summary.rho_posterior_95[0].toFixed(2)},{" "}
                  {result.posterior_summary.rho_posterior_95[1].toFixed(2)}]
                </span>
              </div>
              <div className="text-[10px] text-slate-500">
                prior {result.posterior_summary.rho_prior_range[0].toFixed(2)}–
                {result.posterior_summary.rho_prior_range[1].toFixed(2)}
              </div>
            </div>
          </div>
          <div className="mt-1 text-[10px] text-slate-500">
            ESS{" "}
            <span
              className={
                result.posterior_summary.effective_sample_size < 30
                  ? "text-amber-400"
                  : "text-slate-300"
              }
            >
              {result.posterior_summary.effective_sample_size.toFixed(1)}
            </span>{" "}
            / {result.posterior_summary.n_particles}
            {result.posterior_summary.effective_sample_size < 30
              ? " · low ESS: data is far from the prior, treat with caution"
              : ""}
          </div>
        </div>
      ) : null}
    </div>
  );
}
