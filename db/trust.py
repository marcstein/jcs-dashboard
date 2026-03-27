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
