# Frontend Contract (Phase 3 draft — final in Phase 12)

Canonical machine-readable source: **`docs/openapi.json`** (exported from the running
backend; live copy at `GET /api/openapi.json`). Generated TypeScript types must come
from that file, never hand-written. Swagger UI: `GET /docs`.

## Base URL

Backend serves under `/api`. Frontend (Nginx) proxies `/api/` → backend:8000, so the
axios layer targets **same-origin `/api`** in dev — never a hard-coded host, never a
secret.

## Response envelope (every data response)

```jsonc
// success
{ "success": true, "data": ..., "meta": { ... }, "data_mode": "demo"|"live", "as_of": "2026-11-08T08:15:00+00:00" }
// error — one envelope shape for all failures
{ "success": false, "error": { "code": "not_found"|"validation_error"|"unauthorized"|"duplicate_job"|"internal_error"|..., "message": "...", "details": { ... }? }, "data_mode": "demo", "as_of": "..." }
```

- `as_of` is UTC ISO-8601. `data_mode` is always present.
- **Demo and live rows are NEVER combined in one response.**
- `meta` on list endpoints: `{ limit, offset, total, state: "ok"|"no_data", source, note? }`,
  plus `has_more` where paginated.

## Endpoints (22)

| Method | Path | Auth | Notes |
|---|---|---|---|
| GET | `/api/health` | – | app liveness only |
| GET | `/api/ready` | – | Postgres readiness (200/503) |
| GET | `/api/system/status` | – | data_mode, provider, credentials (names only), feature_status |
| GET | `/api/assets` | – | paginated |
| GET | `/api/assets/{ticker}` | – | 404 unknown ticker |
| GET | `/api/posts/{ticker}` | – | paginated |
| GET | `/api/news/{ticker}` | – | paginated |
| GET | `/api/prices/{ticker}` | – | paginated |
| GET | `/api/sentiment/{ticker}` | – | score / signal / counts |
| GET | `/api/predictions/{ticker}` | – | paginated, `experimental` flag |
| GET | `/api/reports/overview` | – | universe + counts + per-ticker |
| GET | `/api/reports/ranking` | – | ranked by sentiment |
| GET | `/api/models/evaluation` | – | paginated |
| GET | `/api/models/versions` | – | version list |
| GET | `/api/jobs` | admin | paginated job list |
| GET | `/api/jobs/{job_id}` | admin | 404 unknown id |
| POST | `/api/collect/run` | admin | 202 + job id, 409 duplicate |
| POST | `/api/models/train` | admin | 202 + job id, 409 duplicate |

(`docs/openapi.json` also documents `/api/openapi.json` and `/docs` themselves.)

## Demo data

- Demo mode serves a **synthetic, isolated** universe: `DEMO-HK-001`, `DEMO-KR-001`
  (clearly separate from real HKEX/KRX tickers). Every synthetic asset carries
  `is_demo: true`, `provider_ticker: null`, `confirmed: false`, and the whole response
  carries `data_mode: "demo"`.
- Real proposed tickers (`0700`, `005930`, …) remain **unconfirmed** and 404 in demo
  mode. A `DEMO` banner must be shown whenever `data_mode === "demo"`.
- Live mode returns honest `no_data` states until Phases 5–8 populate the DB.

## Admin auth

Admin endpoints require header `X-API-Key`. `401` when the key is absent, wrong, or the
backend has no admin key configured. Send the key only to admin routes; treat a `401`
as "admin not configured / wrong key", not a crash.

## Generated types

```
npx openapi-typescript https://<backend>/api/openapi.json -o frontend/src/types/api.ts
```

Single axios layer in `frontend/src/api/` over these types; no per-page fetch code.

## Scope (not implemented yet)

Collectors, sentiment inference, worker execution and model training arrive in
Phases 5–8. The contract already exposes their shapes (posts/news/prices/sentiment/
predictions/models/jobs) with `no_data` / `planned` states — the console must render
those honestly, not as errors.
