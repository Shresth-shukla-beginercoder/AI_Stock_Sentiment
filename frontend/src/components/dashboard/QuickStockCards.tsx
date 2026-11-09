import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import { useApi } from "../../hooks/useApi";
import { listAssets, getOverview } from "../../api/endpoints";
import { Card, CardContent } from "../common/Card";
import { DataModeBadge } from "../common/StatusBadge";
import { EmptyState, LoadingSpinner } from "../common";
import { SentimentMeter } from "../stocks/SentimentMeter";
import {
  ArrowRight,
} from "lucide-react";
import type { Envelope, Asset, OverviewData } from "../../types/api";

export function QuickStockCards() {
  const assets = useApi<Envelope<Asset[]>, Asset[]>(() => listAssets({ limit: 6 }));
  const overview = useApi<Envelope<OverviewData>, OverviewData>(() => getOverview());
  const perTicker = overview.data?.per_ticker;

  if (assets.status === "loading") {
    return (
      <div className="flex items-center gap-2 text-sm text-muted">
        <LoadingSpinner size="sm" /> Loading stocks…
      </div>
    );
  }

  if (assets.status === "error" || !assets.data?.length) {
    return (
      <EmptyState
        title="No stocks tracked yet"
        description="Assets appear here once the universe is seeded or confirmed."
      />
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="font-display text-base font-semibold tracking-tight text-text-primary">Tracked Stocks</h3>
        <Link to="/stocks" className="flex items-center gap-1 text-xs text-glow-blue transition-colors hover:gap-1.5 hover:text-glow-blue-bright">
          View all <ArrowRight className="h-3 w-3" />
        </Link>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
        {assets.data.map((asset, idx) => {
          const info = perTicker?.[asset.ticker];
          const score = info?.sentiment_score ?? null;

          return (
            <Link to={`/stocks?ticker=${asset.ticker}`} key={asset.ticker} className="group block">
              <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: idx * 0.05 }}
                whileHover={{ y: -2 }}
              >
                <Card hover>
                  <CardContent className="p-5">
                    <div className="flex items-center justify-between mb-4">
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <h4 className="font-mono text-base font-bold text-text-primary">
                            {asset.ticker}
                          </h4>
                          {asset.is_demo && <DataModeBadge mode="demo" />}
                        </div>
                        <p className="mt-1 truncate text-xs text-muted">{asset.name || asset.exchange}</p>
                      </div>
                      <span className="flex shrink-0 items-center gap-1 text-xs text-muted transition-all group-hover:text-glow-blue group-hover:gap-1.5">
                        View <ArrowRight className="h-3 w-3" />
                      </span>
                    </div>

                    {/* Three-zone animated sentiment bar (pos / neutral / neg) */}
                    <SentimentMeter score={score} compact />
                  </CardContent>
                </Card>
              </motion.div>
            </Link>
          );
        })}
      </div>
    </div>
  );
}
