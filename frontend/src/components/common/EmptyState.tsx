import { motion } from "framer-motion";
import { Inbox } from "lucide-react";

interface EmptyStateProps {
  title?: string;
  description?: string;
  icon?: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
}

export function EmptyState({
  title = "No data available",
  description,
  icon,
  action,
  className = "",
}: EmptyStateProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className={`flex flex-col items-center justify-center rounded-xl border border-dashed border-glow-blue/20 bg-navy/20 backdrop-blur-sm p-8 text-center ${className}`}
    >
      <motion.div
        className="rounded-full bg-gradient-to-br from-glow-blue/10 to-bell-amber/10 p-4 text-glow-blue"
        animate={{ scale: [1, 1.05, 1] }}
        transition={{ duration: 2, repeat: Infinity }}
      >
        {icon || <Inbox className="h-6 w-6" />}
      </motion.div>
      <h3 className="mt-4 font-display text-base font-semibold text-text-primary">{title}</h3>
      {description && <p className="mt-2 max-w-sm text-xs text-muted">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </motion.div>
  );
}
