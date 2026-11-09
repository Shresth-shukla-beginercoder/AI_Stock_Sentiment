import { ReactNode } from "react";
import { motion } from "framer-motion";

interface CardProps {
  children: ReactNode;
  className?: string;
  hover?: boolean;
  glow?: boolean;
}

export function Card({ children, className = "", hover = false, glow = false }: CardProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: "easeOut" }}
      whileHover={hover ? { y: -2, transition: { duration: 0.2 } } : undefined}
      className={`
        rounded-xl border border-white/5 bg-navy/30 backdrop-blur-md
        shadow-[0_4px_20px_rgba(0,0,0,0.3),inset_0_1px_0_rgba(255,255,255,0.05)]
        ${glow ? "border-glow-blue/30 shadow-[0_8px_30px_rgba(59,130,246,0.15)]" : ""}
        ${hover ? "cursor-pointer transition-all duration-300 hover:border-glow-blue/30 hover:shadow-[0_8px_30px_rgba(59,130,246,0.15)] hover:-translate-y-0.5" : ""}
        ${className}
      `}
    >
      {children}
    </motion.div>
  );
}

interface CardHeaderProps {
  title: string;
  subtitle?: string;
  action?: ReactNode;
  className?: string;
}

export function CardHeader({ title, subtitle, action, className = "" }: CardHeaderProps) {
  return (
    <div className={`flex items-start justify-between border-b border-white/5 px-6 py-4 ${className}`}>
      <div>
        <h3 className="font-display text-base font-semibold tracking-tight text-text-primary">{title}</h3>
        {subtitle && <p className="mt-1 text-xs text-muted">{subtitle}</p>}
      </div>
      {action && <div className="flex items-center gap-2">{action}</div>}
    </div>
  );
}

interface CardContentProps {
  children: ReactNode;
  className?: string;
}

export function CardContent({ children, className = "" }: CardContentProps) {
  return <div className={`p-6 ${className}`}>{children}</div>;
}
