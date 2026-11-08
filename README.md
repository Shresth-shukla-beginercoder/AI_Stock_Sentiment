# AI Stock Sentiment & Next-Day Prediction Agent

A research platform that collects social media posts and news articles for 10 major stocks (5 HKEX, 5 KRX), analyzes sentiment using NLP, tracks price history, and provides experimental next-day return predictions via REST API.

**⚠️ Disclaimer**: This platform is for research purposes only. It does NOT provide financial advice and should NEVER be used as a trading bot or investment recommendation system. Past performance does not guarantee future results.

---

## Table of Contents

- [Features](#features)
- [Architecture](#architecture)
- [Quick Start](#quick-start)
- [Production Deployment](#production-deployment)
- [Configuration](#configuration)
- [API Usage](#api-usage)
- [Running Workers](#running-workers)
- [Database](#database)
- [Monitoring & Logs](#monitoring--logs)
- [Security](#security)
- [Troubleshooting](#troubleshooting)

---

## Features

### Data Collection
- **Market data**: Daily OHLCV prices from Twelve Data
- **Social media**: Posts from Twitter/X, Reddit, Telegram via Apify
- **News articles**: Web/news search via Exa and Tavily APIs
- **Deduplication**: SHA-256 content-based deduplication with ON CONFLICT DO NOTHING

### Sentiment Analysis
- **Multi-language**: Automatic language detection with support for English, Simplified Chinese, Traditional Chinese, Korean
- **Weighted scoring**: P(positive) − P(negative), weighted by engagement (1 + ln(1 + engagement))
- **Dual-source aggregation**: 40% social media + 60% news (configurable)
- **10-day window**: Rolling window for recent sentiment trends
- **Threshold signals**: ±0.15 threshold for strong signals; `insufficient_data` when n < 3 items

### Prediction Model
- **Target**: Next-day return (%)
- **Validation**: Walk-forward TimeSeriesSplit (gap=1, no data leakage)
- **Baselines**: No-change baseline + always-up baseline for comparison
- **Metrics**: MAE, RMSE, directional accuracy
- **Registry**: Model versioning with git commit tracking

### REST API
- **FastAPI + Pydantic**: Type-safe, auto-documented
- **OpenAPI/Swagger**: At `/api/openapi.json` and `/docs`
- **Demo mode**: Can run with demo data (no external APIs required)
- **Admin authentication**: X-API-Key with constant-time comparison (no timing leaks)
- **Response format**: Every response includes `data_mode` (demo/live) and `as_of` timestamp

### Background Jobs
- **PostgreSQL queue**: FIFO job processing with FOR UPDATE SKIP LOCKED
- **Concurrent workers**: Multiple workers claim jobs concurrently
- **Exponential backoff**: 1, 2, 4, 8... minutes for retries
- **Reaper**: Automatically recovers jobs stuck > 30 minutes
- **Deduplication**: Unique `dedupe_key` prevents duplicate scheduling
- **Advisory locks**: Only one scheduler runs across multiple instances

### Frontend Dashboard
- **React + Vite**: Modern, fast SPA with dark terminal theme
- **Live charts**: Recharts for price and sentiment visualization
- **Job monitoring**: Real-time job status tracking
- **API transparency**: Raw JSON viewer for all responses
- **Admin interface**: Jobs page for manual triggers (requires X-API-Key)

---

## Architecture

```
┌────────────────────────────────────────────────────────────┐
│                     Reverse Proxy (TLS)                    │
│                    (nginx, CloudFlare, etc)                │
└────────────────┬───────────────────────────────────────────┘
                 │
        ┌────────┴────────┐
        │                 │
        ▼                 ▼
  ┌──────────┐      ┌──────────┐
  │ Frontend │      │ Backend  │
  │ (nginx)  │      │(FastAPI) │
  │ :80      │      │ :8000    │
  └──────────┘      └────┬─────┘
                         │
          ┌──────────────┼──────────────┐
          │              │              │
          ▼              ▼              ▼
     ┌─────────┐  ┌─────────┐  ┌──────────────┐
     │PostgreSQL  │ HF Cache │  │ Worker(s)   │
     │(DB)     │  │(/models) │  │(Job Process)│
     └─────────┘  └─────────┘  └──────────────┘
          │                           │
          └───────────────┬───────────┘
                          │
          ┌───────────────┴───────────────┐
          │                               │
          ▼                               ▼
     ┌─────────────┐              ┌────────────────┐
     │ Collectors  │              │ Sentiment      │
     │(Market/News)│              │ Analyzer       │
     │(Social)     │              │(NLP Models)    │
     └─────────────┘              └────────────────┘
          │                               │
          ▼                               ▼
     ┌──────────────────────────────────────┐
     │  External APIs                       │
     │  - Twelve Data (OHLCV)              │
     │  - Exa (Web search)                 │
     │  - Tavily (News search)             │
     │  - Apify (Social media)             │
     └──────────────────────────────────────┘
```

### Key Services

| Service | Port | Purpose | Non-Root |
|---------|------|---------|----------|
| PostgreSQL | 5432 | Primary data store, job queue | ✓ |
| Backend API | 8000 | REST API, migrations, health checks | ✓ (UID 1000) |
| Frontend | 80 | React SPA, /api/ proxy to backend | ✓ (nginx) |
| Worker | none | Background job processing | ✓ (UID 1000) |

---

## Quick Start

### Prerequisites
- **Docker** 20.10+
- **Docker Compose** 2.0+
- **.env file** with required credentials (see [Configuration](#configuration))

### Development Setup

1. **Clone and configure**:
   ```bash
   git clone <repo>
   cd AI-Stock-Sentiment-Agent
   cp .env.example .env
   # Edit .env with your API keys and settings
   ```

2. **Start services** (demo mode):
   ```bash
   docker compose up -d
   ```

3. **Access the platform**:
   - **Frontend**: http://localhost:3000
   - **API**: http://localhost:8000/api
   - **Swagger**: http://localhost:8000/docs

4. **Check status**:
   ```bash
   docker compose ps
   curl http://localhost:8000/api/health
   ```

### Example API Calls (Demo Mode)

```bash
# Get system status
curl http://localhost:8000/api/system

# List assets
curl http://localhost:8000/api/assets

# Get predictions (admin-only endpoint requires X-API-Key)
curl -H "X-API-Key: demo-key-12345" http://localhost:8000/api/predictions

# Trigger a collection job (requires admin key)
curl -X POST -H "X-API-Key: demo-key-12345" \
  -H "Content-Type: application/json" \
  -d '{"ticker":"0700.HK","job_type":"collect:market"}' \
  http://localhost:8000/api/jobs
```

---

## Production Deployment

### Prerequisites
- **Docker** 20.10+ with Compose 2.0+
- **TLS terminator**: nginx, CloudFlare, or cloud load balancer
- **Environment variables**: Set before deployment (see `.env.example`)
- **PostgreSQL backups**: Configure external backups before going live

### Deployment Steps

1. **Prepare environment**:
   ```bash
   # Copy and configure production .env
   cp .env.example .env.prod
   
   # Set required variables in .env.prod:
   # - POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB
   # - API_ADMIN_KEY (strong random string)
   # - DATA_MODE=live
   # - MARKET_DATA_PROVIDER=twelve_data
   # - TWELVE_DATA_API_KEY, EXA_API_KEY, TAVILY_API_KEY, APIFY_API_TOKEN
   # - CORS_ORIGINS=https://yourdomain.com
   # - DOCKERHUB_USERNAME (optional, defaults to local)
   ```

2. **Load environment**:
   ```bash
   export $(cat .env.prod | grep -v '^#' | xargs)
   ```

3. **Start production services**:
   ```bash
   docker compose -f docker-compose.prod.yml up -d
   ```

4. **Configure reverse proxy** (nginx example):
   ```nginx
   upstream backend {
     server frontend:80;  # Frontend handles routing to both UI and API
   }

   server {
     listen 443 ssl http2;
     server_name yourdomain.com;
     
     ssl_certificate /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
     ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;
     
     location / {
       proxy_pass http://backend;
       proxy_set_header Host $host;
       proxy_set_header X-Real-IP $remote_addr;
       proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
       proxy_set_header X-Forwarded-Proto $scheme;
     }
   }
   ```

5. **Verify deployment**:
   ```bash
   # Check all services are healthy
   docker compose -f docker-compose.prod.yml ps
   
   # Verify API health
   curl https://yourdomain.com/api/health
   
   # Check database connectivity
   docker compose -f docker-compose.prod.yml exec backend \
     python -c "from app.database.session import SessionLocal; \
                s = SessionLocal(); \
                print('DB connected:', len(s.execute('SELECT 1').fetchall()))"
   ```

### Scaling Workers

For high-volume job processing, run multiple worker instances:

```bash
# Start 3 worker instances
docker compose -f docker-compose.prod.yml up -d --scale worker=3

# Monitor worker logs
docker compose -f docker-compose.prod.yml logs -f worker
```

---

## Configuration

### Environment Variables

#### Database
- `POSTGRES_USER`: Database user (default: `stock`)
- `POSTGRES_PASSWORD`: Database password (required in prod)
- `POSTGRES_DB`: Database name (default: `stock_sentiment`)
- `POSTGRES_HOST`: Host (dev: `localhost`, prod: `postgres`)
- `POSTGRES_PORT`: Port (dev: `5437`, prod: `5432`)

#### Data Mode
- `DATA_MODE`: `demo` (default, no external APIs) or `live` (requires credentials)

#### API & Authentication
- `API_ADMIN_KEY`: Admin authentication key (required for protected endpoints)
- `HOST`: Server bind address (default: `0.0.0.0`)
- `PORT`: Server port (default: `8000`)
- `CORS_ORIGINS`: Comma-separated list of allowed origins

#### Market Data (Twelve Data)
- `MARKET_DATA_PROVIDER`: `twelve_data` (required)
- `TWELVE_DATA_API_KEY`: Twelve Data API key

#### News & Social Media
- `EXA_API_KEY`: Exa API key (for web search)
- `TAVILY_API_KEY`: Tavily API key (for news)
- `APIFY_API_TOKEN`: Apify token (for social media)

#### ML Models
- `HF_HOME`: Hugging Face cache directory (default: `/models`)

### .env.example Template

```bash
# Development (demo mode)
DATA_MODE=demo
API_ADMIN_KEY=dev-key-12345
POSTGRES_USER=stock
POSTGRES_PASSWORD=stock_dev_password
POSTGRES_DB=stock_sentiment
MARKET_DATA_PROVIDER=twelve_data

# Production (live mode)
# DATA_MODE=live
# API_ADMIN_KEY=<strong-random-key>
# POSTGRES_USER=<secure-username>
# POSTGRES_PASSWORD=<secure-password>
# POSTGRES_DB=stock_sentiment_prod
# MARKET_DATA_PROVIDER=twelve_data
# TWELVE_DATA_API_KEY=<your-key>
# EXA_API_KEY=<your-key>
# TAVILY_API_KEY=<your-key>
# APIFY_API_TOKEN=<your-token>
# CORS_ORIGINS=https://yourdomain.com
```

---

## API Usage

### Health Checks

```bash
# Liveness (application only)
GET /api/health

# Readiness (includes database check)
GET /api/ready
```

### Assets

```bash
# List all assets
GET /api/assets

# Response includes data_mode and as_of timestamp
{
  "data": [...],
  "meta": {
    "data_mode": "demo",
    "as_of": "2026-11-09T20:55:13.638Z",
    "state": "ok"
  }
}
```

### System Status

```bash
# Get system overview
GET /api/system

# Includes credential availability and live-data status
{
  "data": {
    "uptime_seconds": 3600,
    "api_version": "1.0.0",
    "database": {
      "connected": true,
      "tables": 8
    },
    "credentials": {
      "market_data_provider_configured": true,
      "exa_configured": false,
      "tavily_configured": true,
      "apify_configured": false
    }
  },
  "meta": {...}
}
```

### Predictions (Admin Only)

```bash
# Get next-day predictions
GET /api/predictions -H "X-API-Key: <admin-key>"

# Includes walk-forward metrics
{
  "data": [
    {
      "ticker": "0700.HK",
      "date": "2026-11-09",
      "predicted_return": 0.025,
      "confidence": 0.58,
      "experimental": false,
      "metrics": {
        "mae": 0.015,
        "rmse": 0.018,
        "directional_accuracy": 0.62
      }
    }
  ],
  "meta": {...}
}
```

### Jobs (Admin Only)

```bash
# Create a job
POST /api/jobs -H "X-API-Key: <admin-key>" \
  -H "Content-Type: application/json" \
  -d {
    "ticker": "0700.HK",
    "job_type": "collect:market",
    "run_after": "2026-11-09T21:00:00Z"
  }

# Response: 202 Accepted with job_id
{
  "data": {
    "job_id": "uuid",
    "status": "queued",
    "attempts": 0
  },
  "meta": {...}
}

# Get job status
GET /api/jobs/<job_id> -H "X-API-Key: <admin-key>"

# List all jobs
GET /api/jobs -H "X-API-Key: <admin-key>"
```

### Full OpenAPI Documentation

```bash
# Interactive Swagger UI
http://localhost:8000/docs

# OpenAPI JSON
http://localhost:8000/api/openapi.json
```

---

## Running Workers

### Single Worker (Development)

```bash
# Start a worker in the background
docker compose exec backend python -m app.workers.main

# Or run once and exit (for testing)
docker compose exec backend python -m app.workers.main --once
```

### Multiple Workers (Production)

```bash
# Start 3 worker instances
docker compose -f docker-compose.prod.yml up -d --scale worker=3

# Monitor logs
docker compose -f docker-compose.prod.yml logs -f worker

# Scale up/down
docker compose -f docker-compose.prod.yml up -d --scale worker=5
```

### Worker Behavior

- **Job claiming**: Uses PostgreSQL `FOR UPDATE SKIP LOCKED` for concurrent safety
- **Retry logic**: Exponential backoff (1, 2, 4, 8... minutes) on failure
- **Reaper**: Automatically requeues jobs stuck in `running` state > 30 minutes
- **Graceful shutdown**: Catches SIGTERM/SIGINT, completes current job before exiting
- **Scheduler**: Runs every 10 iterations, creates daily collection jobs (only one scheduler runs via advisory lock)

### Job Types

| Type | Purpose | Required Credentials |
|------|---------|----------------------|
| `collect:market` | Fetch daily OHLCV | TWELVE_DATA_API_KEY |
| `collect:social` | Scrape social media | APIFY_API_TOKEN |
| `collect:news` | Fetch news articles | EXA_API_KEY, TAVILY_API_KEY |
| `score:sentiment` | Analyze sentiment | None (uses local HF models) |

---

## Database

### Schema

8 tables created by Alembic migrations:

1. **assets** — Stock tickers and exchanges (HKEX, KRX)
2. **market_prices** — Daily OHLCV data
3. **social_posts** — Twitter, Reddit, Telegram posts
4. **news_articles** — Web articles, deduped by content hash
5. **sentiment_results** — Aggregated sentiment scores (10-day rolling)
6. **features** — Engineered features (technical indicators)
7. **model_evaluations** — ML model performance metrics
8. **collection_jobs** — Job queue for workers

### Migrations

```bash
# Run migrations (happens automatically on backend startup)
docker compose exec backend alembic upgrade head

# Check migration status
docker compose exec backend alembic current

# Create a new migration
docker compose exec backend alembic revision --autogenerate -m "description"
```

### Direct Database Access

```bash
# Connect with psql (dev only, port 5437 exposed)
psql -h localhost -U stock -d stock_sentiment -p 5437

# Inside container (production)
docker compose -f docker-compose.prod.yml exec postgres \
  psql -U ${POSTGRES_USER} -d ${POSTGRES_DB}
```

---

## Monitoring & Logs

### Health Checks

```bash
# Application health
docker compose ps

# Database health
docker compose exec postgres pg_isready -U stock

# Backend API
curl http://localhost:8000/api/health

# Full readiness check
curl http://localhost:8000/api/ready
```

### Logs

```bash
# View all service logs
docker compose logs -f

# Specific service
docker compose logs -f backend
docker compose logs -f worker
docker compose logs -f postgres

# Last N lines
docker compose logs --tail=100 backend

# Time-range (last hour)
docker compose logs --since 1h backend
```

### Production Logging

All services log to `json-file` driver with rotation:

- **Backend**: 50MB max per file, 5 files retained
- **Worker**: 50MB max per file, 5 files retained
- **Postgres**: 50MB max per file, 5 files retained
- **Frontend**: 10MB max per file, 2 files retained

Access logs:

```bash
# Docker logs
docker logs ai_stock_backend_prod

# Or inspect JSON files directly
cat /var/lib/docker/containers/<container-id>/<container-id>-json.log | jq
```

---

## Security

### Authentication

- **Admin endpoints** require `X-API-Key` header
- **Constant-time comparison**: Uses `secrets.compare_digest()` (no timing leaks)
- **Demo mode**: Can run without credentials for development/testing

### Secrets Management

- **Never commit** `.env` files (`.gitignore` protects this)
- **Frontend**: Stored in memory only, never persisted or logged
- **Backend**: Stored in environment only, never logged or exposed in responses
- **Use a secrets manager**: HashiCorp Vault, AWS Secrets Manager, etc. for production

### Data Isolation

- **Demo mode** (default): Uses demo data, no external APIs called
- **Live mode** (`DATA_MODE=live`): Requires valid credentials, calls real APIs
- **Responses**: Every API response includes `data_mode` field (never mix demo and live rows)

### CORS

- **Dev**: `http://localhost:3000,http://127.0.0.1:3000`
- **Prod**: Set via `CORS_ORIGINS` environment variable (no wildcard `*`)

### TLS/HTTPS

- **Dev**: HTTP only (localhost)
- **Prod**: Use external TLS terminator (nginx, CloudFlare, AWS ALB, etc.)
  - Backend listens on HTTP (TLS terminated upstream)
  - Always use HTTPS in production

### Docker Security

- **Non-root user**: Backend (UID 1000) and Worker (UID 1000) run as `appuser`, not root
- **Frontend**: Runs as `nginx` unprivileged user
- **Resource limits**: Configured in `docker-compose.prod.yml` to prevent resource exhaustion

---

## Troubleshooting

### Services Won't Start

```bash
# Check compose syntax
docker compose config

# Check for port conflicts
docker ps -a

# View detailed error logs
docker compose logs backend
docker compose logs postgres
```

### Database Connection Failed

```bash
# Verify database is running and healthy
docker compose ps postgres

# Check credentials in .env
cat .env | grep POSTGRES

# Test connection manually
docker compose exec backend python -c \
  "from app.database.session import SessionLocal; SessionLocal()"
```

### Worker Not Processing Jobs

```bash
# Check worker is running
docker compose ps worker

# View worker logs
docker compose logs -f worker

# Verify database connectivity
docker compose exec worker python -c \
  "from app.database.session import SessionLocal; SessionLocal()"

# Manually check job queue
docker compose exec postgres psql -U stock -d stock_sentiment -c \
  "SELECT job_id, job_type, status, attempts FROM collection_jobs LIMIT 5;"
```

### API Returns 401 Unauthorized

```bash
# Verify admin key is set
echo $API_ADMIN_KEY

# Test with correct header
curl -H "X-API-Key: $API_ADMIN_KEY" http://localhost:8000/api/predictions

# Check API key in database (if using persistent storage)
docker compose exec postgres psql -U stock -d stock_sentiment -c \
  "SELECT * FROM admin_keys;"
```

### Out of Memory

```bash
# Check resource usage
docker stats

# Increase Docker memory allocation
# (Docker settings → Resources → Memory)

# Or adjust compose resource limits
# Edit docker-compose.prod.yml and redeploy
```

### Sentiment Analysis Not Running

```bash
# Check HF_HOME volume is mounted
docker compose exec backend ls -la /models

# Verify transformers model is cached
docker compose exec backend ls -la /models/

# Test sentiment manually
docker compose exec backend python -c \
  "from app.sentiment.analyzer import analyze_text; \
   print(analyze_text('I love this stock!'))"
```

### No Predictions Generated

1. **Verify market data exists**: `SELECT COUNT(*) FROM market_prices;`
2. **Verify sentiment data exists**: `SELECT COUNT(*) FROM sentiment_results;`
3. **Check model training logs**: `docker compose logs worker | grep training`
4. **Verify feature engineering**: `SELECT COUNT(*) FROM features;`
5. **Check model registry**: `SELECT * FROM model_evaluations;`

### Prod Compose Won't Deploy

```bash
# Validate environment variables are set
env | grep POSTGRES | head
env | grep API_ADMIN_KEY

# Test compose with verbose output
docker compose -f docker-compose.prod.yml config

# View detailed logs
docker compose -f docker-compose.prod.yml logs postgres

# Verify all required images are built
docker images | grep ai-stock
```

---

## Support & Development

### Running Tests

```bash
# Backend tests
docker compose exec backend python -m pytest tests/ -v

# Specific test module
docker compose exec backend python -m pytest tests/test_phase10_security.py -v

# With coverage
docker compose exec backend python -m pytest tests/ --cov=app --cov-report=html
```

### Building Images Locally

```bash
# Backend
docker compose build backend

# Frontend
docker compose build frontend

# All services
docker compose build
```

### Cleaning Up (Development Only)

```bash
# Stop all services
docker compose down

# Remove data (WARNING: deletes database!)
# DO NOT use in production without backups
# docker compose down -v
```

---

## License

Research use only. See LICENSE file for details.

## Questions?

For issues, questions, or contributions, please open an issue on the project repository.

---

**Last updated**: 2026-11-09  
**Version**: 1.0.0  
**API Version**: 1.0.0
