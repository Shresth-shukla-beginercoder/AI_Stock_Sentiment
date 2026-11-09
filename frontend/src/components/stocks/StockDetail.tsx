import { useApi } from "../../hooks/useApi";
import {
  getAsset,
  listPrices,
  listNews,
  listPosts,
  getSentiment,
  listPredictions,
} from "../../api/endpoints";
import { StockChart } from "./StockChart";
import { SentimentPanel } from "./SentimentPanel";
import { Card, CardContent, CardHeader } from "../common/Card";
import { StatusBadge, DataModeBadge } from "../common/StatusBadge";
import { EmptyState, LoadingSpinner } from "../common";
import { motion } from "framer-motion";
import { TrendingUp } from "lucide-react";
import type {
  Envelope,
  Asset,
  NewsArticle,
  SocialPost,
  Prediction,
  MarketPrice,
  SentimentData,
} from "../../types/api";

interface StockDetailProps {
  ticker: string;
}

export function StockDetail({ ticker }: StockDetailProps) {
  const asset = useApi<Envelope<Asset>, Asset>(() => getAsset(ticker), { deps: [ticker] });
  const prices = useApi<Envelope<MarketPrice[]>, MarketPrice[]>(() => listPrices(ticker, { limit: 100 }), { deps: [ticker] });
  const news = useApi<Envelope<NewsArticle[]>, NewsArticle[]>(() => listNews(ticker, { limit: 5 }), { deps: [ticker] });
  const posts = useApi<Envelope<SocialPost[]>, SocialPost[]>(() => listPosts(ticker, { limit: 5 }), { deps: [ticker] });
  const sentiment = useApi<Envelope<SentimentData>, SentimentData>(() => getSentiment(ticker), { deps: [ticker] });
  const predictions = useApi<Envelope<Prediction[]>, Prediction[]>(() => listPredictions(ticker, { limit: 10 }), { deps: [ticker] });

  if (asset.status === "loading") {
    return (
      <div className="flex items-center justify-center p-12">
        <LoadingSpinner size="lg" />
      </div>
    );
  }

  if (asset.status === "error") {
    return <EmptyState title="Failed to load stock" description={asset.error?.message} />;
  }

  if (!asset.data) {
    return <EmptyState title="Stock not found" description={`No data found for ${ticker}`} />;
  }

  const { data: a } = asset;

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className="space-y-6"
    >
      {/* Stock Header */}
      <Card>
        <CardContent className="p-5">
          <div className="flex items-start justify-between">
            <div className="flex items-center gap-4">
              <div className="flex h-14 w-14 items-center justify-center rounded-xl bg-gradient-to-br from-accent-primary to-accent-secondary font-mono text-xl font-bold text-white">
                {ticker.slice(0, 2)}
              </div>
              <div>
                <div className="flex items-center gap-3">
                  <h2 className="text-2xl font-bold text-text-primary">{a.ticker}</h2>
                  {a.is_demo && <DataModeBadge mode="demo" />}
                </div>
                <p className="text-sm text-muted">{a.name || a.exchange}</p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <StatusBadge tone={a.confirmed ? "pos" : "warn"}>
                {a.confirmed ? "Confirmed" : "Pending"}
              </StatusBadge>
              <StatusBadge tone={a.active ? "pos" : "neutral"}>
                {a.active ? "Active" : "Inactive"}
              </StatusBadge>
            </div>
          </div>

          <div className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-4">
            <div>
              <p className="text-[10px] uppercase text-muted">Exchange</p>
              <p className="text-sm font-medium text-text-primary">{a.exchange}</p>
            </div>
            <div>
              <p className="text-[10px] uppercase text-muted">Provider Ticker</p>
              <p className="text-sm font-medium text-text-primary font-mono">
                {a.provider_ticker || "—"}
              </p>
            </div>
            <div>
              <p className="text-[10px] uppercase text-muted">Provider</p>
              <p className="text-sm font-medium text-text-primary">
                {a.market_data_provider || "—"}
              </p>
            </div>
            <div>
              <p className="text-[10px] uppercase text-muted">Price Points</p>
              <p className="text-sm font-medium text-text-primary">
                {prices.data?.length || 0}
              </p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Price Chart */}
      <StockChart prices={prices.data || []} />

      {/* Sentiment & Predictions */}
      <div className="grid gap-6 lg:grid-cols-2">
        <SentimentPanel sentiment={sentiment.data} />

        <Card>
          <CardHeader
            title="Next-Day Predictions"
            action={
              predictions.data?.[0]?.experimental && (
                <StatusBadge tone="warn">Experimental</StatusBadge>
              )
            }
          />
          <CardContent>
            {predictions.data && predictions.data.length > 0 ? (
              <div className="space-y-3">
                {predictions.data.slice(0, 5).map((p) => (
                  <div
                    key={p.id}
                    className="flex items-center justify-between rounded-lg bg-bg-tertiary/50 p-3"
                  >
                    <div className="flex items-center gap-3">
                      <TrendingUp className="h-4 w-4 text-accent-primary" />
                      <div>
                        <p className="text-xs text-muted">{p.target_date}</p>
                        <p className="text-sm font-mono font-semibold text-text-primary">
                          {p.predicted_return !== null
                            ? `${(p.predicted_return * 100).toFixed(2)}%`
                            : "—"}
                        </p>
                      </div>
                    </div>
                    <div className="text-right">
                      <p className="text-[10px] text-muted">Actual</p>
                      <p className="text-sm font-mono text-text-primary">
                        {p.actual_close ?? "Pending"}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-muted">No predictions available</p>
            )}
          </CardContent>
        </Card>
      </div>

      {/* News & Social Preview */}
      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader
            title="Latest News"
            action={
              <span className="text-xs text-muted">{news.data?.length || 0} articles</span>
            }
          />
          <CardContent>
            {news.data && news.data.length > 0 ? (
              <div className="space-y-2">
                {news.data.slice(0, 3).map((n) => (
                  <div
                    key={n.id}
                    className="rounded-lg bg-bg-tertiary/50 p-3 transition-colors hover:bg-bg-tertiary"
                  >
                    <p className="text-sm font-medium text-text-primary line-clamp-2">
                      {n.title}
                    </p>
                    <p className="mt-1 text-[10px] text-muted">
                      {n.source} • {n.published_at?.slice(0, 10)}
                    </p>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-muted">No news available</p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader
            title="Social Posts"
            action={
              <span className="text-xs text-muted">{posts.data?.length || 0} posts</span>
            }
          />
          <CardContent>
            {posts.data && posts.data.length > 0 ? (
              <div className="space-y-2">
                {posts.data.slice(0, 3).map((p) => (
                  <div
                    key={p.id}
                    className="rounded-lg bg-bg-tertiary/50 p-3 transition-colors hover:bg-bg-tertiary"
                  >
                    <p className="text-sm text-text-primary line-clamp-2">{p.content}</p>
                    <p className="mt-1 flex items-center gap-2 text-[10px] text-muted">
                      <span>{p.source}</span>
                      {p.engagement !== null && (
                        <>
                          <span>•</span>
                          <span>{(p.engagement as number).toLocaleString()} engagement</span>
                        </>
                      )}
                    </p>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-muted">No social posts available</p>
            )}
          </CardContent>
        </Card>
      </div>
    </motion.div>
  );
}