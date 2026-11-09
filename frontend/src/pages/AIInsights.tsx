import { useMemo, useState } from "react";
import { motion } from "framer-motion";
import { PageContainer } from "../components/layout";
import { Card, CardContent, CardHeader } from "../components/common/Card";
import { StatusBadge } from "../components/common/StatusBadge";
import { useApi } from "../hooks/useApi";
import { getRanking, getSentiment } from "../api/endpoints";
import { Send, Loader2, Info } from "lucide-react";
import type { Envelope, RankingRow, SentimentData } from "../types/api";

export function AIInsights() {
  const ranking = useApi<Envelope<RankingRow[]>, RankingRow[]>(() => getRanking());
  const rows = ranking.data ?? [];

  // Real tallies straight from /reports/ranking — no invented numbers.
  const summary = useMemo(() => {
    const withScore = rows.filter((r) => r.score !== null);
    const positive = rows.filter((r) => r.state === "positive").length;
    const negative = rows.filter((r) => r.state === "negative").length;
    const neutral = rows.length - positive - negative;
    const avg =
      withScore.length > 0
        ? withScore.reduce((sum, r) => sum + (r.score ?? 0), 0) / withScore.length
        : null;
    return { positive, negative, neutral, avg, total: rows.length, scored: withScore.length };
  }, [rows]);

  const covered = summary.total > 0;

  const skewWord =
    summary.avg === null ? "neutral" : summary.avg > 0.15 ? "positive" : summary.avg < -0.15 ? "negative" : "mixed";
  const skewClass =
    summary.avg === null
      ? "text-muted"
      : summary.avg > 0.15
      ? "text-success"
      : summary.avg < -0.15
      ? "text-danger"
      : "text-text-primary";
  const meanText =
    summary.avg === null ? null : ` (mean ${summary.avg > 0 ? "+" : ""}${summary.avg.toFixed(2)})`;

  return (
    <PageContainer
      title="AI Insights"
      subtitle="What the tracked universe is saying right now — computed live, nothing fabricated"
    >
      <div className="space-y-6">
        {/* Market Summary — real data */}
        <Card>
          <CardHeader
            title="Market Summary"
            action={
              <StatusBadge tone={covered ? "info" : "warn"}>
                {covered ? "Live data" : "No data yet"}
              </StatusBadge>
            }
          />
          <CardContent>
            {ranking.status === "loading" ? (
              <div className="flex items-center gap-2 text-sm text-muted">
                <Loader2 className="h-4 w-4 animate-spin" />
                <span>Loading ranking…</span>
              </div>
            ) : covered ? (
              <div className="space-y-4">
                <p className="text-sm leading-relaxed text-text-secondary">
                  Across{" "}
                  <span className="font-semibold text-text-primary">{summary.total}</span> tracked assets{" "}
                  <span className="font-mono text-glow-blue">({summary.scored} with a 10-day score)</span>,{" "}
                  sentiment skews{" "}
                  <span className={`font-semibold ${skewClass}`}>{skewWord}</span>
                  {meanText}.
                </p>
                <div className="flex flex-wrap gap-2">
                  <StatusBadge tone="pos">{summary.positive} Positive</StatusBadge>
                  <StatusBadge tone="neutral">{summary.neutral} Neutral</StatusBadge>
                  <StatusBadge tone="neg">{summary.negative} Negative</StatusBadge>
                </div>
              </div>
            ) : (
              <p className="text-sm text-muted">
                No ranking yet — sentiment appears once assets are collected and scored.
              </p>
            )}
          </CardContent>
        </Card>

        {/* Honest Ask-AI preview — no fake model response */}
        <AskAIBox />

        {/* Top sentiment signals — real per-ticker scores */}
        <Card>
          <CardHeader
            title="Top Sentiment Signals"
            subtitle="Highest-scoring assets from the live ranking"
          />
          <CardContent>
            {ranking.status === "loading" ? (
              <div className="flex items-center gap-2 text-sm text-muted">
                <Loader2 className="h-4 w-4 animate-spin" />
                <span>Loading signals…</span>
              </div>
            ) : rows.length > 0 ? (
              <div className="space-y-3">
                {rows
                  .filter((r) => r.score !== null)
                  .sort((a, b) => (b.score ?? 0) - (a.score ?? 0))
                  .slice(0, 5)
                  .map((row) => (
                    <SignalRow key={row.ticker} row={row} />
                  ))}
              </div>
            ) : (
              <p className="text-sm text-muted">No signals available yet.</p>
            )}
          </CardContent>
        </Card>
      </div>
    </PageContainer>
  );
}

function AskAIBox() {
  const [query, setQuery] = useState("");
  const [sent, setSent] = useState(false);

  return (
    <Card>
      <CardHeader
        title="Ask a question"
        subtitle="Natural-language querying is a preview — not yet wired to a model"
      />
      <CardContent>
        <div className="space-y-3">
          <div className="flex gap-3">
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="e.g. which asset has the strongest positive signal?"
              className="flex-1 rounded-lg border border-white/10 bg-navy/40 px-4 py-2.5 text-sm text-text-primary placeholder:text-muted focus:border-glow-blue focus:outline-none focus:ring-2 focus:ring-glow-blue/20 transition-all"
              onKeyDown={(e) => e.key === "Enter" && setSent(true)}
            />
            <button
              onClick={() => setSent(true)}
              disabled={!query.trim()}
              className="flex items-center justify-center rounded-lg bg-gradient-to-r from-glow-blue to-bell-amber px-4 py-2.5 text-sm font-semibold text-ink disabled:opacity-40"
            >
              <Send className="h-4 w-4" />
            </button>
          </div>
          {sent && (
            <motion.div
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              className="flex items-start gap-3 rounded-lg border border-glow-blue/20 bg-glow-blue/5 p-4"
            >
              <Info className="mt-0.5 h-4 w-4 text-glow-blue" />
              <p className="text-sm text-text-secondary">
                Natural-language answers aren't connected to a model yet. Use the{" "}
                <span className="font-semibold text-text-primary">ranking and signal lists</span> above —
                they reflect the real, current sentiment state.
              </p>
            </motion.div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

function SignalRow({ row }: { row: RankingRow }) {
  const detail = useApi<Envelope<SentimentData>, SentimentData>(
    () => getSentiment(row.ticker),
    { deps: [row.ticker] }
  );
  const signal = detail.data?.signal;
  const score = detail.data?.score ?? row.score;

  const tone = signal === "positive" ? "pos" : signal === "negative" ? "neg" : "neutral";

  return (
    <div className="flex items-center justify-between rounded-lg bg-navy/40 p-3">
      <div className="flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-gradient-to-br from-glow-blue/20 to-bell-amber/10 font-mono text-sm font-bold text-glow-blue">
          {row.ticker.slice(0, 2)}
        </div>
        <div>
          <p className="font-mono font-semibold text-text-primary">{row.ticker}</p>
          <p className="text-xs text-muted">{row.name || "—"}</p>
        </div>
      </div>
      <div className="flex items-center gap-3">
        <span className="font-display text-lg font-bold tabular-nums text-text-primary">
          {score !== null ? (score > 0 ? "+" : "") + score.toFixed(2) : "—"}
        </span>
        <StatusBadge tone={tone as "pos" | "neutral" | "neg"}>{signal ?? "neutral"}</StatusBadge>
      </div>
    </div>
  );
}
