/**
 * TypeScript interfaces for the backend contract.
 *
 * Source of truth: docs/openapi.json + the actual backend route/store response
 * shapes (verified in Phase 3). Fields that are legitimately NULL in the
 * backend (e.g. engagement, volume, actual_close, git_commit) are typed as
 * nullable — the console renders them as "—" and never substitutes 0 or fake
 * values.
 */

export type DataMode = "demo" | "live";

// --- envelope ---------------------------------------------------------------
export interface SuccessEnvelope<T> {
  success: true;
  data: T;
  meta?: EnvelopeMeta;
  data_mode: DataMode;
  as_of: string;
}

export interface ErrorEnvelope {
  success: false;
  error: {
    code: string;
    message: string;
    details?: Record<string, unknown>;
  };
  data_mode?: DataMode;
  as_of: string;
}

export type Envelope<T> = SuccessEnvelope<T> | ErrorEnvelope;

export interface EnvelopeMeta {
  source?: string;
  note?: string;
  state?: "ok" | "no_data" | "insufficient_data" | string;
  total?: number;
  limit?: number;
  offset?: number;
  has_more?: boolean;
}

// --- system -----------------------------------------------------------------
export interface HealthResponse {
  status: string;
  app: string;
  data_mode: DataMode;
  market_data_provider: string | null;
  timestamp: string;
}

export interface ReadyResponse {
  status: "ready" | "not_ready" | string;
  database: "up" | "down" | string;
  detail?: string;
  timestamp: string;
}

export interface SystemStatusData {
  app: string;
  version: string;
  data_mode: DataMode;
  market_data_provider: string | null;
  provider_capability: string;
  credentials: {
    configured: string[];
    missing: string[];
  };
  feature_status: Record<string, string>;
}

// --- assets -----------------------------------------------------------------
export interface Asset {
  exchange: string;
  ticker: string;
  name: string | null;
  provider_ticker: string | null;
  provider_symbol_format: string | null;
  market_data_provider: string | null;
  confirmed: boolean;
  active: boolean;
  is_demo: boolean;
}

// --- posts / news -----------------------------------------------------------
export interface SocialPost {
  id: number;
  asset_ticker: string;
  source: string;
  content_hash: string;
  content: string;
  language: string | null;
  url: string | null;
  published_at: string | null;
  engagement: number | null; // NULL stays NULL — never 0
  is_demo: boolean;
}

export interface NewsArticle {
  id: number;
  asset_ticker: string;
  source: string;
  url_hash: string;
  title: string;
  body: string | null;
  url: string | null;
  published_at: string | null;
  is_demo: boolean;
}

// --- market data ------------------------------------------------------------
export interface MarketPrice {
  id: number;
  asset_ticker: string;
  provider: string;
  trade_date: string;
  open: number | null;
  high: number | null;
  low: number | null;
  close: number | null;
  volume: number | null;
  is_demo: boolean;
}

// --- sentiment --------------------------------------------------------------
export interface SentimentData {
  asset_ticker: string;
  window_days: number;
  as_of: string;
  state: "sufficient" | "insufficient_data" | "no_data" | string;
  counts: {
    positive: number;
    neutral: number;
    negative: number;
  };
  total_items: number;
  p_pos: number | null;
  p_neu: number | null;
  p_neg: number | null;
  score: number | null;
  signal: "positive" | "neutral" | "negative" | null;
  is_demo?: boolean;
}

// --- predictions / models ---------------------------------------------------
export interface Prediction {
  id: number;
  asset_ticker: string;
  model_version: string;
  target_date: string;
  made_at: string | null;
  predicted_return: number | null;
  predicted_price: number | null;
  actual_close: number | null; // stays NULL until backfilled
  experimental: boolean;
  is_demo?: boolean;
}

export interface ModelEvaluation {
  id: number;
  model_version: string;
  mae: number | null;
  rmse: number | null;
  directional_accuracy: number | null;
  baseline_nochange_mae: number | null;
  baseline_nochange_rmse: number | null;
  baseline_nochange_dir_acc: number | null;
  baseline_alwaysup_dir_acc: number | null;
  n_test: number | null;
  params: Record<string, unknown> | null;
  git_commit: string | null; // NULL until a real training run records it
  trained_at: string | null;
  is_demo?: boolean;
}

export interface ModelVersionsData {
  versions: string[];
}

// --- reports ----------------------------------------------------------------
export interface OverviewData {
  universe: string[];
  counts: {
    assets: number;
    social_posts: number;
    news_articles: number;
    market_prices: number;
    predictions: number;
    model_versions: number;
  };
  state: "ok" | "no_data" | string;
  note?: string;
  is_demo?: boolean;
  per_ticker?: Record<string, { sentiment_score: number | null; sentiment_signal: string | null }>;
}

export interface RankingRow {
  ticker: string;
  name: string | null;
  score: number | null;
  state: string;
  rank: number;
}

// W5: per-ticker, exchange-separated report — SAME shape demo & live return.
// null marks "not yet known / no data stored"; a 0 is a real zero count.
export interface TickerReportPrice {
  close: number | null;
  provider: string;
  trade_date: string;
}

export interface TickerReportSentiment {
  score: number | null;
  signal: string | null;
  state: string;
}

export interface TickerReportPrediction {
  model_version: string;
  target_date: string;
  predicted_return: number | null;
  predicted_price: number | null;
  actual_close: number | null;
  experimental: boolean;
  direction: "up" | "down" | "flat" | "none";
}

export interface TickerReportSupportResistance {
  support: number | null;
  resistance: number | null;
  method: string;
  window_sessions: number;
  available_sessions: number;
  data_sufficient: boolean;
  as_of: string | null;
  basis: string;
}

export interface TickerReportRow {
  ticker: string;
  name: string | null;
  rank: number;
  current_price: TickerReportPrice | null;
  sentiment: TickerReportSentiment;
  direction: "up" | "down" | "flat" | "none";
  prediction: TickerReportPrediction | null;
  support_resistance: TickerReportSupportResistance;
  position: "above_resistance" | "between" | "below_support" | "unknown";
  mentions: { social_posts: number; news_articles: number; total: number };
  is_demo: boolean;
}

export interface TickerReportExchange {
  exchange: string;
  timezone: string;
  tickers: TickerReportRow[];
}

export interface TickerReport {
  as_of: string;
  exchanges: TickerReportExchange[];
  ranking: TickerReportRow[];
  meta: {
    generated_at: string;
    ranking_rule: string;
    sentiment_thresholds: {
      bullish: number;
      bearish: number;
      min_items: number;
      window_days: number;
    };
    support_resistance_window_sessions: number;
    direction_rule: string;
    missing_policy: string;
  };
}

// --- jobs -------------------------------------------------------------------
export interface Job {
  id: number;
  job_type: string;
  status: string;
  dedupe_key: string;
  params: Record<string, unknown> | null;
  attempts: number;
  max_attempts: number;
  error: string | null;
  claimed_by: string | null;
  claimed_at: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface JobCreatedData {
  job_id: number;
  dedupe_key: string;
  status: string;
  params: Record<string, unknown> | null;
}

export interface CollectRunRequest {
  tickers: string[];
  source?: "all" | "social" | "news";
  label?: string | null;
}

export interface TrainRequest {
  tickers?: string[] | null;
  model_name?: string | null;
}
