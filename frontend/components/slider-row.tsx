"use client";

type Props = {
  label: string;
  hint?: string;
  value: number;
  min: number;
  max: number;
  step: number;
  format?: (v: number) => string;
  onChange: (v: number) => void;
};

export function SliderRow({ label, hint, value, min, max, step, format, onChange }: Props) {
  const display = format ? format(value) : value.toFixed(step < 1 ? 2 : 0);
  return (
    <div className="space-y-1">
      <div className="flex items-baseline justify-between">
        <label className="text-xs uppercase tracking-wide text-slate-400">{label}</label>
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
    </div>
  );
}
