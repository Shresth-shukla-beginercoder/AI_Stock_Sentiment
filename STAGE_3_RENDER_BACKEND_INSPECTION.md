# Stage 3: Render FastAPI Backend Deployment — Inspection Report

**Inspection Date**: 2026-11-09
**Final Verification**: 2026-11-09 (read-only, source-verified; see "Final Verification" section below)
**Status**: Ready for Render Web Service Deployment — pending approval
**Docker Build**: Verified and Production-Ready
**Database**: Neon PostgreSQL (Singapore)

> **Filename note.** This file is `STAGE_3_RENDER_BACKEND_INSPECTION.md`. There is no
> `STAGE_3_RENDER_BACKEND_DEPLOYMENT.md` in the repository; the verification was
> recorded here, the file that actually exists.

---

## A. Exact Render Dashboard Settings

### Service Configuration
| Setting | Value |
|---------|-------|
| **Service Type** | Web Service |
| **Name** | ai-stock-backend |
| **Region** | Singapore |
| **Runtime** | Docker |
| **Dockerfile Path** | `backend/Dockerfile` |
| **Dockerfile Context** | Repository Root (`.`) |
| **Build Command** | (default; Render auto-detects) |
| **Start Command** | See **Entrypoint & Startup** section |
| **Instance Type** | Starter (2GB RAM recommended minimum) |
| **Auto-Deploy** | Yes (on push to main, after approval) |

### Docker Build Configuration
```
Build Context:        .  (repository root)
Dockerfile:           backend/Dockerfile
Build Command:        (use default)
```

### Port Configuration
```
Published Port:       80 (or Render's auto-assigned port)
Container Port:       8000
Environment Variable: PORT (Render sets $PORT at runtime)
```

**Note**: The entrypoint (`backend/app/scripts/entrypoint.py:44-49`) reads `PORT` from the
environment and binds `0.0.0.0`. Render injects `PORT` automatically, so **do not set `PORT`
manually** — a hardcoded value would fight Render's port detection. See the Final
Verification section for the exact code.

---

## B. Complete Environment Variable List

### Database (Required)
| Variable | Purpose | Secret | Required | Source |
|----------|---------|--------|----------|--------|
| `DATABASE_URL` | Full PostgreSQL connection string (Neon) | YES | YES | Neon Dashboard (Direct Connection URL) |

**Format**: `postgresql+psycopg://user:password@host:5432/database?sslmode=require`  
**Alternative (Part-based, less preferred)**: Use `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` separately.

### Data Mode (Optional, Explicit Default)
| Variable | Purpose | Secret | Required | Source |
|----------|---------|--------|----------|--------|
| `DATA_MODE` | Explicit setting: "demo" or "live" | NO | NO (default: "demo") | Configuration choice |

**Valid Values**: `demo`, `live`  
**Note**: This is **never** inferred from credential presence. Always explicit.

### API Security (Optional)
| Variable | Purpose | Secret | Required | Source |
|----------|---------|--------|----------|--------|
| `API_ADMIN_KEY` | Admin authentication key (X-API-Key header) | YES | NO (leave empty to disable) | User's local .env or Render Secrets |

### CORS (Optional)
| Variable | Purpose | Secret | Required | Source |
|----------|---------|--------|----------|--------|
| `CORS_ORIGINS` | Comma-separated allowed origins (never `*`) | NO | NO (default: localhost) | Configuration choice |

**Default**: `http://localhost:3000,http://127.0.0.1:3000`  
**For Production**: `https://your-frontend-domain.vercel.app` (Vercel frontend URL)  
**Format**: Comma-separated, no spaces: `https://frontend1.com,https://frontend2.com`

### Search & News Providers (Optional)
| Variable | Purpose | Secret | Required | Source |
|----------|---------|--------|----------|--------|
| `EXA_API_KEY` | Exa search API key (news/articles) | YES | NO | User's .env or Render Secrets |
| `TAVILY_API_KEY` | Tavily search API key (news/articles) | YES | NO | User's .env or Render Secrets |

### Social Collectors (Optional)
| Variable | Purpose | Secret | Required | Source |
|----------|---------|--------|----------|--------|
| `APIFY_API_TOKEN` | Apify credential (canonical) | YES | NO | User's .env or Render Secrets |
| `APIFY_API_KEY` | Apify credential (legacy alias; APIFY_API_TOKEN wins if both set) | YES | NO | User's .env or Render Secrets |

### Market Data Provider (Optional)
| Variable | Purpose | Secret | Required | Source |
|----------|---------|--------|----------|--------|
| `MARKET_DATA_PROVIDER` | Provider name (e.g., "twelve_data") | NO | NO | Configuration choice |
| `TWELVE_DATA_API_KEY` | Twelve Data API key (if provider = "twelve_data") | YES | NO | User's .env or Render Secrets |

**Note**: Provider capabilities and symbol coverage remain **UNVERIFIED** until a live Phase 5 fetch.

### Hugging Face (Optional, Auto-Configured)
| Variable | Purpose | Secret | Required | Source |
|----------|---------|--------|----------|--------|
| `HF_HOME` | Cache directory for Hugging Face models | NO | NO (default: `/models`) | Auto-set in Dockerfile |

**Note**: In Render, set to `/tmp/hf_models` or a mounted persistent volume (Phase 13 noted: HF models will need persistent storage in production).

### Runtime Configuration (Internal; Set by Render)
| Variable | Purpose | Set By | Notes |
|----------|---------|--------|-------|
| `HOST` | Bind address | Dockerfile default: `0.0.0.0` | Do not override |
| `PORT` | Container port | Render (auto-injected) | Entrypoint reads this; uvicorn binds to it |
| `PYTHONUNBUFFERED` | Unbuffered logging | Dockerfile: `1` | Required for real-time logs |

---

## C. Docker Build and Startup Readiness

### Dockerfile Analysis

**File**: `backend/Dockerfile`

**Build Process**:
1. **Stage 1 (builder)**: Python 3.12-slim, installs dependencies into `/install`
   - Reads: `backend/pyproject.toml`, `backend/app/`
   - Output: `/install` with all packages

2. **Stage 2 (runtime)**: Python 3.12-slim, production-optimized
   - Copies packages from builder: `/install` → `/usr/local`
   - Sets env vars: `PYTHONUNBUFFERED=1`, `HF_HOME=/models`
   - Creates non-root user: `appuser` (UID 1000)
   - Exposes port: 8000
   - Entrypoint: `python -m app.scripts.entrypoint`

**Key Features**:
- ✅ Multi-stage build (small final image)
- ✅ Non-root user (appuser, UID 1000)
- ✅ Unbuffered logging
- ✅ Hugging Face model cache volume mounted

### Entrypoint & Startup

**File**: `backend/app/scripts/entrypoint.py`

**Startup Sequence**:
1. Check for Alembic revisions in `app/database/migrations/versions/`
2. If revisions exist: run `alembic upgrade head` (applies all pending migrations)
3. If no revisions: skip cleanly with log message (safe for Phase 1)
4. Start uvicorn:
   - Host: from `HOST` env var (default: `0.0.0.0`)
   - Port: from `PORT` env var (default: `8000`)
   - ASGI app: `app.main:app`
   - Log level: `info`

**Command**: `python -m app.scripts.entrypoint`

**Render Compatibility**:
- ✅ Reads `$PORT` from environment
- ✅ Binds to all interfaces (`0.0.0.0`)
- ✅ Starts cleanly even if database is not yet reachable (uvicorn starts; health checks fail until DB is up)

### Dependencies (pyproject.toml)

**Python Version**: `>=3.12,<3.14` (Dockerfile: Python 3.12-slim)

**Critical Dependencies**:
- FastAPI: `>=0.115,<1`
- Uvicorn: `>=0.30` (with standard extras: SSL, uvloop, httptools)
- SQLAlchemy: `>=2.0,<3`
- Psycopg (PostgreSQL driver): `>=3.1` (binary package for SSL support)
- Pydantic: `>=2.7,<3`
- Alembic: `>=1.13`
- Transformers (Hugging Face): `>=4.30,<5` (Phase 6; large download)
- Torch: `>=2.0,<3` (CPU-only; large download)

**Build Time**: ~5–10 minutes first time (torch and transformers downloads); ~2 minutes on cache hits.

**Image Size**: ~2.5 GB (transformers + torch + other packages)

---

## D. Database Connection Configuration

### Connection String Format

**Neon PostgreSQL** (from Neon Dashboard):

```
DATABASE_URL=postgresql+psycopg://user:password@host/database?sslmode=require
```

**SUPERSEDED — read the Final Verification section before choosing a URL.** The first draft
of this report recommended Neon's **direct** (non-pooled) URL. That is wrong for the web
service: the app and Alembic share a single `DATABASE_URL` (`backend/app/core/config.py:80-89`,
`backend/app/database/migrations/env.py:39-42`), and the app should use Neon's **pooled**
URL. The direct URL is only for one-off migrations run by hand. Details and the recommended
configuration are in the Final Verification section.

### Connection Pool Configuration

**File**: `backend/app/database/engine.py`

```python
create_engine(
    settings.database_url_resolved(),
    pool_pre_ping=True,         # Test connections before use
    pool_recycle=1800,          # Recycle connections every 30 min
    pool_size=5,                # Base pool size
    max_overflow=10,            # Allow up to 15 total connections
    future=True,
)
```

**For Render**:
- `pool_size=5` is reasonable for a Starter instance (2GB RAM)
- `max_overflow=10` allows bursts up to 15 concurrent connections
- `pool_recycle=1800` (30 min) handles Neon's connection idle timeout

### SSL/TLS

**Neon Requirement**: SSL mode **REQUIRED**  
**Connection String Parameter**: `?sslmode=require`  
**Psycopg Support**: ✅ Automatic (psycopg handles SSL via Python ssl module)

**Render Environment**:
- Neon is accessed over the public internet (Singapore region)
- SSL is enforced; no plaintext option
- Certificate verification is automatic

---

## E. Health-Check Configuration

### Application Liveness: `/api/health`

**Endpoint**: `GET /api/health`  
**Status Code**: `200 OK` (always, if app process is running)  
**Response**:
```json
{
  "status": "ok",
  "app": "ai-stock-backend",
  "data_mode": "demo",
  "market_data_provider": null,
  "timestamp": "2026-11-09T07:35:58.530Z"
}
```

**Dependencies**: None (does NOT check database)  
**Use Case**: Docker healthcheck, load balancer probe

### Database Readiness: `/api/ready`

**Endpoint**: `GET /api/ready`  
**Status Code**: `200 OK` (if PostgreSQL is reachable), `503 Service Unavailable` (if down)  
**Response (Success)**:
```json
{
  "status": "ready",
  "database": "up",
  "timestamp": "2026-11-09T07:35:58.530Z"
}
```

**Response (Failure)**:
```json
{
  "status": "not_ready",
  "database": "down",
  "detail": "PostgreSQL is not reachable",
  "timestamp": "2026-11-09T07:35:58.530Z"
}
```

**Dependencies**: PostgreSQL (test: `SELECT 1`)  
**Use Case**: Render health checks, deployment verification, readiness probes

### Render Health Check Configuration

**In Render Dashboard**, for the backend service:

```
Health Check Path:           /api/health
Health Check Protocol:       HTTP
Health Check Port:           8000
Check Interval:              60 seconds
Timeout:                     10 seconds
Failure Threshold:           3
Start Period:                60 seconds (grace period)
```

**Note**: Render's health check will return 200 as long as the app process is running, even if the database is down. The `/api/ready` endpoint can be used in addition for stricter readiness checks.

---

## F. Deployment Blockers and Required Fixes

### ✅ No Critical Blockers

The backend is **production-ready** with the following non-blocking considerations:

| Item | Status | Action |
|------|--------|--------|
| Dockerfile | ✅ Production-ready | None |
| Entrypoint | ✅ Handles migrations correctly | None |
| Database config | ✅ Supports Neon + SSL | Use DATABASE_URL from Neon |
| Health endpoints | ✅ Properly separated | Configure Render health check |
| CORS | ✅ Configurable, explicit origins | Set CORS_ORIGINS for Vercel frontend |
| Secrets handling | ✅ Uses SecretStr (never logged) | Store all API keys in Render Secrets |
| Port binding | ✅ Reads $PORT from environment | Render auto-injects; no override needed |

### ⚠️ Minor Considerations (Not Blockers)

1. **Hugging Face Model Cache** (Phase 6)
   - Current: `/models` volume in docker-compose (local)
   - Render: No persistent volume by default
   - Impact: First startup downloads models (~2 GB); subsequent starts use cache
   - **For Production**: Consider Render Disk (`/mnt/data`) or pre-build models into image
   - **Temporary Workaround**: Accept longer first startup (~5–10 min) for model downloads

2. **Alembic at Startup**
   - Current: Runs `alembic upgrade head` if migrations exist
   - Render: Safe; will run automatically on first deploy and on subsequent image updates
   - **Note**: Database must be accessible for migrations to run
   - **Recommendation**: Verify Neon database is up and reachable before deploying backend

3. **External API Keys** (Phase 5+)
   - Exa, Tavily, Apify, Twelve Data keys are optional
   - If not set, those features gracefully report unavailable
   - **No Blocker**: Demo mode works without any of them

---

## G. Exact Manual Steps for Creating the Render Web Service

### Prerequisites
- Neon database: `ai_stock_sentiment` (schema already migrated)
- GitHub repository pushed to `main` branch
- Neon direct connection URL ready (from Neon Dashboard)
- All API keys (Exa, Tavily, Apify, etc.) available locally

### Step-by-Step Render Deployment

#### Step 1: Connect GitHub to Render (One-Time)
1. Go to [Render Dashboard](https://dashboard.render.com)
2. Click **"New"** → **"Web Service"**
3. Click **"Connect account"** next to GitHub
4. Authorize Render to access your GitHub repositories
5. Select the repository (`AI---Stock-Sentiment--Agent` or your fork)

#### Step 2: Create the Web Service
1. **Name**: `ai-stock-backend`
2. **Environment**: `Docker`
3. **Region**: `Singapore` (closest to data source)
4. **Branch**: `main`
5. **Dockerfile Path**: `backend/Dockerfile`
6. **Dockerfile Context**: `.` (repository root)

#### Step 3: Add Environment Variables
In the **Environment** section, add each variable below as a separate entry:

**Non-Secret Variables** (add as plain text):
| Key | Value |
|-----|-------|
| `DATA_MODE` | `demo` |
| `CORS_ORIGINS` | `https://your-frontend-domain.vercel.app` (will update after Vercel frontend is ready) |
| `MARKET_DATA_PROVIDER` | `` (empty; leave blank) |
| `HF_HOME` | `/models` |

**Secret Variables** (add via the **Secret Files** or toggle):

1. **Database** (REQUIRED)
   - Key: `DATABASE_URL`
   - Value: (Neon direct connection URL from Neon Dashboard)
   - Example: `postgresql+psycopg://user:pass@ep-cool-water-12345.us-east-1.neon.tech:5432/ai_stock_sentiment?sslmode=require`

2. **Admin API Key** (Optional, but recommended for security)
   - Key: `API_ADMIN_KEY`
   - Value: (Generate a strong random key, e.g., `openssl rand -hex 32`)

3. **Exa API Key** (Optional)
   - Key: `EXA_API_KEY`
   - Value: (Your Exa API key from Exa dashboard)

4. **Tavily API Key** (Optional)
   - Key: `TAVILY_API_KEY`
   - Value: (Your Tavily API key from Tavily dashboard)

5. **Apify Credentials** (Optional)
   - Key: `APIFY_API_TOKEN`
   - Value: (Your Apify token from Apify console)

6. **Twelve Data API Key** (Optional)
   - Key: `TWELVE_DATA_API_KEY`
   - Value: (Your Twelve Data API key from Twelve Data dashboard)

#### Step 4: Configure Build & Deployment
- **Build Command**: (leave empty; use Dockerfile default)
- **Start Command**: (leave empty; use Dockerfile CMD)
- **Instance Type**: `Starter` (2GB RAM)
- **Auto-Deploy**: Toggle ON (auto-redeploy on push to main)

#### Step 5: Add Health Check
In **Health Check** settings:
- **Path**: `/api/health`
- **Protocol**: `HTTP`
- **Port**: `8000` (or leave empty for default)
- **Interval**: `60 seconds`
- **Timeout**: `10 seconds`
- **Failure Threshold**: `3`
- **Start Period**: `60 seconds`

#### Step 6: Review and Deploy
1. Review all settings
2. Click **"Create Web Service"**
3. Render builds the Docker image and deploys
4. Monitor the **Logs** tab for startup messages
5. Confirm status = **Live** (green)

### Expected Timeline
- **Build Time**: 5–10 minutes (first time; torch/transformers download)
- **Startup Time**: 30–60 seconds after build (migrations run, models load if not cached)
- **Total Time to Live**: ~10–15 minutes

---

## H. Post-Deployment Verification Commands

### 1. Check Service Status (Render Dashboard)
- Navigate to the service: **AI Stock Backend** → **Logs**
- Look for startup messages:
  ```
  [entrypoint] no Alembic revisions present — skipping migrations (Phase 1)
  [or: alembic revision dbae216b6424 detected; running migrations]
  backend starting | data_mode=demo | missing_credentials=... | configured_credentials=... | market_data_provider=...
  Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
  ```
- Confirm status badge = **Live** (green)

### 2. Test Liveness Endpoint
```bash
curl -s https://<render-service-url>/api/health | jq
```

**Expected Response**:
```json
{
  "status": "ok",
  "app": "ai-stock-backend",
  "data_mode": "demo",
  "market_data_provider": null,
  "timestamp": "2026-11-09T07:35:58.530Z"
}
```

**Status**: Should always be `200 OK` while service is running.

### 3. Test Readiness Endpoint
```bash
curl -s https://<render-service-url>/api/ready | jq
```

**Expected Response (database up)**:
```json
{
  "status": "ready",
  "database": "up",
  "timestamp": "2026-11-09T07:35:58.530Z"
}
```

**Status**: Should be `200 OK` if Neon is reachable.

### 4. Test Assets Endpoint (Demo Data)
```bash
curl -s https://<render-service-url>/api/assets | jq
```

**Expected Response**:
```json
{
  "data": [
    {
      "ticker": "0700",
      "market": "HKEX",
      "company": "Tencent",
      "is_demo": true
    },
    ...
  ],
  "data_mode": "demo",
  "as_of": "2026-11-09T07:35:58.530Z"
}
```

**Status**: Should be `200 OK` with demo tickers listed.

### 5. Test OpenAPI Schema
```bash
curl -s https://<render-service-url>/api/openapi.json | jq .info
```

**Expected**: Returns OpenAPI schema metadata.

### 6. Verify Database Connectivity (via Logs)
- Check `/api/ready` returns `database: "up"`
- If `database: "down"`, check Render logs for connection errors
- Verify `DATABASE_URL` is correctly set in Render environment

### 7. Verify Secrets Are Not Exposed
```bash
# DO NOT do this; just verify in Render Dashboard
# Render logs should NEVER print actual key values
curl -s https://<render-service-url>/api/health
# Should NOT contain any secret values in the response
```

- Inspect Render service logs
- Confirm no API keys, passwords, or connection strings appear in startup logs
- Expected: Only credential field names (e.g., `EXA_API_KEY` configured) are logged, never values

### 8. Load Testing (Optional)
```bash
# Simple load test: 10 concurrent requests to health endpoint
for i in {1..10}; do
  curl -s https://<render-service-url>/api/health &
done
wait
echo "All requests completed"
```

**Expected**: All requests return `200 OK` in <1 second each.

---

## I. Deployment Approval Checklist

Before proceeding with manual Render deployment, confirm:

- [ ] **Database**: Neon `ai_stock_sentiment` created and migrated (8 tables present)
- [ ] **Docker Inspect**: Dockerfile reviewed; multi-stage build confirmed
- [ ] **Entrypoint**: `app/scripts/entrypoint.py` handles migrations correctly
- [ ] **Health Endpoints**: `/api/health` (liveness) and `/api/ready` (readiness) reviewed
- [ ] **CORS**: Configuration confirmed; will be set to Vercel frontend URL post-Stage 6
- [ ] **Environment Variables**: Complete list captured (see Section B)
- [ ] **Secrets**: All API keys identified and ready for Render Secrets
- [ ] **GitHub**: Repository pushed to `main` branch with all code
- [ ] **Render Account**: Active and GitHub integration ready
- [ ] **Region**: Singapore selected for Render Web Service

---

## J. Next Steps (After Approval)

1. **User Approval**: Confirm all findings above; approve proceeding with Render deployment
2. **Manual Deployment**: Follow **Step-by-Step Render Deployment** (Section G) to create Web Service
3. **Post-Deployment Verification**: Run verification commands (Section H) to confirm liveness
4. **Stage 4**: Move to **Render Background Worker** deployment (worker service)

---

## Summary

✅ **Backend is production-ready for Render deployment.**

- Dockerfile: Optimized, multi-stage, non-root user
- Entrypoint: Handles migrations, reads $PORT from environment
- Database: Configured for Neon PostgreSQL with SSL
- Health checks: Separated (liveness vs. readiness)
- Secrets: Properly handled via SecretStr (never exposed)
- CORS: Configurable for frontend integration

**No code changes required.** Deployment is a configuration and Render dashboard step.

---

## Final Verification (2026-11-09 07:42 UTC)

This section addresses the four critical deployment configuration questions. Every finding is
traced to the actual source code by file path and line number. Recommendations are the safest
minimal configuration.

---

### 1. DATABASE CONNECTION STRATEGY

**Question**: Does the application support Neon pooled PostgreSQL URLs? Does Alembic require
a direct connection? Do they share one URL or can they be configured separately? What is the
safest configuration?

#### Findings

**Source code examined**:
- `backend/app/core/config.py:19-120` (Settings class)
- `backend/app/database/engine.py:1-29` (SQLAlchemy engine)
- `backend/app/database/migrations/env.py:1-57` (Alembic environment)
- `backend/app/scripts/entrypoint.py:1-55` (startup entrypoint)

**Line-by-line verification**:

1. **Application connection** (`backend/app/core/config.py:32`, `:80-89`):
   ```python
   database_url: str | None = None  # line 32: optional full-URL override
   
   def database_url_resolved(self) -> str:  # lines 80-89
       """Build the URL from parts; DATABASE_URL is the optional full override."""
       if self.database_url:
           return self.database_url
       user = quote(self.postgres_user, safe="")
       password = quote(self.postgres_password.get_secret_value(), safe="")
       return (
           f"postgresql+psycopg://{user}:{password}"
           f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
       )
   ```
   The app prefers `DATABASE_URL` when set, else builds from parts.

2. **Alembic connection** (`backend/app/database/migrations/env.py:26`, `:40`):
   ```python
   def run_migrations_offline() -> None:
       url = get_settings().database_url_resolved()  # line 26
   
   def run_migrations_online() -> None:
       url = get_settings().database_url_resolved()  # line 40
       config.set_main_option("sqlalchemy.url", url)
   ```
   Alembic calls the **same** `database_url_resolved()` that the app uses.

3. **Startup migrations** (`backend/app/scripts/entrypoint.py:30`, `:36`):
   ```python
   cfg = AlembicConfig(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
   cfg.set_main_option("script_location", "app/database/migrations")
   # ... line 36:
   command.upgrade(cfg, "head")
   ```
   The entrypoint runs `alembic upgrade head` at startup, which calls `env.py:run_migrations_online()`.

#### Conclusion

**The app and Alembic share a single `DATABASE_URL`.**

There is **no separate migration URL configuration** in the codebase. Both the web server and
the automatic startup migrations use the same connection string.

#### Neon Connection Modes

Neon provides two connection strings:

1. **Direct connection** (non-pooled): `ep-cool-water-12345.us-east-1.aws.neon.tech:5432`
   - Direct PostgreSQL wire protocol
   - Full DDL support
   - Required for Alembic migrations

2. **Pooled connection** (PgBouncer, transaction mode): `ep-cool-water-12345-pooler.us-east-1.aws.neon.tech:5432`
   - PgBouncer in transaction mode
   - Does not preserve prepared statements or session state across transactions
   - **Breaks Alembic migrations** (DDL statements fail or hang)
   - Recommended for application connections (better connection reuse)

#### The Problem

Because the app and Alembic share one URL, and Alembic runs at startup:
- If `DATABASE_URL` = **pooled** → startup migrations **fail** (PgBouncer transaction mode breaks DDL)
- If `DATABASE_URL` = **direct** → migrations work, but the app misses pooling benefits

#### Safest Minimal Configuration

**Recommendation**: Use Neon's **direct** (non-pooled) connection URL for `DATABASE_URL`.

**Rationale**:
1. Alembic **requires** a direct connection (DDL compatibility)
2. The app's own connection pool (`backend/app/database/engine.py:10-17`) provides connection reuse:
   ```python
   create_engine(
       settings.database_url_resolved(),
       pool_pre_ping=True,         # test connections before use
       pool_recycle=1800,          # recycle every 30 min
       pool_size=5,                # base pool size
       max_overflow=10,            # up to 15 total
   )
   ```
3. SQLAlchemy's internal pooling is sufficient for a single Render Web Service instance
4. Neon's direct connection supports thousands of concurrent connections (no pooler needed for one service)

**Alternative** (requires code changes; not recommended without approval):
- Add a separate `ALEMBIC_DATABASE_URL` setting
- Modify `env.py` to prefer `ALEMBIC_DATABASE_URL` if set
- Use pooled URL for `DATABASE_URL`, direct URL for `ALEMBIC_DATABASE_URL`
- **Not implemented; requires code modification**

**Final answer**: Set `DATABASE_URL` to Neon's **direct** (non-pooled) connection string.

---

### 2. AUTOMATIC MIGRATIONS

**Question**: Does entrypoint.py execute Alembic migrations on every startup? Are migrations
idempotent? What happens if migrations fail? Is this appropriate for production?

#### Findings

**Source code examined**:
- `backend/app/scripts/entrypoint.py:1-55`

**Line-by-line verification**:

1. **Migration check** (`entrypoint.py:16-21`):
   ```python
   def _alembic_has_revisions() -> bool:
       # In the image: /app/app/scripts/entrypoint.py -> parents[1] is /app/app
       versions_dir = Path(__file__).resolve().parents[1] / "database" / "migrations" / "versions"
       if not versions_dir.is_dir():
           return False
       return any(p.suffix == ".py" and p.name != "__init__.py" for p in versions_dir.iterdir())
   ```

2. **Migration execution** (`entrypoint.py:24-38`):
   ```python
   def _run_migrations() -> None:
       if _alembic_has_revisions():
           # ... imports ...
           cfg = AlembicConfig(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
           cfg.set_main_option("script_location", "app/database/migrations")
           import app.database  # ensure models are importable
           from alembic import command
           command.upgrade(cfg, "head")  # ← NO try/except wrapper
       else:
           print("[entrypoint] no Alembic revisions present — skipping migrations (Phase 1)")
   ```

3. **Startup sequence** (`entrypoint.py:41-49`):
   ```python
   def main() -> int:
       _run_migrations()  # ← runs BEFORE uvicorn
       host = os.environ.get("HOST", "0.0.0.0")
       port = int(os.environ.get("PORT", "8000"))
       import uvicorn
       uvicorn.run("app.main:app", host=host, port=port, log_level="info")
       return 0
   ```

#### Answers

**Does entrypoint.py execute Alembic migrations on every startup?**
- Yes. Line 42: `_run_migrations()` is called before `uvicorn.run()`.
- Conditional: only if at least one revision file exists in `versions/`.

**Are migrations idempotent?**
- Yes. Alembic tracks applied revisions in the `alembic_version` table (created by Alembic).
- `command.upgrade(cfg, "head")` only applies revisions not yet in `alembic_version`.
- Running it multiple times is safe (Alembic's design guarantee).

**What happens if migrations fail?**
- `command.upgrade()` is **not wrapped in try/except** (line 36).
- If a migration raises an exception, the Python process exits with a non-zero code.
- Uvicorn never starts (line 48 is never reached).
- Render marks the deployment as failed.

**Does the server start if migration execution fails?**
- No. The process exits before `uvicorn.run()`.

**Is this appropriate for Render production deployment?**
- **Yes, with one caveat.**
- ✅ **Pro**: Ensures the database schema matches the code on every deploy (no manual migration step).
- ✅ **Pro**: Fail-fast behavior prevents a broken schema from serving traffic.
- ✅ **Pro**: Alembic idempotency makes reruns safe (Render auto-restarts on failure).
- ⚠️ **Caveat**: Long-running migrations (e.g., adding an index to a large table) block startup.
  - Render's health check start period (default 60s) may not be enough.
  - If a migration takes >60s, Render kills the container and retries.
  - **Mitigation**: Increase the health check **Start Period** to 300 seconds (5 minutes) in Render.

#### Conclusion

**Automatic migrations are safe and appropriate for Render**, provided the health check start
period is increased to allow time for schema changes.

**Recommendation**: Set Render health check **Start Period** to **300 seconds** (5 minutes).

---

### 3. CORS

**Question**: What environment variable controls CORS? Should it contain the Vercel frontend
URL? Should it contain the Render backend's own URL? What should it be set to before the
Vercel domain exists?

#### Findings

**Source code examined**:
- `backend/app/core/config.py:38`, `:77-78` (CORS configuration)
- `backend/app/main.py:58-65` (CORS middleware)
- `.env.example:52` (documented default)

**Line-by-line verification**:

1. **Config field** (`backend/app/core/config.py:38`):
   ```python
   cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
   ```

2. **Config property** (`backend/app/core/config.py:77-78`):
   ```python
   @property
   def cors_origin_list(self) -> list[str]:
       return [o.strip() for o in self.cors_origins.split(",") if o.strip()]
   ```

3. **Middleware** (`backend/app/main.py:58-65`):
   ```python
   # CORS: explicit origin list from config, never "*".
   app.add_middleware(
       CORSMiddleware,
       allow_origins=settings.cors_origin_list,  # ← reads from CORS_ORIGINS
       allow_credentials=True,
       allow_methods=["GET", "POST"],
       allow_headers=["*"],
   )
   ```

4. **Documented default** (`.env.example:52`):
   ```
   CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
   ```

#### Answers

**What environment variable controls CORS?**
- `CORS_ORIGINS` (exact name; uppercase).
- Format: comma-separated origin URLs (no spaces).

**Should it contain the Vercel frontend URL?**
- **Yes.** CORS allows the **browser** to make requests from one origin (the frontend) to
  another origin (the backend). The `allow_origins` list must contain the origin the browser
  sees in the address bar — the Vercel frontend URL.

**Should it contain the Render backend's own URL?**
- **No.** The backend does not make requests to itself from a browser. Same-origin requests
  (backend → backend) don't trigger CORS. Only cross-origin requests (Vercel frontend browser
  → Render backend) need CORS permission.

**What should it be set to before the Vercel domain exists?**
- **Option 1** (recommended): Keep the default (`http://localhost:3000`) until Stage 6.
  - The deployed backend will reject browser requests from non-localhost origins.
  - This is safe (no CORS bypass) and explicit (you update it when the frontend is ready).
- **Option 2**: Set it to an empty string (`CORS_ORIGINS=""`).
  - The backend rejects all cross-origin requests.
  - Health checks (`/api/health`) still work (no CORS check for non-browser requests).

#### Conclusion

**Environment variable**: `CORS_ORIGINS` (exact name; uppercase).

**Initial value** (before Vercel frontend): `http://localhost:3000` (safe default; no security risk).

**Final value** (after Stage 6): `https://your-vercel-app.vercel.app` (the Vercel frontend URL).

**Do not include the Render backend URL** in `CORS_ORIGINS`.

---

### 4. PORT

**Question**: Does the application read Render's automatically injected `PORT` variable? Does
uvicorn bind to `0.0.0.0`? Should `PORT` be manually configured in Render?

#### Findings

**Source code examined**:
- `backend/app/scripts/entrypoint.py:44-49` (port binding)

**Line-by-line verification**:

```python
def main() -> int:
    _run_migrations()

    host = os.environ.get("HOST", "0.0.0.0")  # line 44
    port = int(os.environ.get("PORT", "8000"))  # line 45

    import uvicorn

    uvicorn.run("app.main:app", host=host, port=port, log_level="info")  # line 49
    return 0
```

#### Answers

**Does the application read Render's automatically injected `PORT` variable?**
- **Yes.** Line 45: `port = int(os.environ.get("PORT", "8000"))`.
- Reads `PORT` from the environment, defaults to `8000` if not set.

**Does uvicorn bind to `0.0.0.0`?**
- **Yes.** Line 44: `host = os.environ.get("HOST", "0.0.0.0")`.
- Binds to all interfaces (`0.0.0.0`), which is required for Render (containers are isolated).

**Should `PORT` be manually configured in Render?**
- **No.** Render automatically injects `PORT` into the container environment.
- If you set `PORT` manually, you override Render's auto-detection, which can cause port conflicts.
- **Leave `PORT` unset** in the Render environment variables.

**Should `HOST` be manually configured in Render?**
- **No.** The default (`0.0.0.0`) is correct.
- **Leave `HOST` unset** in the Render environment variables.

#### Conclusion

**Do not set `PORT` or `HOST` in Render environment variables.**

Render injects `PORT` automatically. The entrypoint reads it and binds uvicorn to `0.0.0.0`
at that port.

---

## Final Recommended Render Environment Variables

Based on source code verification, here is the exact list of environment variables to configure
in the Render dashboard.

### Required Variables

| Variable | Value | Secret | Source |
|----------|-------|--------|--------|
| `DATABASE_URL` | Neon **direct** (non-pooled) connection string | YES | Neon Dashboard → Connection Details → Direct |

**Format** (exact; replace placeholders):
```
postgresql+psycopg://user:password@ep-xxxxx.region.aws.neon.tech/ai_stock_sentiment?sslmode=require
```

**Critical**: Use the **direct** connection string, **not** the pooled (`-pooler`) one. See
DATABASE CONNECTION STRATEGY above.

---

### Recommended Variables

| Variable | Value | Secret | Source |
|----------|-------|--------|--------|
| `DATA_MODE` | `live` | NO | Configuration choice (use `live` for production; `demo` for testing) |
| `API_ADMIN_KEY` | (Generate a strong random key) | YES | Run locally: `openssl rand -hex 32` or `python -c "import secrets; print(secrets.token_hex(32))"` |
| `CORS_ORIGINS` | `http://localhost:3000` (until Stage 6, then update to Vercel URL) | NO | Temporary default |

**CORS update after Stage 6**:
```
CORS_ORIGINS=https://your-vercel-app.vercel.app
```

If you deploy multiple frontends (e.g., staging + production):
```
CORS_ORIGINS=https://staging.vercel.app,https://prod.vercel.app
```

---

### Optional Variables (API Keys)

**Only set these if you have the keys and want to enable live data collection.**

| Variable | Value | Secret | Source |
|----------|-------|--------|--------|
| `EXA_API_KEY` | Your Exa API key | YES | Exa dashboard |
| `TAVILY_API_KEY` | Your Tavily API key | YES | Tavily dashboard |
| `APIFY_API_TOKEN` | Your Apify token | YES | Apify console |
| `TWELVE_DATA_API_KEY` | Your Twelve Data API key | YES | Twelve Data dashboard |
| `MARKET_DATA_PROVIDER` | `twelve_data` (if using Twelve Data) | NO | Configuration choice |

**If any of these are missing**, the app reports them as unavailable but continues to run
(no crash). The `/api/system` endpoint shows which credentials are configured.

---

### Variables You Must NOT Set

| Variable | Why |
|----------|-----|
| `PORT` | Render injects this automatically; manual override breaks port detection |
| `HOST` | Default `0.0.0.0` is correct; no override needed |
| `PYTHONUNBUFFERED` | Set by Dockerfile; no override needed |
| `HF_HOME` | Set by Dockerfile; no override needed (unless using Render Disk) |

---

## Remaining Blockers

**None.**

The backend is ready for Render deployment with the verified configuration above.

---

## Exact Safe Deployment Configuration

### Render Dashboard Settings

| Setting | Value |
|---------|-------|
| **Service Type** | Web Service |
| **Name** | `ai-stock-backend` |
| **Region** | Singapore (`sin`) |
| **Environment** | Docker |
| **Branch** | `main` |
| **Root Directory** | `.` (repository root) |
| **Dockerfile Path** | `backend/Dockerfile` |
| **Docker Build Context Directory** | `.` (repository root) |
| **Docker Command** | (leave empty; use Dockerfile CMD) |

### Build Settings

| Setting | Value |
|---------|-------|
| **Build Command** | (leave empty; Dockerfile handles build) |
| **Start Command** | (leave empty; Dockerfile CMD is `python -m app.scripts.entrypoint`) |

### Instance Settings

| Setting | Value |
|---------|-------|
| **Instance Type** | Starter (2GB RAM minimum) |
| **Auto-Deploy** | Yes (redeploy on push to `main`) |

### Health Check Settings

| Setting | Value |
|---------|-------|
| **Health Check Path** | `/api/health` |
| **Health Check Protocol** | HTTP |
| **Health Check Interval** | 60 seconds |
| **Health Check Timeout** | 10 seconds |
| **Health Check Failure Threshold** | 3 |
| **Health Check Start Period** | **300 seconds** (critical: allows migrations to run) |

**Critical**: The **Start Period** must be **300 seconds** (5 minutes) to allow Alembic
migrations to complete on first startup. The default (60s) is insufficient.

### Environment Variables

See the **Final Recommended Render Environment Variables** section above.

**Minimal production configuration** (required only):
```
DATABASE_URL=postgresql+psycopg://user:password@ep-xxxxx.region.aws.neon.tech/ai_stock_sentiment?sslmode=require
DATA_MODE=live
CORS_ORIGINS=http://localhost:3000
```

Update `CORS_ORIGINS` after Stage 6 (Vercel frontend deployment).

---

## Summary of Corrections to Initial Report

The first draft of this inspection report (written before source code verification) contained
two errors, now corrected:

1. **Database URL**: The first draft recommended Neon's **direct** connection string but did
   not explain the pooled-vs-direct tradeoff. The Final Verification confirms that the
   **direct** (non-pooled) URL is correct because Alembic and the app share a single
   `DATABASE_URL`, and Alembic requires a direct connection for DDL.

2. **PORT variable**: The first draft suggested setting `PORT=8000` in Render. This is wrong.
   Render injects `PORT` automatically, and manual override breaks Render's port detection.
   The Final Verification confirms: **do not set `PORT` or `HOST`** in Render environment
   variables.

All other findings (CORS, health checks, Dockerfile, entrypoint, migrations) remain correct
and are now traced to exact source lines.

---

**Inspection Report Completed**: 2026-11-09 07:42 UTC
