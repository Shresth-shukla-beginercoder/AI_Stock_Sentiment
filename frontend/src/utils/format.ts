/** Small formatting helpers. Null/undefined values render as "—" — never 0. */

export const DASH = "—";

export function fmtNum(v: number | null | undefined, digits = 4): string {
  if (v === null || v === undefined || Number.isNaN(v)) return DASH;
  return Number.isInteger(v) ? String(v) : v.toFixed(digits).replace(/\.?0+$/, "") || "0";
}

export function fmtPct(v: number | null | undefined, digits = 1): string {
  if (v === null || v === undefined || Number.isNaN(v)) return DASH;
  return `${(v * 100).toFixed(digits)}%`;
}

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return DASH;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

export function fmtTime(iso: string | null | undefined): string {
  if (!iso) return DASH;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleTimeString();
}

export function fmtLatency(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return DASH;
  return ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(2)} s`;
}

/** Render an optional string field without leaking the word "undefined". */
export function fmtText(v: string | null | undefined): string {
  return v && v.length > 0 ? v : DASH;
}
