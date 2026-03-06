"""
db/firms.py — Unified Firms Table (Single Source of Truth)

Consolidates the two previous firms table definitions:
- db/documents.py (simple: id, name, settings)
- platform_db.py (full: subscription, OAuth, sync metadata)

All firm-specific configuration lives here. No env-var fallbacks.
Every firm gets its own row with credentials, notification config,
branding, and sync settings.
"""
import logging
from db.connection import get_connection

logger = logging.getLogger(__name__)


FIRMS_SCHEMA = """
-- =============================================================================
-- firms: Central registry for all law firms on the platform
-- =============================================================================
CREATE TABLE IF NOT EXISTS firms (
    -- Core identity
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Subscription & billing
    subscription_status VARCHAR(20) DEFAULT 'trial',
    subscription_tier VARCHAR(20) DEFAULT 'standard',
    stripe_customer_id VARCHAR(255),
    stripe_subscription_id VARCHAR(255),
    trial_ends_at TIMESTAMP,

    -- MyCase integration
    mycase_firm_id INTEGER,
    mycase_connected BOOLEAN DEFAULT FALSE,
    mycase_client_id TEXT,
    mycase_client_secret TEXT,
    mycase_oauth_token TEXT,
    mycase_oauth_refresh TEXT,
    mycase_token_expires_at TIMESTAMP,

    -- Sync configuration
    sync_frequency_minutes INTEGER DEFAULT 240,
    next_sync_at TIMESTAMP,
    last_sync_at TIMESTAMP,
    last_sync_status VARCHAR(20),
    last_sync_error TEXT,
    last_sync_records INTEGER,
    last_sync_duration_seconds REAL,

    -- Notification configuration (all channels in one JSONB column)
    notification_config JSONB DEFAULT '{}'::jsonb,

    -- Firm branding & contact
    firm_phone VARCHAR(20),
    firm_email VARCHAR(255),
    firm_website VARCHAR(255),
    logo_url TEXT,

    -- Generic settings (feature flags, schedule preferences, etc.)
    settings JSONB DEFAULT '{}'::jsonb
);

-- =============================================================================
-- sync_status: Current sync state per firm (upsert pattern)
-- =============================================================================
CREATE TABLE IF NOT EXISTS sync_status (
    firm_id TEXT PRIMARY KEY REFERENCES firms(id) ON DELETE CASCADE,
    status VARCHAR(20) DEFAULT 'pending',
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    records_synced INTEGER DEFAULT 0,
    error_message TEXT
);

-- =============================================================================
-- sync_history: Audit trail of all sync runs
-- =============================================================================
CREATE TABLE IF NOT EXISTS sync_history (
    id SERIAL PRIMARY KEY,
    firm_id TEXT REFERENCES firms(id) ON DELETE CASCADE,
    status VARCHAR(20) DEFAULT 'started',
    triggered_by VARCHAR(50) DEFAULT 'scheduler',
    celery_task_id VARCHAR(255),
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    duration_seconds REAL,
    records_synced INTEGER DEFAULT 0,
    entity_results JSONB,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =============================================================================
-- audit_log: Platform-wide action log
-- =============================================================================
CREATE TABLE IF NOT EXISTS audit_log (
    id SERIAL PRIMARY KEY,
    firm_id TEXT REFERENCES firms(id) ON DELETE CASCADE,
    user_id VARCHAR(36),
    action VARCHAR(100) NOT NULL,
    details JSONB,
    ip_address VARCHAR(45),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_firms_subscription ON firms(subscription_status);
CREATE INDEX IF NOT EXISTS idx_firms_next_sync ON firms(next_sync_at);
CREATE INDEX IF NOT EXISTS idx_sync_history_firm ON sync_history(firm_id);
CREATE INDEX IF NOT EXISTS idx_sync_history_created ON sync_history(created_at);
CREATE INDEX IF NOT EXISTS idx_audit_firm ON audit_log(firm_id);
CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_log(created_at);
"""


# Columns that may not exist on older firms tables (for migration)
_MIGRATION_COLUMNS = [
    ("subscription_status", "VARCHAR(20) DEFAULT 'trial'"),
    ("subscription_tier", "VARCHAR(20) DEFAULT 'standard'"),
    ("stripe_customer_id", "VARCHAR(255)"),
    ("stripe_subscription_id", "VARCHAR(255)"),
    ("trial_ends_at", "TIMESTAMP"),
    ("mycase_firm_id", "INTEGER"),
    ("mycase_connected", "BOOLEAN DEFAULT FALSE"),
    ("mycase_client_id", "TEXT"),
    ("mycase_client_secret", "TEXT"),
    ("mycase_oauth_token", "TEXT"),
    ("mycase_oauth_refresh", "TEXT"),
    ("mycase_token_expires_at", "TIMESTAMP"),
    ("sync_frequency_minutes", "INTEGER DEFAULT 240"),
    ("next_sync_at", "TIMESTAMP"),
    ("last_sync_at", "TIMESTAMP"),
    ("last_sync_status", "VARCHAR(20)"),
    ("last_sync_error", "TEXT"),
    ("last_sync_records", "INTEGER"),
    ("last_sync_duration_seconds", "REAL"),
    ("notification_config", "JSONB DEFAULT '{}'::jsonb"),
    ("firm_phone", "VARCHAR(20)"),
    ("firm_email", "VARCHAR(255)"),
    ("firm_website", "VARCHAR(255)"),
    ("logo_url", "TEXT"),
    ("updated_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
]


def ensure_firms_tables():
    """
    Create or migrate the firms table and supporting tables.

    Uses ALTER TABLE ADD COLUMN IF NOT EXISTS for idempotent migration
    from the old simple schema to the full unified schema.
    """
    with get_connection() as conn:
        cur = conn.cursor()

        # Create tables if they don't exist at all
        for statement in FIRMS_SCHEMA.split(";"):
            statement = statement.strip()
            if statement and not statement.startswith("--"):
                try:
                    cur.execute(statement)
                except Exception as e:
                    # Index/table may already exist
                    conn.rollback()
                    logger.debug(f"Schema statement skipped (already exists): {e}")

        # Migrate: add any missing columns to existing firms table
        for col_name, col_def in _MIGRATION_COLUMNS:
            try:
                cur.execute(f"""
                    ALTER TABLE firms ADD COLUMN IF NOT EXISTS
                    {col_name} {col_def}
                """)
            except Exception as e:
                conn.rollback()
                logger.debug(f"Column {col_name} migration skipped: {e}")

        conn.commit()
        logger.info("Firms tables ensured (unified schema)")


def get_firm(firm_id: str) -> dict:
    """Load a firm record by ID. Returns dict or None."""
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM firms WHERE id = %s", (firm_id,))
        row = cur.fetchone()
        return dict(row) if row else None


def upsert_firm(firm_id: str, name: str, **kwargs) -> dict:
    """
    Create or update a firm record.

    kwargs can include any firms table column (notification_config, firm_phone, etc.)
    """
    with get_connection() as conn:
        cur = conn.cursor()

        # Build dynamic SET clause from kwargs
        set_cols = ["name = %s", "updated_at = CURRENT_TIMESTAMP"]
        set_vals = [name]

        for key, val in kwargs.items():
            set_cols.append(f"{key} = %s")
            set_vals.append(val)

        insert_cols = ["id", "name"] + list(kwargs.keys())
        insert_placeholders = ["%s", "%s"] + ["%s"] * len(kwargs)
        insert_vals = [firm_id, name] + list(kwargs.values())

        cur.execute(f"""
            INSERT INTO firms ({', '.join(insert_cols)})
            VALUES ({', '.join(insert_placeholders)})
            ON CONFLICT (id) DO UPDATE SET {', '.join(set_cols)}
            RETURNING *
        """, insert_vals + set_vals)

        row = cur.fetchone()
        conn.commit()
        return dict(row) if row else None


def list_firms(active_only: bool = True) -> list:
    """List all firms, optionally filtering to active/trial only."""
    with get_connection() as conn:
        cur = conn.cursor()
        if active_only:
            cur.execute("""
                SELECT id, name, subscription_status, subscription_tier,
                       mycase_connected, last_sync_at, last_sync_status,
                       created_at
                FROM firms
                WHERE subscription_status IN ('trial', 'active')
                ORDER BY name
            """)
        else:
            cur.execute("""
                SELECT id, name, subscription_status, subscription_tier,
                       mycase_connected, last_sync_at, last_sync_status,
                       created_at
                FROM firms
                ORDER BY name
            """)
        return [dict(row) for row in cur.fetchall()]


def update_firm_notification_config(firm_id: str, **config_updates):
    """
    Update specific keys in a firm's notification_config JSONB.

    Example:
        update_firm_notification_config('jcs_law',
            sendgrid_api_key='SG.xxx',
            dunning_from_email='billing@jcsattorney.com')
    """
    import json
    with get_connection() as conn:
        cur = conn.cursor()
        for key, value in config_updates.items():
            cur.execute("""
                UPDATE firms
                SET notification_config = jsonb_set(
                    COALESCE(notification_config, '{}'::jsonb),
                    %s, %s::jsonb
                ),
                updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
            """, ([key], json.dumps(value), firm_id))
        conn.commit()
