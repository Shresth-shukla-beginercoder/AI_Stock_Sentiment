/**
 * W5: per-ticker, exchange-separated report.
 *
 * Renders the SAME data the API serves at GET /api/reports/tickers (one
 * section per exchange, ranked). Missing data renders "—" (never 0): a
 * zero in a mentions cell is a real count, while null upstream fields
 * (price / sentiment / S-R) mean "not yet known".
 */
import { useApi } from "../../hooks/useApi";
import { getTickerReport } from "../../api/endpoints";
import { Card, CardHeader, CardContent } from "../common/Card";
import { StatusBadge } from "../common/StatusBadge";
import { ArrowUp, ArrowDown, Minus, Inbox } from "lucide-react";
import { DASH, fmtNum, fmtText } from "../../utils/format";
import type { TickerReport, TickerReportRow, Envelope } from "../../types/api";

function DirectionBadge({ direction }: { direction: TickerReportRow["direction"] }) {
  const map = {
    up: { label: "Up", cls: "text-pos bg-pos/10 border-pos/30", icon: <ArrowUp className="h-3.5 w-3.5" /> },
    down: { label: "Down", cls: "text-danger bg-danger/10 border-danger/30", icon: <ArrowDown className="h-3.5 w-3.5" /> },
    flat: { label: "Flat", cls: "text-muted bg-navy/40 border-white/10", icon: <Minus className="h-3.5 w-3.5" /> },
    none: { label: "No prediction", cls: "text-muted bg-navy/40 border-white/10", icon: <Minus className="h-3.5 w-3.5" /> },
  }[direction];
  return (
    <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium ${map.cls}`}>
      {map.icon}
      {map.label}
    </span>
  );
}

function TickerReportRowCard({ row }: { row: TickerReportRow }) {
  const price = row.current_price;
  const sr = row.support_resistance;
  const pred = row.prediction;
  return (
    <Card>
      <CardContent className="p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2.5">
            <span className="rounded-md bg-navy/60 px-1.5 py-0.5 font-mono text-xs text-muted">#{row.rank}</span>
            <span className="font-mono font-bold text-text-primary">{row.ticker}</span>
            <span className="text-xs text-muted">{fmtText(row.name)}</span>
            {row.is_demo && <StatusBadge tone="warn">demo</StatusBadge>}
            <DirectionBadge direction={row.direction} />
          </div>
          <div className="text-right">
            <div className="font-mono text-lg font-bold text-text-primary">
              {price ? fmtNum(price.close, 2) : DASH}
              {price?.close == null && <span className="ml-1 text-xs text-muted">no data</span>}
            </div>
            <div className="text-xs text-muted">
              {price ? `as of ${fmtText(price.trade_date)} · ${fmtText(price.provider)}` : "price not stored yet"}
            </div>
          </div>
        </div>

        <div className="mt-3 grid grid-cols-2 gap-2 text-xs sm:grid-cols-4">
          <div className="rounded-lg bg-navy/30 p-2">
            <div className="text-muted">Sentiment</div>
            <div className="font-mono font-semibold text-text-primary">
              {row.sentiment.score == null ? DASH : fmtNum(row.sentiment.score, 3)}
            </div>
            <div className="text-muted">{fmtText(row.sentiment.signal)}</div>
          </div>
          <div className="rounded-lg bg-navy/30 p-2">
            <div className="text-muted">Support / Resistance</div>
            <div className="font-mono font-semibold text-text-primary">
              {sr.support == null && sr.resistance == null ? DASH : `${fmtNum(sr.support, 2)} / ${fmtNum(sr.resistance, 2)}`}
            </div>
            <div className="text-muted">
              {sr.data_sufficient
                ? `position: ${row.position}`
                : sr.support == null && sr.resistance == null
                  ? "insufficient history — levels not fabricated"
                  : `position: ${row.position}`}
            </div>
          </div>
          <div className="rounded-lg bg-navy/30 p-2">
            <div className="text-muted">Prediction</div>
            <div className="font-mono font-semibold text-text-primary">
              {pred?.predicted_return == null ? DASH : `${fmtNum(pred.predicted_return * 100, 2)}%`}
            </div>
            <div className="text-muted">
              {pred
                ? `${fmtText(pred.model_version)}${pred.experimental ? " · experimental" : ""}`
                : "no prediction yet"}
            </div>
          </div>
          <div className="rounded-lg bg-navy/30 p-2">
            <div className="text-muted">Mentions (social / news)</div>
            <div className="font-mono font-semibold text-text-primary">
              {row.mentions.social_posts} / {row.mentions.news_articles}
            </div>
            <div className="text-muted">0 = stored count of zero</div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

export function TickerReport() {
  const report = useApi<Envelope<TickerReport>, TickerReport>(() => getTickerReport());

  if (report.status === "loading") {
    return (
      <div className="space-y-3">
        <div className="shimmer h-24 rounded-xl bg-navy/30" />
        <div className="shimmer h-24 rounded-xl bg-navy/30" />
      </div>
    );
  }
  if (report.status === "error" || !report.data) {
    return (
      <Card>
        <CardContent className="flex flex-col items-center gap-2 p-6 text-center">
          <Inbox className="h-6 w-6 text-muted" />
          <p className="text-sm text-muted">
            Report unavailable{report.error ? `: ${report.error.message}` : ""}.
          </p>
        </CardContent>
      </Card>
    );
  }

  const { exchanges, ranking, meta, as_of } = report.data;
  return (
    <div className="space-y-5">
      <Card>
        <CardHeader
          title="Universe report"
          subtitle={`as of ${fmtText(as_of)} · ranking: ${meta.ranking_rule}`}
        />
        <CardContent className="p-3 text-xs text-muted">
          <div className="grid gap-2 sm:grid-cols-2">
            <div>
              Sentiment thresholds: bullish ≥ {meta.sentiment_thresholds.bullish}, bearish ≤{" "}
              {meta.sentiment_thresholds.bearish}, min items {meta.sentiment_thresholds.min_items} (
              {meta.sentiment_thresholds.window_days}-day window)
            </div>
            <div>S/R window: {meta.support_resistance_window_sessions} sessions · {meta.direction_rule}</div>
            <div className="sm:col-span-2">{meta.missing_policy}</div>
          </div>
        </CardContent>
      </Card>

      {exchanges.length === 0 && (
        <Card>
          <CardContent className="flex flex-col items-center gap-2 p-6 text-center">
            <Inbox className="h-6 w-6 text-muted" />
            <p className="text-sm text-muted">No assets stored yet — the report is empty, not fabricated.</p>
          </CardContent>
        </Card>
      )}

      {exchanges.map((ex) => (
        <div key={ex.exchange} className="space-y-3">
          <div className="flex items-center gap-2">
            <h3 className="font-display text-lg font-bold tracking-wide text-text-primary">{ex.exchange}</h3>
            <StatusBadge tone="neutral">{fmtText(ex.timezone)}</StatusBadge>
            <span className="text-xs text-muted">{ex.tickers.length} ticker(s)</span>
          </div>
          {ex.tickers.length === 0 ? (
            <p className="text-sm text-muted">No tickers on {ex.exchange}.</p>
          ) : (
            <div className="grid gap-3">
              {ex.tickers.map((row) => (
                <TickerReportRowCard key={row.ticker} row={row} />
              ))}
            </div>
          )}
        </div>
      ))}

      {ranking.length > 0 && (
        <details className="rounded-xl border border-white/10 bg-navy/30 p-3 text-xs text-muted">
          <summary className="cursor-pointer font-medium text-text-primary">
            Flat ranking across all exchanges ({ranking.length})
          </summary>
          <ol className="mt-2 space-y-1">
            {ranking.map((r, i) => (
              <li key={`${r.ticker}-${i}`} className="font-mono">
                {r.ticker} · {fmtText(r.name)} · sentiment {r.sentiment.score == null ? DASH : fmtNum(r.sentiment.score, 3)} · {r.direction}
              </li>
            ))}
          </ol>
        </details>
      )}
    </div>
  );
}
