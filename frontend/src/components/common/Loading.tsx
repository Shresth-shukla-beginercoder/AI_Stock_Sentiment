import { motion } from "framer-motion";

interface LoadingSkeletonProps {
  className?: string;
  count?: number;
}

export function LoadingSkeleton({ className = "", count = 1 }: LoadingSkeletonProps) {
  return (
    <>
      {Array.from({ length: count }).map((_, i) => (
        <motion.div
          key={i}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className={`shimmer rounded-lg bg-navy/30 ${className}`}
        />
      ))}
    </>
  );
}

export function LoadingSpinner({ size = "md" }: { size?: "sm" | "md" | "lg" }) {
  const sizes = {
    sm: "h-4 w-4 border-2",
    md: "h-6 w-6 border-2",
    lg: "h-8 w-8 border-3",
  };

  return (
    <div
      className={`${sizes[size]} rounded-full border-navy/50 border-t-glow-blue animate-spin`}
    />
  );
}

export function LoadingCard() {
  return (
    <div className="rounded-xl border border-white/5 bg-navy/30 backdrop-blur-md p-5">
      <div className="flex items-center gap-3">
        <LoadingSpinner />
        <span className="text-sm text-muted">Loading...</span>
      </div>
    </div>
  );
}
