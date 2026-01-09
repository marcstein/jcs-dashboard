"""
Database Module

SQLite database for tracking:
- Dunning notice history
- Payment tracking
- Case deadlines
- Analytics data
"""
import sqlite3
from datetime import datetime, date
from pathlib import Path
from typing import List, Dict, Optional, Any
from contextlib import contextmanager

from config import DB_FILE


class Database:
    """SQLite database wrapper for the MyCase agent."""

    def __init__(self, db_path: Path = DB_FILE):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_tables()

    @contextmanager
    def _get_connection(self):
        """Context manager for database connections."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_tables(self):
        """Initialize database tables."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Dunning notices sent
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS dunning_notices (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
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
                    UNIQUE(invoice_id, notice_level)
                )
            """)

            # Payments received (for tracking and stopping dunning)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS payments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    mycase_payment_id INTEGER UNIQUE,
                    invoice_id INTEGER NOT NULL,
                    contact_id INTEGER,
                    amount REAL NOT NULL,
                    payment_date DATE NOT NULL,
                    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    case_id INTEGER,
                    case_name TEXT,
                    attorney_id INTEGER,
                    attorney_name TEXT
                )
            """)

            # Case deadlines for tracking
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS case_deadlines (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
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
                    UNIQUE(case_id, deadline_name, deadline_date)
                )
            """)

            # Attorney notifications sent
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS attorney_notifications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    attorney_id INTEGER NOT NULL,
                    attorney_name TEXT,
                    notification_type TEXT NOT NULL,
                    case_id INTEGER,
                    case_name TEXT,
                    deadline_id INTEGER,
                    message TEXT,
                    sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    delivery_status TEXT DEFAULT 'sent'
                )
            """)

            # Invoice snapshots for analytics
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS invoice_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
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
                    UNIQUE(invoice_id, snapshot_date)
                )
            """)

            # Case stage history for milestone tracking
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS case_stage_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    case_id INTEGER NOT NULL,
                    case_name TEXT,
                    case_type TEXT,
                    stage_name TEXT NOT NULL,
                    stage_entered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    attorney_id INTEGER,
                    attorney_name TEXT
                )
            """)

            conn.commit()

    # ========== Dunning Notice Methods ==========

    def record_dunning_notice(
        self,
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
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO dunning_notices
                (invoice_id, contact_id, case_id, invoice_number, days_overdue,
                 notice_level, amount_due, template_used, sent_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (invoice_id, contact_id, case_id, invoice_number,
                  days_overdue, notice_level, amount_due, template_used))
            return cursor.lastrowid

    def get_last_dunning_level(self, invoice_id: int) -> int:
        """Get the last dunning notice level sent for an invoice."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT MAX(notice_level) as level
                FROM dunning_notices
                WHERE invoice_id = ?
            """, (invoice_id,))
            row = cursor.fetchone()
            return row["level"] if row and row["level"] else 0

    def get_dunning_history(self, invoice_id: int = None, contact_id: int = None) -> List[Dict]:
        """Get dunning notice history."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT * FROM dunning_notices WHERE 1=1"
            params = []

            if invoice_id:
                query += " AND invoice_id = ?"
                params.append(invoice_id)
            if contact_id:
                query += " AND contact_id = ?"
                params.append(contact_id)

            query += " ORDER BY sent_at DESC"
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    # ========== Payment Methods ==========

    def record_payment(
        self,
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
        """Record a payment received."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR IGNORE INTO payments
                (mycase_payment_id, invoice_id, contact_id, amount, payment_date,
                 case_id, case_name, attorney_id, attorney_name)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (mycase_payment_id, invoice_id, contact_id, amount, payment_date,
                  case_id, case_name, attorney_id, attorney_name))
            return cursor.lastrowid

    def has_payment_since_dunning(self, invoice_id: int) -> bool:
        """Check if a payment was received since the last dunning notice."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT p.id
                FROM payments p
                JOIN dunning_notices d ON p.invoice_id = d.invoice_id
                WHERE p.invoice_id = ?
                AND p.recorded_at > d.sent_at
                ORDER BY d.sent_at DESC
                LIMIT 1
            """, (invoice_id,))
            return cursor.fetchone() is not None

    # ========== Deadline Methods ==========

    def upsert_deadline(
        self,
        case_id: int,
        deadline_name: str,
        deadline_date: date,
        case_name: str = None,
        deadline_type: str = None,
        attorney_id: int = None,
        attorney_name: str = None,
    ) -> int:
        """Insert or update a case deadline."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO case_deadlines
                (case_id, case_name, deadline_name, deadline_date, deadline_type,
                 attorney_id, attorney_name, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(case_id, deadline_name, deadline_date) DO UPDATE SET
                    case_name = excluded.case_name,
                    deadline_type = excluded.deadline_type,
                    attorney_id = excluded.attorney_id,
                    attorney_name = excluded.attorney_name,
                    updated_at = CURRENT_TIMESTAMP
            """, (case_id, case_name, deadline_name, deadline_date,
                  deadline_type, attorney_id, attorney_name))
            return cursor.lastrowid

    def get_upcoming_deadlines(self, days_ahead: int = 7, attorney_id: int = None) -> List[Dict]:
        """Get deadlines coming up in the next N days."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            query = """
                SELECT * FROM case_deadlines
                WHERE deadline_date BETWEEN DATE('now') AND DATE('now', '+' || ? || ' days')
                AND notification_sent = FALSE
            """
            params = [days_ahead]

            if attorney_id:
                query += " AND attorney_id = ?"
                params.append(attorney_id)

            query += " ORDER BY deadline_date ASC"
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    def mark_deadline_notified(self, deadline_id: int) -> None:
        """Mark a deadline as having notification sent."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE case_deadlines
                SET notification_sent = TRUE, notification_sent_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (deadline_id,))

    # ========== Attorney Notification Methods ==========

    def record_attorney_notification(
        self,
        attorney_id: int,
        notification_type: str,
        attorney_name: str = None,
        case_id: int = None,
        case_name: str = None,
        deadline_id: int = None,
        message: str = None,
    ) -> int:
        """Record an attorney notification that was sent."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO attorney_notifications
                (attorney_id, attorney_name, notification_type, case_id, case_name,
                 deadline_id, message)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (attorney_id, attorney_name, notification_type, case_id,
                  case_name, deadline_id, message))
            return cursor.lastrowid

    # ========== Analytics Methods ==========

    def record_invoice_snapshot(
        self,
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
        """Record a snapshot of invoice data for analytics."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO invoice_snapshots
                (invoice_id, invoice_number, case_id, case_name, case_type,
                 contact_id, attorney_id, attorney_name, total_amount, amount_paid,
                 balance_due, invoice_date, due_date, paid_date, days_to_payment,
                 status, snapshot_date)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, DATE('now'))
            """, (invoice_id, invoice_number, case_id, case_name, case_type,
                  contact_id, attorney_id, attorney_name, total_amount, amount_paid,
                  balance_due, invoice_date, due_date, paid_date, days_to_payment, status))
            return cursor.lastrowid

    def record_case_stage_change(
        self,
        case_id: int,
        stage_name: str,
        case_name: str = None,
        case_type: str = None,
        attorney_id: int = None,
        attorney_name: str = None,
    ) -> int:
        """Record a case stage change for milestone tracking."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO case_stage_history
                (case_id, case_name, case_type, stage_name, attorney_id, attorney_name)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (case_id, case_name, case_type, stage_name, attorney_id, attorney_name))
            return cursor.lastrowid

    def get_time_to_payment_stats(
        self,
        attorney_id: int = None,
        case_type: str = None,
        start_date: date = None,
        end_date: date = None,
    ) -> Dict:
        """Get time-to-payment statistics."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            query = """
                SELECT
                    AVG(days_to_payment) as avg_days,
                    MIN(days_to_payment) as min_days,
                    MAX(days_to_payment) as max_days,
                    COUNT(*) as invoice_count,
                    SUM(total_amount) as total_billed,
                    SUM(amount_paid) as total_collected
                FROM invoice_snapshots
                WHERE days_to_payment IS NOT NULL
                AND status = 'paid'
            """
            params = []

            if attorney_id:
                query += " AND attorney_id = ?"
                params.append(attorney_id)
            if case_type:
                query += " AND case_type = ?"
                params.append(case_type)
            if start_date:
                query += " AND invoice_date >= ?"
                params.append(start_date)
            if end_date:
                query += " AND invoice_date <= ?"
                params.append(end_date)

            cursor.execute(query, params)
            row = cursor.fetchone()
            return dict(row) if row else {}

    def get_case_milestone_stats(self, case_type: str = None) -> List[Dict]:
        """Get case milestone/stage flow statistics."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            query = """
                SELECT
                    stage_name,
                    COUNT(*) as case_count,
                    AVG(julianday(stage_entered_at) - julianday(
                        (SELECT MIN(stage_entered_at) FROM case_stage_history csh2
                         WHERE csh2.case_id = case_stage_history.case_id)
                    )) as avg_days_to_reach
                FROM case_stage_history
            """
            params = []

            if case_type:
                query += " WHERE case_type = ?"
                params.append(case_type)

            query += " GROUP BY stage_name ORDER BY avg_days_to_reach"
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]


# Singleton database instance
_db_instance = None


def get_db() -> Database:
    """Get or create a singleton database instance."""
    global _db_instance
    if _db_instance is None:
        _db_instance = Database()
    return _db_instance


if __name__ == "__main__":
    # Test database
    db = get_db()
    print(f"Database initialized at: {db.db_path}")

    # Test recording a dunning notice
    notice_id = db.record_dunning_notice(
        invoice_id=1001,
        contact_id=2001,
        days_overdue=15,
        notice_level=1,
        amount_due=1500.00,
        invoice_number="INV-2024-001",
        template_used="dunning_15_day",
    )
    print(f"Recorded dunning notice: {notice_id}")

    # Test getting dunning history
    history = db.get_dunning_history(invoice_id=1001)
    print(f"Dunning history: {history}")
