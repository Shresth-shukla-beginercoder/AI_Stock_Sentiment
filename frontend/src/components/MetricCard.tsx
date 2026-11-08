import type { ReactNode } from "react";
import { Card, Body } from "./states";

export function MetricCard({
  label,
  value,
  sub,
  tone = "neutral",
}: {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  tone?: "neutral" | "pos" | "neg" | "warn" | "accent";
}) {
  const color =
    tone === "pos"
      ? "text-pos"
      : tone === "neg"
        ? "text-neg"
        : tone === "warn"
          ? "text-warn"
          : tone === "accent"
            ? "text-accent"
            : "text-slate-100";
  return (
    <Card>
      <Body>
        <div className="text-xs font-medium uppercase tracking-wide text-muted">{label}</div>
        <div className={`mt-1 text-2xl font-semibold ${color}`}>{value}</div>
        {sub ? <div className="mt-1 text-xs text-muted">{sub}</div> : null}
      </Body>
    </Card>
  );
}
