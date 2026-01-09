"""
KPI Tracker Module

Calculates daily and weekly KPIs for all roles based on SOPs:
- Collections/AR (Melissa Scarlett)
- Legal Assistants (Alison, Cole)
- Intake (Ty Christian)
- Paralegal Ops (Tiffany Willis)
"""
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum

from api_client import MyCaseClient, get_client, MyCaseAPIError
from database import Database, get_db


class KPICategory(Enum):
    COLLECTIONS = "collections"
    INTAKE = "intake"
    LEGAL_ASSISTANT = "legal_assistant"
    PARALEGAL = "paralegal"


@dataclass
class KPIMetric:
    """Represents a single KPI metric."""
    name: str
    value: Any
    target: Optional[Any] = None
    unit: str = ""
    category: KPICategory = KPICategory.COLLECTIONS
    description: str = ""
    met_target: Optional[bool] = None

    def __post_init__(self):
        if self.target is not None and isinstance(self.value, (int, float)):
            if isinstance(self.target, str) and self.target.startswith(">="):
                target_val = float(self.target[2:].strip().rstrip("%"))
                self.met_target = self.value >= target_val
            elif isinstance(self.target, str) and self.target.startswith("<="):
                target_val = float(self.target[2:].strip().rstrip("%"))
                self.met_target = self.value <= target_val
            elif isinstance(self.target, (int, float)):
                self.met_target = self.value >= self.target


@dataclass
class DailyCollectionsKPIs:
    """Daily KPIs for Collections/AR role (Melissa)."""
    date: date
    cash_received: float = 0.0
    payment_count: int = 0
    total_ar_balance: float = 0.0
    ar_0_30: float = 0.0
    ar_31_60: float = 0.0
    ar_61_90: float = 0.0
    ar_90_plus: float = 0.0
    aging_over_60_pct: float = 0.0
    promises_made: int = 0
    promises_kept: int = 0
    promise_rate: float = 0.0
    new_payment_plans: int = 0
    payment_plan_amount: float = 0.0
    delinquent_accounts: int = 0
    delinquent_contacted: int = 0
    contact_rate: float = 0.0


@dataclass
class WeeklyCollectionsKPIs:
    """Weekly KPIs for Collections/AR role (Melissa)."""
    week_start: date
    week_end: date
    total_collected: float = 0.0
    prior_week_collected: float = 0.0
    collection_change_pct: float = 0.0
    ar_trend_start: float = 0.0
    ar_trend_end: float = 0.0
    ar_change_pct: float = 0.0
    collection_rate: float = 0.0  # collected / billed
    total_billed: float = 0.0
    payment_plan_compliance_rate: float = 0.0  # Target >= 90%
    active_payment_plans: int = 0
    delinquent_plans: int = 0
    collected_vs_scheduled: float = 0.0  # Target >= 95%
    scheduled_amount: float = 0.0
    delinquent_followup_sla_rate: float = 0.0  # Target 100%
    wonky_resolved: int = 0
    wonky_opened: int = 0
    wonky_throughput: float = 0.0  # Target >= 1.0
    noiw_count: int = 0
    top_delinquent_accounts: List[Dict] = field(default_factory=list)
    followup_attempts: int = 0
    successful_contacts: int = 0
    contact_success_rate: float = 0.0
    writeoffs: float = 0.0


@dataclass
class MonthlyCollectionsKPIs:
    """Monthly KPIs for Collections/AR role (Melissa)."""
    month: str  # YYYY-MM format
    aged_ar_0_30_pct: float = 0.0  # Target >= 70%
    aged_ar_60_plus_pct: float = 0.0  # Target <= 10%
    monthly_collections: float = 0.0
    monthly_billed: float = 0.0
    realization_rate: float = 0.0  # Target >= 90%
    dso: float = 0.0  # Days Sales Outstanding, Target <= 30
    payment_plan_success_rate: float = 0.0  # Target >= 85%
    plans_completed: int = 0
    plans_defaulted: int = 0
    noiw_issued: int = 0
    noiw_cured: int = 0
    noiw_withdrawn: int = 0
    noiw_conversion_rate: float = 0.0  # Target >= 75%


class KPITracker:
    """
    Tracks and calculates KPIs for all roles based on SOPs.
    """

    def __init__(
        self,
        client: MyCaseClient = None,
        db: Database = None,
    ):
        self.client = client or get_client()
        self.db = db or get_db()
        self._ensure_kpi_tables()

    def _ensure_kpi_tables(self):
        """Create KPI tracking tables if they don't exist."""
        with self.db._get_connection() as conn:
            cursor = conn.cursor()

            # Daily KPI snapshots
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS kpi_daily_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    snapshot_date DATE NOT NULL,
                    category TEXT NOT NULL,
                    kpi_name TEXT NOT NULL,
                    kpi_value REAL,
                    kpi_target TEXT,
                    met_target BOOLEAN,
                    metadata TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(snapshot_date, category, kpi_name)
                )
            """)

            # Payment plan tracking
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS payment_plans (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    mycase_invoice_id INTEGER UNIQUE,
                    contact_id INTEGER,
                    contact_name TEXT,
                    case_id INTEGER,
                    case_name TEXT,
                    total_amount REAL,
                    installment_amount REAL,
                    frequency TEXT,
                    start_date DATE,
                    next_due_date DATE,
                    payments_made INTEGER DEFAULT 0,
                    payments_expected INTEGER DEFAULT 0,
                    amount_paid REAL DEFAULT 0,
                    status TEXT DEFAULT 'active',
                    last_payment_date DATE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Promise to pay tracking
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS promise_to_pay (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    contact_id INTEGER NOT NULL,
                    contact_name TEXT,
                    invoice_id INTEGER,
                    promised_amount REAL,
                    promised_date DATE,
                    actual_payment_date DATE,
                    actual_amount REAL,
                    status TEXT DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Delinquent account follow-ups
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS delinquent_followups (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    invoice_id INTEGER NOT NULL,
                    contact_id INTEGER,
                    contact_name TEXT,
                    delinquent_date DATE NOT NULL,
                    first_contact_date DATE,
                    first_contact_method TEXT,
                    days_to_contact INTEGER,
                    sla_met BOOLEAN,
                    followup_count INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'open',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(invoice_id, delinquent_date)
                )
            """)

            # Wonky invoice queue
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS wonky_invoices (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    invoice_id INTEGER NOT NULL,
                    invoice_number TEXT,
                    case_id INTEGER,
                    case_name TEXT,
                    issue_type TEXT NOT NULL,
                    issue_description TEXT,
                    ea_amount REAL,
                    invoice_amount REAL,
                    discrepancy REAL,
                    status TEXT DEFAULT 'open',
                    opened_date DATE DEFAULT CURRENT_DATE,
                    resolved_date DATE,
                    resolution_notes TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(invoice_id, issue_type)
                )
            """)

            # NOIW (Notice of Intent to Withdraw) tracking
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
                    initiated_date DATE DEFAULT CURRENT_DATE,
                    outcome TEXT,
                    outcome_date DATE,
                    notes TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(case_id, initiated_date)
                )
            """)

            conn.commit()

    # ========== Daily Collections KPIs ==========

    def calculate_daily_collections_kpis(
        self,
        target_date: date = None
    ) -> DailyCollectionsKPIs:
        """
        Calculate daily KPIs for Collections/AR (Melissa).

        Args:
            target_date: Date to calculate KPIs for (default: today)

        Returns:
            DailyCollectionsKPIs with all metrics
        """
        target_date = target_date or date.today()
        kpis = DailyCollectionsKPIs(date=target_date)

        # Get payments and AR data from invoices
        try:
            print(f"Calculating daily collections KPIs for {target_date}...")

            # Fetch all invoices - payment data is embedded in invoice records
            all_invoices = self.client.get_all_pages(self.client.get_invoices)

            # Track invoices updated today (likely received payment)
            # Note: MyCase doesn't have a separate payments endpoint,
            # so we infer from invoices with status=paid and recent updates
            invoices_paid_today = []
            for inv in all_invoices:
                if inv.get("status") == "paid":
                    updated_str = inv.get("updated_at", "")
                    if updated_str:
                        try:
                            updated_dt = datetime.fromisoformat(updated_str.replace("Z", "")).date()
                            if updated_dt == target_date:
                                invoices_paid_today.append(inv)
                        except ValueError:
                            continue

            kpis.cash_received = sum(float(inv.get("paid_amount", 0)) for inv in invoices_paid_today)
            kpis.payment_count = len(invoices_paid_today)

            for inv in all_invoices:
                status = inv.get("status", "")
                if status not in ("overdue", "partial", "sent"):
                    continue

                total = float(inv.get("total_amount", 0))
                paid = float(inv.get("paid_amount", 0))
                balance = total - paid

                if balance <= 0:
                    continue

                due_date_str = inv.get("due_date", "")
                if not due_date_str:
                    continue

                try:
                    due_date = datetime.fromisoformat(due_date_str.replace("Z", "")).date()
                    days_overdue = (target_date - due_date).days
                except ValueError:
                    continue

                kpis.total_ar_balance += balance

                if days_overdue <= 30:
                    kpis.ar_0_30 += balance
                elif days_overdue <= 60:
                    kpis.ar_31_60 += balance
                elif days_overdue <= 90:
                    kpis.ar_61_90 += balance
                else:
                    kpis.ar_90_plus += balance

                if days_overdue > 0:
                    kpis.delinquent_accounts += 1

            # Calculate aging percentage over 60 days
            if kpis.total_ar_balance > 0:
                kpis.aging_over_60_pct = (
                    (kpis.ar_61_90 + kpis.ar_90_plus) / kpis.total_ar_balance
                ) * 100

            # Get promise-to-pay data from our tracking
            with self.db._get_connection() as conn:
                cursor = conn.cursor()

                # Promises made today
                cursor.execute("""
                    SELECT COUNT(*) as count FROM promise_to_pay
                    WHERE DATE(created_at) = ?
                """, (target_date,))
                row = cursor.fetchone()
                kpis.promises_made = row["count"] if row else 0

                # Promises kept (payment received by promised date)
                cursor.execute("""
                    SELECT COUNT(*) as count FROM promise_to_pay
                    WHERE promised_date <= ? AND status = 'fulfilled'
                """, (target_date,))
                row = cursor.fetchone()
                kpis.promises_kept = row["count"] if row else 0

                if kpis.promises_made > 0:
                    kpis.promise_rate = (kpis.promises_kept / kpis.promises_made) * 100

                # Delinquent follow-up tracking
                cursor.execute("""
                    SELECT COUNT(*) as count FROM delinquent_followups
                    WHERE DATE(first_contact_date) = ?
                """, (target_date,))
                row = cursor.fetchone()
                kpis.delinquent_contacted = row["count"] if row else 0

                if kpis.delinquent_accounts > 0:
                    kpis.contact_rate = (kpis.delinquent_contacted / kpis.delinquent_accounts) * 100

        except MyCaseAPIError as e:
            print(f"Error calculating daily KPIs: {e}")

        return kpis

    # ========== Weekly Collections KPIs ==========

    def calculate_weekly_collections_kpis(
        self,
        week_end: date = None
    ) -> WeeklyCollectionsKPIs:
        """
        Calculate weekly KPIs for Collections/AR (Melissa).

        Args:
            week_end: End date of week (default: most recent Sunday)

        Returns:
            WeeklyCollectionsKPIs with all metrics
        """
        if week_end is None:
            today = date.today()
            # Find most recent Sunday
            days_since_sunday = (today.weekday() + 1) % 7
            week_end = today - timedelta(days=days_since_sunday)

        week_start = week_end - timedelta(days=6)
        prior_week_end = week_start - timedelta(days=1)
        prior_week_start = prior_week_end - timedelta(days=6)

        kpis = WeeklyCollectionsKPIs(week_start=week_start, week_end=week_end)

        try:
            print(f"Calculating weekly collections KPIs for {week_start} to {week_end}...")

            # Fetch all invoices - payment data is embedded in invoice records
            all_invoices = self.client.get_all_pages(self.client.get_invoices)

            # Track invoices that were paid (updated) in each week
            current_week_paid = []
            prior_week_paid = []

            for inv in all_invoices:
                if inv.get("status") == "paid":
                    updated_str = inv.get("updated_at", "")
                    if not updated_str:
                        continue
                    try:
                        updated_dt = datetime.fromisoformat(updated_str.replace("Z", "")).date()
                        if week_start <= updated_dt <= week_end:
                            current_week_paid.append(inv)
                        elif prior_week_start <= updated_dt <= prior_week_end:
                            prior_week_paid.append(inv)
                    except ValueError:
                        continue

            kpis.total_collected = sum(float(inv.get("paid_amount", 0)) for inv in current_week_paid)
            kpis.prior_week_collected = sum(float(inv.get("paid_amount", 0)) for inv in prior_week_paid)

            if kpis.prior_week_collected > 0:
                kpis.collection_change_pct = (
                    (kpis.total_collected - kpis.prior_week_collected) / kpis.prior_week_collected
                ) * 100

            # Calculate AR trend and collection rate from same invoices data

            # Calculate AR at start and end of week
            for inv in all_invoices:
                status = inv.get("status", "")
                total = float(inv.get("total_amount", 0))
                paid = float(inv.get("paid_amount", 0))
                balance = total - paid

                due_date_str = inv.get("due_date", "")
                invoice_date_str = inv.get("invoice_date", "")

                if due_date_str:
                    try:
                        due_date = datetime.fromisoformat(due_date_str.replace("Z", "")).date()
                        if due_date <= week_end and balance > 0:
                            kpis.ar_trend_end += balance
                        if due_date <= week_start and balance > 0:
                            kpis.ar_trend_start += balance
                    except ValueError:
                        pass

                # Billed this week
                if invoice_date_str:
                    try:
                        inv_date = datetime.fromisoformat(invoice_date_str.replace("Z", "")).date()
                        if week_start <= inv_date <= week_end:
                            kpis.total_billed += total
                    except ValueError:
                        pass

            if kpis.ar_trend_start > 0:
                kpis.ar_change_pct = (
                    (kpis.ar_trend_end - kpis.ar_trend_start) / kpis.ar_trend_start
                ) * 100

            if kpis.total_billed > 0:
                kpis.collection_rate = (kpis.total_collected / kpis.total_billed) * 100

            # Payment plan metrics from our tracking
            with self.db._get_connection() as conn:
                cursor = conn.cursor()

                # Active payment plans
                cursor.execute("""
                    SELECT COUNT(*) as active,
                           SUM(CASE WHEN status = 'delinquent' THEN 1 ELSE 0 END) as delinquent
                    FROM payment_plans
                    WHERE status IN ('active', 'delinquent')
                """)
                row = cursor.fetchone()
                kpis.active_payment_plans = row["active"] if row and row["active"] else 0
                kpis.delinquent_plans = row["delinquent"] if row and row["delinquent"] else 0

                if kpis.active_payment_plans > 0:
                    compliant = kpis.active_payment_plans - kpis.delinquent_plans
                    kpis.payment_plan_compliance_rate = (compliant / kpis.active_payment_plans) * 100

                # Delinquent follow-up SLA (contacted within 1 business day)
                cursor.execute("""
                    SELECT
                        COUNT(*) as total,
                        SUM(CASE WHEN sla_met = 1 THEN 1 ELSE 0 END) as met
                    FROM delinquent_followups
                    WHERE delinquent_date BETWEEN ? AND ?
                """, (week_start, week_end))
                row = cursor.fetchone()
                total_delinquent = row["total"] if row and row["total"] else 0
                sla_met = row["met"] if row and row["met"] else 0

                if total_delinquent > 0:
                    kpis.delinquent_followup_sla_rate = (sla_met / total_delinquent) * 100

                # Wonky invoice throughput
                cursor.execute("""
                    SELECT
                        COUNT(CASE WHEN resolved_date BETWEEN ? AND ? THEN 1 END) as resolved,
                        COUNT(CASE WHEN opened_date BETWEEN ? AND ? THEN 1 END) as opened
                    FROM wonky_invoices
                """, (week_start, week_end, week_start, week_end))
                row = cursor.fetchone()
                kpis.wonky_resolved = row["resolved"] if row and row["resolved"] else 0
                kpis.wonky_opened = row["opened"] if row and row["opened"] else 0

                if kpis.wonky_opened > 0:
                    kpis.wonky_throughput = kpis.wonky_resolved / kpis.wonky_opened

                # NOIW count
                cursor.execute("""
                    SELECT COUNT(*) as count FROM noiw_tracking
                    WHERE initiated_date BETWEEN ? AND ?
                """, (week_start, week_end))
                row = cursor.fetchone()
                kpis.noiw_count = row["count"] if row and row["count"] else 0

        except MyCaseAPIError as e:
            print(f"Error calculating weekly KPIs: {e}")

        return kpis

    # ========== Monthly Collections KPIs ==========

    def calculate_monthly_collections_kpis(
        self,
        month: str = None
    ) -> MonthlyCollectionsKPIs:
        """
        Calculate monthly KPIs for Collections/AR (Melissa).

        Args:
            month: Month in YYYY-MM format (default: current month)

        Returns:
            MonthlyCollectionsKPIs with all metrics
        """
        if month is None:
            month = date.today().strftime("%Y-%m")

        year, month_num = map(int, month.split("-"))
        month_start = date(year, month_num, 1)

        # Calculate month end
        if month_num == 12:
            month_end = date(year + 1, 1, 1) - timedelta(days=1)
        else:
            month_end = date(year, month_num + 1, 1) - timedelta(days=1)

        kpis = MonthlyCollectionsKPIs(month=month)

        try:
            print(f"Calculating monthly collections KPIs for {month}...")

            # Fetch all invoices - payment data is embedded
            all_invoices = self.client.get_all_pages(self.client.get_invoices)

            # Monthly collections - from invoices paid this month
            for inv in all_invoices:
                if inv.get("status") == "paid":
                    updated_str = inv.get("updated_at", "")
                    if updated_str:
                        try:
                            updated_dt = datetime.fromisoformat(updated_str.replace("Z", "")).date()
                            if month_start <= updated_dt <= month_end:
                                kpis.monthly_collections += float(inv.get("paid_amount", 0))
                        except ValueError:
                            continue

            # AR aging and billing
            total_ar = 0.0
            ar_0_30 = 0.0
            ar_60_plus = 0.0

            for inv in all_invoices:
                total = float(inv.get("total_amount", 0))
                paid = float(inv.get("paid_amount", 0))
                balance = total - paid

                invoice_date_str = inv.get("invoice_date", "")
                due_date_str = inv.get("due_date", "")

                # Monthly billing
                if invoice_date_str:
                    try:
                        inv_date = datetime.fromisoformat(invoice_date_str.replace("Z", "")).date()
                        if month_start <= inv_date <= month_end:
                            kpis.monthly_billed += total
                    except ValueError:
                        pass

                # AR aging
                if balance > 0 and due_date_str:
                    try:
                        due_date = datetime.fromisoformat(due_date_str.replace("Z", "")).date()
                        days_overdue = (month_end - due_date).days

                        total_ar += balance
                        if days_overdue <= 30:
                            ar_0_30 += balance
                        if days_overdue > 60:
                            ar_60_plus += balance
                    except ValueError:
                        pass

            if total_ar > 0:
                kpis.aged_ar_0_30_pct = (ar_0_30 / total_ar) * 100
                kpis.aged_ar_60_plus_pct = (ar_60_plus / total_ar) * 100

            if kpis.monthly_billed > 0:
                kpis.realization_rate = (kpis.monthly_collections / kpis.monthly_billed) * 100

            # DSO calculation: (Average AR / Monthly Revenue) * 30
            if kpis.monthly_collections > 0:
                avg_ar = total_ar  # Simplified - could track daily AR for true average
                kpis.dso = (avg_ar / kpis.monthly_collections) * 30

            # Payment plan and NOIW metrics from tracking
            with self.db._get_connection() as conn:
                cursor = conn.cursor()

                # Payment plan success rate (rolling 6 months)
                six_months_ago = month_start - timedelta(days=180)
                cursor.execute("""
                    SELECT
                        COUNT(CASE WHEN status = 'completed' THEN 1 END) as completed,
                        COUNT(CASE WHEN status = 'defaulted' THEN 1 END) as defaulted,
                        COUNT(*) as total
                    FROM payment_plans
                    WHERE created_at >= ?
                """, (six_months_ago,))
                row = cursor.fetchone()
                kpis.plans_completed = row["completed"] if row and row["completed"] else 0
                kpis.plans_defaulted = row["defaulted"] if row and row["defaulted"] else 0
                total_plans = row["total"] if row and row["total"] else 0

                if total_plans > 0:
                    kpis.payment_plan_success_rate = (kpis.plans_completed / total_plans) * 100

                # NOIW conversion rate
                cursor.execute("""
                    SELECT
                        COUNT(*) as total,
                        COUNT(CASE WHEN outcome IN ('cured', 'withdrawn') THEN 1 END) as converted
                    FROM noiw_tracking
                    WHERE initiated_date BETWEEN ? AND ?
                """, (month_start, month_end))
                row = cursor.fetchone()
                kpis.noiw_issued = row["total"] if row and row["total"] else 0
                converted = row["converted"] if row and row["converted"] else 0

                if kpis.noiw_issued > 0:
                    kpis.noiw_conversion_rate = (converted / kpis.noiw_issued) * 100

        except MyCaseAPIError as e:
            print(f"Error calculating monthly KPIs: {e}")

        return kpis

    # ========== KPI Snapshot Storage ==========

    def save_daily_kpi_snapshot(self, kpis: DailyCollectionsKPIs):
        """Save daily KPI snapshot to database."""
        with self.db._get_connection() as conn:
            cursor = conn.cursor()

            metrics = [
                ("cash_received", kpis.cash_received, None),
                ("payment_count", kpis.payment_count, None),
                ("total_ar_balance", kpis.total_ar_balance, None),
                ("ar_0_30", kpis.ar_0_30, None),
                ("ar_31_60", kpis.ar_31_60, None),
                ("ar_61_90", kpis.ar_61_90, None),
                ("ar_90_plus", kpis.ar_90_plus, None),
                ("aging_over_60_pct", kpis.aging_over_60_pct, "<= 25%"),
                ("promise_rate", kpis.promise_rate, ">= 75%"),
                ("delinquent_accounts", kpis.delinquent_accounts, None),
                ("contact_rate", kpis.contact_rate, ">= 100%"),
            ]

            for name, value, target in metrics:
                met_target = None
                if target:
                    if target.startswith(">="):
                        met_target = value >= float(target[2:].strip().rstrip("%"))
                    elif target.startswith("<="):
                        met_target = value <= float(target[2:].strip().rstrip("%"))

                cursor.execute("""
                    INSERT OR REPLACE INTO kpi_daily_snapshots
                    (snapshot_date, category, kpi_name, kpi_value, kpi_target, met_target)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (kpis.date, "collections", name, value, target, met_target))

            conn.commit()

    def get_kpi_history(
        self,
        category: str,
        kpi_name: str,
        days: int = 30
    ) -> List[Dict]:
        """Get historical KPI values."""
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT snapshot_date, kpi_value, kpi_target, met_target
                FROM kpi_daily_snapshots
                WHERE category = ? AND kpi_name = ?
                AND snapshot_date >= DATE('now', '-' || ? || ' days')
                ORDER BY snapshot_date DESC
            """, (category, kpi_name, days))
            return [dict(row) for row in cursor.fetchall()]

    # ========== Tracking Record Methods ==========

    def record_promise_to_pay(
        self,
        contact_id: int,
        promised_amount: float,
        promised_date: date,
        contact_name: str = None,
        invoice_id: int = None,
    ) -> int:
        """Record a promise-to-pay from a client."""
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO promise_to_pay
                (contact_id, contact_name, invoice_id, promised_amount, promised_date)
                VALUES (?, ?, ?, ?, ?)
            """, (contact_id, contact_name, invoice_id, promised_amount, promised_date))
            return cursor.lastrowid

    def fulfill_promise_to_pay(
        self,
        promise_id: int,
        actual_amount: float,
        payment_date: date = None,
    ):
        """Mark a promise-to-pay as fulfilled."""
        payment_date = payment_date or date.today()
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE promise_to_pay
                SET status = 'fulfilled', actual_amount = ?, actual_payment_date = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (actual_amount, payment_date, promise_id))

    def record_delinquent_followup(
        self,
        invoice_id: int,
        delinquent_date: date,
        contact_id: int = None,
        contact_name: str = None,
    ) -> int:
        """Record when an invoice becomes delinquent."""
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR IGNORE INTO delinquent_followups
                (invoice_id, contact_id, contact_name, delinquent_date)
                VALUES (?, ?, ?, ?)
            """, (invoice_id, contact_id, contact_name, delinquent_date))
            return cursor.lastrowid

    def record_first_contact(
        self,
        invoice_id: int,
        contact_date: date,
        contact_method: str = "call",
    ):
        """Record first contact for a delinquent account."""
        with self.db._get_connection() as conn:
            cursor = conn.cursor()

            # Get delinquent date to calculate SLA
            cursor.execute("""
                SELECT delinquent_date FROM delinquent_followups
                WHERE invoice_id = ? ORDER BY delinquent_date DESC LIMIT 1
            """, (invoice_id,))
            row = cursor.fetchone()

            if row:
                delinquent_date = datetime.strptime(row["delinquent_date"], "%Y-%m-%d").date()
                days_to_contact = (contact_date - delinquent_date).days
                sla_met = days_to_contact <= 1  # 1 business day SLA

                cursor.execute("""
                    UPDATE delinquent_followups
                    SET first_contact_date = ?, first_contact_method = ?,
                        days_to_contact = ?, sla_met = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE invoice_id = ? AND delinquent_date = ?
                """, (contact_date, contact_method, days_to_contact, sla_met,
                      invoice_id, delinquent_date))

    def record_wonky_invoice(
        self,
        invoice_id: int,
        issue_type: str,
        issue_description: str = None,
        invoice_number: str = None,
        case_id: int = None,
        case_name: str = None,
        ea_amount: float = None,
        invoice_amount: float = None,
    ) -> int:
        """Record a wonky invoice that needs correction."""
        discrepancy = None
        if ea_amount is not None and invoice_amount is not None:
            discrepancy = abs(ea_amount - invoice_amount)

        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR IGNORE INTO wonky_invoices
                (invoice_id, invoice_number, case_id, case_name, issue_type,
                 issue_description, ea_amount, invoice_amount, discrepancy)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (invoice_id, invoice_number, case_id, case_name, issue_type,
                  issue_description, ea_amount, invoice_amount, discrepancy))
            return cursor.lastrowid

    def resolve_wonky_invoice(
        self,
        invoice_id: int,
        resolution_notes: str = None,
    ):
        """Mark a wonky invoice as resolved."""
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE wonky_invoices
                SET status = 'resolved', resolved_date = DATE('now'),
                    resolution_notes = ?
                WHERE invoice_id = ? AND status = 'open'
            """, (resolution_notes, invoice_id))

    def record_noiw(
        self,
        case_id: int,
        balance_due: float,
        days_delinquent: int,
        case_name: str = None,
        contact_id: int = None,
        contact_name: str = None,
        invoice_id: int = None,
    ) -> int:
        """Record a Notice of Intent to Withdraw initiation."""
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR IGNORE INTO noiw_tracking
                (case_id, case_name, contact_id, contact_name, invoice_id,
                 balance_due, days_delinquent)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (case_id, case_name, contact_id, contact_name, invoice_id,
                  balance_due, days_delinquent))
            return cursor.lastrowid

    def update_noiw_outcome(
        self,
        case_id: int,
        outcome: str,
        notes: str = None,
    ):
        """Update NOIW outcome (cured, withdrawn, pending)."""
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE noiw_tracking
                SET outcome = ?, outcome_date = DATE('now'), notes = ?
                WHERE case_id = ? AND outcome IS NULL
            """, (outcome, notes, case_id))

    # ========== Report Generation ==========

    def generate_melissa_daily_report(self, target_date: date = None) -> str:
        """
        Generate Melissa's daily collections report (2-3 minute presentation).

        Returns formatted report string.
        """
        kpis = self.calculate_daily_collections_kpis(target_date)

        report = f"""
================================================================================
                    DAILY COLLECTIONS REPORT - {kpis.date}
================================================================================

1. DAILY COLLECTIONS (Cash Received)
   ${kpis.cash_received:,.2f} collected across {kpis.payment_count} payments

2. OUTSTANDING ACCOUNTS RECEIVABLE
   Total AR: ${kpis.total_ar_balance:,.2f}
   ├── 0-30 days:  ${kpis.ar_0_30:,.2f}
   ├── 31-60 days: ${kpis.ar_31_60:,.2f}
   ├── 61-90 days: ${kpis.ar_61_90:,.2f}
   └── 90+ days:   ${kpis.ar_90_plus:,.2f}

3. AGING OVER 60 DAYS
   {kpis.aging_over_60_pct:.1f}% of AR is over 60 days (target <25%)
   {"✓ ON TARGET" if kpis.aging_over_60_pct < 25 else "⚠ NEEDS ATTENTION"}

4. PROMISE-TO-PAY FOLLOW-THROUGH
   {kpis.promises_kept} of {kpis.promises_made} fulfilled ({kpis.promise_rate:.0f}% compliance)

5. NEW PAYMENT ARRANGEMENTS
   {kpis.new_payment_plans} new payment plans, totaling ${kpis.payment_plan_amount:,.2f}

================================================================================
"""
        return report

    def generate_melissa_weekly_report(self, week_end: date = None) -> str:
        """Generate Melissa's weekly collections report."""
        kpis = self.calculate_weekly_collections_kpis(week_end)

        change_symbol = "+" if kpis.collection_change_pct >= 0 else ""
        ar_symbol = "+" if kpis.ar_change_pct >= 0 else ""

        report = f"""
================================================================================
              WEEKLY COLLECTIONS REPORT - {kpis.week_start} to {kpis.week_end}
================================================================================

1. TOTAL COLLECTIONS (Week-to-Date)
   This week: ${kpis.total_collected:,.2f}
   Last week: ${kpis.prior_week_collected:,.2f} ({change_symbol}{kpis.collection_change_pct:.1f}%)

2. AR TREND
   Start of week: ${kpis.ar_trend_start:,.2f}
   End of week:   ${kpis.ar_trend_end:,.2f} ({ar_symbol}{kpis.ar_change_pct:.1f}%)

3. COLLECTION RATE
   {kpis.collection_rate:.1f}% of invoices collected this period
   Total billed: ${kpis.total_billed:,.2f}

4. PAYMENT PLAN COMPLIANCE (Target ≥90%)
   {kpis.payment_plan_compliance_rate:.1f}% - {kpis.active_payment_plans} active, {kpis.delinquent_plans} behind
   {"✓ ON TARGET" if kpis.payment_plan_compliance_rate >= 90 else "⚠ BELOW TARGET"}

5. DELINQUENT FOLLOW-UP SLA (Target 100%)
   {kpis.delinquent_followup_sla_rate:.1f}% contacted within 1 business day
   {"✓ ON TARGET" if kpis.delinquent_followup_sla_rate >= 100 else "⚠ BELOW TARGET"}

6. WONKY INVOICE THROUGHPUT (Target ≥1.0)
   {kpis.wonky_resolved} resolved / {kpis.wonky_opened} opened = {kpis.wonky_throughput:.2f}
   {"✓ BACKLOG SHRINKING" if kpis.wonky_throughput >= 1.0 else "⚠ BACKLOG GROWING"}

7. NOIW INITIATIONS
   {kpis.noiw_count} new NOIWs this week

8. FOLLOW-UP ACTIVITY
   {kpis.followup_attempts} attempts, {kpis.successful_contacts} successful ({kpis.contact_success_rate:.0f}%)

================================================================================
"""
        return report


if __name__ == "__main__":
    tracker = KPITracker()

    print("Testing KPI Tracker...")
    print("(Requires valid MyCase API authentication)")

    try:
        # Generate daily report
        daily_report = tracker.generate_melissa_daily_report()
        print(daily_report)

        # Generate weekly report
        weekly_report = tracker.generate_melissa_weekly_report()
        print(weekly_report)

    except Exception as e:
        print(f"Error: {e}")
        print("Make sure you've authenticated with: python auth.py")
