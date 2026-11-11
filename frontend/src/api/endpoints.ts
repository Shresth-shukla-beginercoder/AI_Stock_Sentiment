/**
 * Typed endpoint functions. One place for every backend call — pages and
 * panels call these, never raw axios. Every public (non-admin) call returns
 * the backend envelope; admin calls additionally attach the in-memory key.
 */
import { client } from "./client";
import { adminKey } from "./admin";
import type {
  Asset,
  CollectRunRequest,
  Envelope,
  HealthResponse,
  Job,
  JobCreatedData,
  MarketPrice,
  ModelEvaluation,
  ModelVersionsData,
  NewsArticle,
  OverviewData,
  Prediction,
  ReadyResponse,
  RankingRow,
  SentimentData,
  SocialPost,
  SystemStatusData,
  TickerReport,
  TrainRequest,
} from "../types/api";

export interface PageParams {
  limit?: number;
  offset?: number;
}

function pageQuery(p: PageParams): Record<string, number> {
  const out: Record<string, number> = {};
  if (p.limit !== undefined) out.limit = p.limit;
  if (p.offset !== undefined) out.offset = p.offset;
  return out;
}

// --- system -----------------------------------------------------------------
export const getHealth = () => client.get<HealthResponse>("/health").then((r) => r.data);
export const getReady = () =>
  // 503 is a valid readiness response, so do NOT let axios reject it.
  client.get<ReadyResponse>("/ready", { validateStatus: (s) => s < 500 }).then((r) => r.data);
export const getSystemStatus = () =>
  client.get<Envelope<SystemStatusData>>("/system/status").then((r) => r.data);

// --- assets -----------------------------------------------------------------
export const listAssets = (p?: PageParams) =>
  client.get<Envelope<Asset[]>>("/assets", { params: pageQuery(p ?? {}) }).then((r) => r.data);

export const getAsset = (ticker: string) =>
  client.get<Envelope<Asset>>(`/assets/${encodeURIComponent(ticker)}`).then((r) => r.data);

// --- posts / news / prices --------------------------------------------------
export const listPosts = (ticker: string, p?: PageParams) =>
  client
    .get<Envelope<SocialPost[]>>(`/posts/${encodeURIComponent(ticker)}`, { params: pageQuery(p ?? {}) })
    .then((r) => r.data);

export const listNews = (ticker: string, p?: PageParams) =>
  client
    .get<Envelope<NewsArticle[]>>(`/news/${encodeURIComponent(ticker)}`, { params: pageQuery(p ?? {}) })
    .then((r) => r.data);

export const listPrices = (ticker: string, p?: PageParams) =>
  client
    .get<Envelope<MarketPrice[]>>(`/prices/${encodeURIComponent(ticker)}`, { params: pageQuery(p ?? {}) })
    .then((r) => r.data);

export const getSentiment = (ticker: string) =>
  client.get<Envelope<SentimentData>>(`/sentiment/${encodeURIComponent(ticker)}`).then((r) => r.data);

export const listPredictions = (ticker: string, p?: PageParams) =>
  client
    .get<Envelope<Prediction[]>>(`/predictions/${encodeURIComponent(ticker)}`, {
      params: pageQuery(p ?? {}),
    })
    .then((r) => r.data);

// --- reports / models -------------------------------------------------------
export const getOverview = () => client.get<Envelope<OverviewData>>("/reports/overview").then((r) => r.data);
export const getRanking = () => client.get<Envelope<RankingRow[]>>("/reports/ranking").then((r) => r.data);
// W5: per-ticker, exchange-separated report (price / sentiment / direction / S-R / mentions).
// Same shape demo and live return; nulls mark missing data, never zero.
export const getTickerReport = () =>
  client.get<Envelope<TickerReport>>("/reports/tickers").then((r) => r.data);

export const listEvaluations = (p?: PageParams) =>
  client
    .get<Envelope<ModelEvaluation[]>>("/models/evaluation", { params: pageQuery(p ?? {}) })
    .then((r) => r.data);

export const listModelVersions = () =>
  client.get<Envelope<ModelVersionsData>>("/models/versions").then((r) => r.data);

// --- jobs (admin) -----------------------------------------------------------
function adminHeaders(): Record<string, string> {
  const key = adminKey.get();
  if (!key) throw new Error("No admin key set in this session.");
  return { "X-API-Key": key };
}

export const listJobs = (p?: PageParams) =>
  client
    .get<Envelope<Job[]>>("/jobs", { params: pageQuery(p ?? {}), headers: adminHeaders() })
    .then((r) => r.data);

export const getJob = (jobId: number) =>
  client.get<Envelope<Job>>(`/jobs/${jobId}`, { headers: adminHeaders() }).then((r) => r.data);

export const queueCollect = (body: CollectRunRequest) =>
  client
    .post<Envelope<JobCreatedData>>("/collect/run", body, {
      headers: adminHeaders(),
      validateStatus: (s) => s < 500, // 409 duplicate is a valid answer
    })
    .then((r) => r.data);

export const queueTrain = (body: TrainRequest) =>
  client
    .post<Envelope<JobCreatedData>>("/models/train", body, {
      headers: adminHeaders(),
      validateStatus: (s) => s < 500,
    })
    .then((r) => r.data);
