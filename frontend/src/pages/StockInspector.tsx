import { useMemo, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
  Bar,
  BarChart,
} from "recharts";
import { useApi } from "../hooks/useApi";
import {
  getAsset,
  listNews,
  listPosts,
  listPrices,
  listAssets,
  getSentiment,
  listPredictions,
} from "../api/endpoints";
import {
  Card,
  CardHeader,
  Body,
  EmptyState,
  ErrorState,
  PageContainer,
} from "../components/states";
import { DataModeBadge, StatusBadge } from "../components/StatusBadge";
import { ChartContainer } from "../components/ChartContainer";
import { DataTable, type Column } from "../components/DataTable";
import { fmtDate, fmtNum, fmtPct, fmtText } from "../utils/format";
import type {
  Asset,
  Envelope,
  MarketPrice,
  NewsArticle,
  Prediction,
  SentimentData,
  SocialPost,
} from "../types/api";

export function StockInspector() {
  const assets = useApi<Envelope<Asset[]>, Asset[]>(() => listAssets({ limit: 200 }));
  const [ticker, setTicker] = useState<string | null>(null);
  const chosen = ticker ?? assets.data?.[0]?.ticker ?? null;

  return (
    <PageContainer
      title="Stock Inspector"
      subtitle="Asset detail: prices, social, news, sentiment and predictions exactly as the API returned them."
    >
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <label className="text-xs text-muted" htmlFor="ticker">Asset</label>
        <select
          id="ticker"
          value={chosen ?? ""}
          onChange={(e) => setTicker(e.target.value)}
          disabled={assets.status === "loading" || (assets.data?.length ?? 0) === 0}
          className="rounded border border-ink-600 bg-ink-900 px-3 py-1.5 text-sm text-slate-200 focus:border-accent focus:outline-none disabled:opacity-50"
        >
          {(assets.data ?? []).map((a) => (
            <option key={a.ticker} value={a.ticker}>
              {a.ticker}
              {a.is_demo ? " · DEMO" : ""}
            </option>
          ))}
        </select>
        {chosen ? <DataModeBadge mode={assets.data?.find((a) => a.ticker === chosen)?.is_demo ? "demo" : "live"} /> : null}
      </div>

      {assets.status === "error" ? (
        <ErrorState title="Could not load assets" detail={assets.error?.message} onRetry={assets.reload} />
      ) : chosen ? (
        <InspectorContent key={chosen} ticker={chosen} />
      ) : (
        <EmptyState
          title="No assets available in this data mode"
          hint="Assets are listed by /api/assets. In live mode the universe is empty until assets are confirmed and seeded."
        />
      )}
    </PageContainer>
  );
}

function InspectorContent({ ticker }: { ticker: string }) {
  const asset = useApi<Envelope<Asset>, Asset>(() => getAsset(ticker), { deps: [ticker] });
  const prices = useApi<Envelope<MarketPrice[]>, MarketPrice[]>(() => listPrices(ticker, { limit: 200 }), { deps: [ticker] });
  const posts = useApi<Envelope<SocialPost[]>, SocialPost[]>(() => listPosts(ticker, { limit: 50 }), { deps: [ticker] });
  const news = useApi<Envelope<NewsArticle[]>, NewsArticle[]>(() => listNews(ticker, { limit: 25 }), { deps: [ticker] });
  const sentiment = useApi<Envelope<SentimentData>, SentimentData>(() => getSentiment(ticker), { deps: [ticker] });
  const predictions = useApi<Envelope<Prediction[]>, Prediction[]>(() => listPredictions(ticker, { limit: 50 }), { deps: [ticker] });

  const demo = asset.data?.is_demo;

  return (
    <div className="space-y-4">
      {asset.status === "error" ? (
        <ErrorState
          title={`Asset ${ticker} not available`}
          detail={asset.error?.message}
          onRetry={asset.reload}
        />
      ) : (
        <Card>
          <CardHeader
            title={`${ticker} ${asset.data?.name ? `— ${asset.data.name}` : ""}`}
            right={
              <div className="flex items-center gap-2">
                {demo ? <StatusBadge tone="warn">synthetic</StatusBadge> : <StatusBadge tone="ok">live</StatusBadge>}
                <StatusBadge tone={asset.data?.confirmed ? "ok" : "warn"}>
                  {asset.data?.confirmed ? "confirmed" : "pending"}
                </StatusBadge>
                <DataModeBadge mode={asset.data?.is_demo ? "demo" : "live"} />
              </div>
            }
          />
          <Body>
            <div className="grid grid-cols-2 gap-3 text-xs lg:grid-cols-4">
              <Field k="Exchange" v={fmtText(asset.data?.exchange)} />
              <Field k="Provider ticker" v={asset.data?.provider_ticker ?? "null"} />
              <Field k="Provider" v={fmtText(asset.data?.market_data_provider)} />
              <Field k="Active" v={String(asset.data?.active ?? "—")} />
            </div>
          </Body>
        </Card>
      )}

      <PriceChart prices={prices.data ?? []} />

      <div className="grid gap-4 lg:grid-cols-2">
        <SentimentPanel sentiment={sentiment.data} state={sentiment.status} ticker={ticker} />
        <PredictionsPanel predictions={predictions.data ?? []} state={predictions.status} />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <SocialPanel posts={posts.data ?? []} state={posts.status} ticker={ticker} />
        <NewsPanel news={news.data ?? []} state={news.status} ticker={ticker} />
      </div>

      <SupportResistanceNote />
    </div>
  );
}

function Field({ k, v }: { k: string; v: string }) {
  return (
    <div>
      <div className="text-muted">{k}</div>
      <div className="font-mono text-slate-200">{v}</div>
    </div>
  );
}

function PriceChart({ prices, }: { prices: MarketPrice[] }) {
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
    last && first && first.close !== null && last.close !== null ? ((last.close - first.close) / first.close) * 100 : null;

  return (
    <Card>
      <CardHeader
        title="Market prices"
        right={
          <span className="text-xs text-muted">
            {data.length} rows · provider: {fmtText(prices[0]?.provider)}
            {delta !== null ? ` · period ${delta >= 0 ? "+" : ""}${delta.toFixed(2)}%` : ""}
          </span>
        }
      />
      <ChartContainer empty={data.length === 0} emptyHint="No price rows returned. Market-data fetching arrives in Phase 5 — nothing is fabricated here.">
        <ResponsiveContainer width="100%" height={240}>
          <LineChart data={data} margin={{ top: 8, right: 12, bottom: 4, left: 0 }}>
            <CartesianGrid stroke="#242f40" strokeDasharray="2 4" vertical={false} />
            <XAxis dataKey="trade_date" tick={{ fill: "#8b98ab", fontSize: 11 }} tickFormatter={(v: string) => v.slice(5)} minTickGap={32} />
            <YAxis tick={{ fill: "#8b98ab", fontSize: 11 }} domain={["auto", "auto"]} width={56} tickFormatter={(v: number) => v.toFixed(1)} />
            <Tooltip
              contentStyle={{ background: "#0f141c", border: "1px solid #242f40", borderRadius: 8, fontSize: 12 }}
              labelStyle={{ color: "#8b98ab" }}
              formatter={(value, name) => [
                `${value}` ,
                name as string,
              ]}
            />
            <ReferenceLine y={first?.close ?? 0} stroke="#33405a" strokeDasharray="4 4" />
            <Line type="monotone" dataKey="close" name="close" stroke="#38bdf8" dot={false} strokeWidth={1.75} />
            <Line type="monotone" dataKey="open" name="open" stroke="#8b98ab" dot={false} strokeWidth={1} strokeOpacity={0.5} />
            <Line type="monotone" dataKey="high" name="high" stroke="#34d399" dot={false} strokeWidth={0.75} strokeOpacity={0.45} />
            <Line type="monotone" dataKey="low" name="low" stroke="#f87171" dot={false} strokeWidth={0.75} strokeOpacity={0.45} />
          </LineChart>
        </ResponsiveContainer>
      </ChartContainer>
    </Card>
  );
}

function SentimentPanel({
  sentiment: s,
  state,
}: {
  sentiment: import("../types/api").SentimentData | null | undefined;
  state: string;
  ticker: string;
}) {
  const rows = s
    ? [
        { name: "positive", value: (s.p_pos ?? 0) * 100, fill: "#34d399" },
        { name: "neutral", value: (s.p_neu ?? 0) * 100, fill: "#8b98ab" },
        { name: "negative", value: (s.p_neg ?? 0) * 100, fill: "#f87171" },
      ]
    : [];
  const noData = state === "error" || !s || s.state === "no_data";
  const score = s?.score ?? null;

  return (
    <Card>
      <CardHeader
        title="Sentiment (10-day window)"
        right={s ? <StatusBadge tone={s.state === "sufficient" ? "ok" : "warn"}>{s.state}</StatusBadge> : null}
      />
      <Body>
        {noData ? (
          <EmptyState
            title="No sentiment results"
            hint="Sentiment scoring arrives in Phase 6. Showing the API's honest state — no generated scores."
          />
        ) : (
          <>
            <div className="mb-3 flex items-end gap-4">
              <div>
                <div className="text-xs text-muted">score (P⁺ − P⁻)</div>
                <div
                  className={`text-2xl font-semibold ${
                    (score ?? 0) > 0.15 ? "text-pos" : (score ?? 0) < -0.15 ? "text-neg" : "text-slate-100"
                  }`}
                >
                  {fmtNum(score)}
                </div>
              </div>
              <div>
                <div className="text-xs text-muted">signal</div>
                <div className="text-lg font-medium text-slate-100">{s.signal ?? "—"}</div>
              </div>
              <div>
                <div className="text-xs text-muted">items</div>
                <div className="text-lg font-medium text-slate-100">{s.total_items}</div>
              </div>
            </div>
            <ResponsiveContainer width="100%" height={120}>
              <BarChart data={rows} layout="vertical" barCategoryGap={8}>
                <XAxis type="number" hide domain={[0, 100]} />
                <YAxis type="category" dataKey="name" tick={{ fill: "#8b98ab", fontSize: 11 }} width={64} />
                <Tooltip
                  contentStyle={{ background: "#0f141c", border: "1px solid #242f40", borderRadius: 8, fontSize: 12 }}
                  formatter={(v, n) => [`${fmtNum(Number(v) / 100)} · ${s.counts[n as keyof typeof s.counts] ?? 0}`, n as string]}
                />
                {rows.map((r) => (
                  <Bar key={r.name} dataKey="value" stackId="a" fill={r.fill} />
                ))}
              </BarChart>
            </ResponsiveContainer>
          </>
        )}
      </Body>
    </Card>
  );
}

function PredictionsPanel({
  predictions,
  state,
}: {
  predictions: Prediction[];
  state: string;
}) {
  const noData = state === "error" || predictions.length === 0;
  const chartData = predictions.map((p) => ({
    target_date: p.target_date,
    predicted: p.predicted_return,
    actual: p.actual_close,
  }));
  const hasAnyValue = predictions.some((p) => p.predicted_return !== null);
  const experimental = predictions[0]?.experimental;

  return (
    <Card>
      <CardHeader
        title="Next-day predictions"
        right={experimental ? <StatusBadge tone="warn">experimental</StatusBadge> : null}
      />
      <Body>
        {noData ? (
          <EmptyState
            title="No predictions"
            hint="Model predictions arrive in Phase 8. Nothing is generated on the frontend."
          />
        ) : (
          <>
            <ChartContainer empty={!hasAnyValue} emptyHint="Rows exist but carry no predicted_return values yet.">
              <ResponsiveContainer width="100%" height={180}>
                <ScatterChart>
                  <CartesianGrid stroke="#242f40" strokeDasharray="2 4" />
                  <XAxis dataKey="target_date" tick={{ fill: "#8b98ab", fontSize: 10 }} tickFormatter={(v: string) => v.slice(5)} type="category" />
                  <YAxis dataKey="predicted" tick={{ fill: "#8b98ab", fontSize: 11 }} tickFormatter={(v: number) => `${(v * 100).toFixed(1)}%`} domain={["auto", "auto"]} width={52} />
                  <ZAxis range={[36, 36]} />
                  <Tooltip
                    contentStyle={{ background: "#0f141c", border: "1px solid #242f40", borderRadius: 8, fontSize: 12 }}
                    formatter={(v, n) => {
                      const name = String(n);
                      return name === "predicted"
                        ? [fmtPct((v as number) ?? null), "predicted return"]
                        : [fmtText(name), name];
                    }}
                  />
                  <Scatter data={chartData} fill="#38bdf8" />
                </ScatterChart>
              </ResponsiveContainer>
            </ChartContainer>
            <div className="mt-3">
              <DataTable
                columns={
                  [
                    { key: "target_date", header: "Target", render: (p: Prediction) => p.target_date },
                    { key: "model_version", header: "Model" },
                    {
                      key: "predicted_return",
                      header: "Pred. return",
                      align: "right",
                      render: (p: Prediction) => (p.predicted_return === null ? "—" : fmtPct(p.predicted_return)),
                    },
                    {
                      key: "actual_close",
                      header: "Actual close",
                      align: "right",
                      render: (p: Prediction) =>
                        p.actual_close === null ? <StatusBadge tone="neutral">pending</StatusBadge> : fmtNum(p.actual_close),
                    },
                  ] as Column<Prediction>[]
                }
                rows={predictions}
                rowKey={(p) => p.id}
              />
            </div>
            <p className="mt-2 text-xs text-muted/60">
              Experimental estimates for research only — not financial advice. actual_close stays null until backfilled by a real run.
            </p>
          </>
        )}
      </Body>
    </Card>
  );
}

const POST_COLS: Column<import("../types/api").SocialPost>[] = [
  { key: "source", header: "Source", render: (p) => p.source },
  {
    key: "content",
    header: "Content",
    render: (p) => (
      <span className="block max-w-[28ch] truncate" title={p.content}>
        {p.content}
      </span>
    ),
  },
  {
    key: "engagement",
    header: "Eng.",
    align: "right",
    render: (p) => (p.engagement === null ? <span className="text-muted/50">null</span> : p.engagement),
  },
  { key: "published_at", header: "Published", render: (p) => fmtDate(p.published_at) },
];

function SocialPanel({ posts, state, ticker }: { posts: import("../types/api").SocialPost[]; state: string; ticker: string }) {
  const noData = state === "error" || posts.length === 0;
  return (
    <Card>
      <CardHeader title={`Social posts · ${ticker}`} right={<span className="text-xs text-muted">{posts.length} rows</span>} />
      <Body>
        {noData ? (
          <EmptyState title="No social posts" hint="Social collection arrives in Phase 5. Rows are empty until then." />
        ) : (
          <div className="max-h-64 overflow-y-auto">
            <DataTable columns={POST_COLS} rows={posts} rowKey={(p) => p.id} />
          </div>
        )}
      </Body>
    </Card>
  );
}

const NEWS_COLS: Column<import("../types/api").NewsArticle>[] = [
  { key: "source", header: "Source" },
  { key: "title", header: "Title", render: (n) => n.title },
  { key: "published_at", header: "Published", render: (n) => fmtDate(n.published_at) },
];

function NewsPanel({ news, state, ticker }: { news: import("../types/api").NewsArticle[]; state: string; ticker: string }) {
  const noData = state === "error" || news.length === 0;
  return (
    <Card>
      <CardHeader title={`News · ${ticker}`} right={<span className="text-xs text-muted">{news.length} rows</span>} />
      <Body>
        {noData ? (
          <EmptyState title="No news articles" hint="News collection arrives in Phase 5. Rows are empty until then." />
        ) : (
          <div className="max-h-64 overflow-y-auto">
            <DataTable columns={NEWS_COLS} rows={news} rowKey={(n) => n.id} />
          </div>
        )}
      </Body>
    </Card>
  );
}

function SupportResistanceNote() {
  return (
    <Card>
      <CardHeader title="Support & resistance" />
      <Body>
        <p className="text-xs text-muted">
          Not provided by the API in the current phase. This section will be populated when the
          feature/support-resistance module ships (Phase 8). No values are estimated or generated here.
        </p>
      </Body>
    </Card>
  );
}
