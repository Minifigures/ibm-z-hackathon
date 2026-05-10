"use client";

function sourceLabel(source: string): string {
  switch (source) {
    case "watsonx":
      return "IBM Granite via watsonx.ai";
    case "anthropic":
      return "Claude Haiku";
    case "template":
      return "templated fallback";
    default:
      return source;
  }
}

type Props = {
  text: string | null;
  source: string | null;
  loading: boolean;
  onRequest: () => void;
  focusName: string | null;
};

export function ExplainPanel({ text, source, loading, onRequest, focusName }: Props) {
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
      {source ? (
        <div className="px-3 pb-2 text-[10px] text-slate-500">
          source: {sourceLabel(source)}
        </div>
      ) : null}
    </div>
  );
}
