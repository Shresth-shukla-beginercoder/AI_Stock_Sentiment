"""Production job failure audit (read-only).

Run this against the Neon production database to investigate the 15 failed jobs
and 3 queued jobs reported on 2026-11-10.

Usage:
    DATABASE_URL="postgresql://..." python backend/scripts/audit_production_jobs.py
"""

import os
import sys
from datetime import datetime, timezone
from sqlalchemy import create_engine, text

def main():
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("ERROR: DATABASE_URL environment variable not set", file=sys.stderr)
        print("Usage: DATABASE_URL='postgresql://...' python scripts/audit_production_jobs.py", file=sys.stderr)
        sys.exit(1)

    engine = create_engine(db_url, echo=False)

    print("=" * 80)
    print("PRODUCTION JOB FAILURE AUDIT")
    print(f"Timestamp: {datetime.now(timezone.utc).isoformat()}")
    print("=" * 80)

    with engine.connect() as conn:
        # Query 1: Status summary
        print("\n### STATUS SUMMARY ###\n")
        result = conn.execute(text("""
            SELECT
                status,
                COUNT(*) as count,
                MIN(created_at) as oldest,
                MAX(updated_at) as newest
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
        for row in result:
            print(f"{row.status:10} | count={row.count:3} | oldest={row.oldest} | newest={row.newest}")

        # Query 2: Failed jobs by type with error samples
        print("\n### FAILED JOBS BY TYPE ###\n")
        result = conn.execute(text("""
            SELECT
                job_type,
                COUNT(*) as failed_count,
                MAX(attempts) as max_attempts_reached,
                COUNT(DISTINCT SUBSTRING(error, 1, 100)) as unique_errors
            FROM collection_jobs
            WHERE status = 'failed'
            GROUP BY job_type
            ORDER BY failed_count DESC
        """))

        failed_types = []
        for row in result:
            failed_types.append(row.job_type)
            print(f"{row.job_type:20} | failures={row.failed_count:2} | attempts={row.max_attempts_reached} | unique_errors={row.unique_errors}")

        # Query 3: Detailed error messages for each failed job type
        if failed_types:
            print("\n### FAILED JOB ERROR DETAILS ###\n")
            for job_type in failed_types:
                print(f"\n--- {job_type} ---")
                result = conn.execute(text("""
                    SELECT
                        id,
                        dedupe_key,
                        attempts,
                        SUBSTRING(error, 1, 250) as error_excerpt,
                        updated_at
                    FROM collection_jobs
                    WHERE status = 'failed' AND job_type = :job_type
                    ORDER BY updated_at DESC
                    LIMIT 3
                """), {"job_type": job_type})

                for idx, row in enumerate(result, 1):
                    print(f"\n  [{idx}] Job {row.id} | {row.dedupe_key}")
                    print(f"      Attempts: {row.attempts} | Updated: {row.updated_at}")
                    print(f"      Error: {row.error_excerpt}")

        # Query 4: Queued jobs eligibility
        print("\n\n### QUEUED JOBS (why still queued?) ###\n")
        result = conn.execute(text("""
            SELECT
                id,
                job_type,
                dedupe_key,
                attempts,
                max_attempts,
                run_after,
                SUBSTRING(error, 1, 150) as last_error,
                created_at,
                CASE
                    WHEN run_after IS NULL THEN 'READY (no delay)'
                    WHEN run_after <= NOW() THEN 'READY (delay expired)'
                    ELSE 'DELAYED (backoff until ' || run_after::text || ')'
                END as eligibility_status
            FROM collection_jobs
            WHERE status = 'queued'
            ORDER BY COALESCE(run_after, created_at)
        """))

        queued_count = 0
        for row in result:
            queued_count += 1
            print(f"\nJob {row.id} | {row.job_type}")
            print(f"  Dedupe: {row.dedupe_key}")
            print(f"  Attempts: {row.attempts}/{row.max_attempts}")
            print(f"  Created: {row.created_at}")
            print(f"  Status: {row.eligibility_status}")
            if row.last_error:
                print(f"  Last error: {row.last_error}")

        if queued_count == 0:
            print("(no queued jobs)")

        # Query 5: Failure time clustering
        print("\n\n### FAILURE TIME CLUSTERING ###\n")
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

        for row in result:
            print(f"{row.failure_hour} | {row.failures:2} failures | types: {row.job_types}")

        # Query 6: Asset eligibility check
        print("\n\n### ASSET ELIGIBILITY (confirmed assets) ###\n")
        result = conn.execute(text("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN confirmed THEN 1 ELSE 0 END) as confirmed,
                SUM(CASE WHEN active THEN 1 ELSE 0 END) as active,
                SUM(CASE WHEN confirmed AND active THEN 1 ELSE 0 END) as eligible
            FROM assets
        """))

        row = result.first()
        print(f"Total assets: {row.total}")
        print(f"Confirmed: {row.confirmed}")
        print(f"Active: {row.active}")
        print(f"Eligible (confirmed AND active): {row.eligible}")

        if row.eligible == 0:
            print("\n⚠️  WARNING: No eligible assets! Scheduler will create 0 jobs.")
        elif row.eligible < 10:
            print(f"\n⚠️  WARNING: Only {row.eligible}/10 expected assets eligible.")

    print("\n" + "=" * 80)
    print("AUDIT COMPLETE")
    print("=" * 80)

if __name__ == "__main__":
    main()
