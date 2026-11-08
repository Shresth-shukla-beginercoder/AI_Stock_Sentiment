# Progress Tracking

## Phases
- [x] Phase 0: Understand and plan — approved with corrections
- [x] Phase 1: Foundation and Docker skeleton — **COMPLETE** (2026-11-08)
- [ ] Phase 2: Database schema and migrations — **IN PROGRESS**
- [ ] Phase 3: API contract and clearly labelled demo data
- [ ] Phase 4: Verification Console v1, Nginx and the frontend service
- [ ] Phase 5: Collectors and normalisation
- [ ] Phase 6: Sentiment engine
- [ ] Phase 7: Worker, jobs and scheduling
- [ ] Phase 8: Features, model, evaluation, support/resistance
- [ ] Phase 9: End-to-end integration run
- [ ] Phase 10: Hardening tests and security
- [ ] Phase 11: Production compose, images and README
- [ ] Phase 12: Frontend handoff package

## Confirmed Decisions (Phase 0)
- **Pinned toolchain (approved)**: Python **3.12**, Node.js **22** — hard runtime
  versions in the backend/frontend Dockerfiles.
- **Ticker universe (PENDING explicit user confirmation — NOT finalized)**:
  - HKEX: Tencent `0700`/`0700.HK`, Alibaba `9988`/`9988.HK`, Xiaomi `1810`/`1810.HK`,
    Meituan `3690`/`3690.HK`, HSBC `0005`/`0005.HK`
  - KRX: Samsung Electronics `005930`/`005930.KS`, SK Hynix `000660`/`000660.KS`,
    NAVER `035420`/`035420.KS`, Kakao `035720`/`035720.KS`, Hyundai Motor `005380`/`005380.KS`
  - These serve as the **proposed assessment universe** for the provider-coverage
    evaluation. Provider tickers remain swappable per vendor.
- **Market data provider: `12data` (OWNER-SELECTED in Phase 1; capability UNVERIFIED).**
  Key recorded in local `.env` (`MARKET_DATA_PROVIDER=12data`, `MARKET_DATA_API_KEY=***
  Phase 1 builds the abstract `get_daily_prices(ticker, start, end)` interface only.
  Vendor symbol coverage/quotas/ToS stay UNVERIFIED until a real Phase 5 fetch.
  Fallback options A–D remain documented in `docs/PROVIDER_COVERAGE.md`.
- **Apify Actors: IDs and input schemas UNVERIFIED.** No assumed Actor support;
  verify with the user before Phase 5.
- **External search/news APIs**: Exa (`exa_py`) and Tavily are the confirmed
  candidates for news/web search. Their respective skill docs
  (Exa `build-with-exa`, Tavily `SKILL.md`) are the canonical references — read them
  before implementing; do not rely on memory. Keys exist in the user's local `.env`
  only; never in chat, code, git, or images.
