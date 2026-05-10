"use client";

import { useState } from "react";
import { api, type DiseaseLookupOk, type DiseaseParams } from "@/lib/api";

type Props = {
  onApply: (params: DiseaseParams) => void;
};

export function DiseaseSearch({ onApply }: Props) {
  const [name, setName] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [last, setLast] = useState<DiseaseLookupOk | null>(null);

  const submit = async () => {
    const trimmed = name.trim();
    if (!trimmed || loading) return;
    setLoading(true);
    setError(null);
    try {
      const r = await api.diseaseLookup(trimmed);
      if (r.status === "ok") {
        setLast(r);
        onApply(r.params);
      } else {
        setLast(null);
        setError(r.message);
      }
    } catch (e) {
      setError((e as Error).message);
      setLast(null);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-1">
      <label className="block text-xs uppercase tracking-wide text-slate-400">
        AI lookup · watsonx + Granite Embedding RAG
      </label>
      <div className="flex gap-1">
        <input
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") submit();
          }}
          placeholder="Type any virus (e.g. ebola, smallpox)…"
          aria-label="Disease name"
          className="flex-1 bg-ink-700 border border-ink-600 rounded px-2 py-1.5 text-sm placeholder:text-slate-500"
          disabled={loading}
        />
        <button
          onClick={submit}
          disabled={loading || !name.trim()}
          className="px-2 py-1.5 rounded text-xs bg-accent/20 text-accent hover:bg-accent/30 disabled:opacity-50"
        >
          {loading ? "…" : "Auto-fill"}
        </button>
      </div>
      {error ? (
        <p className="text-[11px] text-red-400">{error}</p>
      ) : null}
      {last ? (
        <p className="text-[11px] text-slate-500">
          Loaded <span className="text-slate-300">{last.params.label}</span>
          <span> · {last.params.confidence} confidence</span>
          {last.cached ? <span> · cached</span> : null}
          {last.retrieved.length > 0 && last.retrieved[0].disease ? (
            <span> · top match: {last.retrieved[0].disease}</span>
          ) : null}
        </p>
      ) : null}
    </div>
  );
}
