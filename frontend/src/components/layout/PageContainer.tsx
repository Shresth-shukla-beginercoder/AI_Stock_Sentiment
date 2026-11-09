import { ReactNode } from "react";
import { motion } from "framer-motion";

interface PageContainerProps {
  title: string;
  subtitle?: string;
  action?: ReactNode;
  children: ReactNode;
}

export function PageContainer({
  title,
  subtitle,
  action,
  children,
}: PageContainerProps) {
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.5 }}
      className="min-h-[calc(100vh-64px)] flex flex-col"
    >
      {/* Page header */}
      <div className="border-b border-white/5 bg-navy/40 backdrop-blur-sm">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 py-8">
          <div className="flex items-start justify-between gap-4">
            <div className="flex-1">
              <motion.h1
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.1, duration: 0.4 }}
                className="font-display text-3xl font-bold tracking-tight text-text-primary"
              >
                {title}
              </motion.h1>
              {subtitle && (
                <motion.p
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.15, duration: 0.4 }}
                  className="mt-2 text-sm text-text-secondary"
                >
                  {subtitle}
                </motion.p>
              )}
            </div>
            {action && (
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: 0.2, duration: 0.4 }}
              >
                {action}
              </motion.div>
            )}
          </div>
        </div>
      </div>

      {/* Page content */}
      <div className="flex-1 mx-auto w-full max-w-7xl px-4 sm:px-6 lg:px-8 py-8">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2, duration: 0.5 }}
        >
          {children}
        </motion.div>
      </div>
    </motion.div>
  );
}
