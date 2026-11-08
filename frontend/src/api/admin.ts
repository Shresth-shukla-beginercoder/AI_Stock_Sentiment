/**
 * In-memory, session-scoped admin key holder.
 *
 * - The key is stored ONLY in a module-level variable. It is never written to
 *   localStorage/sessionStorage/IndexedDB, never a VITE_ build-time variable,
 *   never logged, and it disappears on page reload.
 * - The admin key must come from the user's own input at runtime (a "Set admin
 *   key" field on the Jobs page) — it is NOT embedded in source code.
 */
let key: string | null = null;

export const adminKey = {
  get(): string | null {
    return key;
  },
  set(value: string): void {
    key = value.trim() ? value.trim() : null;
  },
  clear(): void {
    key = null;
  },
  isConfigured(): boolean {
    return key !== null;
  },
};
