import { useMemo } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Card, CardContent, CardHeader } from "../common/Card";
import type { MarketPrice } from "../../types/api";

interface StockChartProps {
  prices: MarketPrice[];
}

export function StockChart({ prices }: StockChartProps) {
  const data = useMemo(
    () =>
      [...prices]
        .sort((a, b) => a.trade_date.localeCompare(b.trade_date))
        .filter((p) => p.close !== null),
    [prices]
  );

  const last = data[data.length - 1];
  const first = data[0];
  const delta =
    last && first && first.close !== null && last.close !== null
      ? ((last.close - first.close) / first.close) * 100
      : null;

  const formatDate = (date: string) => {
    const d = new Date(date);
    return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
  };

  if (data.length === 0) {
    return (
      <Card>
        <CardHeader title="Price History" />
        <CardContent>
          <p className="text-sm text-muted">No price data available</p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader
        title="Price History"
        action={
          <span className="text-xs text-muted">
            {data.length} data points
            {delta !== null && (
              <span className={delta >= 0 ? "text-pos ml-2" : "text-neg ml-2"}>
                {delta >= 0 ? "+" : ""}
                {delta.toFixed(2)}%
              </span>
            )}
          </span>
        }
      />
      <CardContent>
        <ResponsiveContainer width="100%" height={280}>
          <LineChart data={data} margin={{ top: 10, right: 12, bottom: 10, left: 0 }}>
            <defs>
              <linearGradient id="priceGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#3b82f6" stopOpacity={0.3} />
                <stop offset="100%" stopColor="#3b82f6" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#1a1f2e" vertical={false} />
            <XAxis
              dataKey="trade_date"
              tick={{ fill: "#94a3b8", fontSize: 11 }}
              tickFormatter={formatDate}
              axisLine={{ stroke: "#1a1f2e" }}
              tickLine={{ stroke: "#1a1f2e" }}
            />
            <YAxis
              tick={{ fill: "#94a3b8", fontSize: 11 }}
              domain={["auto", "auto"]}
              width={60}
              tickFormatter={(v) => v.toFixed(1)}
              axisLine={{ stroke: "#1a1f2e" }}
              tickLine={{ stroke: "#1a1f2e" }}
            />
            <Tooltip
              contentStyle={{
                background: "#111827",
                border: "1px solid rgba(255,255,255,0.1)",
                borderRadius: "8px",
                fontSize: "12px",
              }}
              labelStyle={{ color: "#94a3b8" }}
              formatter={(value: number) => [value.toFixed(2), "Close"]}
              labelFormatter={formatDate}
            />
            {first?.close && (
              <ReferenceLine
                y={first.close}
                stroke="#3f4654"
                strokeDasharray="4 4"
              />
            )}
            <Line
              type="monotone"
              dataKey="close"
              stroke="#3b82f6"
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 4, fill: "#3b82f6" }}
            />
          </LineChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}