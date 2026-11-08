import type { ReactNode } from "react";

type Tone = "ok" | "warn" | "err" | "neutral" | "info";

const TONES: Record<Tone, string> = {
  ok: "bg-pos/10 text-pos ring-pos/30",
  warn: "bg-warn/10 text-warn ring-warn/30",
  err: "bg-neg/10 text-neg ring-neg/30",
  neutral: "bg-ink-700/40 text-muted ring-ink-600/40",
  info: "bg-accent/10 text-accent ring-accent/30",
};

export function StatusBadge({ tone, children }: { tone: Tone; children: ReactNode }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset ${TONES[tone]}`}
    >
      <span className="h-1.5 w-1.5 rounded-full bg-current" />
      {children}
    </span>
  );
}

export function DataModeBadge({ mode }: { mode?: string }) {
  if (!mode) return <StatusBadge tone="neutral">unknown</StatusBadge>;
  const demo = mode === "demo";
  return (
    <span
      className={`inline-flex items-center gap-1 rounded px-2 py-0.5 text-xs font-semibold uppercase tracking-wide ring-1 ring-inset ${
        demo ? "bg-warn/10 text-warn ring-warn/30" : "bg-pos/10 text-pos ring-pos/30"
      }`}
      title={demo ? "Synthetic demo data — not real market data" : "Live data from the database"}
    >
      {demo ? "DEMO" : "LIVE"}
    </span>
  );
}
