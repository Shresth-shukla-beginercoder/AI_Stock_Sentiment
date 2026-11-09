import { useMemo } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { useApi } from "../hooks/useApi";
import { listEvaluations, listModelVersions } from "../api/endpoints";
import { PageContainer } from "../components/layout";
import {
  Card,
  CardContent,
  CardHeader,
  StatusBadge,
  DataModeBadge,
  DataTable,
  EmptyState,
  ErrorState,
  type Column,
} from "../components/common";
import { fmtDate, fmtNum, fmtPct } from "../utils/format";
import type { Envelope, ModelEvaluation, ModelVersionsData } from "../types/api";

const EVAL_COLS: Column<ModelEvaluation>[] = [
  { key: "model_version", header: "Version", render: (e) => <span className="font-mono text-xs">{e.model_version}</span> },
  { key: "mae", header: "MAE", align: "right", render: (e) => fmtNum(e.mae) },
  { key: "rmse", header: "RMSE", align: "right", render: (e) => fmtNum(e.rmse) },
  { key: "directional_accuracy", header: "Dir. acc.", align: "right", render: (e) => fmtPct(e.directional_accuracy ?? null, 1) },
  {
    key: "baselines",
    header: "Baselines (dir. acc.)",
    align: "right",
    render: (e) => (
      <span className="font-mono text-xs text-muted">
        no-change {fmtPct(e.baseline_nochange_dir_acc ?? null, 0)} · always-up {fmtPct(e.baseline_alwaysup_dir_acc ?? null, 0)}
      </span>
    ),
  },
  { key: "n_test", header: "n test", align: "right", render: (e) => (e.n_test === null ? "—" : e.n_test) },
  {
    key: "git_commit",
    header: "Commit",
    render: (e) =>
      e.git_commit ? (
        <span className="font-mono text-xs text-text-primary" title={e.git_commit}>{e.git_commit.slice(0, 12)}</span>
      ) : (
        <StatusBadge tone="neutral">unrecorded</StatusBadge>
      ),
  },
  { key: "trained_at", header: "Trained", render: (e) => fmtDate(e.trained_at) },
];

export function ModelPerformance() {
  const evals = useApi<Envelope<ModelEvaluation[]>, ModelEvaluation[]>(() => listEvaluations({ limit: 50 }));
  const versions = useApi<Envelope<ModelVersionsData>, ModelVersionsData>(() => listModelVersions());

  const chartData = useMemo(
    () =>
      (evals.data ?? [])
        .filter((e) => e.directional_accuracy !== null || e.baseline_nochange_dir_acc !== null)
        .map((e) => ({
          version: e.model_version,
          model: e.directional_accuracy,
          "no-change": e.baseline_nochange_dir_acc,
          "always-up": e.baseline_alwaysup_dir_acc,
        })),
    [evals.data]
  );

  const noModels = evals.status === "success" && (evals.data?.length ?? 0) === 0;

  return (
    <PageContainer
      title="Model Performance"
      subtitle="Walk-forward evaluation metrics, exactly as the API reports them."
    >
      <div className="space-y-6">
        {/* Versions strip */}
        <div className="flex flex-wrap items-center gap-2">
          {versions.data?.versions.length ? (
            versions.data.versions.map((v) => <StatusBadge key={v} tone="neutral">{v}</StatusBadge>)
          ) : (
            <StatusBadge tone="warn">no model versions registered</StatusBadge>
          )}
          <DataModeBadge mode={evals.dataMode} />
        </div>

        {evals.status === "error" ? (
          <ErrorState title="Could not load evaluations" message={evals.error?.message} onRetry={evals.reload} />
        ) : noModels ? (
          <EmptyState
            title="No trained model"
            description="model_evaluations is empty until a real training run persists metrics. Nothing is generated here."
          />
        ) : (
          <div className="space-y-4">
            {chartData.length > 0 && (
              <Card>
                <CardHeader title="Directional Accuracy vs Baselines" />
                <CardContent>
                  <ResponsiveContainer width="100%" height={240}>
                    <BarChart data={chartData} barCategoryGap={12}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#1a1f2e" vertical={false} />
                      <XAxis dataKey="version" tick={{ fill: "#94a3b8", fontSize: 11 }} axisLine={{ stroke: "#1a1f2e" }} tickLine={false} />
                      <YAxis
                        tick={{ fill: "#94a3b8", fontSize: 11 }}
                        tickFormatter={(v: number) => `${(v * 100).toFixed(0)}%`}
                        domain={[0, 1]}
                        width={48}
                        axisLine={false}
                        tickLine={false}
                      />
                      <Tooltip
                        contentStyle={{
                          background: "#111827",
                          border: "1px solid rgba(255,255,255,0.1)",
                          borderRadius: "8px",
                          fontSize: "12px",
                        }}
                        formatter={(v, n) => [fmtPct((v as number) ?? null, 1), String(n)]}
                      />
                      <Legend wrapperStyle={{ fontSize: 12 }} />
                      <Bar dataKey="model" fill="#3b82f6" radius={[4, 4, 0, 0]} />
                      <Bar dataKey="no-change" fill="#94a3b8" radius={[4, 4, 0, 0]} />
                      <Bar dataKey="always-up" fill="#ef4444" radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </CardContent>
              </Card>
            )}

            <Card>
              <CardHeader title="Evaluations" subtitle={`${evals.data?.length} rows`} />
              <div className="max-h-96 overflow-y-auto">
                <DataTable columns={EVAL_COLS} rows={evals.data ?? []} rowKey={(e) => e.id} />
              </div>
            </Card>
          </div>
        )}

        <Card>
          <CardHeader title="Raw Response" subtitle="GET /api/models/evaluation — exactly as received" />
          <CardContent>
            <pre className="max-h-64 overflow-auto rounded-lg bg-bg-tertiary/50 p-3 font-mono text-xs text-text-secondary">
              {evals.raw ? JSON.stringify(evals.raw, null, 2) : "—"}
            </pre>
          </CardContent>
        </Card>
      </div>
    </PageContainer>
  );
}
