/**
 * Shown whenever the backend reports data_mode === "demo": makes it
 * impossible to mistake synthetic rows for real market data.
 */
export function DemoBanner() {
  return (
    <div className="flex items-center gap-2 rounded-lg border border-warn/40 bg-warn/10 px-3 py-2 text-xs text-warn">
      <span aria-hidden>⚠</span>
      <span>
        <strong className="font-semibold">DEMO MODE</strong> — showing synthetic, deterministic
        demo data (is_demo&nbsp;= true). This is not real market data and the 10 proposed
        HKEX/KRX tickers remain unconfirmed.
      </span>
    </div>
  );
}
