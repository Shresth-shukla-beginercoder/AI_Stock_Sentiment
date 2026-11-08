# AI Stock Sentiment & Next-Day Prediction Agent

Research platform: collects social posts + news for 10 stocks (5 HKEX, 5 KRX), NLP sentiment,
price history, experimental next-day-return model, served via API. **Not financial advice,
not a trading bot.**

## Lead Engineer Protocol (every phase)
1. Print a short plan: files, commands, risks.
2. Build only the current phase. Never start the next one.
3. Run the phase's verification gate; keep the real output.
4. Print a PHASE REPORT: what was built, commands run with real results, UNVERIFIED items,
   files changed, open questions.
5. Commit as `phase-N: <summary>`, tag `phase-N`, update CLAUDE.md (status line),
   docs/PROGRESS.md, docs/VERIFICATION.md.
6. Stop and wait for the user's go.

## Truth Rules (non-negotiable)
- Never say something works unless you ran it. If you cannot run it (no Docker, no keys,
  no network): write **UNVERIFIED** and give the exact command to run manually.
- Never fabricate data, sources, metrics, URLs, Actor IDs, model names or results.
  Unknown → placeholder + ask the user.
- Demo data allowed only when flagged: `is_demo` column AND `data_mode: demo` in every response.
- No secrets in code, images, git, logs, or the frontend. Only `.env.example` with
  placeholder names. Real keys live only in the user's local `.env`.
- If the master prompt is ambiguous or self-conflicting, say so — do not guess.

## Pinned Versions (hard)
- **Python 3.12** (backend Dockerfile; local dev may differ but Docker is source of truth)
- **Node.js 22** (frontend Dockerfile / build)

## Proposed Ticker Universe (PENDING user's explicit confirmation — not final)
- HKEX: Tencent `0700`/`0700.HK`, Alibaba `9988`/`9988.HK`, Xiaomi `1810`/`1810.HK`,
  Meituan `3690`/`3690.HK`, HSBC `0005`/`0005.HK`
- KRX: Samsung Electronics `005930`/`005930.KS`, SK Hynix `000660`/`000660.KS`,
  NAVER `035420`/`035420.KS`, Kakao `035720`/`035720.KS`, Hyundai Motor `005380`/`005380.KS`

## Provider / Collector Decisions
- **Market data provider: `twelve_data`** (owner-selected in Phase 1). `MARKET_DATA_PROVIDER=twelve_data`
  and `TWELVE_DATA_API_KEY` live in the local `.env` only. Vendor capabilities, symbol
  coverage, quotas and ToS are **UNVERIFIED** until a real Phase 5 fetch. A configured
  key does NOT mean the provider is operational. No vendor code is implemented in Phase 1
  — only the `get_daily_prices(ticker, start, end)` interface.
- **Apify Actor IDs / input schemas: UNVERIFIED.** Do not invent or assume Actor support;
  verify with the user before Phase 5.
- **Exa and Tavily keys** are available in the user's local `.env` (never in chat, code,
  or git). Tavily SKILL.md and Exa `build-with-exa` skill are the canonical references
  for their respective APIs — consult them, don't guess.
- **A third search/market-data API key** also exists in the user's `.env`; its exact
  vendor name is **UNVERIFIED** — do not assume or spell a vendor name until the user
  confirms it.

## Architecture
- **Frontend-agnostic backend.** The Verification Console is a disposable client of the
  REST contract: same `frontend/` folder, same Compose service name `frontend`, host
  port 3000, static build on Nginx with `/api/` proxied to backend.
- Handoff artifacts: `docs/openapi.json`, generated TypeScript types,
  `docs/FRONTEND_CONTRACT.md`.

### Folder tree
```
.
├── .env.example
├── .gitignore
├── .dockerignore
├── docker-compose.yml
├── docker-compose.prod.yml            # Phase 11
├── CLAUDE.md
├── README.md                          # Phase 11
├── backend/
│   ├── Dockerfile
│   ├── pyproject.toml
│   ├── alembic.ini
│   ├── app/
│   │   ├── main.py
│   │   ├── api/                        # routers
│   │   ├── core/                      # config.py, logging.py
│   │   ├── database/                  # base.py, models.py, session.py, migrations/
│   │   ├── collectors/                # provider interface, exa.py, apify.py, market
│   │   ├── sentiment/                 # cleaner, language routing, analyzer, aggregator
│   │   ├── features/                  # indicators, build_features, make_target, sessions
│   │   ├── models/                    # trainer, walk-forward, registry
│   │   ├── workers/                   # main.py: claim, scheduler, reaper, dispatch
│   │   ├── schemas/
│   │   ├── services/
│   │   └── scripts/                   # seed_demo.py, export_openapi.py
│   └── tests/
├── frontend/
│   ├── Dockerfile                     # multi-stage → nginx static
│   ├── nginx.conf                     # /api/ → backend:8000, SPA fallback
│   ├── package.json
│   └── src/
│       ├── api/                       # single axios layer + generated types
│       ├── components/                # Panel, TopBar, DemoBanner
│       ├── pages/                     # ConnectionBoard, SystemStatus, Assets,
│       │                               # StockInspector, Jobs, ModelPerformance, Lineage
│       └── types/                     # generated from docs/openapi.json
└── docs/
    ├── PROGRESS.md
    ├── VERIFICATION.md
    ├── openapi.json                   # Phase 3
    └── FRONTEND_CONTRACT.md           # Phase 3 draft, Phase 12 final
```

## Key Design Constants
- **Ports**: Postgres in-container 5432, host-published 5437 (dev only). Backend 8000.
  Frontend host 3000 → Nginx 80. One network `stock_network`, one volume `postgres_data`.
- **Settings**: defaults suit the laptop (localhost, 5437); Compose overrides
  `POSTGRES_HOST=postgres`, `POSTGRES_PORT=5432`. Real env vars beat `.env`.
- **DATA_MODE**: explicit config setting (`DATA_MODE`, safe default `demo`). Never
  inferred from key presence. Credential availability and live-data availability are
  reported separately.
- **Health endpoints**: `GET /api/health` = application liveness only;
  `GET /api/ready` = PostgreSQL readiness. DB-down tests exercise **readiness**.
- **Alembic at startup**: entrypoint runs `alembic upgrade head` **only when at least
  one migration revision exists** (skips cleanly with a log line while no migrations
  exist, as in Phase 1). Decision: conditional execution, documented here.
- **DB**: 8 tables, created **only by Alembic** (never `create_all`). UTC everywhere.
  Dedupe via SHA-256 content hash + ON CONFLICT DO NOTHING. No data ⇒ NULL, never 0.
- **Sentiment**: score = P(pos) − P(neg); weight = 1 + ln(1 + engagement) (missing ⇒ 0);
  combined = 0.4 social + 0.6 news (configurable); signal thresholds ±0.15;
  min item count ⇒ `insufficient_data`; 10-day window. Sentiment ≠ ML prediction.
- **Prediction**: target = next-day return; walk-forward TimeSeriesSplit(gap=1), never
  random split; scalers fit inside training folds; baselines = no-change & always-up;
  metrics MAE / RMSE / directional accuracy; fixed seeds; model registry with git commit.
  Insufficient overlap ⇒ `experimental: true`.
- **Worker**: `UPDATE ... FOR UPDATE SKIP LOCKED` claim; one scheduler via
  `pg_try_advisory_lock`; unique `dedupe_key`; exponential backoff; reaper for stuck
  running jobs; graceful SIGTERM; `--once` batch mode.
- **API**: prefix `/api`; OpenAPI at `/api/openapi.json`, Swagger `/docs`; heavy work
  queued (POST → 202 + job id, 409 duplicate, 401 bad key); admin via `X-API-Key`
  checked with `secrets.compare_digest`; one error envelope; ISO-8601 UTC;
  list endpoints paginated; every data response carries `data_mode` + `as_of`;
  never mix live and demo rows in one response; CORS explicit origin list, never `*`.

## Status
- **Current Phase**: Phase 2: Database schema and migrations — starting now
- Phase 1: Foundation and Docker skeleton — **COMPLETE** (approved by owner 2026-11-08)
