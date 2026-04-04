"""
db/phone.py — Phone Integration Database Layer

Tables:
- phone_integrations: Per-firm VoIP provider config (webhooks, API keys)
- call_events: Incoming call event log (for analytics, debugging)
- phone_extensions: Extension-to-user mapping (for targeted screen pops)

Also manages the phone_normalized column on cached_clients.
"""
import logging
from datetime import datetime
from typing import Optional

from db.connection import get_connection

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

def ensure_phone_tables():
    """Create phone integration tables if they don't exist."""
    with get_connection() as conn:
        cur = conn.cursor()

        # Phone integration config per firm
        cur.execute("""
            CREATE TABLE IF NOT EXISTS phone_integrations (
                id SERIAL PRIMARY KEY,
                firm_id VARCHAR(36) NOT NULL,
                provider VARCHAR(50) NOT NULL,
                is_active BOOLEAN DEFAULT TRUE,
                webhook_secret TEXT,
                config JSONB NOT NULL DEFAULT '{}',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(firm_id, provider)
            )
        """)

        # Call event log
        cur.execute("""
            CREATE TABLE IF NOT EXISTS call_events (
                id SERIAL PRIMARY KEY,
                firm_id VARCHAR(36) NOT NULL,
                caller_number VARCHAR(30),
                caller_number_normalized VARCHAR(20),
                called_number VARCHAR(30),
                called_extension VARCHAR(20),
                matched_client_id INTEGER,
                matched_client_name TEXT,
                matched_case_count INTEGER DEFAULT 0,
                provider VARCHAR(50),
                event_type VARCHAR(50),
                raw_payload JSONB,
                pop_delivered BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_call_events_firm_date
            ON call_events(firm_id, created_at DESC)
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_call_events_caller
            ON call_events(firm_id, caller_number_normalized)
        """)

        # Extension-to-user mapping
        cur.execute("""
            CREATE TABLE IF NOT EXISTS phone_extensions (
                id SERIAL PRIMARY KEY,
                firm_id VARCHAR(36) NOT NULL,
                extension VARCHAR(20) NOT NULL,
                dashboard_username TEXT NOT NULL,
                label TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(firm_id, extension)
            )
        """)

        # Add phone_normalized column to cached_clients if not exists
        cur.execute("""
            ALTER TABLE cached_clients
            ADD COLUMN IF NOT EXISTS phone_normalized VARCHAR(20)
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_clients_phone_norm
            ON cached_clients(firm_id, phone_normalized)
        """)

        # Also index all three phone columns for multi-number lookup
        cur.execute("""
            ALTER TABLE cached_clients
            ADD COLUMN IF NOT EXISTS cell_phone_normalized VARCHAR(20),
            ADD COLUMN IF NOT EXISTS work_phone_normalized VARCHAR(20),
            ADD COLUMN IF NOT EXISTS home_phone_normalized VARCHAR(20)
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_clients_cell_norm
            ON cached_clients(firm_id, cell_phone_normalized)
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_clients_work_norm
            ON cached_clients(firm_id, work_phone_normalized)
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_clients_home_norm
            ON cached_clients(firm_id, home_phone_normalized)
        """)

        logger.info("Phone integration tables ensured")


# ---------------------------------------------------------------------------
# Phone Integrations CRUD
# ---------------------------------------------------------------------------

def get_phone_integration(firm_id: str, provider: str) -> Optional[dict]:
    """Get a firm's phone integration config for a given provider."""
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT * FROM phone_integrations
            WHERE firm_id = %s AND provider = %s
        """, (firm_id, provider))
        return dict(cur.fetchone()) if cur.rowcount else None


def get_active_integrations(firm_id: str) -> list:
    """Get all active phone integrations for a firm."""
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT * FROM phone_integrations
            WHERE firm_id = %s AND is_active = TRUE
            ORDER BY provider
        """, (firm_id,))
        return [dict(r) for r in cur.fetchall()]


def upsert_phone_integration(
    firm_id: str,
    provider: str,
    webhook_secret: str = None,
    config: dict = None,
    is_active: bool = True,
) -> int:
    """Create or update a phone integration."""
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO phone_integrations (firm_id, provider, webhook_secret, config, is_active)
            VALUES (%s, %s, %s, %s::jsonb, %s)
            ON CONFLICT (firm_id, provider) DO UPDATE SET
                webhook_secret = COALESCE(EXCLUDED.webhook_secret, phone_integrations.webhook_secret),
                config = COALESCE(EXCLUDED.config, phone_integrations.config),
                is_active = EXCLUDED.is_active,
                updated_at = CURRENT_TIMESTAMP
            RETURNING id
        """, (firm_id, provider, webhook_secret,
              __import__('json').dumps(config or {}), is_active))
        return cur.fetchone()['id']


def deactivate_integration(firm_id: str, provider: str) -> bool:
    """Deactivate a phone integration."""
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            UPDATE phone_integrations
            SET is_active = FALSE, updated_at = CURRENT_TIMESTAMP
            WHERE firm_id = %s AND provider = %s
        """, (firm_id, provider))
        return cur.rowcount > 0


# ---------------------------------------------------------------------------
# Call Events
# ---------------------------------------------------------------------------

def log_call_event(
    firm_id: str,
    caller_number: str,
    caller_number_normalized: str,
    called_number: str = None,
    called_extension: str = None,
    matched_client_id: int = None,
    matched_client_name: str = None,
    matched_case_count: int = 0,
    provider: str = None,
    event_type: str = "call.ringing",
    raw_payload: dict = None,
    pop_delivered: bool = False,
) -> int:
    """Log an incoming call event."""
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO call_events (
                firm_id, caller_number, caller_number_normalized,
                called_number, called_extension,
                matched_client_id, matched_client_name, matched_case_count,
                provider, event_type, raw_payload, pop_delivered
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s)
            RETURNING id
        """, (
            firm_id, caller_number, caller_number_normalized,
            called_number, called_extension,
            matched_client_id, matched_client_name, matched_case_count,
            provider, event_type,
            __import__('json').dumps(raw_payload) if raw_payload else None,
            pop_delivered,
        ))
        return cur.fetchone()['id']


def get_call_events(
    firm_id: str,
    limit: int = 50,
    offset: int = 0,
    matched_only: bool = False,
    unmatched_only: bool = False,
) -> list:
    """Get recent call events for a firm."""
    where = ["firm_id = %s"]
    params = [firm_id]

    if matched_only:
        where.append("matched_client_id IS NOT NULL")
    elif unmatched_only:
        where.append("matched_client_id IS NULL")

    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(f"""
            SELECT * FROM call_events
            WHERE {' AND '.join(where)}
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
        """, (*params, limit, offset))
        return [dict(r) for r in cur.fetchall()]


def get_call_stats(firm_id: str, days: int = 30) -> dict:
    """Get call event statistics for a firm."""
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT
                COUNT(*) as total_calls,
                COUNT(matched_client_id) as matched_calls,
                COUNT(*) FILTER (WHERE matched_client_id IS NULL) as unmatched_calls,
                ROUND(
                    100.0 * COUNT(matched_client_id) / NULLIF(COUNT(*), 0)::numeric,
                    1
                ) as match_rate_pct,
                COUNT(DISTINCT caller_number_normalized) as unique_callers,
                COUNT(*) FILTER (WHERE pop_delivered = TRUE) as pops_delivered
            FROM call_events
            WHERE firm_id = %s
              AND created_at >= CURRENT_TIMESTAMP - INTERVAL '1 day' * %s
        """, (firm_id, days))
        return dict(cur.fetchone())


# ---------------------------------------------------------------------------
# Phone Extensions
# ---------------------------------------------------------------------------

def get_extension_user(firm_id: str, extension: str) -> Optional[str]:
    """Get the dashboard username mapped to an extension."""
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT dashboard_username FROM phone_extensions
            WHERE firm_id = %s AND extension = %s
        """, (firm_id, extension))
        row = cur.fetchone()
        return row['dashboard_username'] if row else None


def get_all_extensions(firm_id: str) -> list:
    """Get all extension mappings for a firm."""
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT * FROM phone_extensions
            WHERE firm_id = %s ORDER BY extension
        """, (firm_id,))
        return [dict(r) for r in cur.fetchall()]


def upsert_extension(firm_id: str, extension: str, username: str, label: str = None) -> int:
    """Map an extension to a dashboard user."""
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO phone_extensions (firm_id, extension, dashboard_username, label)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (firm_id, extension) DO UPDATE SET
                dashboard_username = EXCLUDED.dashboard_username,
                label = EXCLUDED.label
            RETURNING id
        """, (firm_id, extension, username, label))
        return cur.fetchone()['id']


def delete_extension(firm_id: str, extension: str) -> bool:
    """Remove an extension mapping."""
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            DELETE FROM phone_extensions
            WHERE firm_id = %s AND extension = %s
        """, (firm_id, extension))
        return cur.rowcount > 0


# ---------------------------------------------------------------------------
# Normalized Phone Number Management
# ---------------------------------------------------------------------------

def populate_normalized_phones(firm_id: str) -> dict:
    """
    Populate phone_normalized columns on cached_clients for a firm.

    Normalizes cell_phone, work_phone, home_phone to E.164 format.
    Sets phone_normalized = cell_phone_normalized (primary for lookup).

    Returns counts of how many were updated.
    """
    from phone.normalize import normalize_phone

    with get_connection() as conn:
        cur = conn.cursor()

        # Fetch all clients with any phone number
        cur.execute("""
            SELECT id, cell_phone, work_phone, home_phone
            FROM cached_clients
            WHERE firm_id = %s
              AND (cell_phone IS NOT NULL OR work_phone IS NOT NULL OR home_phone IS NOT NULL)
        """, (firm_id,))
        clients = cur.fetchall()

        updated = 0
        for client in clients:
            cell_norm = normalize_phone(client['cell_phone']) if client['cell_phone'] else None
            work_norm = normalize_phone(client['work_phone']) if client['work_phone'] else None
            home_norm = normalize_phone(client['home_phone']) if client['home_phone'] else None

            # Primary normalized = first available: cell > work > home
            primary_norm = cell_norm or work_norm or home_norm

            cur.execute("""
                UPDATE cached_clients
                SET phone_normalized = %s,
                    cell_phone_normalized = %s,
                    work_phone_normalized = %s,
                    home_phone_normalized = %s
                WHERE id = %s AND firm_id = %s
            """, (primary_norm, cell_norm, work_norm, home_norm,
                  client['id'], firm_id))
            if cur.rowcount:
                updated += 1

        return {
            "total_clients": len(clients),
            "updated": updated,
            "firm_id": firm_id,
        }
