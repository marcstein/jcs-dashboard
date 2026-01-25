"""
Dashboard Data Access Layer
Read-only access to cached data from local SQLite database.
NO live API calls - all data comes from daily sync.
"""
import sqlite3
import sys
from pathlib import Path
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional
from contextlib import contextmanager

# Add parent directory to path to import existing modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from database import get_db
import dashboard.config as config

# Cache database path
CACHE_DB_PATH = Path(__file__).parent.parent / "data" / "mycase_cache.db"


class DashboardData:
    """Read-only data access for dashboard using cached database data."""

    def __init__(self):
        self.db = get_db()
        self.reports_dir = config.REPORTS_DIR
        self.cache_db_path = CACHE_DB_PATH

    @contextmanager
    def _get_cache_connection(self):
        """Get connection to the cache database."""
        conn = sqlite3.connect(self.cache_db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _get_staff_lookup(self) -> Dict[str, str]:
        """Build a staff ID to name lookup dictionary."""
        lookup = {}
        try:
            if self.cache_db_path.exists():
                with self._get_cache_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT id, name FROM cached_staff")
                    for row in cursor.fetchall():
                        lookup[str(row['id'])] = row['name']
        except Exception:
            pass
        return lookup

    def _get_staff_id_by_name(self, name: str) -> Optional[str]:
        """Get staff ID from name (partial match)."""
        try:
            if self.cache_db_path.exists():
                with self._get_cache_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT id FROM cached_staff WHERE name LIKE ?", (f'%{name}%',))
                    row = cursor.fetchone()
                    if row:
                        return str(row['id'])
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

    def get_daily_collections_summary(self, target_date: date = None, year: int = None) -> Dict:
        """Get daily collections summary from cached invoices for specified year."""
        target_date = target_date or date.today()
        current_year = datetime.now().year
        if year is None:
            year = current_year

        # For closed years, freeze aging at Dec 31 of that year
        if year < current_year:
            reference_date = f"'{year}-12-31'"
        else:
            reference_date = "'now'"

        # First try to get data from the cache database (cached_invoices)
        try:
            if self.cache_db_path.exists():
                with self._get_cache_connection() as conn:
                    cursor = conn.cursor()
                    # Filter to specified year invoices
                    cursor.execute(f"""
                        SELECT
                            SUM(balance_due) as total_ar,
                            SUM(CASE WHEN julianday({reference_date}) - julianday(due_date) < 0 THEN balance_due ELSE 0 END) as ar_current,
                            SUM(CASE WHEN julianday({reference_date}) - julianday(due_date) BETWEEN 0 AND 30 THEN balance_due ELSE 0 END) as ar_0_30,
                            SUM(CASE WHEN julianday({reference_date}) - julianday(due_date) BETWEEN 31 AND 60 THEN balance_due ELSE 0 END) as ar_31_60,
                            SUM(CASE WHEN julianday({reference_date}) - julianday(due_date) BETWEEN 61 AND 90 THEN balance_due ELSE 0 END) as ar_61_90,
                            SUM(CASE WHEN julianday({reference_date}) - julianday(due_date) BETWEEN 91 AND 120 THEN balance_due ELSE 0 END) as ar_91_120,
                            SUM(CASE WHEN julianday({reference_date}) - julianday(due_date) > 120 THEN balance_due ELSE 0 END) as ar_120_plus,
                            SUM(CASE WHEN julianday({reference_date}) - julianday(due_date) > 90 THEN balance_due ELSE 0 END) as ar_90_plus,
                            SUM(CASE WHEN julianday({reference_date}) - julianday(due_date) <= 180 THEN balance_due ELSE 0 END) as ar_under_180,
                            SUM(CASE WHEN julianday({reference_date}) - julianday(due_date) > 180 THEN balance_due ELSE 0 END) as ar_over_180,
                            COUNT(CASE WHEN balance_due > 0 AND julianday({reference_date}) - julianday(due_date) > 30 THEN 1 END) as delinquent
                        FROM cached_invoices
                        WHERE balance_due > 0
                          AND strftime('%Y', invoice_date) = '{year}'
                    """)

                    row = cursor.fetchone()

                    # Get total billed and collected for specified year invoices
                    cursor.execute(f"""
                        SELECT SUM(total_amount) as total_billed, SUM(paid_amount) as total_collected
                        FROM cached_invoices
                        WHERE strftime('%Y', invoice_date) = '{year}'
                    """)
                    billing_row = cursor.fetchone()
                    total_billed = billing_row['total_billed'] or 0 if billing_row else 0
                    total_collected = billing_row['total_collected'] or 0 if billing_row else 0

                    if row and row['total_ar']:
                        total_ar = row['total_ar'] or 0
                        ar_current = row['ar_current'] or 0
                        ar_0_30 = row['ar_0_30'] or 0
                        ar_31_60 = row['ar_31_60'] or 0
                        ar_61_90 = row['ar_61_90'] or 0
                        ar_91_120 = row['ar_91_120'] or 0
                        ar_120_plus = row['ar_120_plus'] or 0
                        ar_90_plus = row['ar_90_plus'] or 0
                        # 60-120 days (actionable aging, excludes old skewed invoices)
                        aging_60_to_120 = ar_61_90 + ar_91_120
                        aging_60_to_120_pct = (aging_60_to_120 / total_billed * 100) if total_billed > 0 else 0
                        # Percentage of total billing that is >60 days past due
                        over_60 = ar_61_90 + ar_90_plus
                        over_60_pct = (over_60 / total_billed * 100) if total_billed > 0 else 0

                        # Get today's payments from cached_payments if available (for specified year)
                        cash_received = 0
                        payment_count = 0
                        try:
                            cursor.execute(f"""
                                SELECT SUM(amount) as total, COUNT(*) as count
                                FROM cached_payments
                                WHERE DATE(payment_date) = DATE({reference_date})
                                  AND strftime('%Y', payment_date) = '{year}'
                            """)
                            prow = cursor.fetchone()
                            if prow and prow['total']:
                                cash_received = prow['total'] or 0
                                payment_count = prow['count'] or 0
                        except Exception:
                            pass

                        ar_under_180 = row['ar_under_180'] or 0
                        ar_over_180 = row['ar_over_180'] or 0

                        # Collection rate = collected / billed
                        collection_rate = (total_collected / total_billed * 100) if total_billed > 0 else 0

                        return {
                            'date': str(target_date),
                            'cash_received': cash_received,
                            'payment_count': payment_count,
                            'total_ar': total_ar,
                            'total_billed': total_billed,
                            'ar_current': ar_current,
                            'ar_0_30': ar_0_30,
                            'ar_31_60': ar_31_60,
                            'ar_61_90': ar_61_90,
                            'ar_91_120': ar_91_120,
                            'ar_120_plus': ar_120_plus,
                            'ar_90_plus': ar_90_plus,
                            'ar_under_180': ar_under_180,
                            'ar_over_180': ar_over_180,
                            'aging_over_60_pct': over_60_pct,
                            'aging_60_to_120_pct': aging_60_to_120_pct,
                            'delinquent_accounts': row['delinquent'] or 0,
                            'total_collected': total_collected,
                            'collection_rate': collection_rate,
                        }
        except Exception:
            pass  # Fall through to legacy method

        # Fallback to legacy KPI snapshots
        with self.db._get_connection() as conn:
            cursor = conn.cursor()

            # Try to get cached KPI data for this date (or most recent)
            cursor.execute("""
                SELECT kpi_name, kpi_value
                FROM kpi_daily_snapshots
                WHERE category = 'collections'
                  AND snapshot_date = (
                      SELECT MAX(snapshot_date) FROM kpi_daily_snapshots
                      WHERE snapshot_date <= ?
                  )
            """, (str(target_date),))

            rows = cursor.fetchall()

            if rows:
                # Build from cached KPIs
                kpis = {row['kpi_name']: row['kpi_value'] for row in rows}
                return {
                    'date': str(target_date),
                    'cash_received': kpis.get('cash_received', 0),
                    'payment_count': int(kpis.get('payment_count', 0)),
                    'total_ar': kpis.get('total_ar', 0),
                    'ar_0_30': kpis.get('ar_0_30', 0),
                    'ar_31_60': kpis.get('ar_31_60', 0),
                    'ar_61_90': kpis.get('ar_61_90', 0),
                    'ar_90_plus': kpis.get('ar_90_plus', 0),
                    'aging_over_60_pct': kpis.get('aging_over_60_pct', 0),
                    'delinquent_accounts': int(kpis.get('delinquent_accounts', 0)),
                }

            # No data at all - return empty placeholder
            return {
                'date': str(target_date),
                'cash_received': 0,
                'payment_count': 0,
                'total_ar': 0,
                'ar_0_30': 0,
                'ar_31_60': 0,
                'ar_61_90': 0,
                'ar_90_plus': 0,
                'aging_over_60_pct': 0,
                'delinquent_accounts': 0,
                'no_data': True,
            }

    def get_ar_aging_breakdown(self, year: int = None) -> Dict:
        """Get AR aging breakdown for charts (for specified year)."""
        summary = self.get_daily_collections_summary(year=year)
        # Use OrderedDict-like insertion order (Python 3.7+) for display order
        return {
            'Collected': summary.get('total_collected', 0),
            'Current': summary.get('ar_current', 0),
            '0-30 days': summary.get('ar_0_30', 0),
            '31-60 days': summary.get('ar_31_60', 0),
            '61-90 days': summary.get('ar_61_90', 0),
            '90+ days': summary.get('ar_90_plus', 0),
        }

    def get_collections_trend(self, days_back: int = 30) -> List[Dict]:
        """Get collections trend for the last N days."""
        with self.db._get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                SELECT snapshot_date, SUM(kpi_value) as total
                FROM kpi_daily_snapshots
                WHERE category = 'collections'
                  AND kpi_name = 'cash_received'
                  AND snapshot_date >= DATE('now', ?)
                GROUP BY snapshot_date
                ORDER BY snapshot_date
            """, (f'-{days_back} days',))

            rows = cursor.fetchall()
            return [{'date': row['snapshot_date'], 'amount': row['total']} for row in rows]

    def get_payment_plans_summary(self) -> Dict:
        """Get payment plans summary from local database."""
        with self.db._get_connection() as conn:
            cursor = conn.cursor()

            # Active plans
            cursor.execute("""
                SELECT COUNT(*) as count, COALESCE(SUM(total_amount), 0) as total
                FROM payment_plans
                WHERE status = 'active'
            """)
            active = cursor.fetchone()

            # Delinquent plans
            cursor.execute("""
                SELECT COUNT(*) as count
                FROM payment_plans
                WHERE status = 'delinquent'
            """)
            delinquent = cursor.fetchone()

            # Completed this month
            cursor.execute("""
                SELECT COUNT(*) as count
                FROM payment_plans
                WHERE status = 'completed'
                  AND DATE(updated_at) >= DATE('now', 'start of month')
            """)
            completed = cursor.fetchone()

            return {
                'active_count': active['count'] if active else 0,
                'active_total': active['total'] if active else 0,
                'delinquent_count': delinquent['count'] if delinquent else 0,
                'completed_month': completed['count'] if completed else 0,
            }

    def get_recent_reports(self, limit: int = 10) -> List[Dict]:
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

    def get_noiw_pipeline(self, status_filter: str = None) -> List[Dict]:
        """Get NOIW pipeline cases from local database."""
        with self.db._get_connection() as conn:
            cursor = conn.cursor()

            if status_filter:
                cursor.execute("""
                    SELECT case_id, case_name, contact_name, invoice_id, balance_due,
                           days_delinquent, status, assigned_to, warning_sent_date,
                           final_notice_date, created_at, updated_at
                    FROM noiw_tracking
                    WHERE status = ?
                    ORDER BY days_delinquent ASC, balance_due DESC
                """, (status_filter,))
            else:
                cursor.execute("""
                    SELECT case_id, case_name, contact_name, invoice_id, balance_due,
                           days_delinquent, status, assigned_to, warning_sent_date,
                           final_notice_date, created_at, updated_at
                    FROM noiw_tracking
                    WHERE status NOT IN ('resolved', 'withdrawn')
                    ORDER BY days_delinquent ASC, balance_due DESC
                """)

            rows = cursor.fetchall()
            return [{
                'case_id': row['case_id'],
                'case_name': row['case_name'],
                'contact_name': row['contact_name'],
                'invoice_id': row['invoice_id'],
                'balance_due': row['balance_due'],
                'days_delinquent': row['days_delinquent'],
                'status': row['status'],
                'assigned_to': row['assigned_to'],
                'warning_sent_date': row['warning_sent_date'],
                'final_notice_date': row['final_notice_date'],
                'created_at': row['created_at'],
                'updated_at': row['updated_at'],
            } for row in rows]

    def get_noiw_summary(self) -> Dict:
        """Get NOIW pipeline summary statistics."""
        with self.db._get_connection() as conn:
            cursor = conn.cursor()

            # Get status counts
            cursor.execute("""
                SELECT status, COUNT(*) as count, SUM(balance_due) as total_balance
                FROM noiw_tracking
                GROUP BY status
            """)
            by_status = {}
            for row in cursor.fetchall():
                by_status[row['status']] = {
                    'count': row['count'],
                    'total_balance': row['total_balance'] or 0
                }

            # Get age buckets for active cases
            cursor.execute("""
                SELECT
                    SUM(CASE WHEN days_delinquent >= 30 AND days_delinquent < 60 THEN 1 ELSE 0 END) as bucket_30_60,
                    SUM(CASE WHEN days_delinquent >= 60 AND days_delinquent < 90 THEN 1 ELSE 0 END) as bucket_60_90,
                    SUM(CASE WHEN days_delinquent >= 90 AND days_delinquent < 180 THEN 1 ELSE 0 END) as bucket_90_180,
                    SUM(CASE WHEN days_delinquent >= 180 THEN 1 ELSE 0 END) as bucket_180_plus,
                    COUNT(*) as total_active,
                    SUM(balance_due) as total_balance
                FROM noiw_tracking
                WHERE status NOT IN ('resolved', 'withdrawn')
            """)
            totals = cursor.fetchone()

            return {
                'by_status': by_status,
                'bucket_30_60': totals['bucket_30_60'] or 0,
                'bucket_60_90': totals['bucket_60_90'] or 0,
                'bucket_90_180': totals['bucket_90_180'] or 0,
                'bucket_180_plus': totals['bucket_180_plus'] or 0,
                'total_active': totals['total_active'] or 0,
                'total_balance': totals['total_balance'] or 0,
            }

    def get_wonky_invoices(self) -> List[Dict]:
        """Get open wonky invoices from local database."""
        with self.db._get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                SELECT invoice_id, invoice_number, case_name, issue_type,
                       issue_description, discrepancy, opened_date
                FROM wonky_invoices
                WHERE status = 'open'
                ORDER BY opened_date DESC
            """)

            rows = cursor.fetchall()
            return [{
                'invoice_id': row['invoice_id'],
                'invoice_number': row['invoice_number'],
                'case_name': row['case_name'],
                'issue_type': row['issue_type'],
                'description': row['issue_description'],
                'discrepancy': row['discrepancy'],
                'opened_date': row['opened_date'],
            } for row in rows]

    def get_overdue_tasks(self, limit: int = 20) -> List[Dict]:
        """Get overdue tasks from cache database (2025 cases only)."""
        try:
            if not self.cache_db_path.exists():
                raise Exception("Cache database not found")

            with self._get_cache_connection() as conn:
                cursor = conn.cursor()

                # Filter to tasks on 2025 cases, exclude tasks > 200 days overdue (stale)
                cursor.execute("""
                    SELECT t.id, t.name as task_name, c.name as case_name, t.assignee_name,
                           t.due_date, t.priority,
                           CAST(julianday('now') - julianday(t.due_date) AS INTEGER) as days_overdue
                    FROM cached_tasks t
                    LEFT JOIN cached_cases c ON t.case_id = c.id
                    WHERE t.due_date < DATE('now')
                      AND t.due_date >= DATE('now', '-200 days')
                      AND (t.completed = 0 OR t.completed IS NULL)
                      AND strftime('%Y', c.created_at) = '2025'
                    ORDER BY t.due_date ASC
                    LIMIT ?
                """, (limit,))

                rows = cursor.fetchall()
                return [{
                    'task_id': row['id'],
                    'task_name': row['task_name'],
                    'case_name': row['case_name'] or 'Unknown',
                    'assignee': row['assignee_name'],
                    'due_date': row['due_date'],
                    'days_overdue': row['days_overdue'],
                    'priority': row['priority'],
                } for row in rows]
        except Exception:
            return []

    def get_last_sync_time(self) -> Optional[datetime]:
        """Get the timestamp of the last data sync."""
        # First check the cache database sync_metadata
        try:
            if self.cache_db_path.exists():
                with self._get_cache_connection() as conn:
                    cursor = conn.cursor()
                    # Check both full and incremental sync times, use the most recent
                    cursor.execute("""
                        SELECT MAX(COALESCE(last_incremental_sync, last_full_sync)) as last_sync
                        FROM sync_metadata
                    """)
                    row = cursor.fetchone()
                    if row and row['last_sync']:
                        return datetime.fromisoformat(row['last_sync'])
        except Exception:
            pass  # Fall through to legacy method

        # Fallback to legacy invoice_snapshots
        with self.db._get_connection() as conn:
            cursor = conn.cursor()

            # Check most recent snapshot date
            cursor.execute("""
                SELECT MAX(snapshot_date) as last_sync
                FROM invoice_snapshots
            """)
            row = cursor.fetchone()
            if row and row['last_sync']:
                return datetime.strptime(row['last_sync'], '%Y-%m-%d')
        return None

    # =========================================================================
    # SOP Widget Data Methods
    # =========================================================================

    def get_melissa_sop_data(self, year: int = None) -> Dict:
        """Get Melissa (AR Specialist) SOP metrics for specified year."""
        summary = self.get_daily_collections_summary(year=year)
        plans = self.get_payment_plans_summary()
        noiw = self.get_noiw_pipeline()

        # Calculate targets and compliance
        aging_target = 25.0
        aging_actual = summary.get('aging_over_60_pct', 0)
        aging_compliant = aging_actual <= aging_target

        plan_compliance_target = 90.0
        active_plans = plans.get('active_count', 0)
        delinquent_plans = plans.get('delinquent_count', 0)
        if active_plans > 0:
            plan_compliance = ((active_plans - delinquent_plans) / active_plans) * 100
        else:
            plan_compliance = 100.0
        plan_compliant = plan_compliance >= plan_compliance_target

        return {
            'total_ar': summary.get('total_ar', 0),
            'total_billed': summary.get('total_billed', 0),
            'cash_received': summary.get('cash_received', 0),
            'payment_count': summary.get('payment_count', 0),
            # A/R Breakdown by aging bucket
            'total_collected': summary.get('total_collected', 0),
            'collection_rate': summary.get('collection_rate', 0),
            'ar_current': summary.get('ar_current', 0),
            'ar_0_30': summary.get('ar_0_30', 0),
            'ar_31_60': summary.get('ar_31_60', 0),
            'ar_61_90': summary.get('ar_61_90', 0),
            'ar_91_120': summary.get('ar_91_120', 0),
            'ar_120_plus': summary.get('ar_120_plus', 0),
            'ar_90_plus': summary.get('ar_90_plus', 0),
            # Compliance metrics
            'aging_over_60_pct': aging_actual,
            'aging_target': aging_target,
            'aging_compliant': aging_compliant,
            'active_plans': active_plans,
            'delinquent_plans': delinquent_plans,
            'plan_compliance': plan_compliance,
            'plan_compliance_target': plan_compliance_target,
            'plan_compliant': plan_compliant,
            'noiw_count': len(noiw),
            'noiw_total': sum(n.get('balance_due', 0) for n in noiw),
        }

    def get_ty_sop_data(self) -> Dict:
        """Get Ty (Intake Lead) SOP metrics from cache database (2025 data only)."""
        try:
            if not self.cache_db_path.exists():
                raise Exception("Cache database not found")

            with self._get_cache_connection() as conn:
                cursor = conn.cursor()

                # New cases in last 7 days (on 2025 cases)
                cursor.execute("""
                    SELECT COUNT(*) as count
                    FROM cached_cases
                    WHERE strftime('%Y', created_at) = '2025'
                      AND DATE(created_at) >= DATE('now', '-7 days')
                """)
                row = cursor.fetchone()
                new_cases_week = row['count'] if row else 0

                # New cases in last 30 days (2025 cases)
                cursor.execute("""
                    SELECT COUNT(*) as count
                    FROM cached_cases
                    WHERE strftime('%Y', created_at) = '2025'
                      AND DATE(created_at) >= DATE('now', '-30 days')
                """)
                row = cursor.fetchone()
                new_cases_month = row['count'] if row else 0

                # Case type breakdown (2025)
                cursor.execute("""
                    SELECT practice_area, COUNT(*) as count
                    FROM cached_cases
                    WHERE strftime('%Y', created_at) = '2025'
                    GROUP BY practice_area
                    ORDER BY count DESC
                    LIMIT 5
                """)
                case_types = [{'type': r['practice_area'] or 'Unknown', 'count': r['count']}
                             for r in cursor.fetchall()]

                # Cases with lead attorney assigned (quality check - 2025)
                cursor.execute("""
                    SELECT
                        COUNT(*) as total,
                        SUM(CASE WHEN lead_attorney_name IS NOT NULL AND lead_attorney_name != '' THEN 1 ELSE 0 END) as with_attorney
                    FROM cached_cases
                    WHERE strftime('%Y', created_at) = '2025'
                """)
                row = cursor.fetchone()
                total_new = row['total'] if row else 0
                with_attorney = row['with_attorney'] if row else 0
                attorney_rate = (with_attorney / total_new * 100) if total_new > 0 else 100

                return {
                    'new_cases_week': new_cases_week,
                    'new_cases_month': new_cases_month,
                    'case_types': case_types,
                    'attorney_assignment_rate': attorney_rate,
                    'attorney_target': 100,
                    'attorney_compliant': attorney_rate >= 99.5,  # Allow for 0.5% variance
                }
        except Exception:
            # Return empty defaults if tables don't exist yet
            return {
                'new_cases_week': 0,
                'new_cases_month': 0,
                'case_types': [],
                'attorney_assignment_rate': 100,
                'attorney_target': 100,
                'attorney_compliant': True,
            }

    def get_tiffany_sop_data(self) -> Dict:
        """Get Tiffany (Senior Paralegal) SOP metrics from cache database (2025 cases only)."""
        try:
            if not self.cache_db_path.exists():
                raise Exception("Cache database not found")

            with self._get_cache_connection() as conn:
                cursor = conn.cursor()

                # Overdue tasks on 2025 cases (exclude > 200 days as stale)
                cursor.execute("""
                    SELECT COUNT(*) as count
                    FROM cached_tasks t
                    JOIN cached_cases c ON t.case_id = c.id
                    WHERE t.due_date < DATE('now')
                      AND t.due_date >= DATE('now', '-200 days')
                      AND (t.completed = 0 OR t.completed IS NULL)
                      AND strftime('%Y', c.created_at) = '2025'
                """)
                row = cursor.fetchone()
                overdue_count = row['count'] if row else 0

                # Critical overdue (more than 7 days, less than 200) on 2025 cases
                cursor.execute("""
                    SELECT COUNT(*) as count
                    FROM cached_tasks t
                    JOIN cached_cases c ON t.case_id = c.id
                    WHERE t.due_date < DATE('now', '-7 days')
                      AND t.due_date >= DATE('now', '-200 days')
                      AND (t.completed = 0 OR t.completed IS NULL)
                      AND strftime('%Y', c.created_at) = '2025'
                """)
                row = cursor.fetchone()
                overdue_critical = row['count'] if row else 0

                # Tasks by assignee (top offenders) on 2025 cases (exclude > 200 days)
                staff_lookup = self._get_staff_lookup()
                cursor.execute("""
                    SELECT t.assignee_name, COUNT(*) as count
                    FROM cached_tasks t
                    JOIN cached_cases c ON t.case_id = c.id
                    WHERE t.due_date < DATE('now')
                      AND t.due_date >= DATE('now', '-200 days')
                      AND (t.completed = 0 OR t.completed IS NULL)
                      AND strftime('%Y', c.created_at) = '2025'
                    GROUP BY t.assignee_name
                    ORDER BY count DESC
                    LIMIT 5
                """)
                top_offenders = []
                for r in cursor.fetchall():
                    name = self._resolve_assignee_ids_to_names(r['assignee_name'], staff_lookup)
                    top_offenders.append({'name': name, 'count': r['count']})

                # Tasks completed in last 7 days on 2025 cases
                cursor.execute("""
                    SELECT COUNT(*) as count
                    FROM cached_tasks t
                    JOIN cached_cases c ON t.case_id = c.id
                    WHERE t.completed = 1
                      AND DATE(t.completed_at) >= DATE('now', '-7 days')
                      AND strftime('%Y', c.created_at) = '2025'
                """)
                row = cursor.fetchone()
                completed_week = row['count'] if row else 0

                # Total pending tasks on 2025 cases (not completed, not overdue - upcoming work)
                cursor.execute("""
                    SELECT COUNT(*) as count
                    FROM cached_tasks t
                    JOIN cached_cases c ON t.case_id = c.id
                    WHERE (t.completed = 0 OR t.completed IS NULL)
                      AND t.due_date >= DATE('now')
                      AND strftime('%Y', c.created_at) = '2025'
                """)
                row = cursor.fetchone()
                pending_count = row['count'] if row else 0

                # Total active tasks on 2025 cases (all non-completed)
                cursor.execute("""
                    SELECT COUNT(*) as count
                    FROM cached_tasks t
                    JOIN cached_cases c ON t.case_id = c.id
                    WHERE (t.completed = 0 OR t.completed IS NULL)
                      AND strftime('%Y', c.created_at) = '2025'
                """)
                row = cursor.fetchone()
                total_open = row['count'] if row else 0

                # Quality score - try from old database if available
                quality_score = None  # Use None to indicate "no data" vs 0
                quality_audits_count = 0
                try:
                    with self.db._get_connection() as old_conn:
                        old_cursor = old_conn.cursor()
                        old_cursor.execute("""
                            SELECT AVG(quality_score) as avg_score, COUNT(*) as audit_count
                            FROM case_quality_audits
                            WHERE DATE(audit_date) >= DATE('now', '-30 days')
                        """)
                        qrow = old_cursor.fetchone()
                        if qrow and qrow['audit_count'] and qrow['audit_count'] > 0:
                            quality_score = qrow['avg_score']
                            quality_audits_count = qrow['audit_count']
                except Exception:
                    pass

                quality_target = 90.0
                quality_compliant = (quality_score or 0) >= quality_target if quality_score is not None else True

                return {
                    'overdue_count': overdue_count,
                    'overdue_critical': overdue_critical,
                    'top_offenders': top_offenders,
                    'completed_week': completed_week,
                    'pending_count': pending_count,
                    'total_open': total_open,
                    'quality_score': quality_score,
                    'quality_audits_count': quality_audits_count,
                    'quality_target': quality_target,
                    'quality_compliant': quality_compliant,
                }
        except Exception:
            # Return empty defaults if tables don't exist yet
            return {
                'overdue_count': 0,
                'overdue_critical': 0,
                'top_offenders': [],
                'completed_week': 0,
                'pending_count': 0,
                'total_open': 0,
                'quality_score': None,
                'quality_audits_count': 0,
                'quality_target': 90.0,
                'quality_compliant': True,
            }

    def get_legal_assistant_sop_data(self, assignee_name: str = None) -> Dict:
        """Get Legal Assistant (Alison/Cole) SOP metrics from cache database (2025 cases only)."""
        try:
            if not self.cache_db_path.exists():
                raise Exception("Cache database not found")

            # Get staff ID for the assignee name
            staff_id = None
            if assignee_name:
                staff_id = self._get_staff_id_by_name(assignee_name)

            with self._get_cache_connection() as conn:
                cursor = conn.cursor()

                # Build assignee filter - search for staff ID in comma-separated assignee_name field
                assignee_filter = ""
                params = []
                if staff_id:
                    # Match staff ID anywhere in the comma-separated list
                    assignee_filter = "AND (t.assignee_name LIKE ? OR t.assignee_name LIKE ? OR t.assignee_name LIKE ? OR t.assignee_name = ?)"
                    params = [f'{staff_id},%', f'%,{staff_id},%', f'%,{staff_id}', staff_id]

                # Overdue tasks for this assignee on 2025 cases (exclude > 200 days as stale)
                cursor.execute(f"""
                    SELECT COUNT(*) as count
                    FROM cached_tasks t
                    JOIN cached_cases c ON t.case_id = c.id
                    WHERE t.due_date < DATE('now')
                      AND t.due_date >= DATE('now', '-200 days')
                      AND (t.completed = 0 OR t.completed IS NULL)
                      AND strftime('%Y', c.created_at) = '2025'
                      {assignee_filter}
                """, params)
                row = cursor.fetchone()
                overdue_count = row['count'] if row else 0

                # Tasks due today on 2025 cases
                cursor.execute(f"""
                    SELECT COUNT(*) as count
                    FROM cached_tasks t
                    JOIN cached_cases c ON t.case_id = c.id
                    WHERE t.due_date = DATE('now')
                      AND (t.completed = 0 OR t.completed IS NULL)
                      AND strftime('%Y', c.created_at) = '2025'
                      {assignee_filter}
                """, params)
                row = cursor.fetchone()
                due_today = row['count'] if row else 0

                # Completed in last 7 days on 2025 cases
                cursor.execute(f"""
                    SELECT COUNT(*) as count
                    FROM cached_tasks t
                    JOIN cached_cases c ON t.case_id = c.id
                    WHERE t.completed = 1
                      AND DATE(t.completed_at) >= DATE('now', '-7 days')
                      AND strftime('%Y', c.created_at) = '2025'
                      {assignee_filter}
                """, params)
                row = cursor.fetchone()
                completed_week = row['count'] if row else 0

                # License deadlines (DOR/PFR tasks) on 2025 cases
                cursor.execute(f"""
                    SELECT t.name as task_name, c.name as case_name, t.due_date,
                           CAST(julianday(t.due_date) - julianday('now') AS INTEGER) as days_until
                    FROM cached_tasks t
                    LEFT JOIN cached_cases c ON t.case_id = c.id
                    WHERE (t.name LIKE '%DOR%' OR t.name LIKE '%PFR%' OR t.name LIKE '%License%')
                      AND (t.completed = 0 OR t.completed IS NULL)
                      AND t.due_date >= DATE('now')
                      AND strftime('%Y', c.created_at) = '2025'
                      {assignee_filter}
                    ORDER BY t.due_date ASC
                    LIMIT 5
                """, params)
                license_deadlines = [{'task': r['task_name'], 'case': r['case_name'] or 'Unknown',
                                     'due': r['due_date'], 'days_until': r['days_until']}
                                    for r in cursor.fetchall()]

                return {
                    'assignee': assignee_name or 'All',
                    'overdue_count': overdue_count,
                    'due_today': due_today,
                    'completed_week': completed_week,
                    'license_deadlines': license_deadlines,
                }
        except Exception:
            # Return empty defaults if tables don't exist yet
            return {
                'assignee': assignee_name or 'All',
                'overdue_count': 0,
                'due_today': 0,
                'completed_week': 0,
                'license_deadlines': [],
            }

    def get_staff_tasks(self, staff_name: str, include_completed: bool = False) -> Dict:
        """Get detailed task list for a specific staff member (2025 cases only)."""
        try:
            if not self.cache_db_path.exists():
                raise Exception("Cache database not found")

            staff_id = self._get_staff_id_by_name(staff_name)
            staff_lookup = self._get_staff_lookup()

            # Get full name from lookup
            full_name = staff_lookup.get(staff_id, staff_name) if staff_id else staff_name

            with self._get_cache_connection() as conn:
                cursor = conn.cursor()

                # Build assignee filter
                assignee_filter = ""
                params = []
                if staff_id:
                    assignee_filter = "AND (t.assignee_name LIKE ? OR t.assignee_name LIKE ? OR t.assignee_name LIKE ? OR t.assignee_name = ?)"
                    params = [f'{staff_id},%', f'%,{staff_id},%', f'%,{staff_id}', staff_id]

                # Get overdue tasks on 2025 cases (exclude > 200 days as stale)
                cursor.execute(f"""
                    SELECT t.id, t.name as task_name, c.name as case_name, t.due_date,
                           CAST(julianday('now') - julianday(t.due_date) AS INTEGER) as days_overdue,
                           t.priority
                    FROM cached_tasks t
                    JOIN cached_cases c ON t.case_id = c.id
                    WHERE t.due_date < DATE('now')
                      AND t.due_date >= DATE('now', '-200 days')
                      AND (t.completed = 0 OR t.completed IS NULL)
                      AND strftime('%Y', c.created_at) = '2025'
                      {assignee_filter}
                    ORDER BY t.due_date ASC
                """, params)
                overdue_tasks = [{
                    'id': r['id'],
                    'task_name': r['task_name'],
                    'case_name': r['case_name'] or 'No Case',
                    'due_date': r['due_date'],
                    'days_overdue': r['days_overdue'],
                    'priority': r['priority']
                } for r in cursor.fetchall()]

                # Get tasks due today on 2025 cases
                cursor.execute(f"""
                    SELECT t.id, t.name as task_name, c.name as case_name, t.due_date, t.priority
                    FROM cached_tasks t
                    JOIN cached_cases c ON t.case_id = c.id
                    WHERE t.due_date = DATE('now')
                      AND (t.completed = 0 OR t.completed IS NULL)
                      AND strftime('%Y', c.created_at) = '2025'
                      {assignee_filter}
                    ORDER BY t.priority DESC, t.name
                """, params)
                due_today = [{
                    'id': r['id'],
                    'task_name': r['task_name'],
                    'case_name': r['case_name'] or 'No Case',
                    'due_date': r['due_date'],
                    'priority': r['priority']
                } for r in cursor.fetchall()]

                # Get upcoming tasks (next 7 days) on 2025 cases
                cursor.execute(f"""
                    SELECT t.id, t.name as task_name, c.name as case_name, t.due_date,
                           CAST(julianday(t.due_date) - julianday('now') AS INTEGER) as days_until,
                           t.priority
                    FROM cached_tasks t
                    JOIN cached_cases c ON t.case_id = c.id
                    WHERE t.due_date > DATE('now') AND t.due_date <= DATE('now', '+7 days')
                      AND (t.completed = 0 OR t.completed IS NULL)
                      AND strftime('%Y', c.created_at) = '2025'
                      {assignee_filter}
                    ORDER BY t.due_date ASC
                """, params)
                upcoming = [{
                    'id': r['id'],
                    'task_name': r['task_name'],
                    'case_name': r['case_name'] or 'No Case',
                    'due_date': r['due_date'],
                    'days_until': r['days_until'],
                    'priority': r['priority']
                } for r in cursor.fetchall()]

                # Get recently completed on 2025 cases (last 7 days)
                completed = []
                if include_completed:
                    cursor.execute(f"""
                        SELECT t.id, t.name as task_name, c.name as case_name, t.completed_at
                        FROM cached_tasks t
                        JOIN cached_cases c ON t.case_id = c.id
                        WHERE t.completed = 1
                          AND DATE(t.completed_at) >= DATE('now', '-7 days')
                          AND strftime('%Y', c.created_at) = '2025'
                          {assignee_filter}
                        ORDER BY t.completed_at DESC
                        LIMIT 20
                    """, params)
                    completed = [{
                        'id': r['id'],
                        'task_name': r['task_name'],
                        'case_name': r['case_name'] or 'No Case',
                        'completed_at': r['completed_at']
                    } for r in cursor.fetchall()]

                return {
                    'staff_name': full_name,
                    'staff_id': staff_id,
                    'overdue_tasks': overdue_tasks,
                    'due_today': due_today,
                    'upcoming': upcoming,
                    'completed': completed,
                    'overdue_count': len(overdue_tasks),
                    'due_today_count': len(due_today),
                    'upcoming_count': len(upcoming),
                }
        except Exception as e:
            return {
                'staff_name': staff_name,
                'staff_id': None,
                'overdue_tasks': [],
                'due_today': [],
                'upcoming': [],
                'completed': [],
                'overdue_count': 0,
                'due_today_count': 0,
                'upcoming_count': 0,
                'error': str(e)
            }

    def get_dashboard_stats(self, year: int = None) -> Dict:
        """Get high-level stats for dashboard overview for specified year."""
        summary = self.get_daily_collections_summary(year=year)
        plans = self.get_payment_plans_summary()
        noiw = self.get_noiw_pipeline()
        wonky = self.get_wonky_invoices()
        overdue = self.get_overdue_tasks(limit=100)
        last_sync = self.get_last_sync_time()

        return {
            'today_collected': summary.get('cash_received', 0),
            'payment_count': summary.get('payment_count', 0),
            'total_ar': summary.get('total_ar', 0),
            'ar_under_180': summary.get('ar_under_180', 0),
            'ar_over_180': summary.get('ar_over_180', 0),
            'aging_over_60_pct': summary.get('aging_over_60_pct', 0),
            'aging_60_to_120_pct': summary.get('aging_60_to_120_pct', 0),
            'active_plans': plans.get('active_count', 0),
            'delinquent_plans': plans.get('delinquent_count', 0),
            'noiw_pipeline': len(noiw),
            'wonky_invoices': len(wonky),
            'overdue_tasks': len(overdue),
            'last_sync': last_sync.strftime('%Y-%m-%d %H:%M') if last_sync else 'Never',
            'no_data': summary.get('no_data', False),
        }

    # =========================================================================
    # Attorney Productivity Methods
    # =========================================================================

    def get_attorney_productivity_data(self, year: int = None) -> List[Dict]:
        """Get per-attorney metrics: active cases, closed MTD/YTD, billing for specified year."""
        current_year = datetime.now().year
        if year is None:
            year = current_year

        try:
            if not self.cache_db_path.exists():
                return []

            with self._get_cache_connection() as conn:
                cursor = conn.cursor()

                # For closed years, use Dec 31 as the reference for MTD
                if year < current_year:
                    mtd_start = f"'{year}-12-01'"
                else:
                    mtd_start = "DATE('now', 'start of month')"

                # Get attorney productivity with case counts and billing for specified year
                cursor.execute(f"""
                    SELECT
                        c.lead_attorney_id as attorney_id,
                        c.lead_attorney_name as attorney_name,
                        COUNT(DISTINCT CASE WHEN LOWER(c.status) = 'open'
                            AND strftime('%Y', c.created_at) = '{year}'
                            THEN c.id END) as active_cases,
                        COUNT(DISTINCT CASE WHEN LOWER(c.status) = 'closed'
                            AND c.date_closed >= {mtd_start}
                            AND strftime('%Y', c.created_at) = '{year}'
                            THEN c.id END) as closed_mtd,
                        COUNT(DISTINCT CASE WHEN LOWER(c.status) = 'closed'
                            AND strftime('%Y', c.date_closed) = '{year}'
                            AND strftime('%Y', c.created_at) = '{year}'
                            THEN c.id END) as closed_ytd,
                        COALESCE(SUM(CASE WHEN strftime('%Y', i.invoice_date) = '{year}' THEN i.total_amount ELSE 0 END), 0) as total_billed,
                        COALESCE(SUM(CASE WHEN strftime('%Y', i.invoice_date) = '{year}' THEN i.paid_amount ELSE 0 END), 0) as total_collected,
                        COALESCE(SUM(CASE WHEN strftime('%Y', i.invoice_date) = '{year}' THEN i.balance_due ELSE 0 END), 0) as total_outstanding
                    FROM cached_cases c
                    LEFT JOIN cached_invoices i ON i.case_id = c.id AND strftime('%Y', i.invoice_date) = '{year}'
                    WHERE c.lead_attorney_name IS NOT NULL AND c.lead_attorney_name != ''
                    GROUP BY c.lead_attorney_id, c.lead_attorney_name
                    ORDER BY active_cases DESC
                """)

                results = []
                for row in cursor.fetchall():
                    total_billed = row['total_billed'] or 0
                    total_collected = row['total_collected'] or 0
                    collection_rate = (total_collected / total_billed * 100) if total_billed > 0 else 0

                    results.append({
                        'attorney_id': row['attorney_id'],
                        'attorney_name': row['attorney_name'],
                        'active_cases': row['active_cases'] or 0,
                        'closed_mtd': row['closed_mtd'] or 0,
                        'closed_ytd': row['closed_ytd'] or 0,
                        'total_billed': total_billed,
                        'total_collected': total_collected,
                        'total_outstanding': row['total_outstanding'] or 0,
                        'collection_rate': collection_rate,
                        'year': year,
                    })
                return results
        except Exception as e:
            print(f"Error getting attorney productivity: {e}")
            return []

    def get_attorney_invoice_aging(self, attorney_id: int = None, year: int = None) -> List[Dict]:
        """Get invoice aging breakdown by attorney with 30/60/90/120+ DPD buckets for specified year."""
        current_year = datetime.now().year
        if year is None:
            year = current_year

        # For closed years, freeze aging at Dec 31 of that year
        if year < current_year:
            reference_date = f"'{year}-12-31'"
        else:
            reference_date = "'now'"

        try:
            if not self.cache_db_path.exists():
                return []

            with self._get_cache_connection() as conn:
                cursor = conn.cursor()

                attorney_filter = ""
                params = []
                if attorney_id:
                    attorney_filter = "AND c.lead_attorney_id = ?"
                    params = [attorney_id]

                # Filter to specified year invoices
                cursor.execute(f"""
                    SELECT
                        c.lead_attorney_id as attorney_id,
                        c.lead_attorney_name as attorney_name,
                        COUNT(i.id) as total_invoices,
                        SUM(CASE WHEN i.balance_due = 0 THEN 1 ELSE 0 END) as paid_full,
                        SUM(CASE WHEN i.balance_due > 0 AND julianday({reference_date}) - julianday(i.due_date) <= 0 THEN 1 ELSE 0 END) as current,
                        SUM(CASE WHEN i.balance_due > 0 AND julianday({reference_date}) - julianday(i.due_date) BETWEEN 1 AND 30 THEN 1 ELSE 0 END) as dpd_1_30,
                        SUM(CASE WHEN i.balance_due > 0 AND julianday({reference_date}) - julianday(i.due_date) BETWEEN 31 AND 60 THEN 1 ELSE 0 END) as dpd_31_60,
                        SUM(CASE WHEN i.balance_due > 0 AND julianday({reference_date}) - julianday(i.due_date) BETWEEN 61 AND 90 THEN 1 ELSE 0 END) as dpd_61_90,
                        SUM(CASE WHEN i.balance_due > 0 AND julianday({reference_date}) - julianday(i.due_date) BETWEEN 91 AND 120 THEN 1 ELSE 0 END) as dpd_91_120,
                        SUM(CASE WHEN i.balance_due > 0 AND julianday({reference_date}) - julianday(i.due_date) BETWEEN 121 AND 180 THEN 1 ELSE 0 END) as dpd_121_180,
                        SUM(CASE WHEN i.balance_due > 0 AND julianday({reference_date}) - julianday(i.due_date) > 180 THEN 1 ELSE 0 END) as dpd_over_180,
                        SUM(CASE WHEN i.balance_due > 0 AND julianday({reference_date}) - julianday(i.due_date) > 60 AND julianday({reference_date}) - julianday(i.due_date) <= 180 THEN i.balance_due ELSE 0 END) as amount_60_to_180
                    FROM cached_cases c
                    JOIN cached_invoices i ON i.case_id = c.id
                    WHERE c.lead_attorney_name IS NOT NULL
                      AND strftime('%Y', i.invoice_date) = '{year}'
                      {attorney_filter}
                    GROUP BY c.lead_attorney_id, c.lead_attorney_name
                    ORDER BY total_invoices DESC
                """, params)

                results = []
                for row in cursor.fetchall():
                    total = row['total_invoices'] or 1
                    # Viable collection: 60-180 days past due
                    viable_60_180 = (row['dpd_61_90'] or 0) + (row['dpd_91_120'] or 0) + (row['dpd_121_180'] or 0)
                    results.append({
                        'attorney_id': row['attorney_id'],
                        'attorney_name': row['attorney_name'],
                        'total_invoices': row['total_invoices'] or 0,
                        'paid_full': row['paid_full'] or 0,
                        'paid_full_pct': round((row['paid_full'] or 0) / total * 100, 1),
                        'current': row['current'] or 0,
                        'dpd_1_30': row['dpd_1_30'] or 0,
                        'dpd_31_60': row['dpd_31_60'] or 0,
                        'dpd_61_90': row['dpd_61_90'] or 0,
                        'dpd_91_120': row['dpd_91_120'] or 0,
                        'dpd_121_180': row['dpd_121_180'] or 0,
                        'dpd_over_180': row['dpd_over_180'] or 0,
                        'amount_60_to_180': row['amount_60_to_180'] or 0,
                        'needs_calls': viable_60_180,  # Only invoices 60-180 days (viable collection)
                    })
                return results
        except Exception as e:
            print(f"Error getting attorney invoice aging: {e}")
            return []

    def get_collection_call_list(self, attorney_id: int = None, year: int = None) -> List[Dict]:
        """Get 60+ DPD invoices with client contact info for calls for specified year."""
        current_year = datetime.now().year
        if year is None:
            year = current_year

        # For closed years, freeze aging at Dec 31 of that year
        if year < current_year:
            reference_date = f"'{year}-12-31'"
        else:
            reference_date = "'now'"

        try:
            if not self.cache_db_path.exists():
                return []

            with self._get_cache_connection() as conn:
                cursor = conn.cursor()

                attorney_filter = ""
                params = []
                if attorney_id:
                    attorney_filter = "AND c.lead_attorney_id = ?"
                    params = [attorney_id]

                # Filter to specified year invoices
                cursor.execute(f"""
                    SELECT
                        i.id as invoice_id,
                        i.invoice_number,
                        i.balance_due,
                        i.due_date,
                        CAST(julianday({reference_date}) - julianday(i.due_date) AS INTEGER) as days_overdue,
                        c.id as case_id,
                        c.name as case_name,
                        c.lead_attorney_name,
                        ct.id as contact_id,
                        ct.name as contact_name,
                        ct.email as contact_email,
                        ct.phone as contact_phone
                    FROM cached_invoices i
                    JOIN cached_cases c ON i.case_id = c.id
                    LEFT JOIN cached_contacts ct ON i.contact_id = ct.id
                    WHERE i.balance_due > 0
                      AND julianday({reference_date}) - julianday(i.due_date) > 60
                      AND julianday({reference_date}) - julianday(i.due_date) <= 180
                      AND c.lead_attorney_name IS NOT NULL
                      AND strftime('%Y', i.invoice_date) = '{year}'
                      {attorney_filter}
                    ORDER BY days_overdue DESC
                """, params)

                results = []
                for row in cursor.fetchall():
                    days = row['days_overdue']
                    if days > 120:
                        aging_bucket = '121-180'
                        collectible = True  # Still viable under 180 days
                    elif days > 90:
                        aging_bucket = '91-120'
                        collectible = True
                    else:
                        aging_bucket = '61-90'
                        collectible = True

                    results.append({
                        'invoice_id': row['invoice_id'],
                        'invoice_number': row['invoice_number'],
                        'balance_due': row['balance_due'],
                        'due_date': row['due_date'],
                        'days_overdue': days,
                        'aging_bucket': aging_bucket,
                        'collectible': collectible,
                        'case_id': row['case_id'],
                        'case_name': row['case_name'],
                        'attorney_name': row['lead_attorney_name'],
                        'contact_id': row['contact_id'],
                        'contact_name': row['contact_name'],
                        'contact_email': row['contact_email'],
                        'contact_phone': row['contact_phone'],
                    })
                return results
        except Exception as e:
            print(f"Error getting collection call list: {e}")
            return []

    def get_attorney_detail(self, attorney_name: str, year: int = None) -> Dict:
        """Get detailed information for a specific attorney for specified year."""
        current_year = datetime.now().year
        if year is None:
            year = current_year

        try:
            if not self.cache_db_path.exists():
                return {}

            # Get attorney ID from name
            attorney_id = None
            with self._get_cache_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT DISTINCT lead_attorney_id FROM cached_cases WHERE lead_attorney_name LIKE ?",
                    (f'%{attorney_name}%',)
                )
                row = cursor.fetchone()
                if row:
                    attorney_id = row['lead_attorney_id']

            if not attorney_id:
                return {'attorney_name': attorney_name, 'error': 'Attorney not found'}

            # Get productivity data for specified year
            productivity = [p for p in self.get_attorney_productivity_data(year=year)
                          if p['attorney_id'] == attorney_id]
            productivity = productivity[0] if productivity else {}

            # Get invoice aging for specified year
            aging = [a for a in self.get_attorney_invoice_aging(attorney_id, year=year)
                    if a['attorney_id'] == attorney_id]
            aging = aging[0] if aging else {}

            # Get call list (60+ DPD invoices) for specified year
            call_list = self.get_collection_call_list(attorney_id, year=year)

            # Get active cases
            with self._get_cache_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, name, case_number, practice_area, date_opened
                    FROM cached_cases
                    WHERE lead_attorney_id = ? AND LOWER(status) = 'open'
                    ORDER BY date_opened DESC
                    LIMIT 50
                """, (attorney_id,))
                active_cases = [{
                    'id': r['id'],
                    'name': r['name'],
                    'case_number': r['case_number'],
                    'practice_area': r['practice_area'],
                    'date_opened': r['date_opened'],
                } for r in cursor.fetchall()]

            return {
                'attorney_id': attorney_id,
                'attorney_name': productivity.get('attorney_name', attorney_name),
                'productivity': productivity,
                'aging': aging,
                'call_list': call_list,
                'active_cases': active_cases,
                'call_list_count': len(call_list),
                'viable_collection': sum(1 for c in call_list if c['collectible']),
                'unlikely_collection': sum(1 for c in call_list if not c['collectible']),
            }
        except Exception as e:
            print(f"Error getting attorney detail: {e}")
            return {'attorney_name': attorney_name, 'error': str(e)}

    def get_attorney_summary(self, year: int = None) -> Dict:
        """Get high-level attorney summary for main dashboard widget for specified year."""
        try:
            productivity = self.get_attorney_productivity_data(year=year)
            if not productivity:
                return {
                    'active_attorneys': 0,
                    'total_active_cases': 0,
                    'total_outstanding': 0,
                    'paid_full': 0,
                    'dpd_1_30': 0,
                    'dpd_31_60': 0,
                    'dpd_61_90': 0,
                    'dpd_91_120': 0,
                    'top_attorneys': [],
                }

            # Filter to active attorneys only (those with active cases)
            active_attorneys = [p for p in productivity if p['active_cases'] > 0]

            total_active_cases = sum(p['active_cases'] for p in active_attorneys)
            total_outstanding = sum(p['total_outstanding'] for p in active_attorneys)
            total_collected = sum(p['total_collected'] for p in active_attorneys)
            total_billed = sum(p['total_billed'] for p in active_attorneys)

            # Get aging data - individual DPD bucket totals (only <180 days)
            aging = self.get_attorney_invoice_aging(year=year)
            total_paid_full = sum(a.get('paid_full', 0) for a in aging)
            total_dpd_1_30 = sum(a.get('dpd_1_30', 0) for a in aging)
            total_dpd_31_60 = sum(a.get('dpd_31_60', 0) for a in aging)
            total_dpd_61_90 = sum(a.get('dpd_61_90', 0) for a in aging)
            total_dpd_91_120 = sum(a.get('dpd_91_120', 0) for a in aging)

            # Sort by active_cases for top attorneys display
            sorted_attorneys = sorted(active_attorneys, key=lambda x: x['active_cases'], reverse=True)
            top_attorneys = [{'name': a['attorney_name'], 'cases': a['active_cases']} for a in sorted_attorneys[:5]]

            return {
                'active_attorneys': len(active_attorneys),
                'total_active_cases': total_active_cases,
                'total_outstanding': total_outstanding,
                'total_collected': total_collected,
                'total_billed': total_billed,
                'collection_rate': (total_collected / total_billed * 100) if total_billed > 0 else 0,
                'paid_full': total_paid_full,
                'dpd_1_30': total_dpd_1_30,
                'dpd_31_60': total_dpd_31_60,
                'dpd_61_90': total_dpd_61_90,
                'dpd_91_120': total_dpd_91_120,
                'top_attorneys': top_attorneys,
            }
        except Exception as e:
            print(f"Error getting attorney summary: {e}")
            return {
                'active_attorneys': 0,
                'total_active_cases': 0,
                'total_outstanding': 0,
                'paid_full': 0,
                'dpd_1_30': 0,
                'dpd_31_60': 0,
                'dpd_61_90': 0,
                'dpd_91_120': 0,
                'top_attorneys': [],
            }

    def get_staff_caseload_data(self, staff_name: str) -> Dict:
        """Get caseload metrics for a staff member (2025 cases only).

        For attorneys: counts open 2025 cases where they are lead_attorney
        For non-attorneys: counts open 2025 cases with assigned tasks
        Separately tracks cases with 2025 invoices in actionable 60-180 DPD range.
        """
        try:
            if not self.cache_db_path.exists():
                return self._empty_caseload_data(staff_name)

            staff_id = self._get_staff_id_by_name(staff_name)
            if not staff_id:
                return self._empty_caseload_data(staff_name)

            with self._get_cache_connection() as conn:
                cursor = conn.cursor()

                # Check if this staff member is an attorney (title contains "Attorney")
                cursor.execute("""
                    SELECT title FROM cached_staff WHERE id = ?
                """, (staff_id,))
                row = cursor.fetchone()
                title = row['title'] if row else ''
                is_attorney = 'attorney' in (title or '').lower()

                if is_attorney:
                    # For attorneys: count open 2025 cases where they are lead_attorney
                    cursor.execute("""
                        SELECT COUNT(*) as active_cases
                        FROM cached_cases c
                        WHERE c.lead_attorney_id = ?
                          AND LOWER(c.status) = 'open'
                          AND strftime('%Y', c.created_at) = '2025'
                    """, (staff_id,))
                    row = cursor.fetchone()
                    active_cases = row['active_cases'] if row else 0

                    # Cases with at least one 2025 invoice in actionable 60-180 DPD range
                    cursor.execute("""
                        SELECT COUNT(DISTINCT c.id) as cases_60_180
                        FROM cached_cases c
                        JOIN cached_invoices i ON i.case_id = c.id
                        WHERE c.lead_attorney_id = ?
                          AND LOWER(c.status) = 'open'
                          AND strftime('%Y', c.created_at) = '2025'
                          AND strftime('%Y', i.invoice_date) = '2025'
                          AND i.balance_due > 0
                          AND julianday('now') - julianday(i.due_date) BETWEEN 60 AND 180
                    """, (staff_id,))
                    row = cursor.fetchone()
                    cases_60_180_dpd = row['cases_60_180'] if row else 0

                    # Get closed 2025 cases count for this attorney
                    cursor.execute("""
                        SELECT COUNT(*) as closed_cases
                        FROM cached_cases c
                        WHERE c.lead_attorney_id = ?
                          AND LOWER(c.status) = 'closed'
                          AND strftime('%Y', c.created_at) = '2025'
                    """, (staff_id,))
                    row = cursor.fetchone()
                    closed_cases = row['closed_cases'] if row else 0
                else:
                    # For non-attorneys: count open 2025 cases where they have any assigned tasks
                    assignee_patterns = [f'{staff_id},%', f'%,{staff_id},%', f'%,{staff_id}', staff_id]
                    cursor.execute("""
                        SELECT COUNT(DISTINCT t.case_id) as task_cases
                        FROM cached_tasks t
                        JOIN cached_cases c ON c.id = t.case_id
                        WHERE (t.assignee_name LIKE ? OR t.assignee_name LIKE ? OR t.assignee_name LIKE ? OR t.assignee_name = ?)
                          AND LOWER(c.status) = 'open'
                          AND strftime('%Y', c.created_at) = '2025'
                    """, assignee_patterns)
                    row = cursor.fetchone()
                    active_cases = row['task_cases'] if row else 0
                    cases_60_180_dpd = 0  # Non-attorneys don't have this metric

                    # For non-attorneys: count closed 2025 cases where they had tasks assigned
                    cursor.execute("""
                        SELECT COUNT(DISTINCT t.case_id) as closed_cases
                        FROM cached_tasks t
                        JOIN cached_cases c ON c.id = t.case_id
                        WHERE (t.assignee_name LIKE ? OR t.assignee_name LIKE ? OR t.assignee_name LIKE ? OR t.assignee_name = ?)
                          AND LOWER(c.status) = 'closed'
                          AND strftime('%Y', c.created_at) = '2025'
                    """, assignee_patterns)
                    row = cursor.fetchone()
                    closed_cases = row['closed_cases'] if row else 0

                    # For non-attorneys: count completed tasks on 2025 cases
                    cursor.execute("""
                        SELECT COUNT(*) as tasks_done
                        FROM cached_tasks t
                        JOIN cached_cases c ON c.id = t.case_id
                        WHERE (t.assignee_name LIKE ? OR t.assignee_name LIKE ? OR t.assignee_name LIKE ? OR t.assignee_name = ?)
                          AND t.completed = 1
                          AND strftime('%Y', c.created_at) = '2025'
                    """, assignee_patterns)
                    row = cursor.fetchone()
                    tasks_done = row['tasks_done'] if row else 0

                    # For non-attorneys: count total tasks assigned on 2025 cases
                    cursor.execute("""
                        SELECT COUNT(*) as tasks_total
                        FROM cached_tasks t
                        JOIN cached_cases c ON c.id = t.case_id
                        WHERE (t.assignee_name LIKE ? OR t.assignee_name LIKE ? OR t.assignee_name LIKE ? OR t.assignee_name = ?)
                          AND strftime('%Y', c.created_at) = '2025'
                    """, assignee_patterns)
                    row = cursor.fetchone()
                    tasks_total = row['tasks_total'] if row else 0

                return {
                    'staff_name': staff_name,
                    'staff_id': staff_id,
                    'active_cases': active_cases,
                    'cases_60_180_dpd': cases_60_180_dpd,
                    'closed_cases': closed_cases,
                    'tasks_done': tasks_done if not is_attorney else 0,
                    'tasks_total': tasks_total if not is_attorney else 0,
                    'is_attorney': is_attorney,
                }
        except Exception as e:
            print(f"Error getting staff caseload: {e}")
            return self._empty_caseload_data(staff_name)

    def _empty_caseload_data(self, staff_name: str) -> Dict:
        """Return empty caseload data structure."""
        return {
            'staff_name': staff_name,
            'staff_id': None,
            'active_cases': 0,
            'cases_60_180_dpd': 0,
            'closed_cases': 0,
            'tasks_done': 0,
            'tasks_total': 0,
            'is_attorney': False,
        }

    def get_staff_active_cases_list(self, staff_name: str) -> List[Dict]:
        """Get list of active cases for a staff member.

        For attorneys: returns open cases where they are lead_attorney (excluding stale cases)
        For non-attorneys: returns cases where they have tasks assigned (excluding stale cases)
        """
        try:
            if not self.cache_db_path.exists():
                return []

            staff_id = self._get_staff_id_by_name(staff_name)
            if not staff_id:
                return []

            # Convert to int for integer comparison in SQL
            staff_id_int = int(staff_id)

            with self._get_cache_connection() as conn:
                cursor = conn.cursor()

                # Check if this staff member is an attorney
                cursor.execute("""
                    SELECT title FROM cached_staff WHERE id = ?
                """, (staff_id_int,))
                row = cursor.fetchone()
                title = row['title'] if row else ''
                is_attorney = 'attorney' in (title or '').lower()

                if is_attorney:
                    # Get active cases for this attorney (same logic as caseload count)
                    cursor.execute("""
                        SELECT c.id, c.name, c.case_number, c.case_type, c.created_at
                        FROM cached_cases c
                        WHERE c.lead_attorney_id = ?
                          AND LOWER(c.status) = 'open'
                          AND (
                            -- New case (under 180 days old)
                            julianday('now') - julianday(c.created_at) <= 180
                            OR
                            -- Has at least one invoice under 180 DPD (or paid in full)
                            EXISTS (
                                SELECT 1 FROM cached_invoices i
                                WHERE i.case_id = c.id
                                  AND (i.balance_due = 0 OR julianday('now') - julianday(i.due_date) <= 180)
                            )
                          )
                        ORDER BY c.name ASC
                    """, (staff_id_int,))
                else:
                    # For non-attorneys, get cases where they have active tasks assigned
                    cursor.execute("""
                        SELECT DISTINCT c.id, c.name, c.case_number, c.case_type, c.created_at
                        FROM cached_cases c
                        JOIN cached_tasks t ON t.case_id = c.id
                        WHERE t.assignee_id = ?
                          AND LOWER(c.status) = 'open'
                          AND LOWER(t.status) != 'completed'
                          AND (
                            -- New case (under 180 days old)
                            julianday('now') - julianday(c.created_at) <= 180
                            OR
                            -- Has at least one invoice under 180 DPD (or paid in full)
                            EXISTS (
                                SELECT 1 FROM cached_invoices i
                                WHERE i.case_id = c.id
                                  AND (i.balance_due = 0 OR julianday('now') - julianday(i.due_date) <= 180)
                            )
                          )
                        ORDER BY c.name ASC
                    """, (staff_id_int,))

                return [{
                    'id': r['id'],
                    'name': r['name'],
                    'case_number': r['case_number'],
                    'case_type': r['case_type'],
                    'created_at': r['created_at']
                } for r in cursor.fetchall()]

        except Exception as e:
            print(f"Error getting staff active cases list: {e}")
            return []
