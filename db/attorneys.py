"""
Attorney Profiles — PostgreSQL Multi-Tenant

Attorney/firm signature block management for document generation.
"""
import logging
from typing import List, Dict, Optional

from db.connection import get_connection

logger = logging.getLogger(__name__)


ATTORNEYS_SCHEMA = """
CREATE TABLE IF NOT EXISTS attorneys (
    id SERIAL PRIMARY KEY,
    firm_id TEXT NOT NULL,
    attorney_name TEXT NOT NULL,
    bar_number TEXT,
    email TEXT,
    phone TEXT,
    fax TEXT,
    firm_name TEXT,
    firm_address TEXT,
    firm_city TEXT,
    firm_state TEXT,
    firm_zip TEXT,
    is_primary BOOLEAN DEFAULT FALSE,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(firm_id, bar_number)
);
CREATE INDEX IF NOT EXISTS idx_attorneys_firm ON attorneys(firm_id);
"""


def ensure_attorneys_tables():
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(ATTORNEYS_SCHEMA)
    logger.info("Attorneys tables ensured")


def add_attorney(
    firm_id: str,
    attorney_name: str,
    bar_number: str = None,
    email: str = None,
    phone: str = None,
    fax: str = None,
    firm_name: str = None,
    firm_address: str = None,
    firm_city: str = None,
    firm_state: str = None,
    firm_zip: str = None,
    is_primary: bool = False,
) -> int:
    with get_connection() as conn:
        cur = conn.cursor()
        # If setting as primary, clear existing primary first
        if is_primary:
            cur.execute(
                "UPDATE attorneys SET is_primary = FALSE WHERE firm_id = %s AND is_primary = TRUE",
                (firm_id,),
            )
        cur.execute(
            """
            INSERT INTO attorneys
                (firm_id, attorney_name, bar_number, email, phone, fax,
                 firm_name, firm_address, firm_city, firm_state, firm_zip, is_primary)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (firm_id, bar_number) DO UPDATE SET
                attorney_name = EXCLUDED.attorney_name,
                email = EXCLUDED.email,
                phone = EXCLUDED.phone,
                fax = EXCLUDED.fax,
                firm_name = EXCLUDED.firm_name,
                firm_address = EXCLUDED.firm_address,
                firm_city = EXCLUDED.firm_city,
                firm_state = EXCLUDED.firm_state,
                firm_zip = EXCLUDED.firm_zip,
                is_primary = EXCLUDED.is_primary,
                updated_at = CURRENT_TIMESTAMP
            RETURNING id
            """,
            (firm_id, attorney_name, bar_number, email, phone, fax,
             firm_name, firm_address, firm_city, firm_state, firm_zip, is_primary),
        )
        row = cur.fetchone()
        return row["id"] if row else 0


def get_attorney(attorney_id: int) -> Optional[Dict]:
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM attorneys WHERE id = %s", (attorney_id,))
        row = cur.fetchone()
        return dict(row) if row else None


def get_attorneys(firm_id: str, active_only: bool = True) -> List[Dict]:
    with get_connection() as conn:
        cur = conn.cursor()
        if active_only:
            cur.execute(
                """
                SELECT * FROM attorneys
                WHERE firm_id = %s AND is_active = TRUE
                ORDER BY is_primary DESC, attorney_name
                """,
                (firm_id,),
            )
        else:
            cur.execute(
                """
                SELECT * FROM attorneys
                WHERE firm_id = %s
                ORDER BY is_primary DESC, attorney_name
                """,
                (firm_id,),
            )
        return [dict(r) for r in cur.fetchall()]


def get_primary_attorney(firm_id: str) -> Optional[Dict]:
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT * FROM attorneys
            WHERE firm_id = %s AND is_primary = TRUE AND is_active = TRUE
            LIMIT 1
            """,
            (firm_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def set_primary_attorney(firm_id: str, attorney_id: int):
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE attorneys SET is_primary = FALSE WHERE firm_id = %s",
            (firm_id,),
        )
        cur.execute(
            "UPDATE attorneys SET is_primary = TRUE, updated_at = CURRENT_TIMESTAMP WHERE id = %s AND firm_id = %s",
            (attorney_id, firm_id),
        )


def update_attorney(attorney_id: int, **kwargs):
    """Update attorney fields. Only provided kwargs are updated."""
    allowed = {
        "attorney_name", "bar_number", "email", "phone", "fax",
        "firm_name", "firm_address", "firm_city", "firm_state", "firm_zip",
        "is_primary", "is_active",
    }
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return

    set_clause = ", ".join(f"{k} = %s" for k in updates)
    values = list(updates.values())
    values.append(attorney_id)

    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            f"""
            UPDATE attorneys
            SET {set_clause}, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
            """,
            values,
        )


def deactivate_attorney(firm_id: str, attorney_id: int):
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE attorneys
            SET is_active = FALSE, is_primary = FALSE, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s AND firm_id = %s
            """,
            (attorney_id, firm_id),
        )


def get_attorney_signature_block(firm_id: str, attorney_id: int = None) -> Optional[Dict]:
    """Get signature block data for document generation.
    If no attorney_id, returns the primary attorney's block."""
    attorney = None
    if attorney_id:
        attorney = get_attorney(attorney_id)
    if not attorney:
        attorney = get_primary_attorney(firm_id)
    if not attorney:
        return None

    return {
        "attorney_name": attorney["attorney_name"],
        "bar_number": attorney.get("bar_number", ""),
        "email": attorney.get("email", ""),
        "phone": attorney.get("phone", ""),
        "fax": attorney.get("fax", ""),
        "firm_name": attorney.get("firm_name", ""),
        "firm_address": attorney.get("firm_address", ""),
        "firm_city": attorney.get("firm_city", ""),
        "firm_state": attorney.get("firm_state", ""),
        "firm_zip": attorney.get("firm_zip", ""),
        "full_address": f"{attorney.get('firm_address', '')}, {attorney.get('firm_city', '')}, {attorney.get('firm_state', '')} {attorney.get('firm_zip', '')}".strip(", "),
    }
