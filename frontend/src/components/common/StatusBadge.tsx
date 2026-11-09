import { ReactNode } from "react";
import { motion } from "framer-motion";

type BadgeTone = "pos" | "neg" | "warn" | "neutral" | "info" | "primary";

interface StatusBadgeProps {
  tone?: BadgeTone;
  children: ReactNode;
  className?: string;
  animated?: boolean;
}

export function StatusBadge({ tone = "neutral", children, className = "", animated = false }: StatusBadgeProps) {
  const tones: Record<BadgeTone, string> = {
    pos: "bg-success/10 text-success border-success/20 shadow-[0_0_10px_rgba(16,185,129,0.15)]",
    neg: "bg-danger/10 text-danger border-danger/20 shadow-[0_0_10px_rgba(239,68,68,0.15)]",
    warn: "bg-warning/10 text-warning border-warning/20 shadow-[0_0_10px_rgba(245,158,11,0.15)]",
    neutral: "bg-navy/30 text-muted border-white/10",
    info: "bg-glow-blue/10 text-glow-blue border-glow-blue/20 shadow-[0_0_10px_rgba(59,130,246,0.15)]",
    primary: "bg-glow-blue/10 text-glow-blue border-glow-blue/20 shadow-[0_0_10px_rgba(59,130,246,0.15)]",
  };

  const Component = animated ? motion.span : "span";

  return (
    <Component
      {...(animated && {
        initial: { opacity: 0, scale: 0.9 },
        animate: { opacity: 1, scale: 1 },
        transition: { duration: 0.2 },
      })}
      className={`inline-flex items-center rounded-md border px-2.5 py-1 text-xs font-semibold tracking-wide uppercase ${tones[tone]} ${className}`}
    >
      {children}
    </Component>
  );
}

interface DataModeBadgeProps {
  mode?: "demo" | "live" | null;
  className?: string;
}

export function DataModeBadge({ mode, className = "" }: DataModeBadgeProps) {
  if (!mode) return null;

  return (
    <StatusBadge tone={mode === "demo" ? "warn" : "pos"} className={className}>
      {mode.toUpperCase()}
    </StatusBadge>
  );
}
