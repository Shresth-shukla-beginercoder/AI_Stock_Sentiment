import { motion } from "framer-motion";
import { useApi } from "../../hooks/useApi";
import { getOverview } from "../../api/endpoints";
import { MetricCard } from "../common/MetricCard";
import {
  TrendingUp,
  Newspaper,
  MessageSquare,
  Sparkles,
  Boxes,
  Database,
} from "lucide-react";
import type { Envelope, OverviewData } from "../../types/api";

export function StatsOverview() {
  const overview = useApi<Envelope<OverviewData>, OverviewData>(() => getOverview());

  const c = overview.data?.counts;

  const stats = [
    {
      label: "Tracked Assets",
      value: c?.assets ?? 0,
      icon: <TrendingUp className="h-4 w-4" />,
      sub: `${overview.data?.universe.length ?? 0} in universe`,
    },
    {
      label: "News Articles",
      value: c?.news_articles ?? 0,
      icon: <Newspaper className="h-4 w-4" />,
    },
    {
      label: "Social Posts",
      value: c?.social_posts ?? 0,
      icon: <MessageSquare className="h-4 w-4" />,
    },
    {
      label: "Price Rows",
      value: c?.market_prices ?? 0,
      icon: <Database className="h-4 w-4" />,
    },
    {
      label: "Predictions",
      value: c?.predictions ?? 0,
      icon: <Sparkles className="h-4 w-4" />,
    },
    {
      label: "Model Versions",
      value: c?.model_versions ?? 0,
      icon: <Boxes className="h-4 w-4" />,
    },
  ];

  return (
    <div className="grid grid-cols-2 gap-4 lg:grid-cols-6">
      {stats.map((stat, idx) => (
        <motion.div
          key={stat.label}
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: idx * 0.05, duration: 0.3 }}
        >
          <MetricCard label={stat.label} value={stat.value.toLocaleString()} sub={stat.sub} icon={stat.icon} />
        </motion.div>
      ))}
    </div>
  );
}
