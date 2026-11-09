import { motion } from "framer-motion";
import { useApi } from "../../hooks/useApi";
import { getHealth, getReady, getSystemStatus } from "../../api/endpoints";
import { Card, CardContent } from "../common/Card";
import { StatusBadge } from "../common/StatusBadge";
import { Activity, Database, Server, Zap } from "lucide-react";
import type { Envelope, SystemStatusData } from "../../types/api";

export function SystemHealthCard() {
  const health = useApi(() => getHealth(), { refreshMs: 30000 });
  const ready = useApi(() => getReady(), { refreshMs: 30000 });
  const system = useApi<Envelope<SystemStatusData>, SystemStatusData>(
    () => getSystemStatus(),
    { refreshMs: 30000 }
  );

  const apiConnected = health.status === "success";
  const dbUp = ready.status === "success" && ready.data?.database === "up";

  const metrics = [
    {
      label: "API Status",
      value: apiConnected ? "Connected" : "Disconnected",
      status: apiConnected ? "pos" : "neg",
      icon: <Server className="h-4 w-4" />,
    },
    {
      label: "Database",
      value: dbUp ? "Ready" : "Down",
      status: dbUp ? "pos" : "neg",
      icon: <Database className="h-4 w-4" />,
    },
    {
      label: "Provider",
      value: health.data?.market_data_provider || "Not configured",
      status: health.data?.market_data_provider ? "info" : "warn",
      icon: <Activity className="h-4 w-4" />,
    },
    {
      label: "Data Mode",
      value: system.dataMode?.toUpperCase() || "—",
      status: system.dataMode === "live" ? "pos" : "warn",
      icon: <Zap className="h-4 w-4" />,
    },
  ];

  return (
    <Card>
      <CardContent className="p-5">
        <div className="flex items-center justify-between mb-5">
          <h3 className="font-display text-base font-semibold tracking-tight text-text-primary">System Health</h3>
          <StatusBadge tone={apiConnected && dbUp ? "pos" : "warn"}>
            {apiConnected && dbUp ? "Operational" : "Issues"}
          </StatusBadge>
        </div>
        <div className="grid grid-cols-2 gap-3">
          {metrics.map((metric, idx) => (
            <motion.div
              key={metric.label}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: idx * 0.05 }}
              className="flex items-center gap-2.5 rounded-lg border border-white/5 bg-navy/40 p-3"
            >
              <div className={`rounded-md p-1.5 ${
                metric.status === "pos" ? "bg-success/10 text-success" :
                metric.status === "neg" ? "bg-danger/10 text-danger" :
                metric.status === "warn" ? "bg-warning/10 text-warning" :
                "bg-glow-blue/10 text-glow-blue"
              }`}>
                {metric.icon}
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-[10px] text-muted uppercase tracking-wider">{metric.label}</p>
                <p className="text-xs font-semibold text-text-primary truncate">{metric.value}</p>
              </div>
            </motion.div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
