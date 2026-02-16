"""
Database Migration: Add Sync Scheduling to Platform Database

Adds columns and tables needed for automated multi-tenant sync:
- sync_frequency_minutes, next_sync_at, last_sync_* columns on firms
- sync_history table for audit trail
- sync_health view (Postgres only)

Run:
    python migrate_sync_tables.py
    python migrate_sync_tables.py --check   # Dry run
"""
import sys

from platform_db import get_platform_db


PG_MIGRATIONS = [
    "ALTER TABLE firms ADD COLUMN IF NOT EXISTS sync_frequency_minutes INTEGER DEFAULT 240",
    "ALTER TABLE firms ADD COLUMN IF NOT EXISTS next_sync_at TIMESTAMPTZ",
    "ALTER TABLE firms ADD COLUMN IF NOT EXISTS last_sync_at TIMESTAMPTZ",
    "ALTER TABLE firms ADD COLUMN IF NOT EXISTS last_sync_status VARCHAR(20)",
    "ALTER TABLE firms ADD COLUMN IF NOT EXISTS last_sync_error TEXT",
    "ALTER TABLE firms ADD COLUMN IF NOT EXISTS last_sync_records INTEGER DEFAULT 0",
    "ALTER TABLE firms ADD COLUMN IF NOT EXISTS last_sync_duration_seconds REAL",

    """CREATE TABLE IF NOT EXISTS sync_history (
        id SERIAL PRIMARY KEY,
        firm_id VARCHAR(36) NOT NULL REFERENCES firms(id) ON DELETE CASCADE,
        status VARCHAR(20) NOT NULL,
        triggered_by VARCHAR(20) DEFAULT 'scheduler',
        started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        completed_at TIMESTAMPTZ,
        duration_seconds REAL,
        records_synced INTEGER DEFAULT 0,
        entity_results JSONB,
        error_message TEXT,
        celery_task_id VARCHAR(255),
        created_at TIMESTAMPTZ DEFAULT NOW()
    )""",

    "CREATE INDEX IF NOT EXISTS idx_sync_history_firm ON sync_history(firm_id)",
    "CREATE INDEX IF NOT EXISTS idx_sync_history_firm_date ON sync_history(firm_id, started_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_sync_history_status ON sync_history(status)",

    """CREATE OR REPLACE VIEW sync_health AS
    SELECT
        f.id AS firm_id,
        f.name AS firm_name,
        f.subscription_status,
        f.sync_frequency_minutes,
        f.last_sync_at,
        f.last_sync_status,
        f.last_sync_records,
        f.next_sync_at,
        f.mycase_token_expires_at,
        CASE
            WHEN f.last_sync_status = 'failed' THEN 'unhealthy'
            WHEN f.last_sync_at IS NULL THEN 'never_synced'
            WHEN f.next_sync_at < NOW() - INTERVAL '1 hour' THEN 'overdue'
            WHEN f.mycase_token_expires_at < NOW() + INTERVAL '1 hour' THEN 'token_expiring'
            ELSE 'healthy'
        END AS health_status,
        (SELECT COUNT(*) FROM sync_history sh
         WHERE sh.firm_id = f.id
         AND sh.status = 'failed'
         AND sh.started_at > NOW() - INTERVAL '24 hours'
        ) AS failures_24h
    FROM firms f
    WHERE f.subscription_status IN ('trial', 'active')
    AND f.mycase_connected = TRUE""",
]

SQLITE_MIGRATIONS = [
    """CREATE TABLE IF NOT EXISTS sync_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        firm_id TEXT NOT NULL REFERENCES firms(id),
        status TEXT NOT NULL,
        triggered_by TEXT DEFAULT 'scheduler',
        started_at TEXT NOT NULL DEFAULT (datetime('now')),
        completed_at TEXT,
        duration_seconds REAL,
        records_synced INTEGER DEFAULT 0,
        entity_results TEXT,
        error_message TEXT,
        celery_task_id TEXT,
        created_at TEXT DEFAULT (datetime('now'))
    )""",
    "CREATE INDEX IF NOT EXISTS idx_sync_history_firm ON sync_history(firm_id)",
    "CREATE INDEX IF NOT EXISTS idx_sync_history_status ON sync_history(status)",
]

SQLITE_ALTER_COLUMNS = [
    ("sync_frequency_minutes", "INTEGER DEFAULT 240"),
    ("next_sync_at", "TEXT"),
    ("last_sync_at", "TEXT"),
    ("last_sync_status", "TEXT"),
    ("last_sync_error", "TEXT"),
    ("last_sync_records", "INTEGER DEFAULT 0"),
    ("last_sync_duration_seconds", "REAL"),
]


def run_migration(check_only: bool = False):
    db = get_platform_db()

    print(f"Database backend: {'PostgreSQL' if db.use_postgres else 'SQLite'}")
    print(f"Mode: {'CHECK (dry run)' if check_only else 'APPLY'}")
    print()

    with db._get_connection() as conn:
        cursor = conn.cursor()

        if db.use_postgres:
            for i, sql in enumerate(PG_MIGRATIONS, 1):
                stmt_preview = sql.strip()[:80].replace("\n", " ")
                if check_only:
                    print(f"  [{i}/{len(PG_MIGRATIONS)}] Would run: {stmt_preview}...")
                else:
                    try:
                        cursor.execute(sql)
                        print(f"  [{i}/{len(PG_MIGRATIONS)}] OK: {stmt_preview}...")
                    except Exception as e:
                        print(f"  [{i}/{len(PG_MIGRATIONS)}] SKIP: {stmt_preview}... ({e})")
        else:
            for col_name, col_type in SQLITE_ALTER_COLUMNS:
                if check_only:
                    print(f"  Would add column: firms.{col_name} ({col_type})")
                else:
                    try:
                        cursor.execute(f"ALTER TABLE firms ADD COLUMN {col_name} {col_type}")
                        print(f"  Added column: firms.{col_name}")
                    except Exception:
                        print(f"  Column exists: firms.{col_name}")

            for i, sql in enumerate(SQLITE_MIGRATIONS, 1):
                stmt_preview = sql.strip()[:80].replace("\n", " ")
                if check_only:
                    print(f"  [{i}/{len(SQLITE_MIGRATIONS)}] Would run: {stmt_preview}...")
                else:
                    try:
                        cursor.execute(sql)
                        print(f"  [{i}/{len(SQLITE_MIGRATIONS)}] OK: {stmt_preview}...")
                    except Exception as e:
                        print(f"  [{i}/{len(SQLITE_MIGRATIONS)}] SKIP: {e}")

    print()
    if check_only:
        print("Dry run complete. Run without --check to apply.")
    else:
        print("Migration complete.")


if __name__ == "__main__":
    check = "--check" in sys.argv or "--dry-run" in sys.argv
    run_migration(check_only=check)
