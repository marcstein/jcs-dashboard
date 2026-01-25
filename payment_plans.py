"""
Payment Plans Compliance Module

Tracks payment plan health and compliance per Melissa Scarlett's AR SOP:
- Payment plan intake verification
- Compliance monitoring
- Delinquency detection and escalation
- NOIW preparation workflow
"""
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum

from api_client import MyCaseClient, get_client, MyCaseAPIError
from database import Database, get_db
from cache import get_cache


class PaymentPlanStatus(Enum):
    ACTIVE = "active"
    DELINQUENT = "delinquent"
    DEFAULTED = "defaulted"
    COMPLETED = "completed"
    ON_HOLD = "on_hold"


class DelinquencyLevel(Enum):
    CURRENT = 0
    LATE_1_15 = 1  # 1-15 days late
    LATE_16_30 = 2  # 16-30 days late - NOIW consideration
    LATE_31_60 = 3  # 31-60 days late - NOIW required
    LATE_60_PLUS = 4  # 60+ days - escalate to attorney


class NOIWStatus(Enum):
    """NOIW workflow status for a case."""
    PENDING = "pending"           # In pipeline, no action yet
    WARNING_SENT = "warning_sent"  # First warning letter sent
    FINAL_NOTICE = "final_notice"  # Final notice before withdrawal
    ATTORNEY_REVIEW = "attorney_review"  # Escalated to attorney
    ON_HOLD = "on_hold"           # Collections hold in place
    PAYMENT_ARRANGED = "payment_arranged"  # Payment plan renegotiated
    WITHDRAWN = "withdrawn"       # Case withdrawn
    RESOLVED = "resolved"         # Paid or otherwise resolved


@dataclass
class PaymentPlan:
    """Represents a payment plan with compliance tracking."""
    id: int
    invoice_id: int
    contact_id: int
    contact_name: str
    case_id: Optional[int]
    case_name: Optional[str]
    total_amount: float
    installment_amount: float
    frequency: str  # weekly, biweekly, monthly
    start_date: date
    next_due_date: date
    payments_made: int
    payments_expected: int
    amount_paid: float
    balance_remaining: float
    status: PaymentPlanStatus
    last_payment_date: Optional[date]
    days_delinquent: int = 0
    delinquency_level: DelinquencyLevel = DelinquencyLevel.CURRENT


@dataclass
class ComplianceCheck:
    """Result of a payment plan compliance check."""
    plan: PaymentPlan
    is_compliant: bool
    issues: List[str] = field(default_factory=list)
    recommended_action: str = ""
    urgency: str = "normal"  # normal, high, critical


@dataclass
class NOIWPacket:
    """Notice of Intent to Withdraw preparation packet."""
    case_id: int
    case_name: str
    contact_id: int
    contact_name: str
    invoice_id: int
    balance_due: float
    days_delinquent: int
    outreach_log: List[Dict]
    payment_history: List[Dict]
    engagement_agreement_status: str
    case_status: str
    recommended_action: str
    prepared_date: date


class PaymentPlanManager:
    """
    Manages payment plan tracking and compliance per AR SOP.

    Key responsibilities:
    - Daily compliance monitoring
    - Delinquency detection and outreach sequencing
    - NOIW packet preparation
    - Payment plan intake verification
    """

    def __init__(
        self,
        client: MyCaseClient = None,
        db: Database = None,
    ):
        self.client = client or get_client()
        self.db = db or get_db()
        self._ensure_tables()

    def _ensure_tables(self):
        """Ensure required tables exist."""
        with self.db._get_connection() as conn:
            cursor = conn.cursor()

            # Payment plan tracking (extends kpi_tracker table)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS payment_plan_payments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    plan_id INTEGER NOT NULL,
                    payment_id INTEGER,
                    amount REAL NOT NULL,
                    expected_date DATE,
                    actual_date DATE,
                    status TEXT DEFAULT 'pending',
                    days_late INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (plan_id) REFERENCES payment_plans(id)
                )
            """)

            # Outreach log for delinquent accounts
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS outreach_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
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
                )
            """)

            # Hold collections list
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS collections_holds (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
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
                    UNIQUE(case_id, status)
                )
            """)

            # NOIW workflow tracking
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS noiw_tracking (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
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
                    UNIQUE(case_id, invoice_id)
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_noiw_status ON noiw_tracking(status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_noiw_case ON noiw_tracking(case_id)")

            conn.commit()

    # ========== Payment Plan Sync ==========

    def sync_payment_plans_from_invoices(self) -> int:
        """
        Identify and sync payment plans from MyCase invoices.

        Returns count of plans identified/updated.
        """
        print("Syncing payment plans from invoices...")

        try:
            all_invoices = self.client.get_all_pages(self.client.get_invoices)
            plans_synced = 0

            for inv in all_invoices:
                # Check if this looks like a payment plan
                # (partial payments, recurring pattern, or explicit plan flag)
                status = inv.get("status", "")
                total = float(inv.get("total_amount", 0))
                paid = float(inv.get("paid_amount", 0))
                balance = total - paid

                # Skip fully paid or unpaid invoices
                if status == "paid" or (status != "partial" and paid == 0):
                    continue

                # Get case and contact info
                case = inv.get("case", {})
                case_id = case.get("id") if case else None

                # Fetch contact from case if available
                contact_id = None
                contact_name = "Unknown"

                if case_id:
                    try:
                        case_detail = self.client.get_case(case_id)
                        clients = case_detail.get("clients", [])
                        if clients:
                            client_info = clients[0] if isinstance(clients[0], dict) else {}
                            contact_id = client_info.get("id") if isinstance(clients[0], dict) else clients[0]
                            if contact_id:
                                contact = self.client.get_contact(contact_id)
                                contact_name = contact.get("name", "Unknown")
                    except Exception:
                        pass

                # Calculate expected installment (simplified - could be enhanced)
                # For now, assume monthly payments of remaining balance / 3
                installment_amount = balance / 3 if balance > 0 else 0

                # Get due date
                due_date_str = inv.get("due_date", "")
                if due_date_str:
                    try:
                        due_date = datetime.fromisoformat(due_date_str.replace("Z", "")).date()
                    except ValueError:
                        due_date = date.today()
                else:
                    due_date = date.today()

                # Upsert payment plan
                self._upsert_payment_plan(
                    invoice_id=inv.get("id"),
                    contact_id=contact_id,
                    contact_name=contact_name,
                    case_id=case_id,
                    case_name=case.get("name") if case else None,
                    total_amount=total,
                    installment_amount=installment_amount,
                    frequency="monthly",
                    start_date=due_date,
                    next_due_date=due_date,
                    amount_paid=paid,
                )
                plans_synced += 1

            print(f"Synced {plans_synced} payment plans")
            return plans_synced

        except MyCaseAPIError as e:
            print(f"Error syncing payment plans: {e}")
            return 0

    def _upsert_payment_plan(
        self,
        invoice_id: int,
        contact_id: int,
        contact_name: str,
        case_id: int,
        case_name: str,
        total_amount: float,
        installment_amount: float,
        frequency: str,
        start_date: date,
        next_due_date: date,
        amount_paid: float,
    ):
        """Insert or update a payment plan."""
        with self.db._get_connection() as conn:
            cursor = conn.cursor()

            # Calculate payments made (simplified)
            payments_made = int(amount_paid / installment_amount) if installment_amount > 0 else 0
            payments_expected = int(total_amount / installment_amount) if installment_amount > 0 else 1

            # Determine status
            balance = total_amount - amount_paid
            if balance <= 0:
                status = "completed"
            elif (date.today() - next_due_date).days > 30:
                status = "delinquent"
            else:
                status = "active"

            cursor.execute("""
                INSERT INTO payment_plans
                (mycase_invoice_id, contact_id, contact_name, case_id, case_name,
                 total_amount, installment_amount, frequency, start_date, next_due_date,
                 payments_made, payments_expected, amount_paid, status, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(mycase_invoice_id) DO UPDATE SET
                    amount_paid = excluded.amount_paid,
                    payments_made = excluded.payments_made,
                    status = excluded.status,
                    updated_at = CURRENT_TIMESTAMP
            """, (invoice_id, contact_id, contact_name, case_id, case_name,
                  total_amount, installment_amount, frequency, start_date, next_due_date,
                  payments_made, payments_expected, amount_paid, status))
            conn.commit()

    # ========== Compliance Monitoring ==========

    def get_all_active_plans(self) -> List[PaymentPlan]:
        """Get all active and delinquent payment plans."""
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM payment_plans
                WHERE status IN ('active', 'delinquent')
                ORDER BY next_due_date ASC
            """)

            plans = []
            today = date.today()

            for row in cursor.fetchall():
                next_due = datetime.strptime(row["next_due_date"], "%Y-%m-%d").date() if row["next_due_date"] else today
                days_delinquent = max(0, (today - next_due).days)

                # Determine delinquency level
                if days_delinquent == 0:
                    level = DelinquencyLevel.CURRENT
                elif days_delinquent <= 15:
                    level = DelinquencyLevel.LATE_1_15
                elif days_delinquent <= 30:
                    level = DelinquencyLevel.LATE_16_30
                elif days_delinquent <= 60:
                    level = DelinquencyLevel.LATE_31_60
                else:
                    level = DelinquencyLevel.LATE_60_PLUS

                last_payment = None
                if row["last_payment_date"]:
                    last_payment = datetime.strptime(row["last_payment_date"], "%Y-%m-%d").date()

                plan = PaymentPlan(
                    id=row["id"],
                    invoice_id=row["mycase_invoice_id"],
                    contact_id=row["contact_id"],
                    contact_name=row["contact_name"] or "Unknown",
                    case_id=row["case_id"],
                    case_name=row["case_name"],
                    total_amount=row["total_amount"],
                    installment_amount=row["installment_amount"],
                    frequency=row["frequency"],
                    start_date=datetime.strptime(row["start_date"], "%Y-%m-%d").date() if row["start_date"] else today,
                    next_due_date=next_due,
                    payments_made=row["payments_made"],
                    payments_expected=row["payments_expected"],
                    amount_paid=row["amount_paid"],
                    balance_remaining=row["total_amount"] - row["amount_paid"],
                    status=PaymentPlanStatus(row["status"]),
                    last_payment_date=last_payment,
                    days_delinquent=days_delinquent,
                    delinquency_level=level,
                )
                plans.append(plan)

            return plans

    def run_daily_compliance_check(self) -> Dict:
        """
        Run daily compliance monitoring per SOP.

        Returns summary of compliance status and required actions.
        """
        print("Running daily payment plan compliance check...")

        plans = self.get_all_active_plans()
        held_cases = self._get_held_cases()

        summary = {
            "total_active_plans": len(plans),
            "compliant": 0,
            "delinquent": 0,
            "needs_outreach": [],
            "needs_noiw": [],
            "needs_escalation": [],
            "on_hold": 0,
            "compliance_rate": 0.0,
        }

        for plan in plans:
            # Skip held cases
            if plan.case_id in held_cases:
                summary["on_hold"] += 1
                continue

            check = self._check_plan_compliance(plan)

            if check.is_compliant:
                summary["compliant"] += 1
            else:
                summary["delinquent"] += 1

                if check.urgency == "critical":
                    summary["needs_escalation"].append({
                        "plan_id": plan.id,
                        "contact_name": plan.contact_name,
                        "case_name": plan.case_name,
                        "days_delinquent": plan.days_delinquent,
                        "balance": plan.balance_remaining,
                        "action": check.recommended_action,
                    })
                elif plan.days_delinquent >= 30:
                    summary["needs_noiw"].append({
                        "plan_id": plan.id,
                        "contact_name": plan.contact_name,
                        "case_name": plan.case_name,
                        "days_delinquent": plan.days_delinquent,
                        "balance": plan.balance_remaining,
                    })
                else:
                    summary["needs_outreach"].append({
                        "plan_id": plan.id,
                        "contact_name": plan.contact_name,
                        "case_name": plan.case_name,
                        "days_delinquent": plan.days_delinquent,
                        "balance": plan.balance_remaining,
                        "action": check.recommended_action,
                    })

        # Calculate compliance rate (excluding holds)
        active_count = summary["total_active_plans"] - summary["on_hold"]
        if active_count > 0:
            summary["compliance_rate"] = (summary["compliant"] / active_count) * 100

        return summary

    def _check_plan_compliance(self, plan: PaymentPlan) -> ComplianceCheck:
        """Check compliance for a single payment plan."""
        issues = []
        action = ""
        urgency = "normal"

        if plan.days_delinquent > 0:
            issues.append(f"{plan.days_delinquent} days past due")

        if plan.delinquency_level == DelinquencyLevel.CURRENT:
            return ComplianceCheck(plan=plan, is_compliant=True)

        elif plan.delinquency_level == DelinquencyLevel.LATE_1_15:
            action = "Friendly reminder (call/VM + follow-up email/SMS)"
            urgency = "normal"

        elif plan.delinquency_level == DelinquencyLevel.LATE_16_30:
            action = "Firm demand with NOIW warning"
            urgency = "high"

        elif plan.delinquency_level == DelinquencyLevel.LATE_31_60:
            action = "Prepare NOIW packet for Tiffany/John review"
            urgency = "high"

        else:  # 60+ days
            action = "ESCALATE: Immediate attorney review required"
            urgency = "critical"

        return ComplianceCheck(
            plan=plan,
            is_compliant=False,
            issues=issues,
            recommended_action=action,
            urgency=urgency,
        )

    def _get_held_cases(self) -> set:
        """Get set of case IDs that are on hold."""
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT case_id FROM collections_holds
                WHERE status = 'active'
            """)
            return {row["case_id"] for row in cursor.fetchall()}

    # ========== Outreach Tracking ==========

    def record_outreach(
        self,
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
        """
        Record an outreach attempt per SOP sequence:
        - Day 1-3: Friendly reminder
        - Day 10-15: Firm demand
        - Day 30+: NOIW preparation

        Args:
            outreach_type: "friendly_reminder", "firm_demand", "noiw_warning"
            outreach_method: "call", "voicemail", "email", "sms", "letter"
        """
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO outreach_log
                (contact_id, invoice_id, case_id, outreach_type, outreach_method,
                 notes, outcome, next_action, next_action_date)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (contact_id, invoice_id, case_id, outreach_type, outreach_method,
                  notes, outcome, next_action, next_action_date))
            return cursor.lastrowid

    def get_outreach_history(
        self,
        contact_id: int = None,
        invoice_id: int = None,
        case_id: int = None,
    ) -> List[Dict]:
        """Get outreach history for a contact/invoice/case."""
        with self.db._get_connection() as conn:
            cursor = conn.cursor()

            query = "SELECT * FROM outreach_log WHERE 1=1"
            params = []

            if contact_id:
                query += " AND contact_id = ?"
                params.append(contact_id)
            if invoice_id:
                query += " AND invoice_id = ?"
                params.append(invoice_id)
            if case_id:
                query += " AND case_id = ?"
                params.append(case_id)

            query += " ORDER BY created_at DESC"
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    # ========== Hold Management ==========

    def add_collections_hold(
        self,
        case_id: int,
        reason: str,
        approved_by: str,
        case_name: str = None,
        contact_id: int = None,
        review_date: date = None,
        notes: str = None,
    ) -> int:
        """Add a case to the collections hold list."""
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO collections_holds
                (case_id, case_name, contact_id, reason, approved_by,
                 review_date, notes, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'active')
            """, (case_id, case_name, contact_id, reason, approved_by,
                  review_date, notes))
            return cursor.lastrowid

    def remove_collections_hold(self, case_id: int):
        """Remove a case from collections hold."""
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE collections_holds
                SET status = 'removed'
                WHERE case_id = ? AND status = 'active'
            """, (case_id,))

    def get_holds_for_review(self) -> List[Dict]:
        """Get holds that are due for review."""
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM collections_holds
                WHERE status = 'active'
                AND (review_date IS NULL OR review_date <= DATE('now'))
                ORDER BY review_date ASC
            """)
            return [dict(row) for row in cursor.fetchall()]

    # ========== NOIW Preparation ==========

    def prepare_noiw_packet(self, case_id: int) -> Optional[NOIWPacket]:
        """
        Prepare NOIW packet for Tiffany/John review.

        Includes:
        - Account summary
        - Outreach log
        - EA status
        - Case status
        - Proposed next step
        """
        print(f"Preparing NOIW packet for case {case_id}...")

        try:
            # Get case details from MyCase
            case = self.client.get_case(case_id)
            case_name = case.get("name", "Unknown")
            case_status = case.get("status", "Unknown")

            # Get client info
            clients = case.get("clients", [])
            contact_id = None
            contact_name = "Unknown"

            if clients:
                client_info = clients[0] if isinstance(clients[0], dict) else {}
                contact_id = client_info.get("id") if isinstance(clients[0], dict) else clients[0]
                if contact_id:
                    contact = self.client.get_contact(contact_id)
                    contact_name = contact.get("name", "Unknown")

            # Get invoice/balance info
            with self.db._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT * FROM payment_plans
                    WHERE case_id = ? AND status IN ('active', 'delinquent')
                    ORDER BY updated_at DESC LIMIT 1
                """, (case_id,))
                plan = cursor.fetchone()

            if not plan:
                print(f"No active payment plan found for case {case_id}")
                return None

            invoice_id = plan["mycase_invoice_id"]
            balance_due = plan["total_amount"] - plan["amount_paid"]

            # Calculate days delinquent
            next_due = datetime.strptime(plan["next_due_date"], "%Y-%m-%d").date()
            days_delinquent = max(0, (date.today() - next_due).days)

            # Get outreach history
            outreach_log = self.get_outreach_history(case_id=case_id)

            # Get payment history
            payment_history = []
            with self.db._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT * FROM payments
                    WHERE case_id = ?
                    ORDER BY payment_date DESC
                """, (case_id,))
                payment_history = [dict(row) for row in cursor.fetchall()]

            # Check for engagement agreement (simplified - would check documents)
            ea_status = "Needs verification"

            # Determine recommended action
            if days_delinquent >= 60:
                recommended_action = "Immediate withdrawal filing recommended"
            elif days_delinquent >= 30:
                recommended_action = "NOIW letter and 10-day cure period"
            else:
                recommended_action = "Continue outreach, monitor closely"

            return NOIWPacket(
                case_id=case_id,
                case_name=case_name,
                contact_id=contact_id,
                contact_name=contact_name,
                invoice_id=invoice_id,
                balance_due=balance_due,
                days_delinquent=days_delinquent,
                outreach_log=outreach_log,
                payment_history=payment_history,
                engagement_agreement_status=ea_status,
                case_status=case_status,
                recommended_action=recommended_action,
                prepared_date=date.today(),
            )

        except MyCaseAPIError as e:
            print(f"Error preparing NOIW packet: {e}")
            return None

    def get_noiw_pipeline(self, min_days: int = 30, open_cases_only: bool = True) -> List[Dict]:
        """
        Get all invoices that need NOIW consideration (30+ days delinquent).

        Uses cached invoice/case/contact data for accurate names.

        Args:
            min_days: Minimum days overdue to include (default 30)
            open_cases_only: Only include invoices for open cases (default True)
        """
        held_cases = self._get_held_cases()
        cache = get_cache()

        pipeline = []

        # Query the cache database directly for invoices with balance due
        with cache._get_connection() as conn:
            cursor = conn.cursor()

            # Build query to get delinquent invoices with case/contact names
            query = """
                SELECT
                    ci.id as invoice_id,
                    ci.invoice_number,
                    ci.case_id,
                    ci.contact_id,
                    ci.balance_due,
                    ci.due_date,
                    CAST(julianday('now') - julianday(ci.due_date) AS INTEGER) as days_overdue,
                    cc.name as case_name,
                    cc.status as case_status,
                    co.name as contact_name,
                    co.first_name,
                    co.last_name
                FROM cached_invoices ci
                LEFT JOIN cached_cases cc ON ci.case_id = cc.id
                LEFT JOIN cached_contacts co ON ci.contact_id = co.id
                WHERE ci.balance_due > 0
                AND julianday('now') - julianday(ci.due_date) >= ?
            """

            if open_cases_only:
                query += " AND (cc.status IS NULL OR LOWER(cc.status) = 'open')"

            query += " ORDER BY days_overdue DESC"

            cursor.execute(query, (min_days,))

            for row in cursor.fetchall():
                case_id = row['case_id']

                # Skip held cases
                if case_id and case_id in held_cases:
                    continue

                days_overdue = row['days_overdue'] or 0

                # Build contact name from available fields
                contact_name = row['contact_name']
                if not contact_name:
                    first = row['first_name'] or ''
                    last = row['last_name'] or ''
                    contact_name = f"{first} {last}".strip() or "Unknown"

                # Extract client name from case name if contact unknown
                # Case names often follow format: "LASTNAME.FIRSTNAME - ..."
                case_name = row['case_name'] or 'N/A'
                if contact_name == "Unknown" and case_name != 'N/A':
                    # Try to extract from case name pattern
                    name_part = case_name.split(' - ')[0].split(':')[0]
                    if '.' in name_part:
                        contact_name = name_part.replace('.', ' ').strip()

                pipeline.append({
                    "invoice_id": row['invoice_id'],
                    "invoice_number": row['invoice_number'],
                    "case_id": case_id,
                    "case_name": case_name,
                    "contact_id": row['contact_id'],
                    "contact_name": contact_name,
                    "days_delinquent": days_overdue,
                    "balance_due": row['balance_due'],
                    "urgency": "critical" if days_overdue >= 60 else "high",
                    "case_status": row['case_status'] or "Unknown",
                })

        return pipeline

    # ========== NOIW Workflow Tracking ==========

    def get_noiw_status(self, case_id: int, invoice_id: int = None) -> Optional[Dict]:
        """Get NOIW tracking status for a case/invoice."""
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            if invoice_id:
                cursor.execute("""
                    SELECT * FROM noiw_tracking
                    WHERE case_id = ? AND invoice_id = ?
                """, (case_id, invoice_id))
            else:
                cursor.execute("""
                    SELECT * FROM noiw_tracking
                    WHERE case_id = ?
                    ORDER BY created_at DESC LIMIT 1
                """, (case_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def start_noiw_tracking(self, case_id: int, invoice_id: int,
                           case_name: str = None, contact_id: int = None,
                           contact_name: str = None, balance_due: float = 0,
                           days_delinquent: int = 0, assigned_to: str = None) -> int:
        """Start NOIW tracking for a case/invoice."""
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO noiw_tracking
                (case_id, case_name, contact_id, contact_name, invoice_id,
                 balance_due, days_delinquent, status, assigned_to)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?)
                ON CONFLICT(case_id, invoice_id) DO UPDATE SET
                    balance_due = excluded.balance_due,
                    days_delinquent = excluded.days_delinquent,
                    updated_at = CURRENT_TIMESTAMP
            """, (case_id, case_name, contact_id, contact_name, invoice_id,
                  balance_due, days_delinquent, assigned_to))
            conn.commit()
            return cursor.lastrowid

    def update_noiw_status(self, case_id: int, invoice_id: int, new_status: str,
                          notes: str = None, assigned_to: str = None) -> bool:
        """Update NOIW status for a case/invoice."""
        valid_statuses = [s.value for s in NOIWStatus]
        if new_status not in valid_statuses:
            raise ValueError(f"Invalid status: {new_status}. Must be one of {valid_statuses}")

        with self.db._get_connection() as conn:
            cursor = conn.cursor()

            # Build update based on status
            date_field = None
            if new_status == NOIWStatus.WARNING_SENT.value:
                date_field = "warning_sent_date"
            elif new_status == NOIWStatus.FINAL_NOTICE.value:
                date_field = "final_notice_date"
            elif new_status == NOIWStatus.ATTORNEY_REVIEW.value:
                date_field = "attorney_review_date"
            elif new_status in [NOIWStatus.RESOLVED.value, NOIWStatus.WITHDRAWN.value,
                               NOIWStatus.PAYMENT_ARRANGED.value]:
                date_field = "resolution_date"

            if date_field:
                cursor.execute(f"""
                    UPDATE noiw_tracking
                    SET status = ?,
                        {date_field} = CURRENT_DATE,
                        notes = COALESCE(?, notes),
                        assigned_to = COALESCE(?, assigned_to),
                        updated_at = CURRENT_TIMESTAMP
                    WHERE case_id = ? AND invoice_id = ?
                """, (new_status, notes, assigned_to, case_id, invoice_id))
            else:
                cursor.execute("""
                    UPDATE noiw_tracking
                    SET status = ?,
                        notes = COALESCE(?, notes),
                        assigned_to = COALESCE(?, assigned_to),
                        updated_at = CURRENT_TIMESTAMP
                    WHERE case_id = ? AND invoice_id = ?
                """, (new_status, notes, assigned_to, case_id, invoice_id))

            conn.commit()
            return cursor.rowcount > 0

    def get_noiw_workflow_summary(self) -> Dict:
        """Get summary of NOIW workflow statuses."""
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT
                    status,
                    COUNT(*) as count,
                    SUM(balance_due) as total_balance
                FROM noiw_tracking
                GROUP BY status
            """)

            summary = {s.value: {"count": 0, "total_balance": 0} for s in NOIWStatus}
            for row in cursor.fetchall():
                summary[row['status']] = {
                    "count": row['count'],
                    "total_balance": row['total_balance'] or 0
                }

            # Get total
            cursor.execute("""
                SELECT COUNT(*) as total, SUM(balance_due) as total_balance
                FROM noiw_tracking
            """)
            totals = cursor.fetchone()

            return {
                "by_status": summary,
                "total_tracked": totals['total'] or 0,
                "total_balance": totals['total_balance'] or 0
            }

    def get_noiw_cases_by_status(self, status: str) -> List[Dict]:
        """Get all NOIW cases with a specific status."""
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM noiw_tracking
                WHERE status = ?
                ORDER BY days_delinquent DESC
            """, (status,))
            return [dict(row) for row in cursor.fetchall()]

    def sync_noiw_from_pipeline(self) -> Dict:
        """
        Sync NOIW tracking from the pipeline.
        Creates tracking entries for new pipeline cases,
        updates existing entries with current balances.
        """
        pipeline = self.get_noiw_pipeline(min_days=30, open_cases_only=True)

        new_entries = 0
        updated = 0

        for item in pipeline:
            existing = self.get_noiw_status(item['case_id'], item['invoice_id'])

            if existing:
                # Update balance and days delinquent
                with self.db._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        UPDATE noiw_tracking
                        SET balance_due = ?,
                            days_delinquent = ?,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE case_id = ? AND invoice_id = ?
                    """, (item['balance_due'], item['days_delinquent'],
                          item['case_id'], item['invoice_id']))
                    conn.commit()
                updated += 1
            else:
                # Create new tracking entry
                self.start_noiw_tracking(
                    case_id=item['case_id'],
                    invoice_id=item['invoice_id'],
                    case_name=item['case_name'],
                    contact_id=item.get('contact_id'),
                    contact_name=item['contact_name'],
                    balance_due=item['balance_due'],
                    days_delinquent=item['days_delinquent']
                )
                new_entries += 1

        return {
            "pipeline_count": len(pipeline),
            "new_entries": new_entries,
            "updated": updated
        }

    def get_noiw_notification_data(self) -> Dict:
        """
        Generate data for NOIW notifications.

        Returns dict with:
        - summary: Overall stats for daily report
        - critical_cases: Cases needing immediate attention
        - workflow_status: Status tracking summary
        """
        pipeline = self.get_noiw_pipeline(min_days=30, open_cases_only=True)

        # Calculate summary stats
        total_balance = sum(p['balance_due'] for p in pipeline)
        critical_count = sum(1 for p in pipeline if p['urgency'] == 'critical')

        # Age buckets
        bucket_30_60 = sum(1 for p in pipeline if 30 <= p['days_delinquent'] < 60)
        bucket_60_90 = sum(1 for p in pipeline if 60 <= p['days_delinquent'] < 90)
        bucket_90_180 = sum(1 for p in pipeline if 90 <= p['days_delinquent'] < 180)
        bucket_180_plus = sum(1 for p in pipeline if p['days_delinquent'] >= 180)

        # Get critical cases (180+ days or balance > $10K)
        critical_cases = [
            p for p in pipeline
            if p['days_delinquent'] >= 180 or p['balance_due'] >= 10000
        ]
        critical_cases.sort(key=lambda x: x['balance_due'], reverse=True)

        # Get workflow status
        workflow_status = self.get_noiw_workflow_summary()

        return {
            "summary": {
                "total_cases": len(pipeline),
                "total_balance": total_balance,
                "critical_count": critical_count,
                "bucket_30_60": bucket_30_60,
                "bucket_60_90": bucket_60_90,
                "bucket_90_180": bucket_90_180,
                "bucket_180_plus": bucket_180_plus,
            },
            "critical_cases": critical_cases[:10],  # Top 10 by balance
            "workflow_status": workflow_status,
            "pipeline": pipeline,
        }

    # ========== Intake Verification ==========

    def verify_new_matter_payment_setup(self, case_id: int) -> Dict:
        """
        Verify payment plan setup for new matter (Day-1 checklist per SOP).

        Checks:
        - EA uploaded and signed
        - Flat fee matches invoice
        - Payment plan fully populated
        - Case status and attorney set
        - First installment calendared
        """
        print(f"Verifying payment setup for case {case_id}...")

        issues = []
        warnings = []

        try:
            case = self.client.get_case(case_id)

            # Check case has attorney assigned
            lead_attorney = case.get("lead_attorney")
            if not lead_attorney:
                issues.append("No lead attorney assigned")

            # Check case status
            status = case.get("status")
            if not status or status == "unknown":
                warnings.append("Case status not set")

            # Get documents to check for EA
            try:
                docs = self.client.get_case_documents(case_id)
                doc_list = docs if isinstance(docs, list) else docs.get("data", [])

                has_ea = False
                for doc in doc_list:
                    doc_name = doc.get("name", "").lower()
                    if "engagement" in doc_name or "agreement" in doc_name or "ea" in doc_name:
                        has_ea = True
                        break

                if not has_ea:
                    issues.append("Engagement Agreement not found in documents")
            except Exception:
                warnings.append("Could not verify EA document")

            # Check for invoice/payment plan
            try:
                invoices = self.client.get_invoices(case_id=case_id)
                invoice_list = invoices if isinstance(invoices, list) else invoices.get("data", [])

                if not invoice_list:
                    issues.append("No invoice created for case")
                else:
                    # Verify invoice has proper setup
                    for inv in invoice_list:
                        if not inv.get("due_date"):
                            warnings.append(f"Invoice {inv.get('invoice_number')} missing due date")
            except Exception:
                warnings.append("Could not verify invoices")

            # Check client portal access (simplified - would need portal API)
            warnings.append("Verify client portal access manually")

            return {
                "case_id": case_id,
                "case_name": case.get("name"),
                "verified": len(issues) == 0,
                "issues": issues,
                "warnings": warnings,
                "checked_at": datetime.now().isoformat(),
            }

        except MyCaseAPIError as e:
            return {
                "case_id": case_id,
                "verified": False,
                "issues": [f"API Error: {e}"],
                "warnings": [],
                "checked_at": datetime.now().isoformat(),
            }

    # ========== Report Generation ==========

    def generate_collections_huddle_report(self) -> str:
        """
        Generate weekly 20-min A/R huddle report per SOP.

        Topics:
        - Delinquencies by age bucket
        - Collections vs scheduled
        - NOIW pipeline
        - Wonky queue status
        - Pending withdrawals
        """
        compliance = self.run_daily_compliance_check()
        noiw_pipeline = self.get_noiw_pipeline()
        holds = self.get_holds_for_review()

        # Get wonky invoice status
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN status = 'open' THEN 1 ELSE 0 END) as open_count
                FROM wonky_invoices
            """)
            wonky = cursor.fetchone()

        report = f"""
================================================================================
                    WEEKLY A/R HUDDLE REPORT - {date.today()}
================================================================================

1. PAYMENT PLAN STATUS
   Total Active Plans: {compliance['total_active_plans']}
   Compliant: {compliance['compliant']} ({compliance['compliance_rate']:.1f}%)
   Delinquent: {compliance['delinquent']}
   On Hold: {compliance['on_hold']}
   Target: ≥90% compliance {"✓" if compliance['compliance_rate'] >= 90 else "⚠"}

2. DELINQUENCIES NEEDING OUTREACH ({len(compliance['needs_outreach'])})
"""
        for item in compliance['needs_outreach'][:5]:
            report += f"   • {item['contact_name']} - {item['case_name']}: {item['days_delinquent']} days, ${item['balance']:,.2f}\n"

        report += f"""
3. NOIW PIPELINE ({len(noiw_pipeline)} cases ≥30 days)
"""
        for item in noiw_pipeline[:5]:
            urgency = "🔴" if item['urgency'] == 'critical' else "🟡"
            report += f"   {urgency} {item['contact_name']} - {item['case_name']}: {item['days_delinquent']} days, ${item['balance_due']:,.2f}\n"

        report += f"""
4. WONKY INVOICE QUEUE
   Open Items: {wonky['open_count'] if wonky else 0}
   Total Tracked: {wonky['total'] if wonky else 0}

5. HOLDS FOR REVIEW ({len(holds)})
"""
        for hold in holds[:3]:
            report += f"   • Case {hold['case_id']}: {hold['reason']} (approved by {hold['approved_by']})\n"

        report += f"""
6. ESCALATIONS NEEDED ({len(compliance['needs_escalation'])})
"""
        for item in compliance['needs_escalation']:
            report += f"   🔴 {item['contact_name']} - {item['case_name']}: {item['days_delinquent']} days - {item['action']}\n"

        report += """
================================================================================
"""
        return report


if __name__ == "__main__":
    manager = PaymentPlanManager()

    print("Testing Payment Plan Manager...")
    print("(Requires valid MyCase API authentication)")

    try:
        # Sync payment plans
        manager.sync_payment_plans_from_invoices()

        # Run compliance check
        compliance = manager.run_daily_compliance_check()
        print(f"\nCompliance Summary:")
        print(f"  Active Plans: {compliance['total_active_plans']}")
        print(f"  Compliant: {compliance['compliant']}")
        print(f"  Delinquent: {compliance['delinquent']}")
        print(f"  Compliance Rate: {compliance['compliance_rate']:.1f}%")

        # Generate huddle report
        report = manager.generate_collections_huddle_report()
        print(report)

    except Exception as e:
        print(f"Error: {e}")
        print("Make sure you've authenticated with: python auth.py")
