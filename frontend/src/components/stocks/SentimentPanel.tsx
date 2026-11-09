import {
  Bar,
  BarChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Card, CardContent, CardHeader } from "../common/Card";
import { StatusBadge } from "../common/StatusBadge";
import { SentimentMeter } from "./SentimentMeter";
import type { SentimentData } from "../../types/api";

interface SentimentPanelProps {
  sentiment: SentimentData | null;
}

export function SentimentPanel({ sentiment }: SentimentPanelProps) {
  if (!sentiment) {
    return (
      <Card>
        <CardHeader title="Sentiment Analysis" />
        <CardContent>
          <p className="text-sm text-muted">No sentiment data available</p>
        </CardContent>
      </Card>
    );
  }

  const { score, state, counts, total_items } = sentiment;
  const hasData = state === "sufficient";

  const chartData = [
    { name: "Positive", value: (sentiment.p_pos ?? 0) * 100, fill: "#10b981" },
    { name: "Neutral", value: (sentiment.p_neu ?? 0) * 100, fill: "#94a3b8" },
    { name: "Negative", value: (sentiment.p_neg ?? 0) * 100, fill: "#ef4444" },
  ];

  return (
    <Card>
      <CardHeader
        title="Sentiment Analysis"
        action={
          <div className="flex items-center gap-2">
            <StatusBadge tone={hasData ? "pos" : "warn"}>
              {hasData ? "Sufficient" : "Insufficient"}
            </StatusBadge>
          </div>
        }
      />
      <CardContent>
        {/* Animated sentiment meter */}
        <div className="mb-6">
          <SentimentMeter score={score} />
        </div>

        {/* Score / items row */}
        <div className="flex items-center gap-6 mb-6">
          <div>
            <p className="text-[10px] uppercase tracking-wider text-muted">Score</p>
            <p
              className={`font-display text-3xl font-bold tabular-nums ${
                score !== null && score > 0.15 ? "text-success" :
                score !== null && score < -0.15 ? "text-danger" :
                "text-text-primary"
              }`}
            >
              {score !== null ? score.toFixed(3) : "—"}
            </p>
          </div>
          <div>
            <p className="text-[10px] uppercase tracking-wider text-muted">Items</p>
            <p className="font-display text-2xl font-bold tabular-nums text-text-primary">{total_items}</p>
          </div>
        </div>

        {/* Bar Chart */}
        <div className="h-40">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData} layout="vertical" barCategoryGap={8}>
              <XAxis type="number" hide domain={[0, 100]} />
              <YAxis
                type="category"
                dataKey="name"
                tick={{ fill: "#94a3b8", fontSize: 11 }}
                width={70}
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
                formatter={(value: number, name: string) => [
                  `${(value / 100).toFixed(1)} (${counts[name.toLowerCase() as keyof typeof counts] || 0})`,
                  "Probability",
                ]}
              />
              {chartData.map((entry) => (
                <Bar key={entry.name} dataKey="value" fill={entry.fill} radius={[0, 4, 4, 0]} />
              ))}
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Counts */}
        <div className="mt-4 flex items-center justify-between text-xs text-muted">
          <span>10-day window</span>
          <div className="flex gap-4 font-mono">
            <span>Pos: {counts.positive}</span>
            <span>Neu: {counts.neutral}</span>
            <span>Neg: {counts.negative}</span>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}