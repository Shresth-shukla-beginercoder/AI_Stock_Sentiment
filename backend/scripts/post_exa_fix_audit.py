"""Post-Exa-fix production job audit (read-only).

Audit production job queue after the Exa category="news" fix to determine:
- Whether failed jobs occurred before or after the fix deployment
- Whether queued jobs are eligible for retry
- Current job status breakdown

Usage:
    DATABASE_URL="postgresql://..." python scripts/post_exa_fix_audit.py
"""

import os
import sys
from datetime import datetime, timezone
from sqlalchemy import create_engine, text

def format_timestamp(ts):
    """Format timestamp for readability."""
    if ts is None:
        return "N/A"
    return ts.strftime("%Y-%m-%d %H:%M:%S UTC")

def main():
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("ERROR: DATABASE_URL environment variable not set", file=sys.stderr)
        print("Usage: DATABASE_URL='postgresql://...' python scripts/post_exa_fix_audit.py", file=sys.stderr)
        sys.exit(1)

    engine = create_engine(db_url, echo=False)

    now = datetime.now(timezone.utc)
    audit_time = now.isoformat()

    print("=" * 80)
    print("POST-EXA-FIX PRODUCTION JOB AUDIT")
    print(f"Audit Time: {format_timestamp(now)}")
    print("=" * 80)

    with engine.connect() as conn:
        # Query 1: Overall status summary
        print("\n## 1. OVERALL JOB STATUS SUMMARY\n")
        result = conn.execute(text("""
            SELECT
                status,
                COUNT(*) as count
            FROM collection_jobs
            GROUP BY status
            ORDER BY
                CASE status
                    WHEN 'failed' THEN 1
                    WHEN 'queued' THEN 2
                    WHEN 'done' THEN 3
                    WHEN 'running' THEN 4
                    ELSE 5
                END
        """))

        status_counts = {}
        for row in result:
            status_counts[row.status] = row.count
            print(f"  {row.status:10} | {row.count:3} jobs")

        # Query 2: Failed jobs grouped by job_type
        print("\n## 2. FAILED JOBS BY TYPE\n")
        result = conn.execute(text("""
            SELECT
                job_type,
                COUNT(*) as failed_count,
                MAX(attempts) as max_attempts_reached,
                MAX(updated_at) as most_recent_failure,
                MIN(updated_at) as first_failure
            FROM collection_jobs
            WHERE status = 'failed'
            GROUP BY job_type
            ORDER BY failed_count DESC
        """))

        failed_by_type = []
        for row in result:
            failed_by_type.append({
                "job_type": row.job_type,
                "count": row.failed_count,
                "attempts": row.max_attempts_reached,
                "most_recent": row.most_recent_failure,
                "first": row.first_failure,
            })
            print(f"  {row.job_type:20} | {row.failed_count:2} failures | attempts={row.max_attempts_reached}")
            print(f"    First: {format_timestamp(row.first_failure)}")
            print(f"    Most recent: {format_timestamp(row.most_recent_failure)}\n")

        # Query 3: Detailed failed job errors (sample)
        if failed_by_type:
            print("\n## 3. FAILED JOB ERROR SAMPLES (most recent per type)\n")
            for ftype in failed_by_type:
                print(f"### Job Type: {ftype['job_type']}\n")
                result = conn.execute(text("""
                    SELECT
                        id,
                        dedupe_key,
                        attempts,
                        SUBSTRING(error, 1, 300) as error_excerpt,
                        updated_at
                    FROM collection_jobs
                    WHERE status = 'failed' AND job_type = :job_type
                    ORDER BY updated_at DESC
                    LIMIT 2
                """), {"job_type": ftype["job_type"]})

                for idx, row in enumerate(result, 1):
                    ticker = None
                    if ":" in row.dedupe_key:
                        parts = row.dedupe_key.split(":")
                        if len(parts) >= 3:
                            ticker = parts[2]

                    print(f"  [{idx}] Job {row.id}")
                    print(f"      Ticker: {ticker or 'unknown'}")
                    print(f"      Dedupe: {row.dedupe_key}")
                    print(f"      Attempts: {row.attempts}")
                    print(f"      Updated: {format_timestamp(row.updated_at)}")
                    print(f"      Error: {row.error_excerpt}")
                    print()

        # Query 4: Queued jobs detail
        print("\n## 4. QUEUED JOBS (pending execution)\n")
        result = conn.execute(text("""
            SELECT
                id,
                job_type,
                dedupe_key,
                attempts,
                max_attempts,
                run_after,
                SUBSTRING(error, 1, 200) as last_error,
                created_at,
                updated_at,
                CASE
                    WHEN run_after IS NULL THEN 'READY (no delay)'
                    WHEN run_after <= NOW() THEN 'READY (delay expired)'
                    ELSE 'DELAYED (backoff until ' || run_after::text || ')'
                END as eligibility
            FROM collection_jobs
            WHERE status = 'queued'
            ORDER BY COALESCE(run_after, created_at)
        """))

        queued_jobs = []
        for row in result:
            queued_jobs.append(row)
            ticker = None
            if ":" in row.dedupe_key:
                parts = row.dedupe_key.split(":")
                if len(parts) >= 3:
                    ticker = parts[2]

            print(f"Job {row.id} | {row.job_type}")
            print(f"  Ticker: {ticker or 'unknown'}")
            print(f"  Attempts: {row.attempts}/{row.max_attempts}")
            print(f"  Created: {format_timestamp(row.created_at)}")
            print(f"  Updated: {format_timestamp(row.updated_at)}")
            print(f"  Status: {row.eligibility}")
            if row.last_error:
                print(f"  Last error: {row.last_error}")
            print()

        if not queued_jobs:
            print("  (no queued jobs)\n")

        # Query 5: Check if any collect:news failures are Exa-related
        print("\n## 5. EXA-RELATED FAILURES (collect:news jobs)\n")
        result = conn.execute(text("""
            SELECT
                id,
                dedupe_key,
                attempts,
                SUBSTRING(error, 1, 400) as error_text,
                updated_at,
                CASE
                    WHEN error ILIKE '%type%' AND error ILIKE '%news%' THEN 'LIKELY EXA BUG'
                    WHEN error ILIKE '%invalid option%' THEN 'LIKELY EXA BUG'
                    WHEN error ILIKE '%400%' THEN 'HTTP 400'
                    WHEN error ILIKE '%validation%' THEN 'VALIDATION ERROR'
                    ELSE 'OTHER'
                END as error_category
            FROM collection_jobs
            WHERE status = 'failed' AND job_type = 'collect:news'
            ORDER BY updated_at DESC
        """))

        exa_failures = list(result)
        if exa_failures:
            for row in exa_failures:
                ticker = None
                if ":" in row.dedupe_key:
                    parts = row.dedupe_key.split(":")
                    if len(parts) >= 3:
                        ticker = parts[2]

                print(f"Job {row.id} | Ticker: {ticker or 'unknown'} | Category: {row.error_category}")
                print(f"  Updated: {format_timestamp(row.updated_at)}")
                print(f"  Error: {row.error_text}")
                print()
        else:
            print("  (no failed collect:news jobs)\n")

        # Query 6: Time-based analysis
        print("\n## 6. FAILURE TIMELINE ANALYSIS\n")
        result = conn.execute(text("""
            SELECT
                DATE_TRUNC('hour', updated_at) as failure_hour,
                COUNT(*) as failures,
                STRING_AGG(DISTINCT job_type, ', ') as job_types
            FROM collection_jobs
            WHERE status = 'failed'
            GROUP BY DATE_TRUNC('hour', updated_at)
            ORDER BY failure_hour DESC
            LIMIT 10
        """))

        print("  Most recent failure hours:\n")
        for row in result:
            print(f"  {row.failure_hour} | {row.failures:2} failures | types: {row.job_types}")

        # Query 7: Asset confirmation status
        print("\n\n## 7. ASSET ELIGIBILITY CHECK\n")
        result = conn.execute(text("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN confirmed THEN 1 ELSE 0 END) as confirmed,
                SUM(CASE WHEN active THEN 1 ELSE 0 END) as active,
                SUM(CASE WHEN confirmed AND active THEN 1 ELSE 0 END) as eligible
            FROM assets
        """))

        row = result.first()
        print(f"  Total assets: {row.total}")
        print(f"  Confirmed: {row.confirmed}")
        print(f"  Active: {row.active}")
        print(f"  Eligible (confirmed AND active): {row.eligible}")

        if row.eligible == 0:
            print("\n  ⚠️  WARNING: No eligible assets! Scheduler will create 0 jobs.")
        elif row.eligible < 10:
            print(f"\n  ⚠️  WARNING: Only {row.eligible}/10 expected assets eligible.")
        else:
            print(f"\n  ✓ {row.eligible} assets eligible for collection.")

    print("\n" + "=" * 80)
    print("AUDIT COMPLETE")
    print("=" * 80)

    # Summary
    print("\n### SUMMARY\n")
    print(f"- Done: {status_counts.get('done', 0)}")
    print(f"- Failed: {status_counts.get('failed', 0)}")
    print(f"- Queued: {status_counts.get('queued', 0)}")
    print(f"- Running: {status_counts.get('running', 0)}")
    print(f"\nQueued jobs eligible for immediate retry: {len([j for j in queued_jobs if 'READY' in j.eligibility])}")
    print(f"Queued jobs delayed by backoff: {len([j for j in queued_jobs if 'DELAYED' in j.eligibility])}")

if __name__ == "__main__":
    main()
