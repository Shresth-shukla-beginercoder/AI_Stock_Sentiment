import { ReactNode } from "react";
import { motion } from "framer-motion";

interface MetricCardProps {
  label: string;
  value: string | number | ReactNode;
  sub?: string;
  trend?: "up" | "down" | "neutral";
  trendValue?: string;
  icon?: ReactNode;
  className?: string;
}

export function MetricCard({ label, value, sub, trend, trendValue, icon, className = "" }: MetricCardProps) {
  const trendColors = {
    up: "text-success",
    down: "text-danger",
    neutral: "text-muted",
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className={`data-card relative overflow-hidden rounded-xl border border-white/5 bg-navy/30 backdrop-blur-md p-5 transition-all duration-300 hover:border-glow-blue/30 hover:shadow-[0_8px_30px_rgba(59,130,246,0.15)] ${className}`}
    >
      <div className="flex items-start justify-between">
        <div className="flex-1">
          <p className="text-xs font-medium text-muted uppercase tracking-wider">{label}</p>
          <div className="mt-2 flex items-baseline gap-2">
            <div className="font-display text-3xl font-bold tabular-nums text-text-primary">{value}</div>
            {trend && trendValue && (
              <span className={`text-xs font-semibold ${trendColors[trend]}`}>
                {trend === "up" ? "↑" : trend === "down" ? "↓" : ""} {trendValue}
              </span>
            )}
          </div>
          {sub && <p className="mt-1 text-xs text-muted">{sub}</p>}
        </div>
        {icon && (
          <motion.div
            className="rounded-lg bg-gradient-to-br from-glow-blue/20 to-bell-amber/10 p-2.5 text-glow-blue"
            whileHover={{ scale: 1.1, rotate: 5 }}
          >
            {icon}
          </motion.div>
        )}
      </div>
    </motion.div>
  );
}
