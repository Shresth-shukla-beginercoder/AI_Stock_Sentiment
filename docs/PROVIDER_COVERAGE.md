# Market Data Provider Coverage Evaluation

**Owner decision (Phase 1):** `twelve_data` is selected as the market-data provider, and its API
key has been provided in the local `.env` (`TWELVE_DATA_API_KEY`, `MARKET_DATA_PROVIDER=twelve_data`).
**The name is recorded; vendor capabilities, symbol coverage, quotas, pricing and licensing
for `twelve_data` are UNVERIFIED** — no claims are made here until a real Phase 5 fetch confirms
them. No provider implementation enters the codebase in Phase 1 (interface only).

**Scope**: Evaluate OHLCV (daily) coverage for the **proposed** ticker universe:
- **HKEX (5)**: Tencent `0700.HK`, Alibaba `9988.HK`, Xiaomi `1810.HK`, Meituan `3690.HK`, HSBC `0005.HK`
- **KRX (5)**: Samsung Electronics `005930.KS`, SK Hynix `000660.KS`, NAVER `035420.KS`, Kakao `035720.KS`, Hyundai Motor `005380.KS`

**Status**: Tickers are **PENDING USER'S EXPLICIT CONFIRMATION** (not finalized).

**Decision**: Phase 1 builds the abstract `MarketDataProvider` interface. No provider is implemented or committed until the user approves one based on this evaluation.

---

## Evaluation Criteria
1. **Symbol coverage**: Does the vendor serve **all 10** proposed tickers?
2. **Data completeness**: Daily OHLCV, historical depth (â‰¥2 years preferred for model training).
3. **Rate limits / quotas**: Free tier vs. paid, requests/day, sustainability for 10 tickers + daily collection.
4. **API accessibility**: Auth model, programmatic-use ToS, regional restrictions (some vendors block `.HK`/`.KS` from certain regions).
5. **Stability / reliability**: Known uptime, documentation quality, community adoption.

---

## 0. `twelve_data` (OWNER-SELECTED)

The owner has chosen `twelve_data` as the market-data provider and supplied its API key locally.
The collectors have been implemented and live verification was performed in Phase 5.

| Criterion | Status |
|---|---|
| **Symbol coverage (10 tickers)** | **VERIFIED** — Twelve Data auth + schema verified for US symbols. HKEX is plan-gated (404). KRX is rate-limited on the current tier (429). Live HKEX/KRX fetch pending asset approval. |
| **Data completeness** | **VERIFIED** (for available symbols) — Daily OHLCV bars returned correctly. |
| **Rate limits / quotas** | **VERIFIED** — Current tier limit (8 credits/minute) confirmed to be insufficient for rapid 10-symbol backfill. |
| **Auth / ToS** | **VERIFIED** — API key auth confirmed operational. |
| **Base URL / API shape** | **VERIFIED** — Endpoint `GET /time_series` schema confirmed. |
| **Stability / docs** | **VERIFIED** — Documentation and API responsiveness confirmed. |

**Phase 5 Verification Outcomes** (actual results):
1. AAPL (US): 200 OK, bars returned.
2. 0700.HK (HKEX): 404 Not Found (plan-gated).
3. 005930.KS (KRX): 429 Too Many Requests (8 credits/min quota exhausted).

**Note:** Collectors are implemented; live HKEX/KRX fetch is pending asset approval. Until approved, real `twelve_data` rows are gated; `market_prices` carry `is_demo` rows only.

---

## Candidate Vendors

### 1. Yahoo Finance (via `yfinance` Python wrapper)

**UNVERIFIED claims below** — the following is a framework for investigation; I have not independently verified symbol availability, current quotas, or ToS compliance for this project.

| Criterion | Assessment (UNVERIFIED) |
|---|---|
| **Symbol coverage (10 tickers)** | Commonly cited as supporting `.HK` and `.KS` suffix tickers. **Verification required**: test fetch for each of the 10 proposed symbols. |
| **Data completeness** | Typically provides daily OHLCV + volume; historical depth often â‰¥5 years. **Verification required**: actual depth per symbol. |
| **Rate limits** | No official API (scrapes Yahoo Finance web); informal rate limits vary. Burst requests may trigger throttling or IP blocks. **Verification required**: sustained collection reliability. |
| **Auth / ToS** | No API key required. `yfinance` is a community wrapper, not officially endorsed by Yahoo. **Risk**: Yahoo's ToS for programmatic use is unclear; scraping-based access may be deprecated or blocked without notice. |
| **Stability** | Community-maintained wrapper; breaks when Yahoo changes their web structure. **Verification required**: check recent issues/uptime. |

**Verdict**: Widely used for prototyping, but **UNVERIFIED** for production reliability and ToS compliance. Recommend investigating Yahoo's current stance on programmatic access before committing.

---

### 2. Alpha Vantage

**UNVERIFIED** — framework only.

| Criterion | Assessment (UNVERIFIED) |
|---|---|
| **Symbol coverage (10 tickers)** | Free tier reportedly supports international exchanges including `.HK` and `.KS`. **Verification required**: test each symbol. |
| **Data completeness** | Daily OHLCV via `TIME_SERIES_DAILY` endpoint; free tier limited to â‰¤5 calls/minute, 500 calls/day. **Risk**: 10 tickers Ã— daily collection may exceed quota quickly; backfill for 2 years would require batching. |
| **Rate limits** | Free tier: 5 calls/min, 500/day. Paid tier increases limits. **Verification required**: calculate exact call volume for 10 tickers + backfill. |
| **Auth / ToS** | API key (free registration). Documented API. **Verification required**: read ToS for research/non-commercial use restrictions. |
| **Stability** | Established vendor, well-documented. |

**Verdict**: Established API, but free-tier quotas are tight for 10 tickers. **UNVERIFIED** until quota math and symbol tests confirm feasibility.

---

### 3. Polygon.io

**UNVERIFIED** — framework only.

| Criterion | Assessment (UNVERIFIED) |
|---|---|
| **Symbol coverage (10 tickers)** | Known for US equities; international coverage (HKEX, KRX) exists on paid tiers. **Verification required**: confirm `.HK`/`.KS` availability and pricing. Free tier is US-only. |
| **Data completeness** | High-quality OHLCV. Paid tiers required for international markets. |
| **Rate limits** | Free tier: US stocks only. Starter tier ($29/month as of some point in 2025) adds international. **Verification required**: current pricing, international symbol limits. |
| **Auth / ToS** | API key, clear ToS. Programmatic use allowed. |
| **Stability** | Professional-grade API. |

**Verdict**: Premium option. **UNVERIFIED** cost/benefit for a research tool. Confirm international coverage before recommending.

---

### 4. KRX-specific vendors (e.g., naver-finance-scraper, KRX Market Data)

**UNVERIFIED** — framework only.

| Criterion | Assessment (UNVERIFIED) |
|---|---|
| **Symbol coverage (5 KRX tickers)** | Naver Finance (via unofficial scrapers like Apify Actor `parseforge/naver-finance-scraper`) covers KRX. **Does not cover HKEX** — would require a second vendor. |
| **Data completeness** | Historical OHLCV available. **Verification required**: actor input schema, output format, rate limits. |
| **Rate limits** | Apify-actor-dependent; actors charge per run or result count. User has an Apify key. **Verification required**: cost per fetch Ã— 5 KRX tickers. |
| **Auth / ToS** | Unofficial scraper. Naver Finance ToS may prohibit scraping. **Risk**: access may break. |
| **Stability** | Community actor; maintenance depends on actor author. |

**Verdict**: Possible for KRX only. **UNVERIFIED** until actor schema is confirmed and HKEX vendor is paired. Not a standalone solution.

---

### 5. HKEX-specific vendors (e.g., HKEXnews, AAStocks APIs)

**UNVERIFIED** — I do not have verified access to official HKEX data APIs or their pricing/ToS. This is a placeholder for investigation.

| Criterion | Assessment (UNVERIFIED) |
|---|---|
| **Symbol coverage (5 HKEX tickers)** | Official HKEX data feeds exist (e.g., HKEXnews, Bloomberg Terminal, Reuters). **Verification required**: free/paid tiers, API access. |
| **Data completeness** | High-quality OHLCV. Official sources are authoritative. |
| **Rate limits** | Typically paid, enterprise-tier. Free-tier alternatives (AAStocks web scraping) are **UNVERIFIED** for reliability/ToS. |
| **Auth / ToS** | Official APIs require licensing. Unofficial scrapers risk ToS violations. |
| **Stability** | Official APIs are stable; unofficial scrapers break on site changes. |

**Verdict**: **UNVERIFIED**. Recommend confirming whether the user has existing data vendor access (Bloomberg, Reuters) or requires a free/low-cost alternative.

---

## Cross-Exchange Hybrid Approach

If no single vendor covers both HKEX and KRX at acceptable cost/quota:

1. **KRX**: Naver Finance scraper (via Apify Actor `parseforge/naver-finance-scraper`, pending verification).
2. **HKEX**: Yahoo Finance (via `yfinance`) or Alpha Vantage, pending verification.
3. **Risk**: Two vendors = two points of failure, two rate-limit regimes, two ToS surfaces.

The `MarketDataProvider` interface (Phase 1) is designed to support multiple implementations; the `provider` column on `market_prices` records which vendor produced each row, so a hybrid is architecturally feasible.

---

## Recommendation (PENDING USER APPROVAL)

**Option A (lowest friction, UNVERIFIED reliability)**:
- Use **Yahoo Finance (yfinance)** for all 10 tickers (if symbol coverage is confirmed).
- **Pros**: No API key, no cost, simple.
- **Cons**: Unofficial wrapper, ToS unclear, may break without notice, rate limits informal.
- **Action**: Test-fetch all 10 symbols for 1 week of data before Phase 5. If any fail or throttle, fall back to Option B.

**Option B (documented APIs, tighter quotas)**:
- **Alpha Vantage** for all 10 tickers, free tier.
- **Pros**: Official API, documented, ToS clear.
- **Cons**: 500 calls/day free tier may be tight for 10 tickers + backfill (requires batching).
- **Action**: Calculate exact call volume; confirm symbol availability; check ToS for research use.

**Option C (premium, professional-grade, cost barrier)**:
- **Polygon.io** starter tier for international coverage.
- **Pros**: Stable, high-quality, clear ToS.
- **Cons**: Paid ($29/month as of 2025 pricing, UNVERIFIED for 2026). Confirm international symbol availability + current pricing.

**Option D (hybrid, two vendors)**:
- **KRX**: Naver Finance scraper (Apify Actor, pending verification).
- **HKEX**: Yahoo Finance or Alpha Vantage.
- **Pros**: Tailored per exchange.
- **Cons**: Complexity, two failure surfaces.

---

## Next Steps (owner selected `twelve_data` — now execute the Phase 5 checklist in Â§0)

1. **User**: Explicitly confirm the 10 tickers, or provide corrections. (Still PENDING CONFIRMATION.)
2. **Phase 5**: Implement `twelve_data` as the concrete `MarketDataProvider`, run the Â§0 verification
   checklist with real requests, and mark each symbol VERIFIED or UNVERIFIED with row counts.
3. **Fallback**: If `twelve_data` cannot serve a symbol or is unavailable, re-open options Aâ€“D and
   report to the owner before committing to a second vendor.

**Until then**, the abstract `MarketDataProvider` interface remains the single contract point;
`twelve_data`'s key is present in `.env` but **no vendor code is implemented or committed** in Phase 1.

---

## Classification Note

**Exa** and **Tavily** are **search/news** providers (web search, article extraction). They are **not** market-data vendors and do not provide OHLCV price history. Their role is sentiment input (news articles, social mentions), evaluated separately in Phase 5 (collectors).

