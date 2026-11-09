# GitHub Actions Background Worker Setup Guide

**Project**: AI Stock Sentiment & Next-Day Prediction Agent  
**Date**: 2026-11-09  
**Production Backend**: https://ai-stock-sentiment.onrender.com  
**Repository**: `Shresth-shukla-beginercoder/AI_Stock_Sentiment`

---

## Overview

This guide explains how to set up GitHub Actions to run background jobs for your AI Stock Sentiment Agent. The worker will:

- Run on a schedule (every 6 hours by default)
- Process collection jobs (market data, news, social posts)
- Score sentiment on collected data
- Support manual execution via GitHub Actions UI
- Connect directly to your Neon PostgreSQL database
- Use the existing worker implementation from `backend/app/workers/`

**Architecture**:
- **Render Web Service**: FastAPI backend (already deployed)
- **Neon PostgreSQL**: Production database (already configured)
- **GitHub Actions**: Background job execution (this setup)
- **Vercel**: Frontend deployment (upcoming)

---

## What You Need to Do

### Step 1: Create the `.github/workflows` Directory Structure

The workflow file has been created at:
```
.github/workflows/background-worker.yml
```

**Action Required**: None. The file is already created in your repository.

---

### Step 2: Configure GitHub Repository Secrets

You need to add the following secrets to your GitHub repository:

#### How to Add Secrets:

1. Go to your GitHub repository: `https://github.com/Shresth-shukla-beginercoder/AI_Stock_Sentiment`
2. Click **Settings** → **Secrets and variables** → **Actions**
3. Click **New repository secret**
4. Add each secret below

#### Required Secrets:

| Secret Name | Value | Where to Get It |
|-------------|-------|-----------------|
| `DATABASE_URL` | Your Neon direct connection string | Neon Dashboard → Connection Details → Direct |
| `DATA_MODE` | `live` | Set manually |
| `MARKET_DATA_PROVIDER` | `twelve_data` | Set manually |
| `TWELVE_DATA_API_KEY` | Your Twelve Data API key | Twelve Data dashboard |
| `EXA_API_KEY` | Your Exa API key | Exa dashboard |
| `TAVILY_API_KEY` | Your Tavily API key | Tavily dashboard |
| `APIFY_API_TOKEN` | Your Apify token | Apify console |

#### Database URL Format:

Your `DATABASE_URL` should look like this (replace with your actual Neon credentials):
```
postgresql+psycopg://username:password@ep-xxxxx.region.aws.neon.tech/ai_stock_sentiment?sslmode=require
```

**Important**: Use the **direct** (non-pooled) connection string from Neon, not the pooled one.

---

### Step 3: Commit and Push the Workflow File

Run these commands in your terminal:

```bash
cd "C:\Users\shres\OneDrive\Desktop\AI - Stock_Sentiment -Agent"

# Add the workflow file
git add .github/workflows/background-worker.yml

# Commit the change
git commit -m "feat: add GitHub Actions background worker workflow"

# Push to GitHub
git push origin main
```

---

### Step 4: Verify the Workflow is Active

1. Go to your GitHub repository
2. Click the **Actions** tab
3. You should see "Background Worker" in the workflows list
4. The workflow will run:
   - **Automatically**: Every 6 hours at 00:00, 06:00, 12:00, 18:00 UTC
   - **Manually**: Click "Run workflow" in the Actions tab

---

### Step 5: Test Manual Execution

Before waiting for the scheduled run, test the workflow manually:

1. Go to **Actions** tab in your GitHub repository
2. Click **Background Worker** in the left sidebar
3. Click **Run workflow** button
4. Select the branch: `main`
5. Leave "Worker run mode" as `once` (default)
6. Click **Run workflow**
7. Wait for the workflow to complete (should take 1-5 minutes)
8. Click on the workflow run to see the logs

---

## How the Worker Executes

### Workflow Schedule

The workflow runs **every 6 hours** at:
- 00:00 UTC (midnight)
- 06:00 UTC (6 AM)
- 12:00 UTC (noon)
- 18:00 UTC (6 PM)

**Timezone**: All times are in UTC.

### Execution Flow

1. **Checkout repository**: Gets the latest code from `main` branch
2. **Set up Python 3.12**: Installs Python and caches dependencies
3. **Install dependencies**: Installs backend packages from `pyproject.toml`
4. **Verify database connectivity**: Checks connection to Neon PostgreSQL
5. **Run background worker**: Executes `python -m app.workers.main --once`
6. **Report execution summary**: Logs the execution status

### What the Worker Does

The worker (`backend/app/workers/main.py`) runs in `--once` mode, which means:

1. **Scheduler** (runs once): Creates collection jobs for all confirmed assets
2. **Reaper** (runs once): Finds and requeues stuck jobs
3. **Job Processor**: Claims and processes one job, then exits

**Job Types**:
- `collect:market` - Fetch daily price data via Twelve Data
- `collect:social` - Verify Apify actors (no runs approved yet)
- `collect:news` - Fetch news articles via Exa
- `score:sentiment` - Analyze sentiment on collected posts/articles

### Job Claiming Logic

- Uses PostgreSQL `FOR UPDATE SKIP LOCKED` for concurrent-safe claiming
- Multiple GitHub Actions runs can execute safely without conflicts
- Each job is processed exactly once (deduplication via `dedupe_key`)
- Failed jobs are retried with exponential backoff (1, 2, 4, 8 minutes)
- Stuck jobs (running > 30 minutes) are automatically reaped and requeued

---

## Expected Logs

### Successful Execution

```
Database connectivity: OK
[workers.main] worker starting worker_id=fv-az123-456:12345 once=True
[workers.scheduler] scheduler acquired lock, running
[workers.scheduler] scheduled daily jobs target_date=2026-11-09 assets=10 jobs_scheduled=40
[workers.reaper] reaper run complete reaped=0
[workers.claim] claimed job job_id=123 job_type=collect:market ticker=0700 attempts=1
[workers.dispatch] dispatching job job_id=123 job_type=collect:market
[workers.dispatch] collecting market data ticker=0700 date=2026-11-09
[workers.claim] job completed job_id=123 counts={'provider': 'twelvedata', 'fetched': 1, 'inserted': 1}
[workers.main] processed one job, exiting (--once mode)
```

### No Jobs Available

```
Database connectivity: OK
[workers.main] worker starting worker_id=fv-az123-456:12345 once=True
[workers.scheduler] scheduler lock held by another instance, skipping
[workers.claim] no jobs available
[workers.main] no jobs available, exiting (--once mode)
```

### Job Failure and Retry

```
[workers.claim] claimed job job_id=124 job_type=collect:news ticker=0700 attempts=1
[workers.dispatch] collecting news articles ticker=0700 date=2026-11-09
[workers.claim] job failed job_id=124 error="ExaAPIError: rate limit exceeded"
[workers.main] job failed job_id=124 will retry at 2026-11-09T09:01:00Z
```

---

## Concurrency Protection

The workflow uses:
```yaml
concurrency:
  group: background-worker
  cancel-in-progress: false
```

This ensures:
- Only one workflow execution runs at a time
- If a workflow is already running, the next scheduled run waits
- No duplicate job processing

---

## GitHub Actions Free Tier Limits

**Free tier allowance** (for public repositories):
- Unlimited minutes per month

**Free tier allowance** (for private repositories):
- 2,000 minutes per month
- This workflow uses ~5 minutes per run
- 4 runs per day × 30 days = 120 runs/month × 5 minutes = **600 minutes/month**
- Well within the free tier limit

---

## Testing Before Production

### Local Testing

You can test the worker locally before relying on GitHub Actions:

```bash
cd backend

# Set environment variables (use your actual Neon connection string)
export DATABASE_URL="postgresql+psycopg://..."
export DATA_MODE="live"
export MARKET_DATA_PROVIDER="twelve_data"
export TWELVE_DATA_API_KEY="your_key"
export EXA_API_KEY="your_key"
export TAVILY_API_KEY="your_key"
export APIFY_API_TOKEN="your_token"

# Run the worker in --once mode
python -m app.workers.main --once
```

### Verify Jobs are Created

After running the worker, check your database:

```sql
-- Check scheduled jobs
SELECT id, job_type, status, params->>'ticker' as ticker, created_at
FROM collection_jobs
ORDER BY created_at DESC
LIMIT 10;

-- Check job status distribution
SELECT status, COUNT(*) 
FROM collection_jobs 
GROUP BY status;
```

---

## Monitoring and Debugging

### View Workflow Runs

1. Go to your GitHub repository
2. Click **Actions** tab
3. Click **Background Worker** workflow
4. See all past runs with their status (success/failure)

### View Detailed Logs

1. Click on a specific workflow run
2. Click **process-jobs** job
3. Expand each step to see detailed logs
4. Look for `[workers.main]` and `[workers.claim]` log lines

### Common Issues

#### Issue 1: Database Connection Failed

**Error**: `sqlalchemy.exc.OperationalError: could not connect to server`

**Solution**: Check that `DATABASE_URL` secret is correctly set in GitHub and includes `?sslmode=require`

#### Issue 2: No Confirmed Assets

**Error**: `[workers.scheduler] no confirmed assets found, nothing to schedule`

**Solution**: Confirm assets in your database:
```sql
UPDATE assets SET confirmed = true WHERE exchange IN ('HKEX', 'KRX');
```

#### Issue 3: API Key Missing

**Error**: `[workers.dispatch] ExaAPIError: authentication failed`

**Solution**: Add the missing API key secret in GitHub repository settings

#### Issue 4: Hugging Face Model Download Fails

**Error**: `[sentiment.analyzer] failed to load model OSError: connection timeout`

**Solution**: The first run downloads models (~500MB). Subsequent runs use cached models in `/tmp/hf_models`. This is expected behavior.

---

## Configuration Changes

### Change Schedule

Edit `.github/workflows/background-worker.yml`:

```yaml
# Run every hour
schedule:
  - cron: '0 * * * *'

# Run every 12 hours at midnight and noon
schedule:
  - cron: '0 0,12 * * *'

# Run daily at 3 AM UTC
schedule:
  - cron: '0 3 * * *'
```

### Change Timeout

Edit `.github/workflows/background-worker.yml`:

```yaml
jobs:
  process-jobs:
    timeout-minutes: 60  # Increase to 60 minutes
```

### Add More Environment Variables

Edit `.github/workflows/background-worker.yml`:

```yaml
- name: Run background worker
  env:
    DATABASE_URL: ${{ secrets.DATABASE_URL }}
    DATA_MODE: ${{ secrets.DATA_MODE }}
    # Add your new variable here
    YOUR_NEW_VARIABLE: ${{ secrets.YOUR_NEW_VARIABLE }}
```

---

## What Happens After Setup

1. **First Scheduled Run**: The workflow runs at the next scheduled time (00:00, 06:00, 12:00, or 18:00 UTC)
2. **Scheduler Creates Jobs**: The scheduler creates collection jobs for all confirmed assets
3. **Jobs are Processed**: Each run processes one job, then exits
4. **Next Runs**: Subsequent runs claim and process the next available job
5. **Job Queue Depletes**: Eventually all jobs are processed
6. **New Jobs Scheduled**: The scheduler creates new jobs for the next day

### Typical Daily Cycle

- **00:00 UTC**: Scheduler creates 40 jobs (10 assets × 4 job types)
- **00:05 UTC**: Worker processes 1 job
- **06:00 UTC**: Worker processes 1 job
- **12:00 UTC**: Worker processes 1 job
- **18:00 UTC**: Worker processes 1 job
- Total: 4 jobs processed per day

**Note**: To process more jobs per run, you can increase the schedule frequency (e.g., every hour instead of every 6 hours).

---

## Limitations

1. **No Continuous Worker**: The worker runs in `--once` mode (processes one job per run). This is by design to stay within GitHub Actions free tier limits.

2. **Scheduled Runs Only**: Jobs are processed only at scheduled times (every 6 hours). Real-time processing is not supported.

3. **No Hugging Face Model Persistence**: Models are downloaded to `/tmp/hf_models` on each run. The first run after a fresh checkout will download models (~500MB, ~5 minutes).

4. **No Job Prioritization**: Jobs are processed in FIFO order (oldest first). Priority queues are not implemented.

5. **Single Job per Run**: Each workflow execution processes exactly one job. To process more jobs, increase the schedule frequency.

---

## Next Steps

After completing this setup:

1. **Stage 6**: Deploy Vercel frontend
2. **Update CORS**: Update `CORS_ORIGINS` in Render to include the Vercel frontend URL
3. **Monitor Jobs**: Check GitHub Actions logs and database to verify jobs are being processed
4. **Adjust Schedule**: If needed, increase or decrease the schedule frequency

---

## Summary Checklist

- [ ] Workflow file created: `.github/workflows/background-worker.yml`
- [ ] GitHub repository secrets configured (7 secrets)
- [ ] Workflow file committed and pushed to GitHub
- [ ] Workflow is visible in GitHub Actions tab
- [ ] Manual test execution completed successfully
- [ ] Scheduled runs are working
- [ ] Database has confirmed assets (`confirmed = true`)
- [ ] Jobs are being created by the scheduler
- [ ] Jobs are being processed by the worker
- [ ] Logs are clear and show no errors

---

**Setup Complete!** Your background worker is now running on GitHub Actions.

For questions or issues, check the GitHub Actions logs or inspect the worker implementation in `backend/app/workers/`.
