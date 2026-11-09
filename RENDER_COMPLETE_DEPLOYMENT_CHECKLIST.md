# RENDER COMPLETE DEPLOYMENT CHECKLIST

**Project**: AI Stock Sentiment & Next-Day Prediction Agent
**Date**: 2026-11-09
**Status**: Ready for Render Deployment

---

## 1. Render Web Service Configuration

### Service Settings

| Setting | Value | Explanation |
|---------|-------|-------------|
| **Service Type** | Web Service | Standard for FastAPI applications |
| **Repository** | (Your GitHub repository) | Connect to your project repository |
| **Branch** | `main` | Production branch |
| **Service Name** | `ai-stock-backend` | Descriptive name for the service |
| **Runtime** | Docker | Uses the Dockerfile in the repository |
| **Region** | Singapore (`sin`) | Closest to Neon database location |
| **Root Directory** | `.` (repository root) | Docker context is the project root |
| **Dockerfile Path** | `backend/Dockerfile` | Exact path to the Dockerfile |
| **Docker Build Context** | `.` (repository root) | Build context is the project root |
| **Docker Command** | (leave blank) | Uses the CMD from Dockerfile |
| **Start Command** | (leave blank) | Uses the CMD from Dockerfile (`python -m app.scripts.entrypoint`) |
| **Health Check Path** | `/api/health` | Application liveness endpoint |
| **Instance Type** | Starter (2GB RAM) | Minimum recommended for production |
| **Auto-Deploy** | Yes | Auto-deploy on push to `main` branch |
| **Build Filters** | (none) | No build filters needed |
| **Persistent Disk** | No | Hugging Face models use a Docker volume |

### Environment Variables

| Variable | Required? | Secret? | Value | Purpose |
|----------|-----------|---------|-------|---------|
| `DATABASE_URL` | Yes | Yes | Neon direct connection string | PostgreSQL connection (use direct, not pooled) |
| `DATA_MODE` | Yes | No | `live` | Production data mode |
| `API_ADMIN_KEY` | Yes | Yes | (Generate a strong key) | Admin API authentication |
| `CORS_ORIGINS` | Yes | No | `http://localhost:3000` (update after Vercel) | Allowed frontend origins |
| `EXA_API_KEY` | No | Yes | (Your Exa API key) | Exa search API key |
| `TAVILY_API_KEY` | No | Yes | (Your Tavily API key) | Tavily search API key |
| `APIFY_API_TOKEN` | No | Yes | (Your Apify token) | Apify API token |
| `MARKET_DATA_PROVIDER` | No | No | `twelve_data` | Market data provider |
| `TWELVE_DATA_API_KEY` | No | Yes | (Your Twelve Data API key) | Twelve Data API key |
| `HF_HOME` | No | No | `/models` | Hugging Face model cache directory |

**Note**: For `DATABASE_URL`, use the **direct** (non-pooled) connection string from Neon. The app and Alembic share this URL, so pooling is not compatible with migrations.

**CORS Update**: After Vercel deployment, update `CORS_ORIGINS` to the Vercel frontend URL.

---

## 2. Docker Configuration

### Dockerfile Verification

- **File**: `backend/Dockerfile`
- **Build Context**: `.` (repository root)
- **Python Version**: 3.12 (pinned in Dockerfile)
- **Multi-stage Build**: Yes (optimized for production)
- **Non-root User**: Yes (appuser, UID 1000)
- **Hugging Face Cache**: Mounted as `/models` volume
- **Port**: 8000 (exposed in Dockerfile)
- **Startup Command**: `python -m app.scripts.entrypoint` (from Dockerfile CMD)

### Docker Settings

| Setting | Value | Explanation |
|---------|-------|-------------|
| **Dockerfile Path** | `backend/Dockerfile` | Exact path to the Dockerfile |
| **Build Context** | `.` (repository root) | Build context is the project root |
| **Docker Command** | (leave blank) | Uses the CMD from Dockerfile |
| **Start Command** | (leave blank) | Uses the CMD from Dockerfile |
| **Port Binding** | 8000 | Application listens on port 8000 |
| **Environment Variables** | (see above) | Configured in Render dashboard |

---

## 3. Background Worker Configuration

### Worker Service Required

Yes, a separate Render Background Worker service is required for:
- Job claiming and dispatch
- Collection job processing
- Scheduled tasks

### Worker Service Configuration

| Setting | Value | Explanation |
|---------|-------|-------------|
| **Service Type** | Background Worker | Separate service for background tasks |
| **Repository** | (Your GitHub repository) | Same repository as web service |
| **Branch** | `main` | Production branch |
| **Service Name** | `ai-stock-worker` | Descriptive name for the worker |
| **Runtime** | Docker | Uses the same Dockerfile as web service |
| **Region** | Singapore (`sin`) | Same region as web service |
| **Root Directory** | `.` (repository root) | Same as web service |
| **Dockerfile Path** | `backend/Dockerfile` | Same Dockerfile as web service |
| **Docker Build Context** | `.` (repository root) | Same as web service |
| **Docker Command** | (leave blank) | Uses the CMD from Dockerfile |
| **Start Command** | `python -m app.workers.main` | Worker entrypoint |
| **Instance Type** | Starter (2GB RAM) | Minimum recommended for worker |
| **Auto-Deploy** | Yes | Auto-deploy on push to `main` branch |
| **Build Filters** | (none) | No build filters needed |
| **Persistent Disk** | No | Hugging Face models use a Docker volume |

### Worker Environment Variables

| Variable | Required? | Secret? | Value | Purpose |
|----------|-----------|---------|-------|---------|
| `DATABASE_URL` | Yes | Yes | Neon direct connection string | PostgreSQL connection (same as web service) |
| `DATA_MODE` | Yes | No | `live` | Production data mode |
| `EXA_API_KEY` | No | Yes | (Your Exa API key) | Exa search API key |
| `TAVILY_API_KEY` | No | Yes | (Your Tavily API key) | Tavily search API key |
| `APIFY_API_TOKEN` | No | Yes | (Your Apify token) | Apify API token |
| `MARKET_DATA_PROVIDER` | No | No | `twelve_data` | Market data provider |
| `TWELVE_DATA_API_KEY` | No | Yes | (Your Twelve Data API key) | Twelve Data API key |
| `HF_HOME` | No | No | `/models` | Hugging Face model cache directory |

---

## 4. Pre-Deployment Verification Checklist

Before deploying to Render, verify:

1. **Database**:
   - Neon database is created and accessible
   - Database schema is migrated (8 tables present)
   - `DATABASE_URL` is set to the direct connection string

2. **Docker**:
   - Dockerfile is in the correct location (`backend/Dockerfile`)
   - Build context is the repository root (`.`) 
   - Docker image builds successfully locally

3. **Environment Variables**:
   - All required variables are configured in Render
   - Secrets are properly marked as secret in Render
   - `DATA_MODE` is set to `live`
   - `CORS_ORIGINS` is set to `http://localhost:3000` (temporary)

4. **Health Checks**:
   - Health check path is `/api/health`
   - Health check start period is set to 300 seconds

5. **Worker Service**:
   - Worker start command is `python -m app.workers.main`
   - Worker shares the same database as the web service

---

## 5. Post-Deployment Testing Checklist

After deployment, test these endpoints:

1. **Liveness Check**:
   ```bash
   curl -s https://<render-service-url>/api/health | jq
   ```
   **Expected Response**:
   ```json
   {
     "status": "ok",
     "app": "ai-stock-backend",
     "data_mode": "live",
     "market_data_provider": "twelve_data",
     "timestamp": "2026-11-09T07:35:58.530Z"
   }
   ```

2. **Readiness Check**:
   ```bash
   curl -s https://<render-service-url>/api/ready | jq
   ```
   **Expected Response**:
   ```json
   {
     "status": "ready",
     "database": "up",
     "timestamp": "2026-11-09T07:35:58.530Z"
   }
   ```

3. **Assets Endpoint**:
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
         "is_demo": false
       },
       ...
     ],
     "data_mode": "live",
     "as_of": "2026-11-09T07:35:58.530Z"
   }
   ```

4. **OpenAPI Schema**:
   ```bash
   curl -s https://<render-service-url>/api/openapi.json | jq .info
   ```
   **Expected**: Returns OpenAPI schema metadata.

5. **Database Connectivity**:
   - Verify `/api/ready` returns `database: "up"`
   - Check Render logs for connection errors
   - Verify `DATABASE_URL` is correctly set in Render environment

6. **Secrets Verification**:
   ```bash
   # DO NOT do this; just verify in Render Dashboard
   # Render logs should NEVER print actual key values
   curl -s https://<render-service-url>/api/health
   # Should NOT contain any secret values in the response
   ```
   - Inspect Render service logs
   - Confirm no API keys, passwords, or connection strings appear in startup logs

7. **Load Testing**:
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

## 6. Known Risks and Required Corrections

1. **CORS Configuration**:
   - Initial `CORS_ORIGINS` is set to `http://localhost:3000`
   - **Correction**: Update to Vercel frontend URL after Stage 6

2. **Hugging Face Model Cache**:
   - Current: `/models` volume in docker-compose (local)
   - Render: No persistent volume by default
   - **Correction**: Consider Render Disk (`/mnt/data`) or pre-build models into image
   - **Temporary Workaround**: Accept longer first startup (~5–10 min) for model downloads

3. **Database Pooling**:
   - Using Neon direct connection (not pooled)
   - **Note**: This is correct for production (Alembic requires direct connection)

4. **Health Check Start Period**:
   - Set to 300 seconds to allow for migrations
   - **Note**: This is correct for production

---

## 7. Deployment Order

1. **Configure Web Service**:
   - Set all required environment variables
   - Verify Docker configuration
   - Set health check path and start period

2. **Deploy Web Service**:
   - Create the Render Web Service
   - Monitor deployment logs
   - Verify liveness and readiness endpoints

3. **Configure Worker Service**:
   - Set all required environment variables
   - Verify worker start command

4. **Deploy Worker Service**:
   - Create the Render Background Worker
   - Monitor deployment logs

5. **Post-Deployment Verification**:
   - Run all post-deployment tests
   - Verify all endpoints are working
   - Check logs for errors

6. **Update CORS Configuration**:
   - After Vercel deployment, update `CORS_ORIGINS` in Render

---

## Summary of Required Configuration

1. **Render Web Service**:
   - Service Type: Web Service
   - Repository: (Your GitHub repository)
   - Branch: `main`
   - Service Name: `ai-stock-backend`
   - Runtime: Docker
   - Region: Singapore (`sin`)
   - Root Directory: `.`
   - Dockerfile Path: `backend/Dockerfile`
   - Docker Build Context: `.`
   - Docker Command: (leave blank)
   - Start Command: (leave blank)
   - Health Check Path: `/api/health`
   - Instance Type: Starter (2GB RAM)
   - Auto-Deploy: Yes
   - Environment Variables: (see table above)

2. **Render Background Worker**:
   - Service Type: Background Worker
   - Repository: (Your GitHub repository)
   - Branch: `main`
   - Service Name: `ai-stock-worker`
   - Runtime: Docker
   - Region: Singapore (`sin`)
   - Root Directory: `.`
   - Dockerfile Path: `backend/Dockerfile`
   - Docker Build Context: `.`
   - Docker Command: (leave blank)
   - Start Command: `python -m app.workers.main`
   - Instance Type: Starter (2GB RAM)
   - Auto-Deploy: Yes
   - Environment Variables: (see table above)

3. **Environment Variables**:
   - `DATABASE_URL`: Neon direct connection string
   - `DATA_MODE`: `live`
   - `API_ADMIN_KEY`: (Generate a strong key)
   - `CORS_ORIGINS`: `http://localhost:3000` (update after Vercel)
   - `EXA_API_KEY`: (Your Exa API key)
   - `TAVILY_API_KEY`: (Your Tavily API key)
   - `APIFY_API_TOKEN`: (Your Apify token)
   - `MARKET_DATA_PROVIDER`: `twelve_data`
   - `TWELVE_DATA_API_KEY`: (Your Twelve Data API key)
   - `HF_HOME`: `/models`

4. **Post-Deployment**:
   - Update `CORS_ORIGINS` to Vercel frontend URL after Stage 6

**Note**: All secret values should be configured in the Render dashboard as secret variables, not in the document.

---

**Documentation Completed**: 2026-11-09 07:55 UTC
