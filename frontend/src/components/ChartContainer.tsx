import type { ReactNode } from "react";
import { EmptyState } from "./states";

/**
 * Frame for Recharts (or any visualisation) with honest empty handling:
 * the caller decides whether data exists; we never render a fake chart.
 */
export function ChartContainer({
  title,
  empty,
  emptyHint,
  height = 240,
  children,
}: {
  title?: string;
  empty: boolean;
  emptyHint?: string;
  height?: number;
  children?: ReactNode;
}) {
  return (
    <div className="rounded-lg border border-ink-700/50 bg-ink-850/60">
      {title ? (
        <div className="border-b border-ink-700/50 px-4 py-2.5 text-sm font-medium text-slate-200">
          {title}
        </div>
      ) : null}
      <div style={{ height }} className="p-2">
        {empty ? (
          <div className="flex h-full items-center justify-center">
            <EmptyState title={emptyHint ?? "No data to plot"} hint="No synthetic or generated series — showing exactly what the API returned." />
          </div>
        ) : (
          children
        )}
      </div>
    </div>
  );
}
