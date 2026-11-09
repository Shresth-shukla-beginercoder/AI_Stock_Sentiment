import { motion } from "framer-motion";
import { AlertCircle, RefreshCw } from "lucide-react";
import { Button } from "./Button";

interface ErrorStateProps {
  title?: string;
  message?: string;
  onRetry?: () => void;
  className?: string;
}

export function ErrorState({
  title = "Something went wrong",
  message,
  onRetry,
  className = "",
}: ErrorStateProps) {
  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.3 }}
      className={`rounded-xl border border-danger/30 bg-gradient-to-br from-danger/10 to-danger/5 backdrop-blur-sm p-6 ${className}`}
    >
      <div className="flex items-start gap-4">
        <motion.div
          className="rounded-lg bg-danger/20 p-2"
          animate={{ scale: [1, 1.1, 1] }}
          transition={{ duration: 2, repeat: Infinity }}
        >
          <AlertCircle className="h-5 w-5 text-danger" />
        </motion.div>
        <div className="flex-1">
          <h3 className="font-display text-sm font-semibold text-text-primary">{title}</h3>
          {message && <p className="mt-1 text-xs text-muted">{message}</p>}
          {onRetry && (
            <Button variant="ghost" size="sm" onClick={onRetry} className="mt-3">
              <RefreshCw className="mr-1.5 h-3.5 w-3.5" />
              Retry
            </Button>
          )}
        </div>
      </div>
    </motion.div>
  );
}
