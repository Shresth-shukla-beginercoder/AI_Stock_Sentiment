import { useApi } from "../hooks/useApi";
import { getHealth, getReady, getSystemStatus } from "../api/endpoints";
import type { Envelope, SystemStatusData } from "../types/api";
import { PageContainer, Card, CardHeader, Body, ErrorState } from "../components/states";
import { StatusBadge, DataModeBadge } from "../components/StatusBadge";
import { ApiResponsePanel } from "../components/ApiResponsePanel";
import { fmtLatency, fmtTime } from "../utils/format";

const POLL_MS = 15_000;

export function ConnectionBoard() {
  const health = useApi(() => getHealth(), { refreshMs: POLL_MS });
  const ready = useApi(() => getReady(), { refreshMs: POLL_MS });
  const system = useApi<Envelope<SystemStatusData>, SystemStatusData>(
    () => getSystemStatus(),
    { refreshMs: POLL_MS }
  );

  const apiConnected = health.status === "success";
  // ready is a raw (non-envelope) response, so ready.data is already the body.
  const dbUp = ready.status === "success" && ready.data?.database === "up";
  const dbDown = ready.status === "success" && ready.data?.database === "down";

  return (
    <PageContainer
      title="Connection Board"
      subtitle="Live connectivity: API, database readiness and data mode. Auto-refreshes every 15 s."
      actions={
        <button
          onClick={() => {
            health.reload();
            ready.reload();
            system.reload();
          }}
          className="rounded border border-ink-600 px-3 py-1.5 text-xs text-muted hover:text-accent"
        >
          Refresh now
        </button>
      }
    >
      <div className="grid gap-4 lg:grid-cols-3">
        <Card>
          <CardHeader
            title="Backend API"
            right={<StatusBadge tone={apiConnected ? "ok" : "err"}>{apiConnected ? "connected" : "disconnected"}</StatusBadge>}
          />
          <Body className="space-y-2 text-sm">
            <Row k="Endpoint" v="/api/health" />
            <Row k="Latency" v={fmtLatency(health.latencyMs)} />
            <Row k="HTTP status" v={health.httpStatus === null ? (apiConnected ? "200" : "n/a") : String(health.httpStatus)} />
            <Row k="Last check" v={fmtTime(health.lastChecked?.toISOString() ?? null)} />
            {!apiConnected ? (
              <ErrorState title="API unreachable" detail="The backend is not responding. Check that the backend container is running." />
            ) : null}
          </Body>
        </Card>

        <Card>
          <CardHeader
            title="PostgreSQL"
            right={
              <StatusBadge tone={dbUp ? "ok" : dbDown ? "err" : "warn"}>
                {dbUp ? "ready" : dbDown ? "down" : "unknown"}
              </StatusBadge>
            }
          />
          <Body className="space-y-2 text-sm">
            <Row k="Endpoint" v="/api/ready" />
            <Row k="Readiness" v={ready.data?.database ?? "—"} />
            <Row k="Latency" v={fmtLatency(ready.latencyMs)} />
            <Row k="Last check" v={fmtTime(ready.lastChecked?.toISOString() ?? null)} />
            <p className="text-xs text-muted/70">
              Readiness is a real SELECT 1 against the database — never inferred from API
              liveness.
            </p>
          </Body>
        </Card>

        <Card>
          <CardHeader
            title="Data mode"
            right={<DataModeBadge mode={system.dataMode ?? health.data?.data_mode} />}
          />
          <Body className="space-y-2 text-sm">
            <Row k="Market data provider" v={health.data?.market_data_provider ?? "—"} />
            <Row
              k="Credentials"
              v={
                system.data?.credentials
                  ? `${system.data.credentials.configured.length} configured / ${system.data.credentials.missing.length} missing`
                  : "—"
              }
            />
            <Row k="Provider capability" v="UNVERIFIED (Phase 5)" />
            {system.status === "success" && system.meta?.note ? (
              <p className="text-xs text-muted/70">{system.meta.note}</p>
            ) : null}
          </Body>
        </Card>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-3">
        <div>
          <ApiResponsePanel state={health} endpoint="/api/health" />
        </div>
        <div>
          <ApiResponsePanel state={ready} endpoint="/api/ready" />
        </div>
        <div>
          <ApiResponsePanel state={system} endpoint="/api/system/status" />
        </div>
      </div>

      <div className="mt-4 text-xs text-muted">
        Docs:{" "}
        <a className="text-accent hover:underline" href="/docs" target="_blank" rel="noreferrer">
          Swagger UI
        </a>{" "}
        ·{" "}
        <a className="text-accent hover:underline" href="/api/openapi.json" target="_blank" rel="noreferrer">
          OpenAPI JSON
        </a>
      </div>
    </PageContainer>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex items-center justify-between gap-4">
      <span className="text-muted">{k}</span>
      <span className="font-mono text-slate-200">{v}</span>
    </div>
  );
}
