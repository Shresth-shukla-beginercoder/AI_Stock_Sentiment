import { motion } from "framer-motion";
import { ExternalLink } from "lucide-react";
import { DataModeBadge } from "../common/StatusBadge";
import { useSystemMode } from "../../hooks/useSystemMode";

interface HeaderProps {
  title: string;
  subtitle?: string;
  action?: React.ReactNode;
}

export function Header({ title, subtitle, action }: HeaderProps) {
  const { mode } = useSystemMode();

  return (
    <motion.header
      initial={{ opacity: 0, y: -10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className="sticky top-0 z-10 border-b border-white/5 bg-bg-primary/80 backdrop-blur-md"
    >
      <div className="flex items-center justify-between px-6 py-4">
        <div className="flex items-center gap-4">
          <div>
            <h1 className="text-xl font-semibold text-text-primary">{title}</h1>
            {subtitle && <p className="mt-0.5 text-sm text-muted">{subtitle}</p>}
          </div>
          {mode === "demo" && <DataModeBadge mode="demo" />}
        </div>

        <div className="flex items-center gap-3">
          {action}
          <div className="flex items-center gap-2 text-xs text-muted">
            <a
              href="/api/openapi.json"
              target="_blank"
              rel="noreferrer"
              className="flex items-center gap-1 transition-colors hover:text-accent-primary"
            >
              API
              <ExternalLink className="h-3 w-3" />
            </a>
            <span className="text-white/20">•</span>
            <a
              href="/docs"
              target="_blank"
              rel="noreferrer"
              className="flex items-center gap-1 transition-colors hover:text-accent-primary"
            >
              Docs
              <ExternalLink className="h-3 w-3" />
            </a>
          </div>
        </div>
      </div>
    </motion.header>
  );
}
