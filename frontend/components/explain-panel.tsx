"use client";

type Props = {
  text: string | null;
  source: string | null;
  loading: boolean;
  onRequest: () => void;
  focusName: string | null;
};

const SOURCE_LABEL: Record<string, { label: string; classes: string }> = {
  watsonx: {
    label: "IBM Granite via watsonx.ai",
    // IBM blue accent. Reads as "the IBM AI ran this" in the demo.
    classes: "bg-[#0f62fe]/15 text-[#78a9ff] border border-[#0f62fe]/40",
  },
  anthropic: {
    label: "Claude Haiku",
    classes: "bg-accent/15 text-accent border border-accent/40",
  },
  template: {
    label: "Templated fallback",
    classes: "bg-slate-700/40 text-slate-400 border border-slate-600/40",
  },
};

export function ExplainPanel({ text, source, loading, onRequest, focusName }: Props) {
  const meta = source ? SOURCE_LABEL[source] ?? null : null;
  return (
    <div className="rounded-md border border-ink-600 bg-ink-800">
      <div className="flex items-center justify-between px-3 py-2 border-b border-ink-600">
        <h3 className="text-xs uppercase tracking-wide text-slate-400">
          AI Explanation
          {focusName ? <span className="text-slate-500"> · {focusName}</span> : null}
        </h3>
        <button
          className="text-[11px] px-2 py-1 rounded bg-accent/20 text-accent hover:bg-accent/30 disabled:opacity-50"
          disabled={loading}
          onClick={onRequest}
        >
          {loading ? "Generating…" : text ? "Regenerate" : "Explain"}
        </button>
      </div>
      <div className="px-3 py-3 text-sm text-slate-200 leading-relaxed min-h-[5rem]">
        {text ?? (
          <p className="text-slate-500 text-xs">
            Click <span className="text-accent">Explain</span> to generate a plain-English
            narrative for the current scenario, grounded in the SEIR + gravity outputs.
          </p>
        )}
      </div>
      {meta ? (
        <div className="px-3 pb-2 flex items-center gap-2">
          <span
            className={`text-[10px] uppercase tracking-wide font-medium px-1.5 py-0.5 rounded ${meta.classes}`}
            title="Provider that generated this explanation"
          >
            {meta.label}
          </span>
        </div>
      ) : null}
    </div>
  );
}
