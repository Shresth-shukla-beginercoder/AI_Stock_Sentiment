import { useApi } from "../hooks/useApi";
import { getHealth, getReady, getSystemStatus } from "../api/endpoints";
import type { Envelope, SystemStatusData } from "../types/api";
import { PageContainer, Card, CardHeader, Body, ErrorState, EmptyState } from "../components/states";
import { StatusBadge, DataModeBadge } from "../components/StatusBadge";
import { MetricCard } from "../components/MetricCard";
import { ApiResponsePanel } from "../components/ApiResponsePanel";
import { fmtLatency } from "../utils/format";

export function SystemStatus() {
  const health = useApi(() => getHealth());
  const ready = useApi(() => getReady());
  const system = useApi<Envelope<SystemStatusData>, SystemStatusData>(() => getSystemStatus());
  const s = system.data;

  return (
    <PageContainer title="System Status" subtitle="What the backend actually reports — no inference.">
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <MetricCard
          label="Backend"
          value={health.status === "success" ? "up" : "down"}
          tone={health.status === "success" ? "pos" : "neg"}
          sub={health.status === "success" ? `latency ${fmtLatency(health.latencyMs)}` : "unreachable"}
        />
        <MetricCard
          label="Database"
          value={ready.data?.database ?? "unknown"}
          tone={ready.data?.database === "up" ? "pos" : ready.data?.database === "down" ? "neg" : "warn"}
          sub="SELECT 1 readiness"
        />
        <MetricCard
          label="Data mode"
          value={(system.dataMode ?? health.data?.data_mode)?.toUpperCase() ?? "—"}
          tone={system.dataMode === "demo" ? "warn" : "neutral"}
          sub="explicit setting, never inferred"
        />
        <MetricCard
          label="Provider"
          value={<span className="text-base">{health.data?.market_data_provider ?? "unselected"}</span>}
          sub="capability UNVERIFIED until Phase 5 fetch"
        />
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader title="Feature status" />
          <Body className="space-y-2 text-sm">
            {s ? (
              <div className="grid grid-cols-2 gap-2">
                {Object.entries(s.feature_status).map(([k, v]) => (
                  <div key={k} className="flex items-center justify-between rounded border border-ink-700/40 bg-ink-900/40 px-2.5 py-1.5 text-xs">
                    <span className="text-muted">{k}</span>
                    <span className="text-slate-200">{v}</span>
                  </div>
                ))}
              </div>
            ) : system.status === "error" ? (
              <ErrorState title="system/status unavailable" detail={system.error?.message} onRetry={system.reload} />
            ) : (
              <EmptyState title="Loading status…" />
            )}
            <div className="flex items-center gap-2 pt-1 text-xs text-muted">
              <StatusBadge tone="neutral">v{s?.version ?? "—"}</StatusBadge>
              app: <span className="font-mono">{s?.app ?? "—"}</span>
            </div>
          </Body>
        </Card>

        <Card>
          <CardHeader title="Credentials (names only — values never shown)" />
          <Body className="space-y-2 text-xs">
            {s ? (
              <>
                <div>
                  <div className="mb-1 text-muted">configured</div>
                  <div className="flex flex-wrap gap-1">
                    {s.credentials.configured.length === 0 ? (
                      <span className="text-muted/60">none</span>
                    ) : (
                      s.credentials.configured.map((c) => (
                        <span key={c} className="rounded bg-pos/10 px-1.5 py-0.5 font-mono text-pos">
                          {c}
                        </span>
                      ))
                    )}
                  </div>
                </div>
                <div>
                  <div className="mb-1 text-muted">missing</div>
                  <div className="flex flex-wrap gap-1">
                    {s.credentials.missing.length === 0 ? (
                      <span className="text-muted/60">none</span>
                    ) : (
                      s.credentials.missing.map((c) => (
                        <span key={c} className="rounded bg-ink-700/50 px-1.5 py-0.5 font-mono text-muted">
                          {c}
                        </span>
                      ))
                    )}
                  </div>
                </div>
              </>
            ) : (
              <EmptyState title="Not available" />
            )}
          </Body>
        </Card>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <div>
          <DataModeBadge mode={system.dataMode} />
        </div>
        <div>
          <ApiResponsePanel state={system} endpoint="/api/system/status" />
        </div>
      </div>
    </PageContainer>
  );
}
