/**
 * React binding over the in-memory admin key.
 *
 * Returns whether a key is configured this session and functions to set / clear
 * it. The key lives ONLY in module memory (see api/admin.ts) — it is never
 * persisted to storage, never a build-time VITE_ var, and never logged.
 */
import { useCallback, useState } from "react";
import { adminKey } from "../api/admin";

export function useAdminAuth() {
  const [configured, setConfigured] = useState<boolean>(adminKey.isConfigured());

  const setKey = useCallback((value: string) => {
    adminKey.set(value);
    setConfigured(adminKey.isConfigured());
  }, []);

  const clearKey = useCallback(() => {
    adminKey.clear();
    setConfigured(false);
  }, []);

  return { configured, setKey, clearKey };
}
