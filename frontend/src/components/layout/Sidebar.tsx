import { NavLink } from "react-router-dom";
import { motion } from "framer-motion";
import {
  LayoutDashboard,
  LineChart,
  Newspaper,
  Sparkles,
  Settings,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";
import { useState } from "react";

interface NavItem {
  to: string;
  label: string;
  icon: React.ReactNode;
}

const NAV_ITEMS: NavItem[] = [
  { to: "/", label: "Dashboard", icon: <LayoutDashboard className="h-4 w-4" /> },
  { to: "/stocks", label: "Stocks", icon: <LineChart className="h-4 w-4" /> },
  { to: "/news", label: "Intelligence", icon: <Newspaper className="h-4 w-4" /> },
  { to: "/insights", label: "AI Insights", icon: <Sparkles className="h-4 w-4" /> },
  { to: "/system", label: "System", icon: <Settings className="h-4 w-4" /> },
];

export function Sidebar() {
  const [collapsed, setCollapsed] = useState(false);

  return (
    <motion.aside
      initial={false}
      animate={{ width: collapsed ? 72 : 224 }}
      transition={{ duration: 0.2, ease: "easeInOut" }}
      className="flex h-screen flex-col border-r border-white/5 bg-bg-secondary"
    >
      {/* Logo */}
      <div className="flex items-center gap-3 border-b border-white/5 px-4 py-4">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-glow-blue to-bell-amber">
          <Sparkles className="h-4 w-4 text-ink" />
        </div>
        <motion.span
          initial={false}
          animate={{ opacity: collapsed ? 0 : 1 }}
          transition={{ duration: 0.15 }}
          className="font-display font-bold tracking-tight text-text-primary whitespace-nowrap"
        >
          HENGSENG
        </motion.span>
      </div>

      {/* Navigation */}
      <nav className="flex-1 space-y-1 px-3 py-4">
        {NAV_ITEMS.map((item, index) => (
          <motion.div
            key={item.to}
            initial={{ opacity: 0, x: -10 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: index * 0.05, duration: 0.2 }}
          >
            <NavLink
              to={item.to}
              end={item.to === "/"}
              className={({ isActive }) =>
                `group flex items-center gap-3 rounded-lg px-3 py-2.5 transition-all duration-200 ${
                  isActive
                    ? "bg-accent-primary/10 text-accent-primary"
                    : "text-muted hover:bg-bg-tertiary hover:text-text-primary"
                }`
              }
            >
              <span className="flex-shrink-0">{item.icon}</span>
              <motion.span
                initial={false}
                animate={{ opacity: collapsed ? 0 : 1 }}
                transition={{ duration: 0.15 }}
                className="text-sm font-medium whitespace-nowrap"
              >
                {item.label}
              </motion.span>
            </NavLink>
          </motion.div>
        ))}
      </nav>

      {/* Collapse Toggle */}
      <button
        onClick={() => setCollapsed(!collapsed)}
        className="flex items-center justify-center gap-2 border-t border-white/5 px-4 py-3 text-muted transition-colors hover:text-text-primary"
      >
        {collapsed ? (
          <ChevronRight className="h-4 w-4" />
        ) : (
          <>
            <ChevronLeft className="h-4 w-4" />
            <span className="text-xs">Collapse</span>
          </>
        )}
      </button>

      {/* Footer */}
      <div className="border-t border-white/5 px-4 py-3">
        <motion.p
          initial={false}
          animate={{ opacity: collapsed ? 0 : 1 }}
          className="text-[10px] leading-relaxed text-muted"
        >
          Research platform. Not financial advice.
        </motion.p>
      </div>
    </motion.aside>
  );
}
