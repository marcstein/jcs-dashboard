"""
Analytics Module

Generates statistics and reports on:
- Time to payment by attorney and case type
- Case flow milestones
- Collections performance
- Attorney productivity
"""
from datetime import datetime, date, timedelta
from typing import List, Dict, Optional
from dataclasses import dataclass
from collections import defaultdict

from api_client import MyCaseClient, get_client, MyCaseAPIError
from database import Database, get_db


@dataclass
class PaymentStats:
    """Payment statistics."""
    avg_days_to_payment: float
    min_days: int
    max_days: int
    total_invoices: int
    total_billed: float
    total_collected: float
    collection_rate: float


@dataclass
class AttorneyMetrics:
    """Metrics for an individual attorney."""
    attorney_id: int
    attorney_name: str
    total_cases: int
    active_cases: int
    closed_cases: int
    total_billed: float
    total_collected: float
    avg_days_to_payment: float
    overdue_invoices: int
    overdue_amount: float


@dataclass
class CaseMilestone:
    """Case milestone/stage statistics."""
    stage_name: str
    case_count: int
    avg_days_to_reach: float


class AnalyticsManager:
    """
    Generates analytics and reports from MyCase data.
    """

    def __init__(
        self,
        client: MyCaseClient = None,
        db: Database = None,
    ):
        self.client = client or get_client()
        self.db = db or get_db()

    def sync_invoice_data(self) -> int:
        """
        Sync invoice data from MyCase for analytics.

        Returns:
            Number of invoices synced
        """
        synced = 0

        try:
            invoices = self.client.get_all_pages(self.client.get_invoices)

            for invoice in invoices:
                invoice_id = invoice.get("id")
                if not invoice_id:
                    continue

                # Get related data
                case = invoice.get("case", {})
                contact = invoice.get("contact", {})

                # Get attorney from case if available
                attorney = {}
                if case.get("id"):
                    try:
                        case_detail = self.client.get_case(case.get("id"))
                        users = case_detail.get("users", [])
                        if users:
                            attorney = users[0]
                    except Exception:
                        pass

                # Parse dates
                invoice_date = None
                due_date = None
                paid_date = None

                if invoice.get("invoice_date"):
                    invoice_date = datetime.fromisoformat(
                        invoice.get("invoice_date").replace("Z", "+00:00")
                    ).date()

                if invoice.get("due_date"):
                    due_date = datetime.fromisoformat(
                        invoice.get("due_date").replace("Z", "+00:00")
                    ).date()

                if invoice.get("paid_date"):
                    paid_date = datetime.fromisoformat(
                        invoice.get("paid_date").replace("Z", "+00:00")
                    ).date()

                # Calculate days to payment
                days_to_payment = None
                if invoice_date and paid_date:
                    days_to_payment = (paid_date - invoice_date).days

                # Get amounts
                total_amount = float(invoice.get("total", 0))
                amount_paid = float(invoice.get("amount_paid", 0))
                balance_due = float(invoice.get("balance_due", total_amount - amount_paid))

                self.db.record_invoice_snapshot(
                    invoice_id=invoice_id,
                    invoice_number=invoice.get("number"),
                    case_id=case.get("id"),
                    case_name=case.get("name"),
                    case_type=case.get("practice_area"),
                    contact_id=contact.get("id"),
                    attorney_id=attorney.get("id"),
                    attorney_name=attorney.get("name"),
                    total_amount=total_amount,
                    amount_paid=amount_paid,
                    balance_due=balance_due,
                    invoice_date=invoice_date,
                    due_date=due_date,
                    paid_date=paid_date,
                    days_to_payment=days_to_payment,
                    status=invoice.get("status"),
                )
                synced += 1

        except MyCaseAPIError as e:
            print(f"Error syncing invoices: {e}")

        return synced

    def sync_case_stages(self) -> int:
        """
        Sync case stage data for milestone tracking.

        Returns:
            Number of case stages recorded
        """
        synced = 0

        try:
            cases = self.client.get_all_pages(self.client.get_cases)

            for case in cases:
                case_id = case.get("id")
                stage = case.get("stage", {})
                stage_name = stage.get("name") if stage else None

                if not case_id or not stage_name:
                    continue

                # Get attorney
                users = case.get("users", [])
                attorney = users[0] if users else {}

                self.db.record_case_stage_change(
                    case_id=case_id,
                    stage_name=stage_name,
                    case_name=case.get("name"),
                    case_type=case.get("practice_area"),
                    attorney_id=attorney.get("id"),
                    attorney_name=attorney.get("name"),
                )
                synced += 1

        except MyCaseAPIError as e:
            print(f"Error syncing case stages: {e}")

        return synced

    def get_time_to_payment_by_attorney(
        self,
        start_date: date = None,
        end_date: date = None,
    ) -> Dict[str, PaymentStats]:
        """
        Get time-to-payment statistics grouped by attorney.

        Args:
            start_date: Filter invoices from this date
            end_date: Filter invoices until this date

        Returns:
            Dictionary of attorney name -> PaymentStats
        """
        stats_by_attorney = {}

        # Query from database
        # For now, we'll calculate from the invoice snapshots
        try:
            with self.db._get_connection() as conn:
                cursor = conn.cursor()
                query = """
                    SELECT
                        attorney_name,
                        AVG(days_to_payment) as avg_days,
                        MIN(days_to_payment) as min_days,
                        MAX(days_to_payment) as max_days,
                        COUNT(*) as invoice_count,
                        SUM(total_amount) as total_billed,
                        SUM(amount_paid) as total_collected
                    FROM invoice_snapshots
                    WHERE days_to_payment IS NOT NULL
                    AND status = 'paid'
                    AND attorney_name IS NOT NULL
                """
                params = []

                if start_date:
                    query += " AND invoice_date >= ?"
                    params.append(start_date.isoformat())
                if end_date:
                    query += " AND invoice_date <= ?"
                    params.append(end_date.isoformat())

                query += " GROUP BY attorney_name"
                cursor.execute(query, params)

                for row in cursor.fetchall():
                    attorney_name = row["attorney_name"]
                    total_billed = row["total_billed"] or 0
                    total_collected = row["total_collected"] or 0
                    collection_rate = (
                        (total_collected / total_billed * 100)
                        if total_billed > 0 else 0
                    )

                    stats_by_attorney[attorney_name] = PaymentStats(
                        avg_days_to_payment=row["avg_days"] or 0,
                        min_days=row["min_days"] or 0,
                        max_days=row["max_days"] or 0,
                        total_invoices=row["invoice_count"] or 0,
                        total_billed=total_billed,
                        total_collected=total_collected,
                        collection_rate=collection_rate,
                    )

        except Exception as e:
            print(f"Error getting payment stats: {e}")

        return stats_by_attorney

    def get_time_to_payment_by_case_type(
        self,
        start_date: date = None,
        end_date: date = None,
    ) -> Dict[str, PaymentStats]:
        """
        Get time-to-payment statistics grouped by case type.

        Args:
            start_date: Filter invoices from this date
            end_date: Filter invoices until this date

        Returns:
            Dictionary of case type -> PaymentStats
        """
        stats_by_type = {}

        try:
            with self.db._get_connection() as conn:
                cursor = conn.cursor()
                query = """
                    SELECT
                        COALESCE(case_type, 'Unknown') as case_type,
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

                if start_date:
                    query += " AND invoice_date >= ?"
                    params.append(start_date.isoformat())
                if end_date:
                    query += " AND invoice_date <= ?"
                    params.append(end_date.isoformat())

                query += " GROUP BY case_type"
                cursor.execute(query, params)

                for row in cursor.fetchall():
                    case_type = row["case_type"]
                    total_billed = row["total_billed"] or 0
                    total_collected = row["total_collected"] or 0
                    collection_rate = (
                        (total_collected / total_billed * 100)
                        if total_billed > 0 else 0
                    )

                    stats_by_type[case_type] = PaymentStats(
                        avg_days_to_payment=row["avg_days"] or 0,
                        min_days=row["min_days"] or 0,
                        max_days=row["max_days"] or 0,
                        total_invoices=row["invoice_count"] or 0,
                        total_billed=total_billed,
                        total_collected=total_collected,
                        collection_rate=collection_rate,
                    )

        except Exception as e:
            print(f"Error getting payment stats by case type: {e}")

        return stats_by_type

    def get_case_flow_milestones(
        self,
        case_type: str = None,
    ) -> List[CaseMilestone]:
        """
        Get case flow milestone statistics.

        Args:
            case_type: Filter by case type

        Returns:
            List of CaseMilestone objects
        """
        milestones = self.db.get_case_milestone_stats(case_type=case_type)

        return [
            CaseMilestone(
                stage_name=m["stage_name"],
                case_count=m["case_count"],
                avg_days_to_reach=m["avg_days_to_reach"] or 0,
            )
            for m in milestones
        ]

    def get_attorney_metrics(self) -> List[AttorneyMetrics]:
        """
        Get comprehensive metrics for each attorney.

        Returns:
            List of AttorneyMetrics objects
        """
        metrics = []

        try:
            with self.db._get_connection() as conn:
                cursor = conn.cursor()

                # Get unique attorneys
                cursor.execute("""
                    SELECT DISTINCT attorney_id, attorney_name
                    FROM invoice_snapshots
                    WHERE attorney_id IS NOT NULL
                """)
                attorneys = cursor.fetchall()

                for atty in attorneys:
                    attorney_id = atty["attorney_id"]
                    attorney_name = atty["attorney_name"]

                    # Get invoice stats
                    cursor.execute("""
                        SELECT
                            COUNT(*) as total_invoices,
                            SUM(total_amount) as total_billed,
                            SUM(amount_paid) as total_collected,
                            AVG(CASE WHEN status = 'paid' THEN days_to_payment END) as avg_days,
                            SUM(CASE WHEN status IN ('overdue', 'partial') THEN 1 ELSE 0 END) as overdue_count,
                            SUM(CASE WHEN status IN ('overdue', 'partial') THEN balance_due ELSE 0 END) as overdue_amount
                        FROM invoice_snapshots
                        WHERE attorney_id = ?
                    """, (attorney_id,))
                    row = cursor.fetchone()

                    # Get case counts (would need case data)
                    cursor.execute("""
                        SELECT COUNT(DISTINCT case_id) as case_count
                        FROM invoice_snapshots
                        WHERE attorney_id = ?
                    """, (attorney_id,))
                    case_row = cursor.fetchone()

                    metrics.append(AttorneyMetrics(
                        attorney_id=attorney_id,
                        attorney_name=attorney_name or "Unknown",
                        total_cases=case_row["case_count"] if case_row else 0,
                        active_cases=0,  # Would need to query cases
                        closed_cases=0,  # Would need to query cases
                        total_billed=row["total_billed"] or 0,
                        total_collected=row["total_collected"] or 0,
                        avg_days_to_payment=row["avg_days"] or 0,
                        overdue_invoices=row["overdue_count"] or 0,
                        overdue_amount=row["overdue_amount"] or 0,
                    ))

        except Exception as e:
            print(f"Error getting attorney metrics: {e}")

        return metrics

    def generate_executive_summary(self) -> Dict:
        """
        Generate an executive summary report.

        Returns:
            Dictionary with summary statistics
        """
        summary = {
            "generated_at": datetime.now().isoformat(),
            "period": "All Time",  # Could be parameterized
            "billing": {
                "total_billed": 0.0,
                "total_collected": 0.0,
                "total_outstanding": 0.0,
                "collection_rate": 0.0,
            },
            "payments": {
                "avg_days_to_payment": 0,
                "fastest_payment": 0,
                "slowest_payment": 0,
            },
            "collections": {
                "total_overdue": 0.0,
                "invoices_overdue": 0,
            },
            "by_attorney": [],
            "by_case_type": [],
        }

        try:
            with self.db._get_connection() as conn:
                cursor = conn.cursor()

                # Overall billing stats
                cursor.execute("""
                    SELECT
                        SUM(total_amount) as total_billed,
                        SUM(amount_paid) as total_collected,
                        SUM(balance_due) as total_outstanding,
                        AVG(CASE WHEN status = 'paid' THEN days_to_payment END) as avg_days,
                        MIN(CASE WHEN status = 'paid' THEN days_to_payment END) as min_days,
                        MAX(CASE WHEN status = 'paid' THEN days_to_payment END) as max_days,
                        SUM(CASE WHEN status IN ('overdue', 'partial') THEN balance_due ELSE 0 END) as overdue_amount,
                        SUM(CASE WHEN status IN ('overdue', 'partial') THEN 1 ELSE 0 END) as overdue_count
                    FROM invoice_snapshots
                """)
                row = cursor.fetchone()

                if row:
                    total_billed = row["total_billed"] or 0
                    total_collected = row["total_collected"] or 0

                    summary["billing"]["total_billed"] = total_billed
                    summary["billing"]["total_collected"] = total_collected
                    summary["billing"]["total_outstanding"] = row["total_outstanding"] or 0
                    summary["billing"]["collection_rate"] = (
                        (total_collected / total_billed * 100)
                        if total_billed > 0 else 0
                    )

                    summary["payments"]["avg_days_to_payment"] = row["avg_days"] or 0
                    summary["payments"]["fastest_payment"] = row["min_days"] or 0
                    summary["payments"]["slowest_payment"] = row["max_days"] or 0

                    summary["collections"]["total_overdue"] = row["overdue_amount"] or 0
                    summary["collections"]["invoices_overdue"] = row["overdue_count"] or 0

        except Exception as e:
            print(f"Error generating summary: {e}")

        # Add attorney breakdown
        attorney_stats = self.get_time_to_payment_by_attorney()
        for name, stats in attorney_stats.items():
            summary["by_attorney"].append({
                "name": name,
                "avg_days": stats.avg_days_to_payment,
                "total_billed": stats.total_billed,
                "total_collected": stats.total_collected,
                "collection_rate": stats.collection_rate,
            })

        # Add case type breakdown
        case_type_stats = self.get_time_to_payment_by_case_type()
        for case_type, stats in case_type_stats.items():
            summary["by_case_type"].append({
                "type": case_type,
                "avg_days": stats.avg_days_to_payment,
                "total_billed": stats.total_billed,
                "collection_rate": stats.collection_rate,
            })

        return summary


def format_currency(amount: float) -> str:
    """Format amount as currency."""
    return f"${amount:,.2f}"


def print_executive_summary(summary: Dict):
    """Print a formatted executive summary."""
    print("\n" + "=" * 60)
    print("EXECUTIVE SUMMARY")
    print(f"Generated: {summary['generated_at']}")
    print("=" * 60)

    print("\nBILLING OVERVIEW")
    print("-" * 40)
    print(f"  Total Billed:      {format_currency(summary['billing']['total_billed'])}")
    print(f"  Total Collected:   {format_currency(summary['billing']['total_collected'])}")
    print(f"  Outstanding:       {format_currency(summary['billing']['total_outstanding'])}")
    print(f"  Collection Rate:   {summary['billing']['collection_rate']:.1f}%")

    print("\nPAYMENT METRICS")
    print("-" * 40)
    print(f"  Avg Days to Payment: {summary['payments']['avg_days_to_payment']:.0f}")
    print(f"  Fastest Payment:     {summary['payments']['fastest_payment']} days")
    print(f"  Slowest Payment:     {summary['payments']['slowest_payment']} days")

    print("\nCOLLECTIONS")
    print("-" * 40)
    print(f"  Overdue Amount:    {format_currency(summary['collections']['total_overdue'])}")
    print(f"  Overdue Invoices:  {summary['collections']['invoices_overdue']}")

    if summary["by_attorney"]:
        print("\nBY ATTORNEY")
        print("-" * 40)
        for atty in summary["by_attorney"]:
            print(f"  {atty['name']}:")
            print(f"    Avg Days: {atty['avg_days']:.0f} | Collection: {atty['collection_rate']:.1f}%")

    if summary["by_case_type"]:
        print("\nBY CASE TYPE")
        print("-" * 40)
        for ct in summary["by_case_type"]:
            print(f"  {ct['type']}:")
            print(f"    Avg Days: {ct['avg_days']:.0f} | Collection: {ct['collection_rate']:.1f}%")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    analytics = AnalyticsManager()

    print("=== Analytics Manager Test ===")
    print("(Note: Requires valid API authentication and synced data)")

    try:
        # Sync data
        print("\nSyncing invoice data...")
        invoices_synced = analytics.sync_invoice_data()
        print(f"Synced {invoices_synced} invoices")

        print("\nSyncing case stages...")
        stages_synced = analytics.sync_case_stages()
        print(f"Synced {stages_synced} case stages")

        # Generate summary
        print("\nGenerating executive summary...")
        summary = analytics.generate_executive_summary()
        print_executive_summary(summary)

    except Exception as e:
        print(f"Error: {e}")
        print("Make sure you've authenticated with: python auth.py")
