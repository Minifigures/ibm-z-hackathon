"use client";

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

type Props = {
  label: string;
  hint?: string;
  info?: string;
  value: number;
  min: number;
  max: number;
  step: number;
  format?: (v: number) => string;
  onChange: (v: number) => void;
};

export function SliderRow({ label, hint, info, value, min, max, step, format, onChange }: Props) {
  const display = format ? format(value) : value.toFixed(step < 1 ? 2 : 0);
  const iconRef = useRef<HTMLSpanElement>(null);
  const [tipPos, setTipPos] = useState<{ left: number; top: number } | null>(null);
  const [pinned, setPinned] = useState(false);

  const computePos = () => {
    const r = iconRef.current?.getBoundingClientRect();
    if (!r) return null;
    return { left: r.right + 8, top: r.top + r.height / 2 };
  };

  const showTooltip = () => {
    const p = computePos();
    if (p) setTipPos(p);
  };
  const hideTooltip = () => {
    if (!pinned) setTipPos(null);
  };
  const toggleTooltip = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (pinned) {
      setPinned(false);
      setTipPos(null);
    } else {
      const p = computePos();
      if (p) setTipPos(p);
      setPinned(true);
    }
  };

  useEffect(() => {
    if (!pinned) return;
    const onDocClick = (e: MouseEvent) => {
      if (iconRef.current && !iconRef.current.contains(e.target as Node)) {
        setPinned(false);
        setTipPos(null);
      }
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setPinned(false);
        setTipPos(null);
      }
    };
    document.addEventListener("mousedown", onDocClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDocClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [pinned]);

  return (
    <div className="space-y-1">
      <div className="flex items-baseline justify-between">
        <label className="text-xs uppercase tracking-wide text-slate-400 flex items-center gap-1.5">
          <span>{label}</span>
          {info ? (
            <span
              ref={iconRef}
              role="button"
              aria-label={`About ${label}`}
              aria-pressed={pinned}
              tabIndex={0}
              onMouseEnter={showTooltip}
              onMouseLeave={hideTooltip}
              onFocus={showTooltip}
              onBlur={hideTooltip}
              onClick={toggleTooltip}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  toggleTooltip(e as unknown as React.MouseEvent);
                }
              }}
              className={`inline-flex items-center justify-center w-3.5 h-3.5 rounded-full border text-[9px] font-semibold leading-none cursor-help select-none normal-case tracking-normal focus:outline-none ${
                pinned
                  ? "border-accent text-accent"
                  : "border-slate-500 text-slate-400 hover:border-slate-300 hover:text-slate-200 focus:border-accent focus:text-accent"
              }`}
            >
              i
            </span>
          ) : null}
        </label>
        <span className="text-sm font-mono tabular-nums text-accent">{display}</span>
      </div>
      <input
        className="slider"
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(parseFloat(e.target.value))}
      />
      {hint ? <p className="text-[10px] text-slate-500">{hint}</p> : null}
      {info && tipPos && typeof document !== "undefined"
        ? createPortal(
            <span
              role="tooltip"
              style={{
                position: "fixed",
                left: tipPos.left,
                top: tipPos.top,
                transform: "translateY(-50%)",
                zIndex: 9999,
              }}
              className="pointer-events-none w-48 rounded border border-ink-600 bg-ink-900 px-2 py-1 text-[10px] font-normal normal-case tracking-normal text-slate-200 shadow-lg"
            >
              {info}
            </span>,
            document.body,
          )
        : null}
    </div>
  );
}
