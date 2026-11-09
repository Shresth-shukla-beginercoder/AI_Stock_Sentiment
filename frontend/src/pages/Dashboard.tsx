import { motion } from "framer-motion";
import { PageContainer } from "../components/layout";
import { StatsOverview, SystemHealthCard, QuickStockCards } from "../components/dashboard";
import { ShieldAlert } from "lucide-react";

export function Dashboard() {
  return (
    <PageContainer
      title="Dashboard"
      subtitle="AI-powered stock sentiment and next-day prediction platform"
    >
      <div className="space-y-6">
        {/* Stats Overview */}
        <StatsOverview />

        {/* System Health + Stocks */}
        <div className="grid gap-6 lg:grid-cols-3">
          <div className="lg:col-span-2">
            <QuickStockCards />
          </div>
          <div>
            <SystemHealthCard />
          </div>
        </div>

        {/* Platform disclaimer */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.4 }}
          className="rounded-xl border border-white/5 bg-navy/20 p-4"
        >
          <div className="flex items-center justify-center gap-2 text-muted">
            <ShieldAlert className="h-4 w-4 text-warning" />
            <p className="text-xs text-center">
              Research platform for stock sentiment analysis and next-day prediction.
              Not financial advice. Not a trading bot.
            </p>
          </div>
        </motion.div>
      </div>
    </PageContainer>
  );
}