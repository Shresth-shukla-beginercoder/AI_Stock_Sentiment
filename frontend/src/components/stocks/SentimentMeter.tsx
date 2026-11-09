import { motion } from "framer-motion";

/**
 * Animated three-zone sentiment bar.
 *
 * The track is split into three visually distinct zones — NEGATIVE (red),
 * NEUTRAL (gray) and POSITIVE (green) — each animates in with its own
 * staggered reveal, glow and shimmer. A glowing needle springs to the exact
 * score position, and an emoji + label reflect the overall signal.
 *
 * Accepts a score in [-1, 1] (P(pos) - P(neg)). `null` renders a resting
 * neutral state.
 */

interface SentimentMeterProps {
  score: number | null;
  /** Compact mode for small cards / table cells. */
  compact?: boolean;
  showEmoji?: boolean;
}

type Signal = "positive" | "negative" | "neutral";

function signalFromScore(score: number | null): Signal {
  if (score === null) return "neutral";
  if (score > 0.15) return "positive";
  if (score < -0.15) return "negative";
  return "neutral";
}

function emojiFor(score: number | null): string {
  if (score === null) return "💤";
  const s = signalFromScore(score);
  if (s === "positive") return score > 0.5 ? "🚀" : "📈";
  if (s === "negative") return score < -0.5 ? "🔥" : "📉";
  return "⚖️";
}

const ZONES: { key: Signal; color: string; label: string }[] = [
  { key: "negative", color: "#ef4444", label: "Neg" },
  { key: "neutral", color: "#94a3b8", label: "Norm" },
  { key: "positive", color: "#10b981", label: "Pos" },
];

export function SentimentMeter({ score, compact = false, showEmoji = true }: SentimentMeterProps) {
  const s = signalFromScore(score);
  const emoji = emojiFor(score);
  const label = s.charAt(0).toUpperCase() + s.slice(1);
  const activeColor = ZONES.find((z) => z.key === s)!.color;

  // Score magnitude → how much of the outer zones light up. Neutral band stays centered.
  const mag = score === null ? 0 : Math.min(1, Math.abs(score));
  // zone widths (%) that add to 100: neg grows with negative magnitude, pos with positive.
  const negW = s === "negative" ? 15 + mag * 35 : 15;
  const posW = s === "positive" ? 15 + mag * 35 : 15;
  const neuW = 100 - negW - posW;
  const widths: Record<string, number> = { negative: negW, neutral: neuW, positive: posW };

  // Needle position on a 0-100 scale (left=most negative, right=most positive).
  const position = score === null ? 50 : Math.max(0, Math.min(100, ((score + 1) / 2) * 100));

  return (
    <div className={`w-full ${compact ? "space-y-2" : "space-y-4"}`}>
      {/* Header: emoji + label */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <motion.div
            key={emoji}
            initial={{ scale: 0.3, rotate: -20, opacity: 0 }}
            animate={{ scale: 1, rotate: 0, opacity: 1 }}
            transition={{ type: "spring", stiffness: 320, damping: 14 }}
            className={compact ? "text-2xl" : "text-4xl"}
            aria-label={label}
          >
            {showEmoji ? emoji : "•"}
          </motion.div>
          <div>
            <p className="text-[10px] uppercase tracking-widest text-muted">Sentiment</p>
            <motion.p
              key={s}
              initial={{ opacity: 0, x: -8 }}
              animate={{ opacity: 1, x: 0 }}
              className={`font-display font-bold ${compact ? "text-base" : "text-xl"}`}
              style={{ color: activeColor }}
            >
              {label}
            </motion.p>
          </div>
        </div>
        {!compact && (
          <p
            className="font-display text-3xl font-bold tabular-nums"
            style={{ color: activeColor }}
          >
            {score !== null ? (score > 0 ? "+" : "") + score.toFixed(2) : "—"}
          </p>
        )}
      </div>

      {/* Three-zone track */}
      <div className="relative">
        <div
          className={`flex overflow-hidden rounded-full ring-1 ring-white/10 ${
            compact ? "h-2.5" : "h-4"
          }`}
        >
          {ZONES.map((zone, i) => {
            const isActive = zone.key === s;
            return (
              <div key={zone.key} className="relative h-full" style={{ width: `${widths[zone.key]}%` }}>
                {/* zone base (staggered reveal) */}
                <motion.div
                  className="absolute inset-0"
                  initial={{ scaleX: 0, opacity: 0 }}
                  animate={{ scaleX: 1, opacity: isActive ? 1 : 0.55 }}
                  transition={{ delay: i * 0.12, duration: 0.5, ease: "easeOut" }}
                  style={{
                    transformOrigin: "left",
                    background: isActive
                      ? `linear-gradient(90deg, transparent, ${zone.color})`
                      : `linear-gradient(90deg, ${zone.color}22, ${zone.color}44)`,
                  }}
                />
                {/* shimmer sweep on the active zone only */}
                {isActive && (
                  <motion.div
                    className="absolute inset-0 overflow-hidden"
                    style={{ borderRadius: "inherit" }}
                  >
                    <motion.div
                      className="h-full w-1/3"
                      style={{
                        background:
                          "linear-gradient(90deg, transparent, rgba(255,255,255,0.5), transparent)",
                      }}
                      initial={{ x: "-150%" }}
                      animate={{ x: "400%" }}
                      transition={{ duration: 1.6, repeat: Infinity, ease: "linear", delay: i * 0.2 }}
                    />
                  </motion.div>
                )}
                {/* glow for active zone */}
                {isActive && (
                  <motion.div
                    className="absolute inset-0"
                    animate={{ opacity: [0.4, 0.8, 0.4] }}
                    transition={{ duration: 1.5, repeat: Infinity, ease: "easeInOut" }}
                    style={{ boxShadow: `inset 0 0 12px ${zone.color}` }}
                  />
                )}
              </div>
            );
          })}
        </div>

        {/* Needle marker */}
        <motion.div
          className="absolute top-1/2 -translate-y-1/2"
          initial={{ left: "50%" }}
          animate={{ left: `${position}%` }}
          transition={{ type: "spring", stiffness: 140, damping: 16, mass: 0.9 }}
          style={{ transform: "translateX(-50%)" }}
        >
          <div
            className={`rounded-full border-2 border-ink ${compact ? "h-4 w-4" : "h-6 w-6"} flex items-center justify-center`}
            style={{
              background: activeColor,
              boxShadow: `0 0 12px ${activeColor}`,
            }}
          >
            {compact && showEmoji && (
              <span className="text-[10px] leading-none">{emoji}</span>
            )}
          </div>
        </motion.div>
      </div>

      {/* Zone legend labels */}
      <div className={`flex justify-between ${compact ? "text-[9px]" : "text-[10px]"} font-mono uppercase tracking-wider`}>
        <span style={{ color: "#ef4444" }}>◄ Neg</span>
        <span className="text-muted">Neutral</span>
        <span style={{ color: "#10b981" }}>Pos ►</span>
      </div>
    </div>
  );
}
