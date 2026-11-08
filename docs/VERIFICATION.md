# Verification Gates

## Phase 0: Understand and plan
- [x] Tool availability reported (docker 29.9.2, compose v5.6.1, python 3.13.7, node 26.10.0, git 2.42.0)
- [x] `CLAUDE.md`, `PROGRESS.md`, `VERIFICATION.md` created
- [x] Folder tree documented in `CLAUDE.md`
- [x] Conflicts listed
- [x] Section 2 values requested
- [x] Pinned versions confirmed: Python 3.12, Node 22
- [x] Ticker universe recorded as PENDING user's explicit confirmation
- [ ] Final "go" from user for Phase 1

## Phase 1: Foundation and Docker skeleton
- [ ] `docker compose config` passes
- [ ] `docker compose build` succeeds
- [ ] `docker compose up -d` works
- [ ] `docker compose ps` shows healthy
- [ ] `pg_isready` inside container works
- [ ] Host client connects on localhost:5437
- [ ] `curl localhost:8000/api/health` returns 200 (liveness, independent of DB)
- [ ] `GET /api/ready` returns 200 when Postgres is up
- [ ] With Postgres stopped: `/api/health` still 200 (app alive) and `/api/ready` returns 503
- [ ] Restart Postgres: `/api/ready` returns 200 again
- [ ] No secrets in logs
- [ ] `DATA_MODE` is an explicit config setting (default `demo`), not inferred from keys
- [ ] Provider interface exists (`get_daily_prices`, abstract only — no implementation);
  coverage evaluation report written for all 10 symbols, unverified claims marked
  UNVERIFIED — **no provider committed**
- [ ] Tickers remain PENDING CONFIRMATION in all docs

## Phase 2: Database schema and migrations
- [ ] `alembic upgrade head` / `downgrade -1` succeed
- [ ] Tables and constraints exist (verified)
- [ ] Duplicate inserts rejected/ignored
- [ ] Data persists across restart

## Phase 3: API contract and demo data
- [ ] Pytest for health, 404, 401, 202, 409, 422
- [ ] Test proving no mixed live/demo data
- [ ] `curl` all endpoints
- [ ] OpenAPI export runs

## Phase 4: Verification Console v1
- [ ] `npm run build` succeeds
- [ ] Frontend serves at localhost:3000
- [ ] API works through Nginx
- [ ] No 404 on nested route refresh
- [ ] Connection Board all green (demo data)
- [ ] DEMO banner shows
- [ ] No hard-coded host or secrets in VITE vars

## Phase 5: Collectors and normalisation
- [ ] Unit tests with mocks
- [ ] Dedupe test (count unchanged)
- [ ] Naive-timestamp test
- [ ] Real fetch per source (if keys provided)

## Phase 6: Sentiment engine
- [ ] Tests for missing engagement, viral-post cap
- [ ] Cleaner tests
- [ ] Score 10 sample texts results
- [ ] No duplicate rows on second run

## Phase 7: Worker, jobs and scheduling
- [ ] Parallel workers test
- [ ] Double-job run counts unchanged
- [ ] Reaping killed worker's job
- [ ] SIGTERM graceful exit
- [ ] `--once` exits 0 on empty queue
- [ ] Failed job records error and retries

## Phase 8: Features, model, evaluation
- [ ] Time-travel leakage test
- [ ] Chronological-split test
- [ ] Session-cutoff test
- [ ] Model vs baseline numbers printed

## Phase 9: End-to-end integration
- [ ] Connection Board all green
- [ ] All pages show real/empty states
- [ ] Gaps listed

## Phase 10: Hardening, tests and security
- [ ] Full pytest suite passes
- [ ] Admin protection verified
- [ ] Secrets scan (no keys in git/images)

## Phase 11: Production compose
- [ ] `docker compose -f docker-compose.prod.yml config` passes
- [ ] Clean pull-and-up test
- [ ] UNVERIFIED items listed

## Phase 12: Frontend handoff
- [ ] Contract matches API (spot-check)
- [ ] Generated client calls health
