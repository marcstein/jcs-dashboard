"""
Collections & NOIW Pipeline — PostgreSQL Multi-Tenant

Payment plan payments, outreach logging, collections holds,
and NOIW (Notice of Intent to Withdraw) tracking.
"""
import logging
from datetime import date
from typing import List, Dict, Optional

from db.connection import get_connection

logger = logging.getLogger(__name__)


COLLECTIONS_SCHEMA = """
CREATE TABLE IF NOT EXISTS payment_plan_payments (
    id SERIAL PRIMARY KEY,
    firm_id VARCHAR(36) NOT NULL,
    plan_id INTEGER NOT NULL,
    payment_id INTEGER,
    amount REAL NOT NULL,
    expected_date DATE,
    actual_date DATE,
    status TEXT DEFAULT 'pending',
    days_late INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_ppp_firm_plan ON payment_plan_payments(firm_id, plan_id);

CREATE TABLE IF NOT EXISTS outreach_log (
    id SERIAL PRIMARY KEY,
    firm_id VARCHAR(36) NOT NULL,
    contact_id INTEGER NOT NULL,
    invoice_id INTEGER,
    case_id INTEGER,
    outreach_type TEXT NOT NULL,
    outreach_method TEXT NOT NULL,
    notes TEXT,
    outcome TEXT,
    next_action TEXT,
    next_action_date DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_outreach_firm_contact ON outreach_log(firm_id, contact_id);
CREATE INDEX IF NOT EXISTS idx_outreach_firm_case ON outreach_log(firm_id, case_id);

CREATE TABLE IF NOT EXISTS collections_holds (
    id SERIAL PRIMARY KEY,
    firm_id VARCHAR(36) NOT NULL,
    case_id INTEGER NOT NULL,
    case_name TEXT,
    contact_id INTEGER,
    reason TEXT NOT NULL,
    approved_by TEXT,
    start_date DATE DEFAULT CURRENT_DATE,
    review_date DATE,
    notes TEXT,
    status TEXT DEFAULT 'active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(firm_id, case_id, status)
);
CREATE INDEX IF NOT EXISTS idx_holds_firm_status ON collections_holds(firm_id, status);

CREATE TABLE IF NOT EXISTS noiw_tracking (
    id SERIAL PRIMARY KEY,
    firm_id VARCHAR(36) NOT NULL,
    case_id INTEGER NOT NULL,
    case_name TEXT,
    contact_id INTEGER,
    contact_name TEXT,
    invoice_id INTEGER,
    balance_due REAL,
    days_delinquent INTEGER,
    status TEXT DEFAULT 'pending',
    warning_sent_date DATE,
    final_notice_date DATE,
    attorney_review_date DATE,
    resolution_date DATE,
    resolution_notes TEXT,
    assigned_to TEXT,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(firm_id, case_id, invoice_id)
);
CREATE INDEX IF NOT EXISTS idx_noiw_firm_status ON noiw_tracking(firm_id, status);
CREATE INDEX IF NOT EXISTS idx_noiw_firm_case ON noiw_tracking(firm_id, case_id);
"""


def ensure_collections_tables():
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(COLLECTIONS_SCHEMA)
    logger.info("Collections tables ensured")


# ── Payment Plan Payments ─────────────────────────────────────

def record_plan_payment(
    firm_id: str,
    plan_id: int,
    amount: float,
    expected_date: date = None,
    actual_date: date = None,
    status: str = "pending",
    payment_id: int = None,
) -> int:
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO payment_plan_payments
                (firm_id, plan_id, payment_id, amount, expected_date, actual_date, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (firm_id, plan_id, payment_id, amount, expected_date, actual_date, status),
        )
        row = cur.fetchone()
        return row["id"] if row else 0


def get_plan_payments(firm_id: str, plan_id: int) -> List[Dict]:
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT * FROM payment_plan_payments
            WHERE firm_id = %s AND plan_id = %s
            ORDER BY expected_date ASC
            """,
            (firm_id, plan_id),
        )
        return [dict(r) for r in cur.fetchall()]


def update_payment_status(
    firm_id: str, payment_id: int, status: str, actual_date: date = None, days_late: int = 0
):
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE payment_plan_payments
            SET status = %s, actual_date = %s, days_late = %s
            WHERE firm_id = %s AND id = %s
            """,
            (status, actual_date, days_late, firm_id, payment_id),
        )


# ── Outreach Log ──────────────────────────────────────────────

def log_outreach(
    firm_id: str,
    contact_id: int,
    outreach_type: str,
    outreach_method: str,
    invoice_id: int = None,
    case_id: int = None,
    notes: str = None,
    outcome: str = None,
    next_action: str = None,
    next_action_date: date = None,
) -> int:
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO outreach_log
                (firm_id, contact_id, invoice_id, case_id, outreach_type,
                 outreach_method, notes, outcome, next_action, next_action_date)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (firm_id, contact_id, invoice_id, case_id, outreach_type,
             outreach_method, notes, outcome, next_action, next_action_date),
        )
        row = cur.fetchone()
        return row["id"] if row else 0


def get_outreach_history(
    firm_id: str, contact_id: int = None, case_id: int = None, limit: int = 50
) -> List[Dict]:
    with get_connection() as conn:
        cur = conn.cursor()
        conditions = ["firm_id = %s"]
        params = [firm_id]
        if contact_id:
            conditions.append("contact_id = %s")
            params.append(contact_id)
        if case_id:
            conditions.append("case_id = %s")
            params.append(case_id)
        params.append(limit)
        cur.execute(
            f"""
            SELECT * FROM outreach_log
            WHERE {' AND '.join(conditions)}
            ORDER BY created_at DESC
            LIMIT %s
            """,
            params,
        )
        return [dict(r) for r in cur.fetchall()]


def get_pending_follow_ups(firm_id: str) -> List[Dict]:
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT * FROM outreach_log
            WHERE firm_id = %s
              AND next_action IS NOT NULL
              AND next_action_date <= CURRENT_DATE
              AND outcome IS NULL
            ORDER BY next_action_date ASC
            """,
            (firm_id,),
        )
        return [dict(r) for r in cur.fetchall()]


# ── Collections Holds ─────────────────────────────────────────

def add_collections_hold(
    firm_id: str,
    case_id: int,
    reason: str,
    case_name: str = None,
    contact_id: int = None,
    approved_by: str = None,
    review_date: date = None,
    notes: str = None,
) -> int:
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO collections_holds
                (firm_id, case_id, case_name, contact_id, reason,
                 approved_by, review_date, notes)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (firm_id, case_id, status) DO UPDATE SET
                reason = EXCLUDED.reason,
                approved_by = EXCLUDED.approved_by,
                review_date = EXCLUDED.review_date,
                notes = EXCLUDED.notes
            RETURNING id
            """,
            (firm_id, case_id, case_name, contact_id, reason,
             approved_by, review_date, notes),
        )
        row = cur.fetchone()
        return row["id"] if row else 0


def get_active_holds(firm_id: str) -> List[Dict]:
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT * FROM collections_holds
            WHERE firm_id = %s AND status = 'active'
            ORDER BY start_date DESC
            """,
            (firm_id,),
        )
        return [dict(r) for r in cur.fetchall()]


def is_case_on_hold(firm_id: str, case_id: int) -> bool:
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT 1 FROM collections_holds
            WHERE firm_id = %s AND case_id = %s AND status = 'active'
            LIMIT 1
            """,
            (firm_id, case_id),
        )
        return cur.fetchone() is not None


def release_hold(firm_id: str, case_id: int):
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE collections_holds
            SET status = 'released'
            WHERE firm_id = %s AND case_id = %s AND status = 'active'
            """,
            (firm_id, case_id),
        )


# ── NOIW Tracking ─────────────────────────────────────────────

def upsert_noiw_case(
    firm_id: str,
    case_id: int,
    invoice_id: int,
    case_name: str = None,
    contact_id: int = None,
    contact_name: str = None,
    balance_due: float = None,
    days_delinquent: int = None,
    status: str = "pending",
    assigned_to: str = None,
    notes: str = None,
) -> int:
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO noiw_tracking
                (firm_id, case_id, case_name, contact_id, contact_name,
                 invoice_id, balance_due, days_delinquent, status, assigned_to, notes)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (firm_id, case_id, invoice_id) DO UPDATE SET
                case_name = COALESCE(EXCLUDED.case_name, noiw_tracking.case_name),
                contact_name = COALESCE(EXCLUDED.contact_name, noiw_tracking.contact_name),
                balance_due = COALESCE(EXCLUDED.balance_due, noiw_tracking.balance_due),
                days_delinquent = COALESCE(EXCLUDED.days_delinquent, noiw_tracking.days_delinquent),
                status = EXCLUDED.status,
                assigned_to = COALESCE(EXCLUDED.assigned_to, noiw_tracking.assigned_to),
                updated_at = CURRENT_TIMESTAMP
            RETURNING id
            """,
            (firm_id, case_id, case_name, contact_id, contact_name,
             invoice_id, balance_due, days_delinquent, status, assigned_to, notes),
        )
        row = cur.fetchone()
        return row["id"] if row else 0


def update_noiw_status(
    firm_id: str, case_id: int, invoice_id: int, status: str, notes: str = None
):
    """Update NOIW case status and set the appropriate date field."""
    date_field = {
        "warning_sent": "warning_sent_date",
        "final_notice": "final_notice_date",
        "attorney_review": "attorney_review_date",
        "resolved": "resolution_date",
        "withdrawn": "resolution_date",
    }.get(status)

    with get_connection() as conn:
        cur = conn.cursor()
        if date_field:
            cur.execute(
                f"""
                UPDATE noiw_tracking
                SET status = %s, {date_field} = CURRENT_DATE,
                    resolution_notes = COALESCE(%s, resolution_notes),
                    updated_at = CURRENT_TIMESTAMP
                WHERE firm_id = %s AND case_id = %s AND invoice_id = %s
                """,
                (status, notes, firm_id, case_id, invoice_id),
            )
        else:
            cur.execute(
                """
                UPDATE noiw_tracking
                SET status = %s, notes = COALESCE(%s, notes),
                    updated_at = CURRENT_TIMESTAMP
                WHERE firm_id = %s AND case_id = %s AND invoice_id = %s
                """,
                (status, notes, firm_id, case_id, invoice_id),
            )


def get_noiw_pipeline(firm_id: str, status: str = None, limit: int = 100) -> List[Dict]:
    with get_connection() as conn:
        cur = conn.cursor()
        if status:
            cur.execute(
                """
                SELECT * FROM noiw_tracking
                WHERE firm_id = %s AND status = %s
                ORDER BY days_delinquent DESC
                LIMIT %s
                """,
                (firm_id, status, limit),
            )
        else:
            cur.execute(
                """
                SELECT * FROM noiw_tracking
                WHERE firm_id = %s AND status NOT IN ('resolved', 'withdrawn')
                ORDER BY days_delinquent DESC
                LIMIT %s
                """,
                (firm_id, limit),
            )
        return [dict(r) for r in cur.fetchall()]


def get_noiw_summary(firm_id: str) -> Dict:
    """Get summary counts by status."""
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT status, COUNT(*) as count, SUM(balance_due) as total_balance
            FROM noiw_tracking
            WHERE firm_id = %s
            GROUP BY status
            ORDER BY count DESC
            """,
            (firm_id,),
        )
        rows = [dict(r) for r in cur.fetchall()]
        return {
            "by_status": rows,
            "total_cases": sum(r["count"] for r in rows),
            "total_balance": sum(r["total_balance"] or 0 for r in rows),
        }
