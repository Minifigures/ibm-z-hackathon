"use client";

import { useEffect, useState } from "react";

type Props = {
  onLaunch: () => void;
};

export function Landing({ onLaunch }: Props) {
  const [leaving, setLeaving] = useState(false);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    const t = setTimeout(() => setMounted(true), 30);
    return () => clearTimeout(t);
  }, []);

  const launch = () => {
    setLeaving(true);
    setTimeout(onLaunch, 480);
  };

  return (
    <div
      className={`fixed inset-0 z-50 overflow-hidden bg-ink-950 text-slate-100 transition-opacity duration-500 ${
        leaving ? "pointer-events-none opacity-0" : "opacity-100"
      }`}
    >
      <div className="absolute inset-0">
        <div
          className="absolute inset-0"
          style={{
            background:
              "radial-gradient(60% 50% at 50% 35%, rgba(124, 242, 200, 0.18) 0%, rgba(15, 20, 28, 0) 70%), radial-gradient(40% 30% at 80% 80%, rgba(251, 146, 60, 0.10) 0%, rgba(15, 20, 28, 0) 70%)",
          }}
        />
        <div
          className="absolute inset-0 opacity-[0.08]"
          style={{
            backgroundImage:
              "radial-gradient(circle at 1px 1px, rgba(255,255,255,0.55) 1px, transparent 0)",
            backgroundSize: "32px 32px",
          }}
        />
      </div>

      <div className="absolute left-6 top-6 flex items-center gap-2 text-[11px] uppercase tracking-[0.2em] text-slate-500">
        <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-accent" />
        live · IBM Cloud · ca-tor
      </div>
      <div className="absolute right-6 top-6 flex items-center gap-3 text-[11px] uppercase tracking-[0.2em] text-slate-500">
        <span>v0.2 · open source</span>
        <a
          href="https://github.com/Minifigures/ibm-z-hackathon"
          target="_blank"
          rel="noreferrer"
          className="hover:text-slate-200"
        >
          github ↗
        </a>
      </div>

      <div className="relative z-10 flex min-h-full flex-col items-center justify-center px-6 text-center">
        <div
          className={`transition-all duration-1000 ${
            mounted ? "translate-y-0 opacity-100" : "translate-y-2 opacity-0"
          }`}
        >
          <p className="mb-4 inline-flex items-center gap-2 rounded-full border border-ink-600 bg-ink-800/60 px-3 py-1 text-[10px] uppercase tracking-[0.25em] text-slate-400 backdrop-blur">
            <span className="inline-block h-1.5 w-1.5 rounded-full bg-accent" />
            disease outflow forecaster
          </p>
          <h1
            className="mb-3 font-mono text-[clamp(2.75rem,9vw,7rem)] font-semibold leading-none tracking-tight text-slate-50"
            style={{ letterSpacing: "-0.04em" }}
          >
            Pandexis
          </h1>
          <p className="mx-auto max-w-2xl text-base text-slate-300 sm:text-lg">
            Pick a disease and a starting city. Slide R<sub>0</sub>, masks, travel curbs.
            Watch a calibrated world map of likely spread, with an AI explainer per region.
          </p>
          <p className="mx-auto mt-2 max-w-2xl text-xs text-slate-500">
            Built on IBM Cloud · watsonx.ai · IBM Granite chat + embedding · grounded in 17 peer-reviewed papers.
          </p>
        </div>

        <div
          className={`mt-10 transition-all duration-1000 delay-200 ${
            mounted ? "translate-y-0 opacity-100" : "translate-y-2 opacity-0"
          }`}
        >
          <button
            onClick={launch}
            className="group relative inline-flex items-center gap-3 rounded-full bg-accent px-8 py-3 text-sm font-semibold tracking-wide text-ink-950 shadow-[0_0_60px_-15px_rgba(124,242,200,0.55)] transition-all hover:scale-[1.02] hover:shadow-[0_0_80px_-10px_rgba(124,242,200,0.7)]"
          >
            <span className="absolute inset-0 -z-10 rounded-full bg-accent opacity-0 blur-xl transition-opacity duration-300 group-hover:opacity-50" />
            Launch forecaster
            <span className="text-base transition-transform group-hover:translate-x-0.5">→</span>
          </button>
          <p className="mt-3 text-[11px] uppercase tracking-[0.2em] text-slate-500">
            no sign-in · no tracking · world map loads in &lt;1s
          </p>
        </div>

        <div
          className={`mt-16 grid grid-cols-2 gap-x-10 gap-y-3 text-left text-[11px] text-slate-500 sm:grid-cols-4 transition-all duration-1000 delay-300 ${
            mounted ? "translate-y-0 opacity-100" : "translate-y-2 opacity-0"
          }`}
        >
          <Stat label="Modelled regions" value="81" />
          <Stat label="Monte Carlo runs" value="200+" />
          <Stat label="Calibration metrics" value="CRPS · log score" />
          <Stat label="Explainer" value="Granite via watsonx" />
        </div>
      </div>

      <div className="absolute inset-x-0 bottom-4 text-center text-[10px] uppercase tracking-[0.3em] text-slate-600">
        Press the button. Drag a slider. Watch a continent light up.
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-[0.18em] text-slate-600">{label}</div>
      <div className="mt-0.5 font-mono text-sm text-slate-200">{value}</div>
    </div>
  );
}
