import type { UseApiState } from "../hooks/useApi";
import { DataModeBadge } from "./StatusBadge";
import { RawJsonViewer } from "./RawJsonViewer";
import { ErrorState } from "./states";
import { fmtLatency, fmtTime } from "../utils/format";

/**
 * Standard API-response header panel. Drop it above any section to expose
 * endpoint, status, latency, data mode, freshness and the raw JSON.
 */
export function ApiResponsePanel<T>({
  state,
  endpoint,
}: {
  state: UseApiState<T>;
  endpoint: string;
}) {
  const tone =
    state.status === "success"
      ? "text-pos"
      : state.status === "error"
        ? "text-neg"
        : state.status === "loading"
          ? "text-accent"
          : "text-muted";

  const statusLabel =
    state.status === "success"
      ? state.httpStatus === null
        ? "OK"
        : `HTTP ${state.httpStatus}`
      : state.status === "error"
        ? state.httpStatus === null
          ? "unreachable"
          : `HTTP ${state.httpStatus}`
        : state.status === "no_key"
          ? "auth required"
          : state.status;

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 rounded-lg border border-ink-700/50 bg-ink-850/40 px-3 py-2 text-xs">
        <span className="font-mono text-slate-200">GET {endpoint}</span>
        <span className={`font-semibold ${tone}`}>{statusLabel}</span>
        <span className="text-muted" title="Time this request took">
          {fmtLatency(state.latencyMs)}
        </span>
        <DataModeBadge mode={state.dataMode} />
        <span className="text-muted" title="When this check was last made">
          checked {fmtTime(state.lastChecked?.toISOString() ?? null)}
        </span>
        {state.status === "loading" ? <span className="text-accent">refreshing…</span> : null}
        <span className="ml-auto text-muted" title="Backend as_of, if the envelope carries one">
          {state.asOf ? `as_of ${fmtTime(state.asOf)}` : ""}
        </span>
      </div>
      {state.status === "error" ? (
        <ErrorState
          title={
            state.httpStatus === null
              ? "Backend unreachable"
              : `Request failed (HTTP ${state.httpStatus})`
          }
          detail={
            state.error instanceof Error
              ? state.error.message
              : "Unexpected error — see raw response."
          }
          onRetry={state.reload}
        />
      ) : null}
      <RawJsonViewer value={state.raw} label="raw JSON response" />
    </div>
  );
}
