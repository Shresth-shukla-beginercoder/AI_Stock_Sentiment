/**
 * App-wide data_mode awareness: polls /api/health (which carries data_mode)
 * and exposes { mode, reachable } so the DemoBanner and per-page badges can
 * be driven by the REAL backend, never guessed.
 */
import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { getHealth } from "../api/endpoints";
import type { DataMode } from "../types/api";

interface SystemModeCtx {
  mode: DataMode | null;
  reachable: boolean;
  lastChecked: Date | null;
}

const Ctx = createContext<SystemModeCtx>({ mode: null, reachable: false, lastChecked: null });

export function SystemModeProvider({ children }: { children: ReactNode }) {
  const [mode, setMode] = useState<DataMode | null>(null);
  const [reachable, setReachable] = useState(false);
  const [lastChecked, setLastChecked] = useState<Date | null>(null);

  useEffect(() => {
    let live = true;
    const poll = async () => {
      try {
        const h = await getHealth();
        if (!live) return;
        setReachable(true);
        setMode(h.data_mode);
        setLastChecked(new Date());
      } catch {
        if (live) setReachable(false);
      }
    };
    poll();
    const t = setInterval(poll, 30_000);
    return () => {
      live = false;
      clearInterval(t);
    };
  }, []);

  return <Ctx.Provider value={{ mode, reachable, lastChecked }}>{children}</Ctx.Provider>;
}

export function useSystemMode() {
  return useContext(Ctx);
}
