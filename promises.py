"""
Payment Promise Tracking Module

Tracks client payment promises for AR collections:
- Record payment promises with expected dates
- Monitor for kept/broken promises
- Alert when promise dates pass without payment
- Integration with collections workflow
"""
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass
from enum import Enum

from database import Database, get_db


class PromiseStatus(Enum):
    """Status of a payment promise."""
    PENDING = "pending"      # Promise date not yet reached
    KEPT = "kept"           # Payment received on/before promise date
    BROKEN = "broken"       # Promise date passed, no payment
    PARTIAL = "partial"     # Some payment received, less than promised
    CANCELLED = "cancelled" # Promise cancelled by staff


@dataclass
class PaymentPromise:
    """Represents a client payment promise."""
    id: int
    contact_id: int
    contact_name: str
    case_id: Optional[int]
    case_name: Optional[str]
    invoice_id: Optional[int]
    promised_amount: float
    promised_date: date
    actual_amount: Optional[float]
    actual_date: Optional[date]
    status: PromiseStatus
    notes: Optional[str]
    recorded_by: str
    recorded_at: datetime
    days_until_due: int
    days_overdue: int


class PromiseTracker:
    """
    Tracks payment promises for collections follow-up.

    Key features:
    - Record promises during outreach calls
    - Monitor for payment on promise date
    - Alert when promises are broken
    - Track promise-keeping rate by client
    """

    def __init__(self, db: Database = None):
        self.db = db or get_db()
        self._ensure_tables()

    def _ensure_tables(self):
        """Ensure required tables exist."""
        with self.db._get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS payment_promises (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
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
                    UNIQUE(contact_id, invoice_id, promised_date)
                )
            """)

            # Index for quick lookups
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_promises_status
                ON payment_promises(status, promised_date)
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_promises_contact
                ON payment_promises(contact_id)
            """)

            conn.commit()

    # ========== Promise Recording ==========

    def record_promise(
        self,
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
        """
        Record a payment promise from a client.

        Args:
            contact_id: Client contact ID
            promised_amount: Amount client promised to pay
            promised_date: Date client promised to pay by
            recorded_by: Staff member who recorded the promise
            contact_name: Client name
            case_id: Related case ID
            case_name: Related case name
            invoice_id: Related invoice ID
            notes: Additional notes about the promise

        Returns:
            Promise ID
        """
        with self.db._get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                INSERT INTO payment_promises
                (contact_id, contact_name, case_id, case_name, invoice_id,
                 promised_amount, promised_date, status, notes, recorded_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)
            """, (contact_id, contact_name, case_id, case_name, invoice_id,
                  promised_amount, promised_date, notes, recorded_by))

            promise_id = cursor.lastrowid
            conn.commit()

            print(f"Recorded promise #{promise_id}: ${promised_amount:,.2f} by {promised_date}")
            return promise_id

    def update_promise(
        self,
        promise_id: int,
        status: PromiseStatus = None,
        actual_amount: float = None,
        actual_date: date = None,
        notes: str = None,
    ):
        """Update a promise status."""
        with self.db._get_connection() as conn:
            cursor = conn.cursor()

            updates = ["updated_at = CURRENT_TIMESTAMP"]
            params = []

            if status:
                updates.append("status = ?")
                params.append(status.value)

            if actual_amount is not None:
                updates.append("actual_amount = ?")
                params.append(actual_amount)

            if actual_date:
                updates.append("actual_date = ?")
                params.append(actual_date.isoformat())

            if notes:
                updates.append("notes = notes || ' | ' || ?")
                params.append(notes)

            params.append(promise_id)

            cursor.execute(f"""
                UPDATE payment_promises
                SET {', '.join(updates)}
                WHERE id = ?
            """, params)

            conn.commit()

    def mark_kept(self, promise_id: int, actual_amount: float, actual_date: date = None):
        """Mark a promise as kept."""
        self.update_promise(
            promise_id=promise_id,
            status=PromiseStatus.KEPT,
            actual_amount=actual_amount,
            actual_date=actual_date or date.today(),
        )

    def mark_broken(self, promise_id: int, notes: str = None):
        """Mark a promise as broken."""
        self.update_promise(
            promise_id=promise_id,
            status=PromiseStatus.BROKEN,
            notes=notes or "Promise date passed without payment",
        )

    def mark_partial(self, promise_id: int, actual_amount: float, actual_date: date = None):
        """Mark a promise as partially kept."""
        self.update_promise(
            promise_id=promise_id,
            status=PromiseStatus.PARTIAL,
            actual_amount=actual_amount,
            actual_date=actual_date or date.today(),
        )

    def cancel_promise(self, promise_id: int, reason: str):
        """Cancel a promise."""
        self.update_promise(
            promise_id=promise_id,
            status=PromiseStatus.CANCELLED,
            notes=f"Cancelled: {reason}",
        )

    # ========== Promise Retrieval ==========

    def get_promise(self, promise_id: int) -> Optional[PaymentPromise]:
        """Get a specific promise by ID."""
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM payment_promises WHERE id = ?", (promise_id,))
            row = cursor.fetchone()

            if not row:
                return None

            return self._row_to_promise(dict(row))

    def get_pending_promises(self) -> List[PaymentPromise]:
        """Get all pending promises."""
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM payment_promises
                WHERE status = 'pending'
                ORDER BY promised_date ASC
            """)

            return [self._row_to_promise(dict(row)) for row in cursor.fetchall()]

    def get_due_today(self) -> List[PaymentPromise]:
        """Get promises due today."""
        today = date.today()

        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM payment_promises
                WHERE status = 'pending'
                AND promised_date = ?
                ORDER BY promised_amount DESC
            """, (today.isoformat(),))

            return [self._row_to_promise(dict(row)) for row in cursor.fetchall()]

    def get_overdue(self) -> List[PaymentPromise]:
        """Get promises that are past their date without payment."""
        today = date.today()

        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM payment_promises
                WHERE status = 'pending'
                AND promised_date < ?
                ORDER BY promised_date ASC
            """, (today.isoformat(),))

            return [self._row_to_promise(dict(row)) for row in cursor.fetchall()]

    def get_upcoming(self, days: int = 7) -> List[PaymentPromise]:
        """Get promises coming due in the next N days."""
        today = date.today()
        end_date = today + timedelta(days=days)

        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM payment_promises
                WHERE status = 'pending'
                AND promised_date BETWEEN ? AND ?
                ORDER BY promised_date ASC
            """, (today.isoformat(), end_date.isoformat()))

            return [self._row_to_promise(dict(row)) for row in cursor.fetchall()]

    def get_by_contact(self, contact_id: int) -> List[PaymentPromise]:
        """Get all promises for a contact."""
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM payment_promises
                WHERE contact_id = ?
                ORDER BY promised_date DESC
            """, (contact_id,))

            return [self._row_to_promise(dict(row)) for row in cursor.fetchall()]

    def get_by_case(self, case_id: int) -> List[PaymentPromise]:
        """Get all promises for a case."""
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM payment_promises
                WHERE case_id = ?
                ORDER BY promised_date DESC
            """, (case_id,))

            return [self._row_to_promise(dict(row)) for row in cursor.fetchall()]

    def _row_to_promise(self, row: Dict) -> PaymentPromise:
        """Convert a database row to a PaymentPromise object."""
        today = date.today()
        promised_date = datetime.strptime(row["promised_date"], "%Y-%m-%d").date()

        days_until = (promised_date - today).days
        days_overdue = max(0, -days_until)

        actual_date = None
        if row["actual_date"]:
            actual_date = datetime.strptime(row["actual_date"], "%Y-%m-%d").date()

        recorded_at = datetime.fromisoformat(row["recorded_at"])

        return PaymentPromise(
            id=row["id"],
            contact_id=row["contact_id"],
            contact_name=row["contact_name"] or "Unknown",
            case_id=row["case_id"],
            case_name=row["case_name"],
            invoice_id=row["invoice_id"],
            promised_amount=row["promised_amount"],
            promised_date=promised_date,
            actual_amount=row["actual_amount"],
            actual_date=actual_date,
            status=PromiseStatus(row["status"]),
            notes=row["notes"],
            recorded_by=row["recorded_by"],
            recorded_at=recorded_at,
            days_until_due=max(0, days_until),
            days_overdue=days_overdue,
        )

    # ========== Promise Monitoring ==========

    def run_daily_check(self) -> Dict:
        """
        Run daily promise monitoring.

        Returns summary of:
        - Promises due today
        - Overdue promises (auto-marked as broken)
        - Upcoming promises
        """
        summary = {
            "checked_at": datetime.now().isoformat(),
            "due_today": [],
            "newly_broken": [],
            "upcoming_7_days": [],
            "stats": {},
        }

        # Get promises due today
        due_today = self.get_due_today()
        summary["due_today"] = [
            {
                "id": p.id,
                "contact_name": p.contact_name,
                "case_name": p.case_name,
                "amount": p.promised_amount,
            }
            for p in due_today
        ]

        # Find and mark broken promises (overdue > 1 day)
        overdue = self.get_overdue()
        for promise in overdue:
            if promise.days_overdue > 0:  # Give 1 day grace
                self.mark_broken(promise.id)
                summary["newly_broken"].append({
                    "id": promise.id,
                    "contact_name": promise.contact_name,
                    "case_name": promise.case_name,
                    "amount": promise.promised_amount,
                    "days_overdue": promise.days_overdue,
                })

        # Get upcoming promises
        upcoming = self.get_upcoming(days=7)
        summary["upcoming_7_days"] = [
            {
                "id": p.id,
                "contact_name": p.contact_name,
                "case_name": p.case_name,
                "amount": p.promised_amount,
                "days_until": p.days_until_due,
            }
            for p in upcoming
        ]

        # Calculate stats
        summary["stats"] = self.get_promise_stats()

        return summary

    def get_promise_stats(self, days_back: int = 30) -> Dict:
        """Get promise-keeping statistics."""
        cutoff = (date.today() - timedelta(days=days_back)).isoformat()

        with self.db._get_connection() as conn:
            cursor = conn.cursor()

            # Overall stats
            cursor.execute("""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN status = 'kept' THEN 1 ELSE 0 END) as kept,
                    SUM(CASE WHEN status = 'broken' THEN 1 ELSE 0 END) as broken,
                    SUM(CASE WHEN status = 'partial' THEN 1 ELSE 0 END) as partial,
                    SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending,
                    SUM(promised_amount) as total_promised,
                    SUM(CASE WHEN status = 'kept' THEN actual_amount ELSE 0 END) as total_collected
                FROM payment_promises
                WHERE recorded_at >= ?
            """, (cutoff,))

            row = cursor.fetchone()

            total = row["total"] or 0
            kept = row["kept"] or 0
            broken = row["broken"] or 0

            # Calculate keep rate (excluding pending)
            resolved = kept + broken + (row["partial"] or 0)
            keep_rate = (kept / resolved * 100) if resolved > 0 else 0

            return {
                "period_days": days_back,
                "total_promises": total,
                "kept": kept,
                "broken": broken,
                "partial": row["partial"] or 0,
                "pending": row["pending"] or 0,
                "keep_rate": keep_rate,
                "total_promised": row["total_promised"] or 0,
                "total_collected": row["total_collected"] or 0,
            }

    def get_contact_reliability(self, contact_id: int) -> Dict:
        """Get promise reliability for a specific contact."""
        with self.db._get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN status = 'kept' THEN 1 ELSE 0 END) as kept,
                    SUM(CASE WHEN status = 'broken' THEN 1 ELSE 0 END) as broken
                FROM payment_promises
                WHERE contact_id = ?
            """, (contact_id,))

            row = cursor.fetchone()

            total = row["total"] or 0
            kept = row["kept"] or 0
            broken = row["broken"] or 0

            resolved = kept + broken
            reliability = (kept / resolved * 100) if resolved > 0 else None

            return {
                "contact_id": contact_id,
                "total_promises": total,
                "kept": kept,
                "broken": broken,
                "reliability_pct": reliability,
                "risk_level": self._calculate_risk_level(reliability, broken),
            }

    def _calculate_risk_level(self, reliability: Optional[float], broken: int) -> str:
        """Calculate risk level based on promise history."""
        if reliability is None:
            return "unknown"
        if broken >= 3 or reliability < 50:
            return "high"
        if broken >= 1 or reliability < 75:
            return "medium"
        return "low"

    # ========== Report Generation ==========

    def generate_daily_report(self) -> str:
        """Generate daily promise tracking report."""
        check = self.run_daily_check()
        stats = check["stats"]

        report = f"""
================================================================================
                    PAYMENT PROMISE TRACKER - {date.today()}
================================================================================

SUMMARY (Last 30 Days)
  Total Promises: {stats['total_promises']}
  Keep Rate: {stats['keep_rate']:.1f}%
  Kept: {stats['kept']} | Broken: {stats['broken']} | Pending: {stats['pending']}
  Promised: ${stats['total_promised']:,.2f} | Collected: ${stats['total_collected']:,.2f}

"""

        if check["due_today"]:
            report += f"DUE TODAY ({len(check['due_today'])})\n"
            for p in check["due_today"]:
                report += f"  - {p['contact_name']}: ${p['amount']:,.2f}"
                if p['case_name']:
                    report += f" ({p['case_name']})"
                report += "\n"
            report += "\n"

        if check["newly_broken"]:
            report += f"NEWLY BROKEN ({len(check['newly_broken'])})\n"
            for p in check["newly_broken"]:
                report += f"  - {p['contact_name']}: ${p['amount']:,.2f} ({p['days_overdue']} days overdue)\n"
            report += "\n"

        if check["upcoming_7_days"]:
            report += f"UPCOMING (Next 7 Days: {len(check['upcoming_7_days'])})\n"
            for p in check["upcoming_7_days"]:
                report += f"  - {p['contact_name']}: ${p['amount']:,.2f} in {p['days_until']} days\n"

        report += """
================================================================================
"""
        return report


if __name__ == "__main__":
    tracker = PromiseTracker()

    print("Testing Promise Tracker...")

    # Record a test promise
    promise_id = tracker.record_promise(
        contact_id=12345,
        promised_amount=500.00,
        promised_date=date.today() + timedelta(days=3),
        recorded_by="Melissa",
        contact_name="Test Client",
        case_name="Test Case",
        notes="Client promised to pay by end of week",
    )

    # Get pending promises
    pending = tracker.get_pending_promises()
    print(f"\nPending Promises: {len(pending)}")

    # Run daily check
    print("\nRunning daily check...")
    check = tracker.run_daily_check()
    print(f"Due Today: {len(check['due_today'])}")
    print(f"Newly Broken: {len(check['newly_broken'])}")
    print(f"Upcoming: {len(check['upcoming_7_days'])}")

    # Generate report
    print(tracker.generate_daily_report())
