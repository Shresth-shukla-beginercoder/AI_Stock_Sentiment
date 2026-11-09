import { useMemo, useState } from "react";
import { motion } from "framer-motion";
import { useApi } from "../../hooks/useApi";
import { listAssets } from "../../api/endpoints";
import { Card, CardContent } from "../common/Card";
import { StatusBadge, DataModeBadge } from "../common/StatusBadge";
import { Search } from "lucide-react";
import type { Envelope, Asset } from "../../types/api";

interface StockListProps {
  onSelect?: (ticker: string) => void;
}

export function StockList({ onSelect }: StockListProps) {
  const assets = useApi<Envelope<Asset[]>, Asset[]>(() => listAssets({ limit: 200 }));
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<"all" | "demo" | "live">("all");

  const filteredAssets = useMemo(() => {
    const list = assets.data ?? [];
    return list.filter((a) => {
      if (filter === "demo" && !a.is_demo) return false;
      if (filter === "live" && a.is_demo) return false;
      if (!search) return true;
      const s = search.toLowerCase();
      return (
        a.ticker.toLowerCase().includes(s) ||
        (a.name ?? "").toLowerCase().includes(s) ||
        a.exchange.toLowerCase().includes(s)
      );
    });
  }, [assets.data, search, filter]);

  if (assets.status === "loading") {
    return (
      <div className="space-y-3">
        {[...Array(5)].map((_, i) => (
          <div key={i} className="shimmer h-16 rounded-xl bg-navy/30" />
        ))}
      </div>
    );
  }

  if (assets.status === "error") {
    return <p className="text-sm text-danger">Failed to load assets</p>;
  }

  return (
    <div className="space-y-4">
      {/* Search and Filter */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative flex-1 min-w-[200px]">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
          <input
            type="text"
            placeholder="Search stocks..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full rounded-lg border border-white/10 bg-navy/40 py-2.5 pl-10 pr-4 text-sm text-text-primary placeholder:text-muted focus:border-glow-blue focus:outline-none focus:ring-2 focus:ring-glow-blue/20 transition-all"
          />
        </div>
        <div className="flex rounded-lg border border-white/10 bg-navy/40 p-1">
          {(["all", "demo", "live"] as const).map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`rounded-md px-3 py-1.5 text-xs font-medium transition-all ${
                filter === f
                  ? "bg-gradient-to-r from-glow-blue to-bell-amber text-ink font-semibold shadow-[0_2px_10px_rgba(59,130,246,0.3)]"
                  : "text-muted hover:text-text-primary"
              }`}
            >
              {f.charAt(0).toUpperCase() + f.slice(1)}
            </button>
          ))}
        </div>
      </div>

      {/* Stock Count */}
      <p className="text-xs text-muted">
        Showing {filteredAssets.length} of {assets.data?.length ?? 0} stocks
      </p>

      {/* Stock Grid */}
      <div className="grid gap-3">
        {filteredAssets.map((asset, idx) => (
          <motion.div
            key={asset.ticker}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: idx * 0.02 }}
          >
            <div
              onClick={() => onSelect?.(asset.ticker)}
              className="cursor-pointer"
            >
              <Card hover>
              <CardContent className="flex items-center justify-between p-4">
                <div className="flex items-center gap-3">
                  <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-gradient-to-br from-glow-blue/20 to-bell-amber/10 font-mono text-sm font-bold text-glow-blue">
                    {asset.ticker.slice(0, 2)}
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-mono font-bold text-text-primary">
                        {asset.ticker}
                      </span>
                      {asset.is_demo && <DataModeBadge mode="demo" />}
                    </div>
                    <p className="text-xs text-muted">{asset.name || asset.exchange}</p>
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <StatusBadge tone={asset.confirmed ? "pos" : "warn"}>
                    {asset.confirmed ? "Confirmed" : "Pending"}
                  </StatusBadge>
                  <StatusBadge tone={asset.active ? "pos" : "neutral"}>
                    {asset.active ? "Active" : "Inactive"}
                  </StatusBadge>
                </div>
              </CardContent>
              </Card>
            </div>
          </motion.div>
        ))}
      </div>
    </div>
  );
}