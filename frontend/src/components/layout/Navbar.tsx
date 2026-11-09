import { useState } from "react";
import { NavLink } from "react-router-dom";
import { motion } from "framer-motion";
import {
  LayoutDashboard,
  LineChart,
  Newspaper,
  Sparkles,
  Settings,
  Menu,
  X,
} from "lucide-react";

interface NavItem {
  to: string;
  label: string;
  icon: React.ReactNode;
}

const NAV_ITEMS: NavItem[] = [
  { to: "/", label: "Dashboard", icon: <LayoutDashboard className="h-4 w-4" /> },
  { to: "/stocks", label: "Markets", icon: <LineChart className="h-4 w-4" /> },
  { to: "/news", label: "Intelligence", icon: <Newspaper className="h-4 w-4" /> },
  { to: "/insights", label: "AI Insights", icon: <Sparkles className="h-4 w-4" /> },
  { to: "/system", label: "System", icon: <Settings className="h-4 w-4" /> },
];

export function Navbar() {
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <motion.nav
      initial={{ opacity: 0, y: -10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.6 }}
      className="sticky top-0 z-40 border-b border-white/5 bg-navy/80 backdrop-blur-xl"
    >
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="flex h-16 items-center justify-between">
          {/* Logo */}
          <motion.div
            whileHover={{ scale: 1.02 }}
            className="flex items-center gap-3"
          >
            <div className="relative">
              <img
                src="/favicon.png"
                alt="NEXTBELL"
                className="h-9 w-9 rounded-lg shadow-lg"
              />
              <motion.div
                className="absolute -inset-1 rounded-lg bg-gradient-to-r from-glow-blue to-bell-amber opacity-30 blur-md"
                animate={{
                  opacity: [0.2, 0.4, 0.2],
                }}
                transition={{
                  duration: 2,
                  repeat: Infinity,
                }}
              />
            </div>
            <div className="flex flex-col">
              <span className="font-display font-bold tracking-tight text-text-primary text-lg">
                NEXTBELL
              </span>
              <span className="text-[9px] text-muted uppercase tracking-wider">Terminal</span>
            </div>
          </motion.div>

          {/* Desktop Nav */}
          <div className="hidden md:flex items-center gap-1">
            {NAV_ITEMS.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === "/"}
                className={({ isActive }) =>
                  `group relative flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition-all duration-300 ${
                    isActive
                      ? "text-text-primary"
                      : "text-muted hover:text-text-primary"
                  }`
                }
              >
                {({ isActive }) => (
                  <>
                    {isActive && (
                      <motion.div
                        layoutId="activeNav"
                        className="absolute inset-0 rounded-lg bg-gradient-to-r from-glow-blue/10 to-bell-amber/10 border border-glow-blue/20"
                        transition={{ type: "spring", bounce: 0.2, duration: 0.6 }}
                      />
                    )}
                    <span className={`relative z-10 ${isActive ? "text-glow-blue" : ""}`}>
                      {item.icon}
                    </span>
                    <span className="relative z-10 hidden lg:inline">{item.label}</span>
                    <motion.div
                      className="absolute inset-0 rounded-lg bg-gradient-to-r from-glow-blue/5 to-bell-amber/5 opacity-0 transition-opacity duration-300"
                      whileHover={{ opacity: 1 }}
                    />
                  </>
                )}
              </NavLink>
            ))}
          </div>

          {/* Right side */}
          <div className="flex items-center gap-3">
            {/* Live indicator */}
            <div className="hidden md:flex items-center gap-2 px-3 py-1.5 rounded-full bg-navy/50 border border-white/5">
              <motion.div
                className="w-2 h-2 rounded-full bg-success"
                animate={{ opacity: [1, 0.5, 1] }}
                transition={{ duration: 2, repeat: Infinity }}
              />
              <span className="text-xs font-mono text-muted">LIVE</span>
            </div>

            {/* Mobile Menu Button */}
            <button
              onClick={() => setMobileOpen(!mobileOpen)}
              className="md:hidden p-2 rounded-lg hover:bg-white/5 transition-colors"
            >
              {mobileOpen ? (
                <X className="h-5 w-5" />
              ) : (
                <Menu className="h-5 w-5" />
              )}
            </button>
          </div>
        </div>

        {/* Mobile Nav */}
        {mobileOpen && (
          <motion.div
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            className="md:hidden border-t border-white/5 py-3 space-y-1"
          >
            {NAV_ITEMS.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === "/"}
                onClick={() => setMobileOpen(false)}
                className={({ isActive }) =>
                  `flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-all duration-300 ${
                    isActive
                      ? "bg-gradient-to-r from-glow-blue/10 to-bell-amber/10 text-glow-blue border border-glow-blue/20"
                      : "text-muted hover:text-text-primary hover:bg-white/5"
                  }`
                }
              >
                {item.icon}
                {item.label}
              </NavLink>
            ))}
          </motion.div>
        )}
      </div>
    </motion.nav>
  );
}
