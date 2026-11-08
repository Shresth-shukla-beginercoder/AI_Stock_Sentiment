/**
 * Single data-access hook for the whole console.
 *
 * Every panel/page goes through useApi — no page owns its own fetch logic.
 *
 * - `data`   is the UNWRAPPED payload (T for raw endpoints, X for Envelope<X>).
 * - `raw`    is the full response as received (the whole envelope, or the raw
 *            body) — feed this to RawJsonViewer for transparency.
 * - `meta`/`dataMode`/`asOf` are lifted from the envelope when present.
 *
 * Admin-protected fetchers are NOT issued unless a key is present in this
 * session (status "no_key" instead of 401 spam).
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { ApiHttpError, normalizeAxiosError } from "../api/client";
import { adminKey } from "../api/admin";
import type { DataMode, Envelope, EnvelopeMeta } from "../types/api";

export type ApiStatus = "idle" | "loading" | "success" | "error" | "no_key";

export interface UseApiState<P> {
  status: ApiStatus;
  /** Unwrapped payload (never the envelope). null until a successful fetch. */
  data: P | null;
  /** The full response as received (envelope or raw body) — for RawJsonViewer. */
  raw: unknown;
  meta: EnvelopeMeta | undefined;
  dataMode: DataMode | undefined;
  asOf: string | undefined;
  httpStatus: number | null;
  latencyMs: number | null;
  error: Error | null;
  lastChecked: Date | null;
  reload: () => void;
}

interface Options {
  /** Refresh automatically every N ms (0 = off). */
  refreshMs?: number;
  /** Bump this value to force a reload. */
  reloadKey?: unknown;
  /** Admin-protected endpoint: do not fire the request without a session key. */
  requiresAdmin?: boolean;
  deps?: unknown[];
}

export function isEnvelope(x: unknown): x is Envelope<unknown> {
  return typeof x === "object" && x !== null && "success" in x && "as_of" in x;
}

/**
 * @param fetcher Resolves to the raw response (an Envelope for most calls, a
 *   plain body for /health and /ready).
 * @param opts
 * @returns state where `data` is the unwrapped payload of type P.
 */
export function useApi<T, P = T>(
  fetcher: () => Promise<T>,
  opts: Options = {}
): UseApiState<P> {
  const { refreshMs = 0, reloadKey, requiresAdmin = false, deps = [] } = opts;
  const [status, setStatus] = useState<ApiStatus>("idle");
  const [data, setData] = useState<P | null>(null);
  const [raw, setRaw] = useState<unknown>(null);
  const [meta, setMeta] = useState<EnvelopeMeta | undefined>(undefined);
  const [dataMode, setDataMode] = useState<DataMode | undefined>(undefined);
  const [asOf, setAsOf] = useState<string | undefined>(undefined);
  const [httpStatus, setHttpStatus] = useState<number | null>(null);
  const [latencyMs, setLatencyMs] = useState<number | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [lastChecked, setLastChecked] = useState<Date | null>(null);
  const reqId = useRef(0);

  const run = useCallback(async () => {
    if (requiresAdmin && !adminKey.isConfigured()) {
      setStatus("no_key");
      return;
    }
    const id = ++reqId.current;
    setStatus("loading");
    setError(null);
    const t0 = performance.now();
    try {
      const res = await fetcher();
      if (id !== reqId.current) return; // stale
      setLatencyMs(Math.round(performance.now() - t0));
      setLastChecked(new Date());
      setHttpStatus(null);
      setRaw(res);
      if (isEnvelope(res)) {
        const env = res as Envelope<unknown>;
        setMeta("meta" in env ? env.meta : undefined);
        setDataMode(env.data_mode);
        setAsOf(env.as_of);
        if (env.success === false) {
          setError(new Error(env.error.message));
          setData(null);
          setStatus("error");
          return;
        }
        setData(env.data as P);
      } else {
        setData(res as unknown as P);
      }
      setStatus("success");
    } catch (err) {
      if (id !== reqId.current) return;
      setLatencyMs(Math.round(performance.now() - t0));
      setLastChecked(new Date());
      const norm =
        err instanceof ApiHttpError ? err : normalizeAxiosError(err as never);
      setHttpStatus(norm.httpStatus);
      setRaw(norm.body ?? null);
      setError(norm);
      setData(null);
      setStatus("error");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [requiresAdmin, ...deps]);

  useEffect(() => {
    run();
    if (refreshMs > 0) {
      const t = setInterval(run, refreshMs);
      return () => clearInterval(t);
    }
  }, [run, refreshMs, reloadKey]);

  return {
    status,
    data,
    raw,
    meta,
    dataMode,
    asOf,
    httpStatus,
    latencyMs,
    error,
    lastChecked,
    reload: run,
  };
}
