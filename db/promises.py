"""
Payment Promise Tracking — PostgreSQL Multi-Tenant

Track client payment promises during collections calls.
"""
import logging
from datetime import date
from typing import List, Dict, Optional

from db.connection import get_connection

logger = logging.getLogger(__name__)


PROMISES_SCHEMA = """
CREATE TABLE IF NOT EXISTS payment_promises (
    id SERIAL PRIMARY KEY,
    firm_id VARCHAR(36) NOT NULL,
    contact_id INTEGER NOT NULL,
    contact_name TEXT,
    case_id INTEGER,
    case_name TEXT,
    invoice_id INTEGER,
    promised_amount REAL NOT NULL,
    promised_date DATE NOT NULL,
    actual_amount REAL,
    actual_date DATE,
    status TEXT DEFAULT 'pending',
    notes TEXT,
    recorded_by TEXT NOT NULL,
    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(firm_id, contact_id, invoice_id, promised_date)
);
CREATE INDEX IF NOT EXISTS idx_pp_status ON payment_promises(firm_id, status, promised_date);
CREATE INDEX IF NOT EXISTS idx_pp_contact ON payment_promises(firm_id, contact_id);
"""


def ensure_promises_tables():
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(PROMISES_SCHEMA)
    logger.info("Promise tables ensured")


def add_promise(
    firm_id: str,
    contact_id: int,
    promised_amount: float,
    promised_date: date,
    recorded_by: str,
    contact_name: str = None,
    case_id: int = None,
    case_name: str = None,
    invoice_id: int = None,
    notes: str = None,
) -> int:
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO payment_promises
                (firm_id, contact_id, contact_name, case_id, case_name,
                 invoice_id, promised_amount, promised_date, recorded_by, notes)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (firm_id, contact_id, contact_name, case_id, case_name,
             invoice_id, promised_amount, promised_date, recorded_by, notes),
        )
        row = cur.fetchone()
        return row["id"] if row else 0


def list_promises(firm_id: str, status: str = None) -> List[Dict]:
    with get_connection() as conn:
        cur = conn.cursor()
        if status:
            cur.execute(
                "SELECT * FROM payment_promises WHERE firm_id = %s AND status = %s ORDER BY promised_date",
                (firm_id, status),
            )
        else:
            cur.execute(
                "SELECT * FROM payment_promises WHERE firm_id = %s ORDER BY promised_date DESC",
                (firm_id,),
            )
        return [dict(r) for r in cur.fetchall()]


def get_due_today(firm_id: str) -> List[Dict]:
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM payment_promises WHERE firm_id = %s AND status = 'pending' AND promised_date = CURRENT_DATE",
            (firm_id,),
        )
        return [dict(r) for r in cur.fetchall()]


def get_overdue(firm_id: str) -> List[Dict]:
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM payment_promises WHERE firm_id = %s AND status = 'pending' AND promised_date < CURRENT_DATE",
            (firm_id,),
        )
        return [dict(r) for r in cur.fetchall()]


def mark_kept(firm_id: str, promise_id: int, actual_amount: float):
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE payment_promises
            SET status = 'kept', actual_amount = %s, actual_date = CURRENT_DATE, updated_at = CURRENT_TIMESTAMP
            WHERE firm_id = %s AND id = %s
            """,
            (actual_amount, firm_id, promise_id),
        )


def mark_broken(firm_id: str, promise_id: int):
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE payment_promises
            SET status = 'broken', updated_at = CURRENT_TIMESTAMP
            WHERE firm_id = %s AND id = %s
            """,
            (firm_id, promise_id),
        )


def get_promise_stats(firm_id: str) -> Dict:
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE status = 'kept') as kept,
                COUNT(*) FILTER (WHERE status = 'broken') as broken,
                COUNT(*) FILTER (WHERE status = 'pending') as pending,
                COALESCE(SUM(promised_amount) FILTER (WHERE status = 'kept'), 0) as kept_amount,
                COALESCE(SUM(promised_amount) FILTER (WHERE status = 'broken'), 0) as broken_amount,
                COALESCE(SUM(promised_amount) FILTER (WHERE status = 'pending'), 0) as pending_amount
            FROM payment_promises
            WHERE firm_id = %s
            """,
            (firm_id,),
        )
        row = cur.fetchone()
        result = dict(row) if row else {}
        total = result.get("total", 0)
        kept = result.get("kept", 0)
        result["keep_rate"] = round(kept / total * 100, 1) if total > 0 else 0.0
        return result
