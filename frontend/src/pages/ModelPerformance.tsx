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
import {
  Card,
  CardHeader,
  EmptyState,
  ErrorState,
  PageContainer,
} from "../components/states";
import { StatusBadge, DataModeBadge } from "../components/StatusBadge";
import { DataTable, type Column } from "../components/DataTable";
import { ApiResponsePanel } from "../components/ApiResponsePanel";
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
        <span className="font-mono text-xs text-slate-300" title={e.git_commit}>{e.git_commit.slice(0, 12)}</span>
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
      subtitle="Walk-forward evaluation metrics, exactly as the API reports them. No metrics are fabricated when a model does not exist."
    >
      <div className="mb-4 flex flex-wrap items-center gap-2">
        {versions.data?.versions.length ? (
          versions.data.versions.map((v) => (
            <StatusBadge key={v} tone="neutral">
              {v}
            </StatusBadge>
          ))
        ) : (
          <StatusBadge tone="warn">no model versions registered</StatusBadge>
        )}
        <DataModeBadge mode={evals.dataMode} />
        {noModels ? (
          <span className="text-xs text-muted">
            Training arrives in Phase 8 — until then this page stays an empty state.
          </span>
        ) : null}
      </div>

      {evals.status === "error" ? (
        <ErrorState title="Could not load evaluations" detail={evals.error?.message} onRetry={evals.reload} />
      ) : noModels ? (
        <EmptyState
          title="No trained model"
          hint="model_evaluations is empty until a real Phase 8 training run persists metrics. Nothing is generated on the frontend."
        />
      ) : (
        <div className="space-y-4">
          {chartData.length > 0 ? (
            <Card>
              <CardHeader title="Directional accuracy vs baselines" />
              <div className="p-3">
                <ResponsiveContainer width="100%" height={220}>
                  <BarChart data={chartData} barCategoryGap={12}>
                    <CartesianGrid stroke="#242f40" strokeDasharray="2 4" vertical={false} />
                    <XAxis dataKey="version" tick={{ fill: "#8b98ab", fontSize: 11 }} />
                    <YAxis
                      tick={{ fill: "#8b98ab", fontSize: 11 }}
                      tickFormatter={(v: number) => `${(v * 100).toFixed(0)}%`}
                      domain={[0, 1]}
                      width={48}
                    />
                    <Tooltip
                      contentStyle={{ background: "#0f141c", border: "1px solid #242f40", borderRadius: 8, fontSize: 12 }}
                      formatter={(v, n) => [fmtPct((v as number) ?? null, 1), String(n)]}
                    />
                    <Legend wrapperStyle={{ fontSize: 12 }} />
                    <Bar dataKey="model" fill="#38bdf8" />
                    <Bar dataKey="no-change" fill="#8b98ab" />
                    <Bar dataKey="always-up" fill="#f87171" />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </Card>
          ) : null}

          <Card>
            <CardHeader
              title="Evaluations"
              right={<span className="text-xs text-muted">{evals.data?.length} rows</span>}
            />
            <div className="max-h-96 overflow-y-auto">
              <DataTable columns={EVAL_COLS} rows={evals.data ?? []} rowKey={(e) => e.id} />
            </div>
          </Card>
        </div>
      )}

      <div className="mt-4">
        <ApiResponsePanel state={evals} endpoint="/api/models/evaluation" />
      </div>
    </PageContainer>
  );
}
