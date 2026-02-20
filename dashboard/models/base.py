"""
Dashboard Data Access Layer - Base Class
Read-only access to cached data from PostgreSQL database.
NO live API calls - all data comes from daily sync.
"""
import os
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional

# Add parent directory to path to import existing modules
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import psycopg2.extensions
from db.connection import get_connection
import dashboard.config as config


class DashboardData:
    """Read-only data access for dashboard using cached database data."""

    def __init__(self, firm_id: str = None):
        self.firm_id = firm_id or os.environ.get('DASHBOARD_FIRM_ID') or self._detect_firm_id()
        self.reports_dir = config.REPORTS_DIR

    @staticmethod
    def _detect_firm_id() -> str:
        """Auto-detect the firm_id from cached data."""
        try:
            with get_connection() as conn:
                cur = conn.cursor(cursor_factory=psycopg2.extensions.cursor)
                cur.execute("SELECT DISTINCT firm_id FROM cached_cases LIMIT 1")
                row = cur.fetchone()
                if row:
                    return row[0]
        except Exception:
            pass
        return 'default'

    @staticmethod
    def _cursor(conn):
        """Get a regular tuple cursor for queries that use positional indexing."""
        return conn.cursor(cursor_factory=psycopg2.extensions.cursor)

    def _get_staff_lookup(self) -> Dict[str, str]:
        """Build a staff ID to name lookup dictionary."""
        lookup = {}
        try:
            with get_connection() as conn:
                cursor = self._cursor(conn)
                cursor.execute(
                    "SELECT id, name FROM cached_staff WHERE firm_id = %s",
                    (self.firm_id,)
                )
                for row in cursor.fetchall():
                    lookup[str(row[0])] = row[1]
        except Exception:
            pass
        return lookup

    def _get_staff_id_by_name(self, name: str) -> Optional[str]:
        """Get staff ID from name (partial match)."""
        try:
            with get_connection() as conn:
                cursor = self._cursor(conn)
                cursor.execute(
                    "SELECT id FROM cached_staff WHERE firm_id = %s AND name ILIKE %s",
                    (self.firm_id, f'%{name}%')
                )
                row = cursor.fetchone()
                if row:
                    return str(row[0])
        except Exception:
            pass
        return None

    def _resolve_assignee_ids_to_names(self, assignee_ids_str: str, staff_lookup: Dict[str, str]) -> str:
        """Convert comma-separated staff IDs to names, return first name only."""
        if not assignee_ids_str:
            return 'Unassigned'
        ids = assignee_ids_str.split(',')
        names = []
        for id_str in ids[:1]:  # Only get first assignee for display
            name = staff_lookup.get(id_str.strip(), None)
            if name:
                names.append(name)
        return names[0] if names else 'Unknown'

    def get_recent_reports(self, limit: int = 10) -> list:
        """Get list of recent reports from filesystem."""
        reports = []
        if self.reports_dir.exists():
            for file in sorted(self.reports_dir.glob('*.txt'), reverse=True)[:limit]:
                reports.append({
                    'name': file.name,
                    'path': str(file),
                    'size': file.stat().st_size,
                    'modified': datetime.fromtimestamp(file.stat().st_mtime),
                })
        return reports

    def get_report_content(self, filename: str) -> Optional[str]:
        """Get content of a specific report."""
        report_path = self.reports_dir / filename
        if report_path.exists() and report_path.is_file():
            try:
                return report_path.read_text()
            except Exception as e:
                print(f"Error reading report: {e}")
        return None

    def get_last_sync_time(self) -> Optional[datetime]:
        """Get the timestamp of the last data sync."""
        try:
            with get_connection() as conn:
                cursor = self._cursor(conn)
                cursor.execute("""
                    SELECT MAX(COALESCE(last_incremental_sync, last_full_sync)) as last_sync
                    FROM sync_metadata
                    WHERE firm_id = %s
                """, (self.firm_id,))
                row = cursor.fetchone()
                if row and row[0]:
                    return row[0]
        except Exception:
            pass
        return None

    # ─── Dashboard Stats ───────────────────────────────────────────

    def get_dashboard_stats(self, year: int = None) -> Dict:
        """Get high-level dashboard statistics."""
        current_year = datetime.now().year
        if year is None:
            year = current_year
        try:
            with get_connection() as conn:
                cursor = self._cursor(conn)

                # Total active cases
                cursor.execute("""
                    SELECT COUNT(*) FROM cached_cases
                    WHERE firm_id = %s AND status = 'open'
                """, (self.firm_id,))
                active_cases = cursor.fetchone()[0] or 0

                # Total cases for the year
                cursor.execute("""
                    SELECT COUNT(*) FROM cached_cases
                    WHERE firm_id = %s AND EXTRACT(YEAR FROM created_at) = %s
                """, (self.firm_id, year))
                year_cases = cursor.fetchone()[0] or 0

                # Total open invoices
                cursor.execute("""
                    SELECT COUNT(*), COALESCE(SUM(balance_due), 0)
                    FROM cached_invoices
                    WHERE firm_id = %s AND balance_due > 0
                      AND EXTRACT(YEAR FROM invoice_date) = %s
                """, (self.firm_id, year))
                row = cursor.fetchone()
                open_invoices = row[0] or 0
                total_ar = row[1] or 0

                # Total overdue tasks
                cursor.execute("""
                    SELECT COUNT(*) FROM cached_tasks t
                    JOIN cached_cases c ON t.case_id = c.id AND t.firm_id = c.firm_id
                    WHERE t.firm_id = %s
                      AND t.due_date < CURRENT_DATE
                      AND t.due_date >= CURRENT_DATE - INTERVAL '200 days'
                      AND (t.completed = false OR t.completed IS NULL)
                      AND EXTRACT(YEAR FROM c.created_at) = %s
                """, (self.firm_id, year))
                overdue_tasks = cursor.fetchone()[0] or 0

                # AR aging buckets for Key Metrics section
                if year < current_year:
                    ref_date = f"DATE('{year}-12-31')"
                else:
                    ref_date = "CURRENT_DATE"

                cursor.execute(f"""
                    SELECT
                        COALESCE(SUM(CASE WHEN ({ref_date} - due_date) <= 180 THEN balance_due ELSE 0 END), 0),
                        COALESCE(SUM(CASE WHEN ({ref_date} - due_date) > 180 THEN balance_due ELSE 0 END), 0),
                        COALESCE(SUM(CASE WHEN ({ref_date} - due_date) BETWEEN 61 AND 120 THEN balance_due ELSE 0 END), 0),
                        COALESCE(SUM(balance_due), 0)
                    FROM cached_invoices
                    WHERE firm_id = %s AND balance_due > 0
                      AND EXTRACT(YEAR FROM invoice_date) = %s
                """, (self.firm_id, year))
                ar_row = cursor.fetchone()
                ar_under_180 = ar_row[0] or 0
                ar_over_180 = ar_row[1] or 0
                ar_60_to_120 = ar_row[2] or 0
                total_ar_all = ar_row[3] or 0

                # Get today's payments
                today_collected = 0
                payment_count = 0
                try:
                    cursor.execute("""
                        SELECT COALESCE(SUM(amount), 0), COUNT(*)
                        FROM cached_payments
                        WHERE firm_id = %s AND DATE(payment_date) = CURRENT_DATE
                    """, (self.firm_id,))
                    pay_row = cursor.fetchone()
                    today_collected = pay_row[0] or 0
                    payment_count = pay_row[1] or 0
                except Exception:
                    pass

                # Payment plans summary
                active_plans = 0
                delinquent_plans = 0
                try:
                    cursor.execute("""
                        SELECT
                            COUNT(CASE WHEN status = 'active' THEN 1 END),
                            COUNT(CASE WHEN status = 'delinquent' THEN 1 END)
                        FROM payment_plans WHERE firm_id = %s
                    """, (self.firm_id,))
                    plan_row = cursor.fetchone()
                    active_plans = plan_row[0] or 0
                    delinquent_plans = plan_row[1] or 0
                except Exception:
                    pass

                # NOIW pipeline count
                noiw_pipeline = 0
                try:
                    cursor.execute("""
                        SELECT COUNT(*) FROM noiw_tracking
                        WHERE firm_id = %s AND status NOT IN ('resolved', 'withdrawn')
                    """, (self.firm_id,))
                    noiw_pipeline = cursor.fetchone()[0] or 0
                except Exception:
                    pass

                # Last sync time
                last_sync = self.get_last_sync_time()

                aging_60_to_120_pct = (ar_60_to_120 / total_ar_all * 100) if total_ar_all > 0 else 0

                return {
                    'active_cases': active_cases,
                    'year_cases': year_cases,
                    'open_invoices': open_invoices,
                    'total_ar': total_ar,
                    'overdue_tasks': overdue_tasks,
                    'last_sync': last_sync,
                    'ar_under_180': ar_under_180,
                    'ar_over_180': ar_over_180,
                    'aging_60_to_120_pct': aging_60_to_120_pct,
                    'today_collected': today_collected,
                    'payment_count': payment_count,
                    'active_plans': active_plans,
                    'delinquent_plans': delinquent_plans,
                    'noiw_pipeline': noiw_pipeline,
                }
        except Exception as e:
            print(f"get_dashboard_stats error: {e}")
            return {
                'active_cases': 0, 'year_cases': 0,
                'open_invoices': 0, 'total_ar': 0,
                'overdue_tasks': 0, 'last_sync': None,
                'ar_under_180': 0, 'ar_over_180': 0,
                'aging_60_to_120_pct': 0, 'today_collected': 0,
                'payment_count': 0, 'active_plans': 0,
                'delinquent_plans': 0, 'noiw_pipeline': 0,
            }

    # ─── Staff Caseload (for dashboard widgets) ───────────────────

    def _is_attorney(self, staff_name: str) -> bool:
        """Check if a staff member is an attorney (by staff_type or lead_attorney presence)."""
        try:
            with get_connection() as conn:
                cursor = self._cursor(conn)
                # Check staff_type first
                cursor.execute("""
                    SELECT staff_type FROM cached_staff
                    WHERE firm_id = %s AND name ILIKE %s
                """, (self.firm_id, f'%{staff_name}%'))
                row = cursor.fetchone()
                if row and row[0] and 'attorney' in (row[0] or '').lower():
                    return True
                # Also check if they appear as lead_attorney on any case
                cursor.execute("""
                    SELECT COUNT(*) FROM cached_cases
                    WHERE firm_id = %s AND lead_attorney_name ILIKE %s AND status = 'open'
                """, (self.firm_id, f'%{staff_name}%'))
                return (cursor.fetchone()[0] or 0) > 0
        except Exception:
            return False

    def get_staff_caseload_data(self, staff_name: str) -> Dict:
        """Get caseload summary for a staff member (dashboard widget).

        For attorneys: active cases = cases where they are lead attorney.
        For staff: active cases = cases where they have tasks assigned.
        """
        try:
            with get_connection() as conn:
                cursor = self._cursor(conn)
                staff_id = self._get_staff_id_by_name(staff_name)
                is_attorney = self._is_attorney(staff_name)

                if not staff_id and not is_attorney:
                    return {'active_cases': 0, 'tasks_done': 0, 'tasks_total': 0, 'overdue_tasks': 0}

                # Build assignee filter for tasks (used for task counts)
                assignee_filter = ""
                assignee_params = []
                if staff_id:
                    assignee_filter = "AND (t.assignee_name LIKE %s OR t.assignee_name LIKE %s OR t.assignee_name LIKE %s OR t.assignee_name = %s)"
                    assignee_params = [f'{staff_id},%', f'%,{staff_id},%', f'%,{staff_id}', staff_id]

                # Active cases: attorneys use lead_attorney_name, staff use task assignments
                closed_cases = 0
                if is_attorney:
                    cursor.execute("""
                        SELECT COUNT(*) FROM cached_cases
                        WHERE firm_id = %s AND lead_attorney_name ILIKE %s AND status = 'open'
                    """, (self.firm_id, f'%{staff_name}%'))
                    active_cases = cursor.fetchone()[0] or 0

                    # Closed cases this year for attorneys
                    cursor.execute("""
                        SELECT COUNT(*) FROM cached_cases
                        WHERE firm_id = %s AND lead_attorney_name ILIKE %s AND status = 'closed'
                          AND EXTRACT(YEAR FROM date_closed) = EXTRACT(YEAR FROM CURRENT_DATE)
                    """, (self.firm_id, f'%{staff_name}%'))
                    closed_cases = cursor.fetchone()[0] or 0
                elif staff_id:
                    cursor.execute(f"""
                        SELECT COUNT(DISTINCT t.case_id)
                        FROM cached_tasks t
                        JOIN cached_cases c ON t.case_id = c.id AND t.firm_id = c.firm_id
                        WHERE t.firm_id = %s
                          AND c.status = 'open'
                          {assignee_filter}
                    """, [self.firm_id] + assignee_params)
                    active_cases = cursor.fetchone()[0] or 0
                else:
                    active_cases = 0

                # Tasks done this week
                tasks_done = 0
                if staff_id:
                    cursor.execute(f"""
                        SELECT COUNT(*)
                        FROM cached_tasks t
                        JOIN cached_cases c ON t.case_id = c.id AND t.firm_id = c.firm_id
                        WHERE t.firm_id = %s
                          AND t.completed = true
                          AND DATE(t.completed_at) >= CURRENT_DATE - INTERVAL '7 days'
                          {assignee_filter}
                    """, [self.firm_id] + assignee_params)
                    tasks_done = cursor.fetchone()[0] or 0

                # Total open tasks assigned
                tasks_total = 0
                if staff_id:
                    cursor.execute(f"""
                        SELECT COUNT(*)
                        FROM cached_tasks t
                        JOIN cached_cases c ON t.case_id = c.id AND t.firm_id = c.firm_id
                        WHERE t.firm_id = %s
                          AND (t.completed = false OR t.completed IS NULL)
                          {assignee_filter}
                    """, [self.firm_id] + assignee_params)
                    tasks_total = cursor.fetchone()[0] or 0

                # Overdue tasks
                overdue_tasks = 0
                if staff_id:
                    cursor.execute(f"""
                        SELECT COUNT(*)
                        FROM cached_tasks t
                        JOIN cached_cases c ON t.case_id = c.id AND t.firm_id = c.firm_id
                        WHERE t.firm_id = %s
                          AND t.due_date < CURRENT_DATE
                          AND t.due_date >= CURRENT_DATE - INTERVAL '200 days'
                          AND (t.completed = false OR t.completed IS NULL)
                          {assignee_filter}
                    """, [self.firm_id] + assignee_params)
                    overdue_tasks = cursor.fetchone()[0] or 0

                return {
                    'active_cases': active_cases,
                    'closed_cases': closed_cases,
                    'tasks_done': tasks_done,
                    'tasks_total': tasks_total,
                    'overdue_tasks': overdue_tasks,
                }
        except Exception as e:
            print(f"get_staff_caseload_data error for {staff_name}: {e}")
            return {'active_cases': 0, 'closed_cases': 0, 'tasks_done': 0, 'tasks_total': 0, 'overdue_tasks': 0}

    # ─── Staff Active Cases List (for detail page) ────────────────

    def get_staff_active_cases_list(self, staff_name: str) -> list:
        """Get list of active cases for a staff member (detail page).

        For attorneys: cases where they are lead attorney.
        For staff: cases where they have tasks assigned.
        """
        try:
            with get_connection() as conn:
                cursor = self._cursor(conn)
                is_attorney = self._is_attorney(staff_name)

                if is_attorney:
                    cursor.execute("""
                        SELECT c.id, c.name, c.practice_area as case_type, c.case_number
                        FROM cached_cases c
                        WHERE c.firm_id = %s
                          AND c.lead_attorney_name ILIKE %s
                          AND c.status = 'open'
                        ORDER BY c.name
                    """, (self.firm_id, f'%{staff_name}%'))
                else:
                    staff_id = self._get_staff_id_by_name(staff_name)
                    if not staff_id:
                        return []

                    assignee_filter = "AND (t.assignee_name LIKE %s OR t.assignee_name LIKE %s OR t.assignee_name LIKE %s OR t.assignee_name = %s)"
                    assignee_params = [f'{staff_id},%', f'%,{staff_id},%', f'%,{staff_id}', staff_id]

                    cursor.execute(f"""
                        SELECT DISTINCT c.id, c.name, c.practice_area as case_type, c.case_number
                        FROM cached_cases c
                        JOIN cached_tasks t ON t.case_id = c.id AND t.firm_id = c.firm_id
                        WHERE c.firm_id = %s
                          AND c.status = 'open'
                          {assignee_filter}
                        ORDER BY c.name
                    """, [self.firm_id] + assignee_params)

                return [{'id': r[0], 'name': r[1], 'case_type': r[2], 'case_number': r[3]}
                        for r in cursor.fetchall()]
        except Exception as e:
            print(f"get_staff_active_cases_list error for {staff_name}: {e}")
            return []

    # ─── Attorney Summary (for dashboard widget) ──────────────────

    def get_attorney_summary(self, year: int = None) -> Dict:
        """Get attorney summary for the dashboard home page."""
        current_year = datetime.now().year
        if year is None:
            year = current_year

        # For closed years, freeze aging at Dec 31 of that year
        if year < current_year:
            reference_date = f"DATE('{year}-12-31')"
        else:
            reference_date = "CURRENT_DATE"

        try:
            with get_connection() as conn:
                cursor = self._cursor(conn)

                # Count unique attorneys with active cases
                cursor.execute("""
                    SELECT COUNT(DISTINCT lead_attorney_name)
                    FROM cached_cases
                    WHERE firm_id = %s
                      AND lead_attorney_name IS NOT NULL AND lead_attorney_name != ''
                      AND status = 'open'
                """, (self.firm_id,))
                attorney_count = cursor.fetchone()[0] or 0

                # Total active cases
                cursor.execute("""
                    SELECT COUNT(*) FROM cached_cases
                    WHERE firm_id = %s AND status = 'open'
                """, (self.firm_id,))
                total_active_cases = cursor.fetchone()[0] or 0

                # Invoice aging buckets (DPD = days past due)
                cursor.execute(f"""
                    SELECT
                        COUNT(CASE WHEN i.balance_due = 0 OR i.paid_amount >= i.total_amount THEN 1 END) as paid_full,
                        COUNT(CASE WHEN i.balance_due > 0 AND ({reference_date} - i.due_date) BETWEEN 1 AND 30 THEN 1 END) as dpd_1_30,
                        COUNT(CASE WHEN i.balance_due > 0 AND ({reference_date} - i.due_date) BETWEEN 31 AND 60 THEN 1 END) as dpd_31_60,
                        COUNT(CASE WHEN i.balance_due > 0 AND ({reference_date} - i.due_date) BETWEEN 61 AND 90 THEN 1 END) as dpd_61_90,
                        COUNT(CASE WHEN i.balance_due > 0 AND ({reference_date} - i.due_date) BETWEEN 91 AND 120 THEN 1 END) as dpd_91_120,
                        COUNT(CASE WHEN i.balance_due > 0 AND ({reference_date} - i.due_date) > 180 THEN 1 END) as dpd_180_plus,
                        COALESCE(SUM(i.total_amount), 0) as total_billed,
                        COALESCE(SUM(i.paid_amount), 0) as total_collected
                    FROM cached_invoices i
                    WHERE i.firm_id = %s
                      AND EXTRACT(YEAR FROM i.invoice_date) = %s
                """, (self.firm_id, year))
                row = cursor.fetchone()

                paid_full = row[0] or 0
                dpd_1_30 = row[1] or 0
                dpd_31_60 = row[2] or 0
                dpd_61_90 = row[3] or 0
                dpd_91_120 = row[4] or 0
                dpd_180_plus = row[5] or 0
                total_billed = row[6] or 0
                total_collected = row[7] or 0

                # Top attorneys by billing
                cursor.execute("""
                    SELECT c.lead_attorney_name,
                           COUNT(DISTINCT c.id) as case_count,
                           COALESCE(SUM(i.total_amount), 0) as billed,
                           COALESCE(SUM(i.paid_amount), 0) as collected
                    FROM cached_cases c
                    LEFT JOIN cached_invoices i ON i.case_id = c.id AND i.firm_id = c.firm_id
                        AND EXTRACT(YEAR FROM i.invoice_date) = %s
                    WHERE c.firm_id = %s
                      AND c.lead_attorney_name IS NOT NULL AND c.lead_attorney_name != ''
                      AND c.status = 'open'
                    GROUP BY c.lead_attorney_name
                    ORDER BY billed DESC
                    LIMIT 5
                """, (year, self.firm_id))
                top_attorneys = [{'name': r[0], 'cases': r[1], 'billed': r[2], 'collected': r[3]}
                                 for r in cursor.fetchall()]

                return {
                    'attorney_count': attorney_count,
                    'total_active_cases': total_active_cases,
                    'total_billed': total_billed,
                    'total_collected': total_collected,
                    'collection_rate': (total_collected / total_billed * 100) if total_billed > 0 else 0,
                    'paid_full': paid_full,
                    'dpd_1_30': dpd_1_30,
                    'dpd_31_60': dpd_31_60,
                    'dpd_61_90': dpd_61_90,
                    'dpd_91_120': dpd_91_120,
                    'dpd_180_plus': dpd_180_plus,
                    'top_attorneys': top_attorneys,
                }
        except Exception as e:
            print(f"get_attorney_summary error: {e}")
            return {
                'attorney_count': 0, 'total_active_cases': 0,
                'total_billed': 0, 'total_collected': 0, 'collection_rate': 0,
                'paid_full': 0, 'dpd_1_30': 0, 'dpd_31_60': 0,
                'dpd_61_90': 0, 'dpd_91_120': 0, 'dpd_180_plus': 0,
                'top_attorneys': [],
            }
