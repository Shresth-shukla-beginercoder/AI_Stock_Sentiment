import { NavLink, Outlet } from "react-router-dom";
import { DemoBanner } from "../components/DemoBanner";
import { useSystemMode } from "../hooks/useSystemMode";

const NAV = [
  { to: "/", label: "Connection", icon: "◈" },
  { to: "/system", label: "System Status", icon: "▤" },
  { to: "/assets", label: "Assets", icon: "◍" },
  { to: "/inspector", label: "Stock Inspector", icon: "◉" },
  { to: "/jobs", label: "Jobs & Pipeline", icon: "⚙" },
  { to: "/models", label: "Model Performance", icon: "◫" },
];

export function AppLayout() {
  const { mode } = useSystemMode();

  return (
    <div className="flex min-h-screen bg-ink-950 text-slate-200">
      <aside className="hidden w-56 shrink-0 border-r border-ink-700/50 bg-ink-900 md:block">
        <div className="flex items-center gap-2 px-4 py-4">
          <span className="text-accent">◈</span>
          <span className="text-sm font-semibold tracking-tight text-slate-100">
            Sentiment Console
          </span>
        </div>
        <nav className="mt-2 space-y-0.5 px-2">
          {NAV.map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              end={n.to === "/"}
              className={({ isActive }) =>
                `flex items-center gap-2.5 rounded-md px-3 py-2 text-sm transition-colors ${
                  isActive
                    ? "bg-ink-800 text-slate-50"
                    : "text-muted hover:bg-ink-800/60 hover:text-slate-200"
                }`
              }
            >
              <span className="text-xs">{n.icon}</span>
              {n.label}
            </NavLink>
          ))}
        </nav>
        <div className="mt-6 border-t border-ink-700/50 px-4 py-3 text-[11px] leading-relaxed text-muted/70">
          Research platform. Not financial advice. Not a trading bot.
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-10 flex items-center justify-between border-b border-ink-700/50 bg-ink-900/80 px-4 py-3 backdrop-blur md:px-6">
          <div className="text-xs text-muted">
            AI Stock Sentiment &amp; Next-Day Prediction Agent
          </div>
          <div className="flex items-center gap-3 text-xs">
            <a
              href="/api/openapi.json"
              target="_blank"
              rel="noreferrer"
              className="text-muted hover:text-accent"
            >
              OpenAPI
            </a>
            <a href="/docs" target="_blank" rel="noreferrer" className="text-muted hover:text-accent">
              Swagger
            </a>
          </div>
        </header>

        {mode === "demo" ? <div className="px-4 pt-3 md:px-6"><DemoBanner /></div> : null}

        <main className="flex-1 px-4 py-4 md:px-6 md:py-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
