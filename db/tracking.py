"""
Tracking & Analytics — PostgreSQL Multi-Tenant

Replaces database.py (SQLite). All tracking tables for dunning,
payments, deadlines, notifications, invoice snapshots, and stage history.

All queries scoped by firm_id.
"""
import logging
from datetime import date, datetime
from typing import List, Dict, Optional

from db.connection import get_connection

logger = logging.getLogger(__name__)


# ============================================================
# Schema
# ============================================================

TRACKING_SCHEMA = """
CREATE TABLE IF NOT EXISTS dunning_notices (
    id SERIAL PRIMARY KEY,
    firm_id VARCHAR(36) NOT NULL,
    invoice_id INTEGER NOT NULL,
    contact_id INTEGER NOT NULL,
    case_id INTEGER,
    invoice_number TEXT,
    days_overdue INTEGER NOT NULL,
    notice_level INTEGER NOT NULL,
    amount_due REAL NOT NULL,
    sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    template_used TEXT,
    delivery_method TEXT DEFAULT 'email',
    delivery_status TEXT DEFAULT 'sent',
    UNIQUE(firm_id, invoice_id, notice_level)
);
CREATE INDEX IF NOT EXISTS idx_dn_firm ON dunning_notices(firm_id);

CREATE TABLE IF NOT EXISTS payments (
    id SERIAL PRIMARY KEY,
    firm_id VARCHAR(36) NOT NULL,
    mycase_payment_id INTEGER,
    invoice_id INTEGER NOT NULL,
    contact_id INTEGER,
    amount REAL NOT NULL,
    payment_date DATE NOT NULL,
    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    case_id INTEGER,
    case_name TEXT,
    attorney_id INTEGER,
    attorney_name TEXT,
    UNIQUE(firm_id, mycase_payment_id)
);
CREATE INDEX IF NOT EXISTS idx_pay_firm ON payments(firm_id);

CREATE TABLE IF NOT EXISTS case_deadlines (
    id SERIAL PRIMARY KEY,
    firm_id VARCHAR(36) NOT NULL,
    case_id INTEGER NOT NULL,
    case_name TEXT,
    deadline_name TEXT NOT NULL,
    deadline_date DATE NOT NULL,
    deadline_type TEXT,
    attorney_id INTEGER,
    attorney_name TEXT,
    notification_sent BOOLEAN DEFAULT FALSE,
    notification_sent_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(firm_id, case_id, deadline_name, deadline_date)
);
CREATE INDEX IF NOT EXISTS idx_cd_firm ON case_deadlines(firm_id);
CREATE INDEX IF NOT EXISTS idx_cd_date ON case_deadlines(firm_id, deadline_date);

CREATE TABLE IF NOT EXISTS attorney_notifications (
    id SERIAL PRIMARY KEY,
    firm_id VARCHAR(36) NOT NULL,
    attorney_id INTEGER NOT NULL,
    attorney_name TEXT,
    notification_type TEXT NOT NULL,
    case_id INTEGER,
    case_name TEXT,
    deadline_id INTEGER,
    message TEXT,
    sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    delivery_status TEXT DEFAULT 'sent'
);
CREATE INDEX IF NOT EXISTS idx_an_firm ON attorney_notifications(firm_id);

CREATE TABLE IF NOT EXISTS invoice_snapshots (
    id SERIAL PRIMARY KEY,
    firm_id VARCHAR(36) NOT NULL,
    invoice_id INTEGER NOT NULL,
    invoice_number TEXT,
    case_id INTEGER,
    case_name TEXT,
    case_type TEXT,
    contact_id INTEGER,
    attorney_id INTEGER,
    attorney_name TEXT,
    total_amount REAL,
    amount_paid REAL,
    balance_due REAL,
    invoice_date DATE,
    due_date DATE,
    paid_date DATE,
    days_to_payment INTEGER,
    status TEXT,
    snapshot_date DATE DEFAULT CURRENT_DATE,
    UNIQUE(firm_id, invoice_id, snapshot_date)
);
CREATE INDEX IF NOT EXISTS idx_is_firm ON invoice_snapshots(firm_id);

CREATE TABLE IF NOT EXISTS case_stage_history (
    id SERIAL PRIMARY KEY,
    firm_id VARCHAR(36) NOT NULL,
    case_id INTEGER NOT NULL,
    case_name TEXT,
    case_type TEXT,
    stage_name TEXT NOT NULL,
    stage_entered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    attorney_id INTEGER,
    attorney_name TEXT
);
CREATE INDEX IF NOT EXISTS idx_csh_firm ON case_stage_history(firm_id);
CREATE INDEX IF NOT EXISTS idx_csh_case ON case_stage_history(firm_id, case_id);
"""


def ensure_tracking_tables():
    """Create tracking tables if they don't exist."""
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(TRACKING_SCHEMA)
    logger.info("Tracking tables ensured")


# ============================================================
# Dunning Notices
# ============================================================

def record_dunning_notice(
    firm_id: str,
    invoice_id: int,
    contact_id: int,
    days_overdue: int,
    notice_level: int,
    amount_due: float,
    invoice_number: str = None,
    case_id: int = None,
    template_used: str = None,
) -> int:
    """Record a dunning notice that was sent."""
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO dunning_notices
                (firm_id, invoice_id, contact_id, case_id, invoice_number,
                 days_overdue, notice_level, amount_due, template_used, sent_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (firm_id, invoice_id, notice_level) DO UPDATE SET
                days_overdue = EXCLUDED.days_overdue,
                amount_due = EXCLUDED.amount_due,
                template_used = EXCLUDED.template_used,
                sent_at = CURRENT_TIMESTAMP
            RETURNING id
            """,
            (firm_id, invoice_id, contact_id, case_id, invoice_number,
             days_overdue, notice_level, amount_due, template_used),
        )
        row = cur.fetchone()
        return row["id"] if row else 0


def get_last_dunning_level(firm_id: str, invoice_id: int) -> int:
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT MAX(notice_level) as level FROM dunning_notices WHERE firm_id = %s AND invoice_id = %s",
            (firm_id, invoice_id),
        )
        row = cur.fetchone()
        return row["level"] if row and row["level"] else 0


def get_dunning_history(firm_id: str, invoice_id: int = None, contact_id: int = None) -> List[Dict]:
    with get_connection() as conn:
        cur = conn.cursor()
        query = "SELECT * FROM dunning_notices WHERE firm_id = %s"
        params: list = [firm_id]
        if invoice_id:
            query += " AND invoice_id = %s"
            params.append(invoice_id)
        if contact_id:
            query += " AND contact_id = %s"
            params.append(contact_id)
        query += " ORDER BY sent_at DESC"
        cur.execute(query, params)
        return [dict(r) for r in cur.fetchall()]


# ============================================================
# Payments
# ============================================================

def record_payment(
    firm_id: str,
    mycase_payment_id: int,
    invoice_id: int,
    amount: float,
    payment_date: date,
    contact_id: int = None,
    case_id: int = None,
    case_name: str = None,
    attorney_id: int = None,
    attorney_name: str = None,
) -> int:
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO payments
                (firm_id, mycase_payment_id, invoice_id, contact_id, amount,
                 payment_date, case_id, case_name, attorney_id, attorney_name)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (firm_id, mycase_payment_id) DO NOTHING
            RETURNING id
            """,
            (firm_id, mycase_payment_id, invoice_id, contact_id, amount,
             payment_date, case_id, case_name, attorney_id, attorney_name),
        )
        row = cur.fetchone()
        return row["id"] if row else 0


def has_payment_since_dunning(firm_id: str, invoice_id: int) -> bool:
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT p.id FROM payments p
            JOIN dunning_notices d ON p.invoice_id = d.invoice_id AND p.firm_id = d.firm_id
            WHERE p.firm_id = %s AND p.invoice_id = %s AND p.recorded_at > d.sent_at
            ORDER BY d.sent_at DESC LIMIT 1
            """,
            (firm_id, invoice_id),
        )
        return cur.fetchone() is not None


# ============================================================
# Deadlines
# ============================================================

def upsert_deadline(
    firm_id: str,
    case_id: int,
    deadline_name: str,
    deadline_date: date,
    case_name: str = None,
    deadline_type: str = None,
    attorney_id: int = None,
    attorney_name: str = None,
) -> int:
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO case_deadlines
                (firm_id, case_id, case_name, deadline_name, deadline_date,
                 deadline_type, attorney_id, attorney_name, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (firm_id, case_id, deadline_name, deadline_date) DO UPDATE SET
                case_name = EXCLUDED.case_name,
                deadline_type = EXCLUDED.deadline_type,
                attorney_id = EXCLUDED.attorney_id,
                attorney_name = EXCLUDED.attorney_name,
                updated_at = CURRENT_TIMESTAMP
            RETURNING id
            """,
            (firm_id, case_id, case_name, deadline_name, deadline_date,
             deadline_type, attorney_id, attorney_name),
        )
        row = cur.fetchone()
        return row["id"] if row else 0


def get_upcoming_deadlines(firm_id: str, days_ahead: int = 7, attorney_id: int = None) -> List[Dict]:
    with get_connection() as conn:
        cur = conn.cursor()
        query = """
            SELECT * FROM case_deadlines
            WHERE firm_id = %s
              AND deadline_date BETWEEN CURRENT_DATE AND CURRENT_DATE + %s * INTERVAL '1 day'
              AND notification_sent = FALSE
        """
        params: list = [firm_id, days_ahead]
        if attorney_id:
            query += " AND attorney_id = %s"
            params.append(attorney_id)
        query += " ORDER BY deadline_date ASC"
        cur.execute(query, params)
        return [dict(r) for r in cur.fetchall()]


def mark_deadline_notified(firm_id: str, deadline_id: int):
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE case_deadlines
            SET notification_sent = TRUE, notification_sent_at = CURRENT_TIMESTAMP
            WHERE firm_id = %s AND id = %s
            """,
            (firm_id, deadline_id),
        )


# ============================================================
# Attorney Notifications
# ============================================================

def record_attorney_notification(
    firm_id: str,
    attorney_id: int,
    notification_type: str,
    attorney_name: str = None,
    case_id: int = None,
    case_name: str = None,
    deadline_id: int = None,
    message: str = None,
) -> int:
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO attorney_notifications
                (firm_id, attorney_id, attorney_name, notification_type,
                 case_id, case_name, deadline_id, message)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (firm_id, attorney_id, attorney_name, notification_type,
             case_id, case_name, deadline_id, message),
        )
        row = cur.fetchone()
        return row["id"] if row else 0


# ============================================================
# Invoice Snapshots / Analytics
# ============================================================

def record_invoice_snapshot(
    firm_id: str,
    invoice_id: int,
    invoice_number: str = None,
    case_id: int = None,
    case_name: str = None,
    case_type: str = None,
    contact_id: int = None,
    attorney_id: int = None,
    attorney_name: str = None,
    total_amount: float = None,
    amount_paid: float = None,
    balance_due: float = None,
    invoice_date: date = None,
    due_date: date = None,
    paid_date: date = None,
    days_to_payment: int = None,
    status: str = None,
) -> int:
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO invoice_snapshots
                (firm_id, invoice_id, invoice_number, case_id, case_name, case_type,
                 contact_id, attorney_id, attorney_name, total_amount, amount_paid,
                 balance_due, invoice_date, due_date, paid_date, days_to_payment,
                 status, snapshot_date)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_DATE)
            ON CONFLICT (firm_id, invoice_id, snapshot_date) DO UPDATE SET
                total_amount = EXCLUDED.total_amount,
                amount_paid = EXCLUDED.amount_paid,
                balance_due = EXCLUDED.balance_due,
                status = EXCLUDED.status,
                days_to_payment = EXCLUDED.days_to_payment,
                paid_date = EXCLUDED.paid_date
            RETURNING id
            """,
            (firm_id, invoice_id, invoice_number, case_id, case_name, case_type,
             contact_id, attorney_id, attorney_name, total_amount, amount_paid,
             balance_due, invoice_date, due_date, paid_date, days_to_payment, status),
        )
        row = cur.fetchone()
        return row["id"] if row else 0


def record_case_stage_change(
    firm_id: str,
    case_id: int,
    stage_name: str,
    case_name: str = None,
    case_type: str = None,
    attorney_id: int = None,
    attorney_name: str = None,
) -> int:
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO case_stage_history
                (firm_id, case_id, case_name, case_type, stage_name, attorney_id, attorney_name)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (firm_id, case_id, case_name, case_type, stage_name, attorney_id, attorney_name),
        )
        row = cur.fetchone()
        return row["id"] if row else 0


def get_time_to_payment_stats(
    firm_id: str,
    attorney_id: int = None,
    case_type: str = None,
    start_date: date = None,
    end_date: date = None,
) -> Dict:
    with get_connection() as conn:
        cur = conn.cursor()
        query = """
            SELECT
                AVG(days_to_payment) as avg_days,
                MIN(days_to_payment) as min_days,
                MAX(days_to_payment) as max_days,
                COUNT(*) as invoice_count,
                SUM(total_amount) as total_billed,
                SUM(amount_paid) as total_collected
            FROM invoice_snapshots
            WHERE firm_id = %s AND days_to_payment IS NOT NULL AND status = 'paid'
        """
        params: list = [firm_id]
        if attorney_id:
            query += " AND attorney_id = %s"
            params.append(attorney_id)
        if case_type:
            query += " AND case_type = %s"
            params.append(case_type)
        if start_date:
            query += " AND invoice_date >= %s"
            params.append(start_date)
        if end_date:
            query += " AND invoice_date <= %s"
            params.append(end_date)
        cur.execute(query, params)
        row = cur.fetchone()
        return dict(row) if row else {}


def get_case_milestone_stats(firm_id: str, case_type: str = None) -> List[Dict]:
    with get_connection() as conn:
        cur = conn.cursor()
        query = """
            SELECT
                stage_name,
                COUNT(*) as case_count,
                AVG(EXTRACT(EPOCH FROM (stage_entered_at -
                    (SELECT MIN(stage_entered_at) FROM case_stage_history csh2
                     WHERE csh2.firm_id = case_stage_history.firm_id
                       AND csh2.case_id = case_stage_history.case_id)
                )) / 86400.0) as avg_days_to_reach
            FROM case_stage_history
            WHERE firm_id = %s
        """
        params: list = [firm_id]
        if case_type:
            query += " AND case_type = %s"
            params.append(case_type)
        query += " GROUP BY stage_name ORDER BY avg_days_to_reach"
        cur.execute(query, params)
        return [dict(r) for r in cur.fetchall()]
