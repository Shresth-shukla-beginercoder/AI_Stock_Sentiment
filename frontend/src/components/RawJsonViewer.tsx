import { useState } from "react";

/**
 * Collapsible raw-JSON viewer. Shows the exact bytes the backend returned —
 * this is a verification console, so transparency wins over prettiness.
 */
export function RawJsonViewer({ value, label = "raw response" }: { value: unknown; label?: string }) {
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const text = typeof value === "string" ? value : JSON.stringify(value, null, 2);

  return (
    <div className="rounded-lg border border-ink-700/50 bg-ink-900/60">
      <div className="flex items-center justify-between px-3 py-1.5 text-xs">
        <button
          onClick={() => setOpen((v) => !v)}
          className="font-medium text-muted hover:text-slate-200"
        >
          {open ? "▾" : "▸"} {label}
        </button>
        {open ? (
          <button
            onClick={async () => {
              try {
                await navigator.clipboard.writeText(text ?? "");
                setCopied(true);
                setTimeout(() => setCopied(false), 1200);
              } catch {
                /* clipboard may be blocked; silently ignore */
              }
            }}
            className="text-muted hover:text-accent"
          >
            {copied ? "copied" : "copy"}
          </button>
        ) : null}
      </div>
      {open ? (
        <pre className="max-h-72 overflow-auto border-t border-ink-700/50 p-3 font-mono text-xs leading-relaxed text-slate-300">
          {text}
        </pre>
      ) : null}
    </div>
  );
}
