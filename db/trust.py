"""
Trust Transfer — PostgreSQL Multi-Tenant

Fee schedule storage and queries for phase-based trust-to-operating
transfer reports.
"""
import json
import logging
from typing import List, Dict, Optional

from db.connection import get_connection

logger = logging.getLogger(__name__)


TRUST_SCHEMA = """
CREATE TABLE IF NOT EXISTS trust_fee_schedules (
    id SERIAL PRIMARY KEY,
    firm_id VARCHAR(36) NOT NULL,
    schedule_key TEXT NOT NULL,
    label TEXT NOT NULL,
    case_type_patterns TEXT NOT NULL DEFAULT '[]',
    phase_percentages JSONB NOT NULL DEFAULT '{}',
    is_default BOOLEAN DEFAULT FALSE,
    display_order INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(firm_id, schedule_key)
);

CREATE INDEX IF NOT EXISTS idx_tfs_firm ON trust_fee_schedules(firm_id);

-- Trust ledger uploads: batch-based CSV uploads of trust account balances
CREATE TABLE IF NOT EXISTS trust_ledger_uploads (
    id SERIAL PRIMARY KEY,
    firm_id VARCHAR(36) NOT NULL,
    upload_batch_id VARCHAR(36) NOT NULL,
    case_id INTEGER,
    case_number TEXT,
    case_name TEXT,
    client_name TEXT,
    trust_balance NUMERIC(12, 2),
    match_method TEXT,
    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_tlu_firm ON trust_ledger_uploads(firm_id);
CREATE INDEX IF NOT EXISTS idx_tlu_batch ON trust_ledger_uploads(upload_batch_id);
CREATE INDEX IF NOT EXISTS idx_tlu_case ON trust_ledger_uploads(firm_id, case_id);

-- Trust transfer confirmations: records when transfers were confirmed
CREATE TABLE IF NOT EXISTS trust_transfers (
    id SERIAL PRIMARY KEY,
    firm_id VARCHAR(36) NOT NULL,
    batch_id VARCHAR(36) NOT NULL,
    case_id INTEGER NOT NULL,
    case_name TEXT,
    transfer_amount NUMERIC(12, 2) NOT NULL,
    trust_balance_before NUMERIC(12, 2),
    confirmed_by TEXT,
    confirmed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    source_upload_batch_id VARCHAR(36),
    notes TEXT
);

CREATE INDEX IF NOT EXISTS idx_tt_firm ON trust_transfers(firm_id);
CREATE INDEX IF NOT EXISTS idx_tt_batch ON trust_transfers(batch_id);
CREATE INDEX IF NOT EXISTS idx_tt_case ON trust_transfers(firm_id, case_id);
"""


def ensure_trust_tables():
    """Create trust tables if they don't exist."""
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(TRUST_SCHEMA)
        conn.commit()
    logger.info("Trust tables ensured")


# =============================================================================
# Fee Schedule CRUD
# =============================================================================

def get_fee_schedules(firm_id: str) -> List[Dict]:
    """Get all fee schedules for a firm, ordered by display_order."""
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT id, firm_id, schedule_key, label, case_type_patterns,
                   phase_percentages, is_default, display_order
            FROM trust_fee_schedules
            WHERE firm_id = %s
            ORDER BY display_order, schedule_key
        """, (firm_id,))
        rows = cur.fetchall()

    schedules = []
    for row in rows:
        row = dict(row)
        # Parse JSON fields
        if isinstance(row["case_type_patterns"], str):
            row["case_type_patterns"] = json.loads(row["case_type_patterns"])
        if isinstance(row["phase_percentages"], str):
            row["phase_percentages"] = json.loads(row["phase_percentages"])
        schedules.append(row)
    return schedules


def get_fee_schedule(firm_id: str, schedule_key: str) -> Optional[Dict]:
    """Get a single fee schedule by key."""
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT id, firm_id, schedule_key, label, case_type_patterns,
                   phase_percentages, is_default, display_order
            FROM trust_fee_schedules
            WHERE firm_id = %s AND schedule_key = %s
        """, (firm_id, schedule_key))
        row = cur.fetchone()

    if not row:
        return None
    row = dict(row)
    if isinstance(row["case_type_patterns"], str):
        row["case_type_patterns"] = json.loads(row["case_type_patterns"])
    if isinstance(row["phase_percentages"], str):
        row["phase_percentages"] = json.loads(row["phase_percentages"])
    return row


def upsert_fee_schedule(firm_id: str, schedule_key: str, label: str,
                        case_type_patterns: List[str], phase_percentages: Dict[str, int],
                        is_default: bool = False, display_order: int = 0) -> int:
    """Insert or update a fee schedule. Returns the schedule id."""
    patterns_json = json.dumps(case_type_patterns)
    phases_json = json.dumps(phase_percentages)

    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO trust_fee_schedules
                (firm_id, schedule_key, label, case_type_patterns, phase_percentages,
                 is_default, display_order, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (firm_id, schedule_key) DO UPDATE SET
                label = EXCLUDED.label,
                case_type_patterns = EXCLUDED.case_type_patterns,
                phase_percentages = EXCLUDED.phase_percentages,
                is_default = EXCLUDED.is_default,
                display_order = EXCLUDED.display_order,
                updated_at = CURRENT_TIMESTAMP
            RETURNING id
        """, (firm_id, schedule_key, label, patterns_json, phases_json,
              is_default, display_order))
        row = cur.fetchone()
        conn.commit()
        return dict(row)["id"]


def delete_fee_schedule(firm_id: str, schedule_key: str) -> bool:
    """Delete a fee schedule. Returns True if deleted."""
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            DELETE FROM trust_fee_schedules
            WHERE firm_id = %s AND schedule_key = %s
        """, (firm_id, schedule_key))
        conn.commit()
        return cur.rowcount > 0


def seed_default_schedules(firm_id: str) -> int:
    """Seed the default fee schedules for a firm. Returns count of schedules created."""
    from trust_transfer import _HARDCODED_SCHEDULES, _HARDCODED_DEFAULT

    count = 0
    for idx, (key, schedule) in enumerate(_HARDCODED_SCHEDULES.items()):
        upsert_fee_schedule(
            firm_id=firm_id,
            schedule_key=key,
            label=schedule["label"],
            case_type_patterns=schedule["case_type_patterns"],
            phase_percentages=schedule["phases"],
            is_default=False,
            display_order=idx + 1,
        )
        count += 1

    # Seed the default/fallback schedule
    upsert_fee_schedule(
        firm_id=firm_id,
        schedule_key="_default",
        label=_HARDCODED_DEFAULT["label"],
        case_type_patterns=[],
        phase_percentages=_HARDCODED_DEFAULT["phases"],
        is_default=True,
        display_order=99,
    )
    count += 1

    logger.info(f"Seeded {count} fee schedules for firm {firm_id}")
    return count


# =============================================================================
# Trust Ledger Uploads
# =============================================================================

def get_latest_trust_balances(firm_id: str) -> Dict:
    """
    Get trust balances from the latest upload batch.
    Returns dict keyed by case_id -> {trust_balance, case_name, client_name, match_method}.
    """
    with get_connection() as conn:
        cur = conn.cursor()
        # Find latest batch
        cur.execute("""
            SELECT upload_batch_id
            FROM trust_ledger_uploads
            WHERE firm_id = %s
            GROUP BY upload_batch_id
            ORDER BY MIN(uploaded_at) DESC
            LIMIT 1
        """, (firm_id,))
        row = cur.fetchone()
        if not row:
            return {}

        batch_id = dict(row)["upload_batch_id"]

        cur.execute("""
            SELECT case_id, case_name, client_name, trust_balance, match_method
            FROM trust_ledger_uploads
            WHERE firm_id = %s AND upload_batch_id = %s AND case_id IS NOT NULL
        """, (firm_id, batch_id))

        balances = {}
        for r in cur.fetchall():
            r = dict(r)
            balances[r["case_id"]] = {
                "trust_balance": float(r["trust_balance"]) if r["trust_balance"] else 0,
                "case_name": r["case_name"],
                "client_name": r["client_name"],
                "match_method": r["match_method"],
            }
        return balances


def get_trust_upload_history(firm_id: str, limit: int = 10) -> List[Dict]:
    """Get recent trust ledger upload history."""
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT upload_batch_id,
                   COUNT(*) as total_rows,
                   COUNT(case_id) as matched_rows,
                   SUM(trust_balance) as total_balance,
                   MIN(uploaded_at) as uploaded_at
            FROM trust_ledger_uploads
            WHERE firm_id = %s
            GROUP BY upload_batch_id
            ORDER BY MIN(uploaded_at) DESC
            LIMIT %s
        """, (firm_id, limit))
        return [dict(r) for r in cur.fetchall()]


def get_latest_upload_batch_id(firm_id: str) -> Optional[str]:
    """Get the batch_id of the most recent trust ledger upload."""
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT upload_batch_id
            FROM trust_ledger_uploads
            WHERE firm_id = %s
            GROUP BY upload_batch_id
            ORDER BY MIN(uploaded_at) DESC
            LIMIT 1
        """, (firm_id,))
        row = cur.fetchone()
        return dict(row)["upload_batch_id"] if row else None


# =============================================================================
# Trust Transfer Confirmations
# =============================================================================

def record_transfer_batch(firm_id: str, transfers: List[Dict],
                          confirmed_by: str, source_upload_batch_id: str = None) -> str:
    """
    Record a batch of confirmed transfers.
    Each transfer dict: {case_id, case_name, transfer_amount, trust_balance_before}
    Returns the batch_id.
    """
    import uuid
    batch_id = str(uuid.uuid4())

    with get_connection() as conn:
        cur = conn.cursor()
        for t in transfers:
            cur.execute("""
                INSERT INTO trust_transfers
                    (firm_id, batch_id, case_id, case_name, transfer_amount,
                     trust_balance_before, confirmed_by, source_upload_batch_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                firm_id, batch_id, t["case_id"], t.get("case_name", ""),
                t["transfer_amount"], t.get("trust_balance_before"),
                confirmed_by, source_upload_batch_id,
            ))
        conn.commit()

    logger.info(f"Recorded {len(transfers)} transfers in batch {batch_id} for firm {firm_id}")
    return batch_id


def get_transfer_history(firm_id: str, limit: int = 10) -> List[Dict]:
    """Get recent transfer confirmation batches."""
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT batch_id,
                   COUNT(*) as case_count,
                   SUM(transfer_amount) as total_transferred,
                   confirmed_by,
                   MIN(confirmed_at) as confirmed_at
            FROM trust_transfers
            WHERE firm_id = %s
            GROUP BY batch_id, confirmed_by
            ORDER BY MIN(confirmed_at) DESC
            LIMIT %s
        """, (firm_id, limit))
        return [dict(r) for r in cur.fetchall()]
