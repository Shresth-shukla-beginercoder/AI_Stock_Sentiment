import { useState } from "react";
import { motion } from "framer-motion";
import { useApi } from "../hooks/useApi";
import { useAdminAuth } from "../hooks/useAdminAuth";
import { listJobs, getJob, queueCollect, queueTrain } from "../api/endpoints";
import { PageContainer } from "../components/layout";
import {
  Card,
  CardContent,
  CardHeader,
  StatusBadge,
  DataTable,
  EmptyState,
  ErrorState,
  Button,
  type Column,
} from "../components/common";
import { fmtDate, fmtText } from "../utils/format";
import type { Envelope, Job } from "../types/api";

const JOB_COLS: Column<Job>[] = [
  { key: "id", header: "ID", align: "right", width: "64px" },
  { key: "job_type", header: "Type", render: (j) => <span className="font-mono text-xs">{j.job_type}</span> },
  {
    key: "status",
    header: "Status",
    render: (j) => (
      <StatusBadge
        tone={
          j.status === "queued" ? "info" : j.status === "running" ? "warn" : j.status === "failed" ? "neg" : "neutral"
        }
      >
        {j.status}
      </StatusBadge>
    ),
  },
  {
    key: "dedupe_key",
    header: "Dedupe key",
    render: (j) => (
      <span className="block max-w-[36ch] truncate font-mono text-xs" title={j.dedupe_key}>
        {j.dedupe_key}
      </span>
    ),
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
  const [selected, setSelected] = useState<Job | null>(null);

  const jobs = useApi<Envelope<Job[]>, Job[]>(() => listJobs({ limit: 50 }), {
    requiresAdmin: true,
    reloadKey: configured,
    deps: [configured],
  });
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
      const res = (await fn()) as {
        success: boolean;
        data?: { job_id: number; dedupe_key: string };
        error?: { code: string; message: string };
      };
      setActionMsg(
        res.success
          ? `Queued job ${res.data?.job_id} (${res.data?.dedupe_key}).`
          : `HTTP ${res.error?.code}: ${res.error?.message}`
      );
      setSelected(null);
      jobs.reload();
    } catch (e) {
      setActionMsg(e instanceof Error ? e.message : String(e));
    }
  };

  return (
    <PageContainer title="Jobs & Pipeline" subtitle="The real collection_jobs queue. Every action below is explicit.">
      <div className="space-y-6">
        {/* Admin access */}
        <Card>
          <CardHeader
            title="Admin Access"
            subtitle="X-API-Key — held in memory for this session only, never persisted"
            action={
              <StatusBadge tone={configured ? "pos" : "warn"}>
                {configured ? "Authenticated" : "Unauthenticated"}
              </StatusBadge>
            }
          />
          <CardContent>
            <div className="flex flex-wrap items-center gap-2">
              <input
                type="password"
                value={keyInput}
                onChange={(e) => setKeyInput(e.target.value)}
                placeholder="Paste admin key…"
                autoComplete="off"
                spellCheck={false}
                className="w-64 rounded-lg border border-white/10 bg-bg-tertiary px-3 py-2 font-mono text-xs text-text-primary placeholder:text-muted/40 focus:border-accent-primary focus:outline-none"
              />
              <Button size="sm" variant="secondary" onClick={() => { setKey(keyInput); setKeyInput(""); }}>
                Use key
              </Button>
              {configured && (
                <Button size="sm" variant="ghost" onClick={() => { clearKey(); setSelected(null); }}>
                  Clear
                </Button>
              )}
            </div>
            {actionMsg && <p className="mt-3 text-xs text-muted">{actionMsg}</p>}
          </CardContent>
        </Card>

        {/* Job list */}
        {configured ? (
          jobs.status === "no_key" ? (
            <EmptyState title="No admin key" description="Paste the key above to load the job queue." />
          ) : jobs.status === "success" && jobs.data?.length === 0 ? (
            <EmptyState title="Queue is empty" description="No collection or training jobs yet. Queue one below." />
          ) : jobs.status === "error" ? (
            <ErrorState
              title={jobs.httpStatus === 401 ? "Admin key rejected (401)" : "Could not load jobs"}
              message={jobs.error?.message}
              onRetry={jobs.reload}
            />
          ) : jobs.status === "success" ? (
            <Card>
              <CardHeader title="Jobs" subtitle={`${jobs.data?.length} rows`} />
              <div className="max-h-96 overflow-y-auto">
                <DataTable columns={JOB_COLS} rows={jobs.data ?? []} rowKey={(j) => j.id} />
              </div>
            </Card>
          ) : null
        ) : null}

        {/* Queue forms */}
        {configured && (
          <div className="grid gap-4 lg:grid-cols-2">
            <QueueCollection onQueue={(tickers, source) => queue(() => queueCollect({ tickers, source }))} />
            <QueueTraining onQueue={(model_name) => queue(() => queueTrain({ model_name }))} />
          </div>
        )}

        {/* Selected job detail */}
        {selected && (
          <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}>
            <Card>
              <CardHeader
                title={`Job #${selected.id}`}
                action={
                  <button onClick={() => setSelected(null)} className="text-xs text-muted hover:text-text-primary">
                    close
                  </button>
                }
              />
              <CardContent>
                <div className="mb-3 flex flex-wrap items-center gap-2 text-xs">
                  <StatusBadge tone="info">{detail.data?.status ?? selected.status}</StatusBadge>
                  <span className="font-mono text-muted">{fmtText(detail.data?.dedupe_key)}</span>
                </div>
                <pre className="mb-3 max-h-40 overflow-auto rounded-lg bg-bg-tertiary/50 p-3 font-mono text-xs text-text-secondary">
                  {JSON.stringify(detail.data?.params ?? selected.params ?? null, null, 2)}
                </pre>
              </CardContent>
            </Card>
          </motion.div>
        )}
      </div>
    </PageContainer>
  );
}

function QueueCollection({ onQueue }: { onQueue: (tickers: string[], source: "all" | "social" | "news") => void }) {
  const [ticker, setTicker] = useState("");
  const [source, setSource] = useState<"all" | "social" | "news">("all");

  return (
    <Card>
      <CardHeader title="Queue Collection Job" />
      <CardContent className="space-y-3">
        <div>
          <label className="mb-1 block text-xs text-muted">Ticker</label>
          <input
            value={ticker}
            onChange={(e) => setTicker(e.target.value)}
            placeholder="e.g. DEMO-HK-001"
            className="w-full rounded-lg border border-white/10 bg-bg-tertiary px-3 py-2 font-mono text-xs text-text-primary placeholder:text-muted/40 focus:border-accent-primary focus:outline-none"
          />
        </div>
        <div>
          <label className="mb-1 block text-xs text-muted">Source</label>
          <select
            value={source}
            onChange={(e) => setSource(e.target.value as "all" | "social" | "news")}
            className="w-full rounded-lg border border-white/10 bg-bg-tertiary px-3 py-2 text-xs text-text-primary focus:border-accent-primary focus:outline-none"
          >
            <option value="all">all</option>
            <option value="social">social</option>
            <option value="news">news</option>
          </select>
        </div>
        <Button
          variant="secondary"
          onClick={() => onQueue([ticker.trim()].filter(Boolean), source)}
          disabled={!ticker.trim()}
        >
          Queue collection
        </Button>
      </CardContent>
    </Card>
  );
}

function QueueTraining({ onQueue }: { onQueue: (model_name: string | null) => void }) {
  const [name, setName] = useState("");

  return (
    <Card>
      <CardHeader title="Queue Training Job" />
      <CardContent className="space-y-3">
        <div>
          <label className="mb-1 block text-xs text-muted">Model name</label>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. ridge-v1"
            className="w-full rounded-lg border border-white/10 bg-bg-tertiary px-3 py-2 font-mono text-xs text-text-primary placeholder:text-muted/40 focus:border-accent-primary focus:outline-none"
          />
        </div>
        <Button variant="secondary" onClick={() => onQueue(name.trim() || null)}>
          Queue training
        </Button>
      </CardContent>
    </Card>
  );
}
