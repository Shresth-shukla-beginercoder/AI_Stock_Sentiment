import { useState } from "react";
import { useApi } from "../hooks/useApi";
import { useAdminAuth } from "../hooks/useAdminAuth";
import { listJobs, getJob, queueCollect, queueTrain } from "../api/endpoints";
import { PageContainer, Card, CardHeader, Body, EmptyState, ErrorState } from "../components/states";
import { StatusBadge } from "../components/StatusBadge";
import { DataTable, type Column } from "../components/DataTable";
import { ApiResponsePanel } from "../components/ApiResponsePanel";
import { fmtDate, fmtText } from "../utils/format";
import type { Envelope, Job } from "../types/api";

const JOB_COLS: Column<Job>[] = [
  { key: "id", header: "ID", align: "right", width: "64px" },
  {
    key: "job_type",
    header: "Type",
    render: (j) => <span className="font-mono text-xs">{j.job_type}</span>,
  },
  {
    key: "status",
    header: "Status",
    render: (j) => (
      <StatusBadge
        tone={
          j.status === "queued" ? "info" : j.status === "running" ? "warn" : j.status === "failed" ? "err" : "neutral"
        }
      >
        {j.status}
      </StatusBadge>
    ),
  },
  {
    key: "dedupe_key",
    header: "Dedupe key",
    render: (j) => <span className="block max-w-[36ch] truncate font-mono text-xs" title={j.dedupe_key}>{j.dedupe_key}</span>,
  },
  { key: "attempts", header: "Attempts", align: "right", render: (j) => `${j.attempts}/${j.max_attempts}` },
  { key: "created_at", header: "Created", render: (j) => fmtDate(j.created_at) },
  { key: "updated_at", header: "Updated", render: (j) => fmtDate(j.updated_at) },
  {
    key: "error",
    header: "Error",
    render: (j) =>
      j.error ? (
        <span className="block max-w-[24ch] truncate text-neg" title={j.error}>{j.error}</span>
      ) : (
        <span className="text-muted/40">—</span>
      ),
  },
];

export function Jobs() {
  const { configured, setKey, clearKey } = useAdminAuth();
  const [keyInput, setKeyInput] = useState("");
  const [actionMsg, setActionMsg] = useState<string | null>(null);

  const jobs = useApi<Envelope<Job[]>, Job[]>(() => listJobs({ limit: 50 }), {
    requiresAdmin: true,
    reloadKey: configured,
    deps: [configured],
  });
  const [selected, setSelected] = useState<Job | null>(null);
  const detail = useApi<Envelope<Job>, Job>(
    () => (selected ? getJob(selected.id) : Promise.resolve(null as unknown as Envelope<Job>)),
    {
      requiresAdmin: true,
      reloadKey: selected ? selected.id : "none",
      deps: [selected?.id],
    }
  );

  const queue = async (fn: () => Promise<unknown>) => {
    try {
      const res = await fn();
      const env = res as {
        success: boolean;
        data?: { job_id: number; dedupe_key: string };
        error?: { code: string; message: string };
      };
      setActionMsg(
        env.success
          ? `Queued job ${env.data?.job_id} (${env.data?.dedupe_key}). It will run once Phase 7 workers land.`
          : `HTTP ${env.error?.code}: ${env.error?.message}`
      );
      setSelected(null);
      jobs.reload();
    } catch (e) {
      setActionMsg(e instanceof Error ? e.message : String(e));
    }
  };

  return (
    <PageContainer
      title="Jobs & Pipeline"
      subtitle="The real collection_jobs queue. Nothing is auto-triggered on page open; every action below is explicit."
    >
      <Card className="mb-4">
        <CardHeader
          title="Admin access (X-API-Key)"
          right={
            configured ? (
              <StatusBadge tone="ok">authenticated</StatusBadge>
            ) : (
              <StatusBadge tone="warn">unauthenticated</StatusBadge>
            )
          }
        />
        <Body>
          <p className="mb-3 text-xs leading-relaxed text-muted">
            Jobs are an admin-protected resource. Paste your admin key to load them. The key is held
            in memory for this session only — it is not written to storage, not a build-time
            variable, and is cleared on reload.
          </p>
          <div className="flex flex-wrap items-center gap-2">
            <input
              type="password"
              value={keyInput}
              onChange={(e) => setKeyInput(e.target.value)}
              placeholder="Paste admin key…"
              className="w-64 rounded border border-ink-600 bg-ink-900 px-3 py-1.5 font-mono text-xs text-slate-200 placeholder:text-muted/40 focus:border-accent focus:outline-none"
              autoComplete="off"
              spellCheck={false}
            />
            <button
              onClick={() => {
                setKey(keyInput);
                setKeyInput("");
              }}
              className="rounded border border-accent/40 px-3 py-1.5 text-xs text-accent hover:bg-accent/10"
            >
              Use key
            </button>
            {configured ? (
              <button
                onClick={() => {
                  clearKey();
                  setSelected(null);
                }}
                className="rounded border border-ink-600 px-3 py-1.5 text-xs text-muted hover:text-neg"
              >
                Clear
              </button>
            ) : null}
            <span className="text-xs text-muted/60">
              {configured ? "Authenticated for this session." : "No key → protected requests are not sent."}
            </span>
          </div>
          {actionMsg ? <p className="mt-2 text-xs text-muted">{actionMsg}</p> : null}
        </Body>
      </Card>

      {configured && jobs.status === "no_key" ? (
        <EmptyState title="No admin key in this session" hint="Paste the key above to load the job queue." />
      ) : configured && jobs.status === "success" && jobs.data?.length === 0 ? (
        <EmptyState
          title="Queue is empty"
          hint="No collection or training jobs yet. Queue one explicitly below."
        />
      ) : configured && jobs.status === "error" ? (
        <ErrorState
          title={jobs.httpStatus === 401 ? "Admin key rejected (401)" : "Could not load jobs"}
          detail={jobs.error?.message}
          onRetry={jobs.reload}
        />
      ) : configured && jobs.status === "success" ? (
        <Card>
          <CardHeader title="Jobs" right={<span className="text-xs text-muted">{jobs.data?.length} rows</span>} />
          <div className="max-h-96 overflow-y-auto">
            <DataTable
              columns={JOB_COLS}
              rows={jobs.data ?? []}
              rowKey={(j) => j.id}
            />
          </div>
        </Card>
      ) : null}

      {configured ? (
        <div className="mt-4 grid gap-4 lg:grid-cols-2">
          <Card>
            <CardHeader title="Queue a collection job (explicit action)" />
            <Body>
              <label className="mb-1 block text-xs text-muted">Ticker</label>
              <input
                id="collect-ticker"
                placeholder="e.g. DEMO-HK-001"
                className="mb-2 w-full rounded border border-ink-600 bg-ink-900 px-3 py-1.5 font-mono text-xs text-slate-200 focus:border-accent focus:outline-none"
              />
              <label className="mb-1 block text-xs text-muted">Source</label>
              <select
                id="collect-source"
                className="mb-3 w-full rounded border border-ink-600 bg-ink-900 px-3 py-1.5 text-xs text-slate-200 focus:border-accent focus:outline-none"
                defaultValue="all"
              >
                <option value="all">all</option>
                <option value="social">social</option>
                <option value="news">news</option>
              </select>
              <button
                onClick={() =>
                  queue(() =>
                    queueCollect({
                      tickers: [(document.getElementById("collect-ticker") as HTMLInputElement | null)?.value?.trim() || ""].filter(Boolean),
                      source: ((document.getElementById("collect-source") as HTMLSelectElement | null)?.value as "all" | "social" | "news") || "all",
                    })
                  )
                }
                className="rounded border border-accent/40 px-3 py-1.5 text-xs text-accent hover:bg-accent/10"
              >
                Queue collection
              </button>
            </Body>
          </Card>

          <Card>
            <CardHeader title="Queue a training job (explicit action)" />
            <Body>
              <label className="mb-1 block text-xs text-muted">Model name</label>
              <input
                placeholder="e.g. ridge-v1"
                className="mb-3 w-full rounded border border-ink-600 bg-ink-900 px-3 py-1.5 font-mono text-xs text-slate-200 focus:border-accent focus:outline-none"
                id="train-name"
              />
              <button
                onClick={() =>
                  queue(() => queueTrain({ model_name: (document.getElementById("train-name") as HTMLInputElement | null)?.value?.trim() || null }))
                }
                className="rounded border border-accent/40 px-3 py-1.5 text-xs text-accent hover:bg-accent/10"
              >
                Queue training
              </button>
            </Body>
          </Card>
        </div>
      ) : null}

      {selected ? (
        <div className="mt-4">
          <Card>
            <CardHeader
              title={`Job #${selected.id}`}
              right={
                <button onClick={() => setSelected(null)} className="text-xs text-muted hover:text-slate-200">
                  close
                </button>
              }
            />
            <Body>
              <div className="mb-3 flex flex-wrap items-center gap-2 text-xs">
                <StatusBadge tone="info">{detail.data?.status ?? selected.status}</StatusBadge>
                <span className="font-mono text-muted">{fmtText(detail.data?.dedupe_key)}</span>
              </div>
              <pre className="mb-3 max-h-40 overflow-auto rounded bg-ink-900 p-3 font-mono text-xs text-slate-300">
                {JSON.stringify(detail.data?.params ?? selected.params ?? null, null, 2)}
              </pre>
              <ApiResponsePanel state={detail} endpoint={`/api/jobs/${selected.id}`} />
            </Body>
          </Card>
        </div>
      ) : null}

      {configured ? (
        <div className="mt-4">
          <ApiResponsePanel state={jobs} endpoint="/api/jobs" />
        </div>
      ) : null}
    </PageContainer>
  );
}
