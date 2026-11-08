import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useApi } from "../hooks/useApi";
import { listAssets } from "../api/endpoints";
import { PageContainer, Card, CardHeader, Body, EmptyState, ErrorState } from "../components/states";
import { StatusBadge, DataModeBadge } from "../components/StatusBadge";
import { DataTable, type Column } from "../components/DataTable";
import { ApiResponsePanel } from "../components/ApiResponsePanel";
import type { Asset, Envelope } from "../types/api";

type Filter = "all" | "demo" | "live";

const COLS: Column<Asset>[] = [
  { key: "ticker", header: "Ticker", render: (a) => <span className="font-mono text-slate-100">{a.ticker}</span> },
  { key: "exchange", header: "Exchange", render: (a) => a.exchange },
  { key: "name", header: "Name", render: (a) => a.name ?? <span className="text-muted/50">—</span> },
  {
    key: "confirmed",
    header: "Confirmed",
    align: "center",
    render: (a) => (
      <StatusBadge tone={a.confirmed ? "ok" : "warn"}>{a.confirmed ? "yes" : "pending"}</StatusBadge>
    ),
  },
  {
    key: "is_demo",
    header: "Classification",
    align: "center",
    render: (a) => (a.is_demo ? <DataModeBadge mode="demo" /> : <DataModeBadge mode="live" />),
  },
  { key: "provider_ticker", header: "Provider ticker", render: (a) => a.provider_ticker ?? <span className="text-muted/50">null</span> },
  {
    key: "active",
    header: "Active",
    align: "center",
    render: (a) => (a.active ? <StatusBadge tone="ok">active</StatusBadge> : <StatusBadge tone="neutral">inactive</StatusBadge>),
  },
];

export function Assets() {
  const assets = useApi<Envelope<Asset[]>, Asset[]>(() => listAssets({ limit: 200 }));
  const [q, setQ] = useState("");
  const [filter, setFilter] = useState<Filter>("all");

  const rows = useMemo(() => {
    const list = assets.data ?? [];
    const needle = q.trim().toLowerCase();
    return list.filter((a) => {
      if (filter === "demo" && !a.is_demo) return false;
      if (filter === "live" && a.is_demo) return false;
      if (!needle) return true;
      return (
        a.ticker.toLowerCase().includes(needle) ||
        (a.name ?? "").toLowerCase().includes(needle) ||
        a.exchange.toLowerCase().includes(needle)
      );
    });
  }, [assets.data, q, filter]);

  const demoCount = (assets.data ?? []).filter((a) => a.is_demo).length;
  const liveCount = (assets.data ?? []).filter((a) => !a.is_demo).length;

  return (
    <PageContainer
      title="Assets"
      subtitle={`${(assets.data?.length ?? 0)} assets — ${demoCount} synthetic demo, ${liveCount} live. Synthetic assets are kept visibly separate from any confirmed real universe.`}
    >
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search ticker / name / exchange…"
          className="rounded border border-ink-600 bg-ink-900 px-3 py-1.5 text-sm text-slate-200 placeholder:text-muted/50 focus:border-accent focus:outline-none"
        />
        <div className="flex overflow-hidden rounded border border-ink-600 text-xs">
          {(["all", "demo", "live"] as Filter[]).map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`px-3 py-1.5 uppercase ${
                filter === f ? "bg-accent/20 text-accent" : "text-muted hover:text-slate-200"
              }`}
            >
              {f}
            </button>
          ))}
        </div>
        {assets.meta?.note ? <span className="text-xs text-muted/60">{assets.meta.note}</span> : null}
      </div>

      <div className="grid gap-4">
        {assets.status === "loading" ? (
          <Card><Body><EmptyState title="Loading assets…" /></Body></Card>
        ) : assets.status === "error" ? (
          <ErrorState title="Could not load assets" detail={assets.error?.message} onRetry={assets.reload} />
        ) : rows.length === 0 ? (
          <EmptyState
            title={q || filter !== "all" ? "No assets match the current filter" : "No assets in this mode"}
            hint={
              filter === "live"
                ? "No live assets confirmed yet — the 10 proposed HKEX/KRX tickers remain pending owner confirmation."
                : undefined
            }
          />
        ) : (
          <Card>
            <CardHeader title="Assets" />
            <DataTable columns={COLS} rows={rows} rowKey={(a) => a.ticker} />
          </Card>
        )}
      </div>

      <div className="mt-4">
        <div className="mb-2 text-xs text-muted">
          Inspect a single asset:{" "}
          <Link to="/inspector" className="text-accent hover:underline">Stock Inspector →</Link>
        </div>
        <ApiResponsePanel state={assets} endpoint="/api/assets" />
      </div>
    </PageContainer>
  );
}
