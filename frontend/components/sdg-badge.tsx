"use client";

import { useState } from "react";

type SDG = { num: number; name: string; why: string };

const SDGS: SDG[] = [
  {
    num: 3,
    name: "Good Health and Well-being",
    why: "Helps public-health teams forecast outbreaks and target interventions before they overwhelm hospitals.",
  },
  {
    num: 9,
    name: "Industry, Innovation and Infrastructure",
    why: "Open, auditable AI for public-health planning, runnable on commodity cloud or IBM Z.",
  },
  {
    num: 11,
    name: "Sustainable Cities and Communities",
    why: "Region-indexed SEIR with mobility makes city-level resilience planning legible to non-experts.",
  },
  {
    num: 13,
    name: "Climate Action",
    why: "Climate-sensitive disease ranges (dengue, malaria, cholera) are first-class scenarios.",
  },
  {
    num: 17,
    name: "Partnerships for the Goals",
    why: "Stitches WHO, JHU CSSE, OpenFlights, UN/UNCTAD, CDC NWSS into one open pipeline.",
  },
];

/**
 * Compact "UN SDG impact" badge that floats near the calibration badge.
 * Click expands into a panel listing each SDG and how the project advances it.
 */
export function SDGBadge() {
  const [open, setOpen] = useState(false);
  return (
    <div className="absolute top-3 right-[12rem] z-20 pointer-events-auto">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="text-[10px] uppercase tracking-wide font-semibold px-2 py-1 rounded border border-[#56a83b]/40 bg-[#56a83b]/15 text-[#9be07c] hover:bg-[#56a83b]/25 transition-colors"
        aria-expanded={open}
        aria-label="UN Sustainable Development Goals alignment"
      >
        UN SDGs · 3 · 9 · 11 · 13 · 17
      </button>
      {open ? (
        <div
          className="mt-2 w-80 rounded-md border border-ink-600 bg-ink-800/98 backdrop-blur p-3 text-xs text-slate-200 shadow-xl"
          role="dialog"
          aria-label="SDG alignment details"
        >
          <div className="flex items-center justify-between mb-2">
            <span className="text-[10px] uppercase tracking-wide text-slate-500">
              UN Sustainable Development Goals
            </span>
            <button
              type="button"
              onClick={() => setOpen(false)}
              className="text-slate-500 hover:text-slate-200 text-xs"
              aria-label="Close SDG details"
            >
              ✕
            </button>
          </div>
          <ul className="space-y-2">
            {SDGS.map((sdg) => (
              <li key={sdg.num} className="flex gap-2">
                <span className="font-mono text-[10px] tabular-nums text-[#9be07c] w-5 shrink-0 mt-0.5">
                  SDG {sdg.num}
                </span>
                <span>
                  <span className="font-medium text-slate-100">{sdg.name}.</span>{" "}
                  <span className="text-slate-400">{sdg.why}</span>
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}
