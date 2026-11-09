import { useApi } from "../hooks/useApi";
import { getHealth, getReady, getSystemStatus } from "../api/endpoints";
import type { Envelope, SystemStatusData } from "../types/api";
import { PageContainer } from "../components/layout";
import { Card, CardContent, CardHeader } from "../components/common/Card";
import { StatusBadge, DataModeBadge } from "../components/common/StatusBadge";
import { MetricCard } from "../components/common/MetricCard";
import { EmptyState, LoadingSpinner } from "../components/common";
import { Server, Database, Cpu, KeyRound, Activity, Plug } from "lucide-react";
import { fmtLatency } from "../utils/format";

export function SystemStatus() {
  const health = useApi(() => getHealth(), { refreshMs: 30000 });
  const ready = useApi(() => getReady(), { refreshMs: 30000 });
  const system = useApi<Envelope<SystemStatusData>, SystemStatusData>(() => getSystemStatus());
  const s = system.data;

  const backendUp = health.status === "success";

  return (
    <PageContainer
      title="System Status"
      subtitle="What the backend reports — no inference. Auto-refreshes every 30 s."
      action={
        <button
          onClick={() => {
            health.reload();
            ready.reload();
            system.reload();
          }}
          className="rounded-lg border border-white/10 bg-bg-tertiary px-3 py-1.5 text-xs text-muted transition-colors hover:text-accent-primary"
        >
          Refresh
        </button>
      }
    >
      <div className="space-y-6">
        {/* Top metrics */}
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          <MetricCard
            label="Backend API"
            value={backendUp ? "Up" : "Down"}
            sub={backendUp ? `latency ${fmtLatency(health.latencyMs)}` : "unreachable"}
            icon={<Server className="h-4 w-4" />}
          />
          <MetricCard
            label="Database"
            value={ready.data?.database ?? "unknown"}
            sub="SELECT 1 readiness"
            icon={<Database className="h-4 w-4" />}
          />
          <MetricCard
            label="Data Mode"
            value={(system.dataMode ?? health.data?.data_mode)?.toUpperCase() ?? "—"}
            sub="explicit, never inferred"
            icon={<Plug className="h-4 w-4" />}
          />
          <MetricCard
            label="Provider"
            value={<span className="text-base">{health.data?.market_data_provider ?? "unselected"}</span>}
            sub="capability unverified"
            icon={<Cpu className="h-4 w-4" />}
          />
        </div>

        {/* Feature status + credentials */}
        <div className="grid gap-4 lg:grid-cols-2">
          <Card>
            <CardHeader
              title="Feature Status"
              action={
                <StatusBadge tone="neutral">
                  v{s?.version ?? "—"}
                </StatusBadge>
              }
            />
            <CardContent>
              {s ? (
                <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                  {Object.entries(s.feature_status).map(([k, v]) => (
                    <div
                      key={k}
                      className="flex items-center justify-between rounded-lg bg-bg-tertiary/50 px-3 py-2 text-xs"
                    >
                      <span className="text-muted">{k}</span>
                      <span className="text-text-primary">{v}</span>
                    </div>
                  ))}
                </div>
              ) : system.status === "error" ? (
                <EmptyState title="Status unavailable" description={system.error?.message} />
              ) : (
                <div className="flex items-center gap-2 text-sm text-muted">
                  <LoadingSpinner size="sm" /> Loading…
                </div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader title="Credentials" subtitle="Names only — values never shown" />
            <CardContent>
              {s ? (
                <div className="space-y-3">
                  <div>
                    <div className="mb-1.5 flex items-center gap-1.5 text-xs text-muted">
                      <KeyRound className="h-3 w-3" /> Configured
                    </div>
                    <div className="flex flex-wrap gap-1">
                      {s.credentials.configured.length === 0 ? (
                        <span className="text-xs text-muted/60">none</span>
                      ) : (
                        s.credentials.configured.map((c) => (
                          <span key={c} className="rounded bg-pos/10 px-1.5 py-0.5 font-mono text-xs text-pos">
                            {c}
                          </span>
                        ))
                      )}
                    </div>
                  </div>
                  <div>
                    <div className="mb-1.5 flex items-center gap-1.5 text-xs text-muted">
                      <Activity className="h-3 w-3" /> Missing
                    </div>
                    <div className="flex flex-wrap gap-1">
                      {s.credentials.missing.length === 0 ? (
                        <span className="text-xs text-muted/60">none</span>
                      ) : (
                        s.credentials.missing.map((c) => (
                          <span key={c} className="rounded bg-bg-tertiary px-1.5 py-0.5 font-mono text-xs text-muted">
                            {c}
                          </span>
                        ))
                      )}
                    </div>
                  </div>
                  <div className="flex items-center justify-between border-t border-white/5 pt-3 text-xs">
                    <DataModeBadge mode={system.dataMode} />
                    <span className="font-mono text-muted">app: {s.app}</span>
                  </div>
                </div>
              ) : (
                <EmptyState title="Not available" />
              )}
            </CardContent>
          </Card>
        </div>

        {/* Raw response transparency */}
        <Card>
          <CardHeader title="Raw Response" subtitle="GET /api/system/status — exactly as received" />
          <CardContent>
            <pre className="max-h-64 overflow-auto rounded-lg bg-bg-tertiary/50 p-3 font-mono text-xs text-text-secondary">
              {system.raw ? JSON.stringify(system.raw, null, 2) : "—"}
            </pre>
          </CardContent>
        </Card>
      </div>
    </PageContainer>
  );
}
