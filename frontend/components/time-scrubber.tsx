"use client";

import { useEffect, useRef } from "react";

type Props = {
  horizonDays: number;
  currentDay: number | null;
  playing: boolean;
  onScrub: (day: number) => void;
  onPlayToggle: () => void;
  onLive: () => void;
};

const TICK_MS = 140;

export function TimeScrubber({
  horizonDays,
  currentDay,
  playing,
  onScrub,
  onPlayToggle,
  onLive,
}: Props) {
  const tickRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (!playing) {
      if (tickRef.current) clearInterval(tickRef.current);
      tickRef.current = null;
      return;
    }
    tickRef.current = setInterval(() => {
      const next = ((currentDay ?? -1) + 1) % (horizonDays + 1);
      onScrub(next);
    }, TICK_MS);
    return () => {
      if (tickRef.current) clearInterval(tickRef.current);
      tickRef.current = null;
    };
  }, [playing, currentDay, horizonDays, onScrub]);

  const day = currentDay ?? horizonDays;
  const live = currentDay == null;

  return (
    <div className="flex items-center gap-3 rounded-md border border-ink-600 bg-ink-800/95 px-3 py-2 backdrop-blur">
      <button
        aria-label={playing ? "Pause" : "Play"}
        onClick={onPlayToggle}
        className="flex h-7 w-7 items-center justify-center rounded bg-accent/20 text-accent hover:bg-accent/30"
      >
        {playing ? (
          <svg width="10" height="12" viewBox="0 0 10 12" fill="currentColor">
            <rect x="0" y="0" width="3" height="12" />
            <rect x="7" y="0" width="3" height="12" />
          </svg>
        ) : (
          <svg width="10" height="12" viewBox="0 0 10 12" fill="currentColor">
            <path d="M0 0 L10 6 L0 12 Z" />
          </svg>
        )}
      </button>
      <button
        onClick={onLive}
        disabled={live}
        className={`text-[10px] uppercase tracking-wide px-2 py-1 rounded border ${
          live
            ? "border-accent text-accent bg-accent/10"
            : "border-ink-600 text-slate-400 hover:border-slate-400"
        }`}
      >
        {live ? "Live" : "Go Live"}
      </button>
      <div className="text-[11px] font-mono tabular-nums text-slate-300 w-20">
        Day {day} / {horizonDays}
      </div>
      <input
        type="range"
        min={0}
        max={horizonDays}
        step={1}
        value={day}
        onChange={(e) => onScrub(parseInt(e.target.value, 10))}
        className="slider flex-1"
        aria-label="Forecast day"
      />
    </div>
  );
}
