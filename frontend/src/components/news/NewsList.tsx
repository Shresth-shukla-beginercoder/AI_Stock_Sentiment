import { useState } from "react";
import { motion } from "framer-motion";
import { useApi } from "../../hooks/useApi";
import {
  getRanking,
  listNews,
  listPosts,
} from "../../api/endpoints";
import { Card, CardContent, CardHeader } from "../common/Card";
import { StatusBadge } from "../common/StatusBadge";
import { EmptyState, LoadingSpinner } from "../common";
import {
  Newspaper,
  MessageSquare,
  ExternalLink,
  TrendingUp,
} from "lucide-react";
import type {
  Envelope,
  RankingRow,
  NewsArticle,
  SocialPost,
} from "../../types/api";

type Tab = "news" | "social";

/**
 * Cross-ticker sentiment ranking + a per-ticker intelligence feed.
 * The backend news/posts endpoints are per-ticker, so the user selects a
 * ticker (via the ranking or directly) and we fetch that asset's items.
 */
export function NewsList() {
  const ranking = useApi<Envelope<RankingRow[]>, RankingRow[]>(() => getRanking());
  const [ticker, setTicker] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("news");

  const activeTicker = ticker ?? ranking.data?.[0]?.ticker ?? null;

  return (
    <div className="space-y-6">
      {/* Sentiment ranking strip */}
      <Card>
        <CardHeader
          title="Sentiment Ranking"
          subtitle="Ranked by 10-day sentiment score across the tracked universe"
        />
        <CardContent>
          {ranking.status === "loading" ? (
            <div className="flex items-center gap-2 text-sm text-muted">
              <LoadingSpinner size="sm" /> Loading ranking…
            </div>
          ) : ranking.status === "error" ? (
            <EmptyState
              title="No ranking available"
              description={ranking.error?.message ?? "The reports endpoint returned an error."}
            />
          ) : ranking.data && ranking.data.length > 0 ? (
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {ranking.data.map((row, idx) => (
                <motion.div
                  key={row.ticker}
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: idx * 0.03 }}
                >
                  <button
                    onClick={() => setTicker(row.ticker)}
                    className={`w-full rounded-lg border p-3 text-left transition-all duration-200 ${
                      activeTicker === row.ticker
                        ? "border-accent-primary/50 bg-accent-primary/10"
                        : "border-white/10 bg-bg-tertiary/40 hover:border-white/20"
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className="rounded bg-bg-tertiary px-1.5 py-0.5 text-[10px] font-medium text-muted">
                          #{row.rank}
                        </span>
                        <span className="font-mono text-sm font-semibold text-text-primary">
                          {row.ticker}
                        </span>
                      </div>
                      <StatusBadge
                        tone={
                          row.state === "positive"
                            ? "pos"
                            : row.state === "negative"
                            ? "neg"
                            : "neutral"
                        }
                      >
                        {row.state ?? "neutral"}
                      </StatusBadge>
                    </div>
                    <div className="mt-2 flex items-center justify-between">
                      <span className="text-xs text-muted">{row.name ?? "—"}</span>
                      <span className="font-mono text-sm text-text-primary">
                        {row.score !== null ? row.score.toFixed(2) : "—"}
                      </span>
                    </div>
                  </button>
                </motion.div>
              ))}
            </div>
          ) : (
            <EmptyState
              title="No assets to rank yet"
              description="Ranking appears once assets are collected and scored."
            />
          )}
        </CardContent>
      </Card>

      {/* Per-ticker feed */}
      {activeTicker ? (
        <TickerFeed ticker={activeTicker} tab={tab} setTab={setTab} />
      ) : (
        <EmptyState
          title="Select a stock above"
          description="Pick a ticker to see its news and social intelligence."
        />
      )}
    </div>
  );
}

function TickerFeed({
  ticker,
  tab,
  setTab,
}: {
  ticker: string;
  tab: Tab;
  setTab: (t: Tab) => void;
}) {
  const news = useApi<Envelope<NewsArticle[]>, NewsArticle[]>(
    () => listNews(ticker, { limit: 50 }),
    { deps: [ticker] }
  );
  const posts = useApi<Envelope<SocialPost[]>, SocialPost[]>(
    () => listPosts(ticker, { limit: 50 }),
    { deps: [ticker] }
  );

  const tabs = [
    { id: "news" as const, label: "News", icon: <Newspaper className="h-4 w-4" />, data: news },
    { id: "social" as const, label: "Social", icon: <MessageSquare className="h-4 w-4" />, data: posts },
  ];

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h3 className="font-mono text-sm font-semibold text-text-primary">{ticker}</h3>
          <span className="text-xs text-muted">intelligence feed</span>
        </div>
        <div className="flex rounded-lg border border-white/10 bg-bg-secondary p-1">
          {tabs.map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`flex items-center gap-2 rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
                tab === t.id ? "bg-accent-primary text-white" : "text-muted hover:text-text-primary"
              }`}
            >
              {t.icon}
              {t.label}
              <span className="rounded-full bg-white/10 px-1.5 py-0.5 text-[10px]">
                {t.data.status === "success" ? (t.data.data?.length ?? 0) : "…"}
              </span>
            </button>
          ))}
        </div>
      </div>

      {tab === "news" ? <NewsPanel news={news.data} loading={news.status === "loading"} error={news.status === "error"} /> : <SocialPanel posts={posts.data} loading={posts.status === "loading"} error={posts.status === "error"} />}
    </div>
  );
}

function NewsPanel({
  news,
  loading,
  error,
}: {
  news: NewsArticle[] | null;
  loading: boolean;
  error: boolean;
}) {
  if (loading) {
    return (
      <div className="flex items-center justify-center rounded-xl border border-white/10 bg-bg-secondary/40 p-10">
        <LoadingSpinner size="md" />
      </div>
    );
  }
  if (error) {
    return <EmptyState title="Failed to load news" description="The news endpoint returned an error." />;
  }
  if (!news?.length) {
    return <EmptyState title="No news available" description="News will appear here once collected for this asset." />;
  }

  return (
    <div className="space-y-3">
      {news.map((article, idx) => (
        <motion.div
          key={article.id}
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: idx * 0.03 }}
        >
          <Card hover>
            <CardContent className="p-4">
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1 min-w-0">
                  <h4 className="font-medium text-text-primary line-clamp-2">{article.title}</h4>
                  {article.body && <p className="mt-2 text-sm text-muted line-clamp-2">{article.body}</p>}
                  <div className="mt-3 flex items-center gap-3 text-xs text-muted">
                    <span className="flex items-center gap-1">
                      <Newspaper className="h-3 w-3" />
                      {article.source}
                    </span>
                    {article.published_at && <span>{new Date(article.published_at).toLocaleDateString()}</span>}
                  </div>
                </div>
                {article.url && (
                  <a
                    href={article.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex-shrink-0 rounded-lg bg-bg-tertiary p-2 text-muted transition-colors hover:text-accent-primary"
                    aria-label="Open source"
                  >
                    <ExternalLink className="h-4 w-4" />
                  </a>
                )}
              </div>
            </CardContent>
          </Card>
        </motion.div>
      ))}
    </div>
  );
}

function SocialPanel({
  posts,
  loading,
  error,
}: {
  posts: SocialPost[] | null;
  loading: boolean;
  error: boolean;
}) {
  if (loading) {
    return (
      <div className="flex items-center justify-center rounded-xl border border-white/10 bg-bg-secondary/40 p-10">
        <LoadingSpinner size="md" />
      </div>
    );
  }
  if (error) {
    return <EmptyState title="Failed to load social posts" description="The posts endpoint returned an error." />;
  }
  if (!posts?.length) {
    return <EmptyState title="No social posts available" description="Posts will appear here once collected for this asset." />;
  }

  return (
    <div className="space-y-3">
      {posts.map((post, idx) => (
        <motion.div
          key={post.id}
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: idx * 0.03 }}
        >
          <Card hover>
            <CardContent className="p-4">
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-text-primary line-clamp-3">{post.content}</p>
                  <div className="mt-3 flex items-center gap-4 text-xs text-muted">
                    <span className="flex items-center gap-1">
                      <MessageSquare className="h-3 w-3" />
                      {post.source}
                    </span>
                    {post.engagement !== null && (
                      <span className="flex items-center gap-1">
                        <TrendingUp className="h-3 w-3" />
                        {post.engagement.toLocaleString()}
                      </span>
                    )}
                    {post.published_at && <span>{new Date(post.published_at).toLocaleDateString()}</span>}
                  </div>
                </div>
                {post.url && (
                  <a
                    href={post.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex-shrink-0 rounded-lg bg-bg-tertiary p-2 text-muted transition-colors hover:text-accent-primary"
                    aria-label="Open source"
                  >
                    <ExternalLink className="h-4 w-4" />
                  </a>
                )}
              </div>
            </CardContent>
          </Card>
        </motion.div>
      ))}
    </div>
  );
}
