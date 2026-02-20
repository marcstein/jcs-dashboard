"""
A/R and Collections Data Access
"""
from datetime import date, datetime
from typing import Dict, List

from db.connection import get_connection


class ARDataMixin:
    """Mixin providing A/R, collections, aging, dunning, payment plans, and NOIW data methods."""

    def get_daily_collections_summary(self, target_date: date = None, year: int = None) -> Dict:
        """Get daily collections summary from cached invoices for specified year."""
        target_date = target_date or date.today()
        current_year = datetime.now().year
        if year is None:
            year = current_year

        # For closed years, freeze aging at Dec 31 of that year
        if year < current_year:
            reference_date = f"DATE('{year}-12-31')"
        else:
            reference_date = "CURRENT_DATE"

        # First try to get data from the cache database (cached_invoices)
        try:
            with get_connection() as conn:
                cursor = self._cursor(conn)
                # Filter to specified year invoices
                cursor.execute(f"""
                    SELECT
                        SUM(balance_due) as total_ar,
                        SUM(CASE WHEN {reference_date} - due_date < 0 THEN balance_due ELSE 0 END) as ar_current,
                        SUM(CASE WHEN {reference_date} - due_date BETWEEN 0 AND 30 THEN balance_due ELSE 0 END) as ar_0_30,
                        SUM(CASE WHEN {reference_date} - due_date BETWEEN 31 AND 60 THEN balance_due ELSE 0 END) as ar_31_60,
                        SUM(CASE WHEN {reference_date} - due_date BETWEEN 61 AND 90 THEN balance_due ELSE 0 END) as ar_61_90,
                        SUM(CASE WHEN {reference_date} - due_date BETWEEN 91 AND 120 THEN balance_due ELSE 0 END) as ar_91_120,
                        SUM(CASE WHEN {reference_date} - due_date > 120 THEN balance_due ELSE 0 END) as ar_120_plus,
                        SUM(CASE WHEN {reference_date} - due_date > 90 THEN balance_due ELSE 0 END) as ar_90_plus,
                        SUM(CASE WHEN {reference_date} - due_date <= 180 THEN balance_due ELSE 0 END) as ar_under_180,
                        SUM(CASE WHEN {reference_date} - due_date > 180 THEN balance_due ELSE 0 END) as ar_over_180,
                        COUNT(CASE WHEN balance_due > 0 AND {reference_date} - due_date > 30 THEN 1 END) as delinquent
                    FROM cached_invoices
                    WHERE firm_id = %s
                      AND balance_due > 0
                      AND EXTRACT(YEAR FROM invoice_date) = %s
                """, (self.firm_id, year))

                row = cursor.fetchone()

                # Get total billed and collected for specified year invoices
                cursor.execute(f"""
                    SELECT SUM(total_amount) as total_billed, SUM(paid_amount) as total_collected
                    FROM cached_invoices
                    WHERE firm_id = %s
                      AND EXTRACT(YEAR FROM invoice_date) = %s
                """, (self.firm_id, year))
                billing_row = cursor.fetchone()
                total_billed = (billing_row[0] or 0) if billing_row else 0
                total_collected = (billing_row[1] or 0) if billing_row else 0

                if row and row[0]:
                    total_ar = row[0] or 0
                    ar_current = row[1] or 0
                    ar_0_30 = row[2] or 0
                    ar_31_60 = row[3] or 0
                    ar_61_90 = row[4] or 0
                    ar_91_120 = row[5] or 0
                    ar_120_plus = row[6] or 0
                    ar_90_plus = row[7] or 0
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
                            WHERE firm_id = %s
                              AND DATE(payment_date) = {reference_date}
                              AND EXTRACT(YEAR FROM payment_date) = %s
                        """, (self.firm_id, year))
                        prow = cursor.fetchone()
                        if prow and prow[0]:
                            cash_received = prow[0] or 0
                            payment_count = prow[1] or 0
                    except Exception:
                        pass

                    ar_under_180 = row[8] or 0
                    ar_over_180 = row[9] or 0

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
                        'delinquent_accounts': row[10] or 0,
                        'total_collected': total_collected,
                        'collection_rate': collection_rate,
                    }
        except Exception:
            pass  # Fall through to legacy method

        # Fallback to legacy KPI snapshots
        with get_connection() as conn:
            cursor = self._cursor(conn)

            # Try to get cached KPI data for this date (or most recent)
            cursor.execute("""
                SELECT kpi_name, kpi_value
                FROM kpi_snapshots
                WHERE firm_id = %s
                  AND category = 'collections'
                  AND snapshot_date = (
                      SELECT MAX(snapshot_date) FROM kpi_snapshots
                      WHERE firm_id = %s
                        AND snapshot_date <= %s
                  )
            """, (self.firm_id, self.firm_id, str(target_date)))

            rows = cursor.fetchall()

            if rows:
                # Build from cached KPIs
                kpis = {row[0]: row[1] for row in rows}
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
        with get_connection() as conn:
            cursor = self._cursor(conn)

            cursor.execute("""
                SELECT snapshot_date, SUM(kpi_value) as total
                FROM kpi_snapshots
                WHERE firm_id = %s
                  AND category = 'collections'
                  AND kpi_name = 'cash_received'
                  AND snapshot_date >= CURRENT_DATE - INTERVAL %s
                GROUP BY snapshot_date
                ORDER BY snapshot_date
            """, (self.firm_id, f'{days_back} days'))

            rows = cursor.fetchall()
            return [{'date': str(row[0]), 'amount': row[1]} for row in rows]

    def get_payment_plans_summary(self) -> Dict:
        """Get payment plans summary from local database."""
        with get_connection() as conn:
            cursor = self._cursor(conn)

            # Active plans
            cursor.execute("""
                SELECT COUNT(*) as count, COALESCE(SUM(total_amount), 0) as total
                FROM payment_plans
                WHERE firm_id = %s
                  AND status = 'active'
            """, (self.firm_id,))
            active = cursor.fetchone()

            # Delinquent plans
            cursor.execute("""
                SELECT COUNT(*) as count
                FROM payment_plans
                WHERE firm_id = %s
                  AND status = 'delinquent'
            """, (self.firm_id,))
            delinquent = cursor.fetchone()

            # Completed this month
            cursor.execute("""
                SELECT COUNT(*) as count
                FROM payment_plans
                WHERE firm_id = %s
                  AND status = 'completed'
                  AND DATE(updated_at) >= DATE_TRUNC('month', CURRENT_DATE)
            """, (self.firm_id,))
            completed = cursor.fetchone()

            return {
                'active_count': active[0] if active else 0,
                'active_total': active[1] if active else 0,
                'delinquent_count': delinquent[0] if delinquent else 0,
                'completed_month': completed[0] if completed else 0,
            }

    def get_noiw_pipeline(self, status_filter: str = None) -> List[Dict]:
        """Get NOIW pipeline cases from local database."""
        with get_connection() as conn:
            cursor = self._cursor(conn)

            if status_filter:
                cursor.execute("""
                    SELECT case_id, case_name, contact_name, invoice_id, balance_due,
                           days_delinquent, status, assigned_to, warning_sent_date,
                           final_notice_date, created_at, updated_at
                    FROM noiw_tracking
                    WHERE firm_id = %s
                      AND status = %s
                    ORDER BY days_delinquent ASC, balance_due DESC
                """, (self.firm_id, status_filter))
            else:
                cursor.execute("""
                    SELECT case_id, case_name, contact_name, invoice_id, balance_due,
                           days_delinquent, status, assigned_to, warning_sent_date,
                           final_notice_date, created_at, updated_at
                    FROM noiw_tracking
                    WHERE firm_id = %s
                      AND status NOT IN ('resolved', 'withdrawn')
                    ORDER BY days_delinquent ASC, balance_due DESC
                """, (self.firm_id,))

            rows = cursor.fetchall()
            return [{
                'case_id': row[0],
                'case_name': row[1],
                'contact_name': row[2],
                'invoice_id': row[3],
                'balance_due': row[4],
                'days_delinquent': row[5],
                'status': row[6],
                'assigned_to': row[7],
                'warning_sent_date': row[8],
                'final_notice_date': row[9],
                'created_at': row[10],
                'updated_at': row[11],
            } for row in rows]

    def get_noiw_summary(self) -> Dict:
        """Get NOIW pipeline summary statistics."""
        with get_connection() as conn:
            cursor = self._cursor(conn)

            # Get status counts
            cursor.execute("""
                SELECT status, COUNT(*) as count, SUM(balance_due) as total_balance
                FROM noiw_tracking
                WHERE firm_id = %s
                GROUP BY status
            """, (self.firm_id,))
            by_status = {}
            for row in cursor.fetchall():
                by_status[row[0]] = {
                    'count': row[1],
                    'total_balance': row[2] or 0
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
                WHERE firm_id = %s
                  AND status NOT IN ('resolved', 'withdrawn')
            """, (self.firm_id,))
            totals = cursor.fetchone()

            return {
                'by_status': by_status,
                'bucket_30_60': totals[0] or 0,
                'bucket_60_90': totals[1] or 0,
                'bucket_90_180': totals[2] or 0,
                'bucket_180_plus': totals[3] or 0,
                'total_active': totals[4] or 0,
                'total_balance': totals[5] or 0,
            }

    def get_wonky_invoices(self) -> List[Dict]:
        """Get open wonky invoices from local database."""
        with get_connection() as conn:
            cursor = self._cursor(conn)

            cursor.execute("""
                SELECT invoice_id, invoice_number, case_name, issue_type,
                       issue_description, discrepancy, opened_date
                FROM wonky_invoices
                WHERE firm_id = %s
                  AND status = 'open'
                ORDER BY opened_date DESC
            """, (self.firm_id,))

            rows = cursor.fetchall()
            return [{
                'invoice_id': row[0],
                'invoice_number': row[1],
                'case_name': row[2],
                'issue_type': row[3],
                'description': row[4],
                'discrepancy': row[5],
                'opened_date': row[6],
            } for row in rows]

    def get_dunning_preview(self, stage: int = None) -> List[Dict]:
        """Get preview of dunning notices by stage."""
        try:
            with get_connection() as conn:
                cursor = self._cursor(conn)

                if stage:
                    cursor.execute("""
                        SELECT invoice_id, case_name, contact_name, balance_due, days_delinquent,
                               stage, last_notice_date
                        FROM dunning_notices
                        WHERE firm_id = %s
                          AND stage = %s
                          AND status = 'pending'
                        ORDER BY days_delinquent DESC
                    """, (self.firm_id, stage))
                else:
                    cursor.execute("""
                        SELECT invoice_id, case_name, contact_name, balance_due, days_delinquent,
                               stage, last_notice_date
                        FROM dunning_notices
                        WHERE firm_id = %s
                          AND status = 'pending'
                        ORDER BY stage ASC, days_delinquent DESC
                    """, (self.firm_id,))

                return [{'invoice_id': r[0], 'case_name': r[1], 'contact_name': r[2],
                        'balance_due': r[3], 'days_delinquent': r[4], 'stage': r[5],
                        'last_notice_date': r[6]} for r in cursor.fetchall()]
        except Exception:
            return []

    def get_dunning_summary(self) -> Dict:
        """Get dunning summary with counts per stage."""
        try:
            with get_connection() as conn:
                cursor = self._cursor(conn)
                cursor.execute("""
                    SELECT stage, COUNT(*) as count, COALESCE(SUM(balance_due), 0) as total
                    FROM dunning_notices
                    WHERE firm_id = %s AND status = 'pending'
                    GROUP BY stage ORDER BY stage
                """, (self.firm_id,))
                by_stage = {}
                total_count = 0
                total_amount = 0
                for r in cursor.fetchall():
                    by_stage[r[0]] = {'count': r[1], 'total': r[2]}
                    total_count += r[1]
                    total_amount += r[2]
                return {
                    'by_stage': by_stage,
                    'total_count': total_count,
                    'total_amount': total_amount,
                }
        except Exception:
            return {'by_stage': {}, 'total_count': 0, 'total_amount': 0}

    def get_dunning_queue(self, stage: int = None) -> List[Dict]:
        """Get dunning queue (alias for get_dunning_preview)."""
        return self.get_dunning_preview(stage=stage)

    def get_dunning_history(self, limit: int = 20) -> List[Dict]:
        """Get recent dunning notice history."""
        try:
            with get_connection() as conn:
                cursor = self._cursor(conn)
                cursor.execute("""
                    SELECT invoice_id, case_name, contact_name, balance_due,
                           stage, status, last_notice_date, updated_at
                    FROM dunning_notices
                    WHERE firm_id = %s AND status != 'pending'
                    ORDER BY updated_at DESC
                    LIMIT %s
                """, (self.firm_id, limit))
                return [{'invoice_id': r[0], 'case_name': r[1], 'contact_name': r[2],
                        'balance_due': r[3], 'stage': r[4], 'status': r[5],
                        'last_notice_date': r[6], 'updated_at': r[7]}
                       for r in cursor.fetchall()]
        except Exception:
            return []

    def get_payment_analytics_summary(self, year: int = None) -> Dict:
        """Get payment analytics summary."""
        from datetime import datetime
        current_year = datetime.now().year
        if year is None:
            year = current_year
        try:
            with get_connection() as conn:
                cursor = self._cursor(conn)
                cursor.execute("""
                    SELECT COUNT(*) as total_invoices,
                           COALESCE(SUM(total_amount), 0) as total_billed,
                           COALESCE(SUM(paid_amount), 0) as total_collected,
                           COALESCE(AVG(CASE WHEN paid_amount > 0
                               THEN GREATEST((CURRENT_DATE - due_date), 0) END), 0) as avg_days_to_payment
                    FROM cached_invoices
                    WHERE firm_id = %s AND EXTRACT(YEAR FROM invoice_date) = %s
                """, (self.firm_id, year))
                r = cursor.fetchone()
                return {
                    'total_invoices': r[0] or 0,
                    'total_billed': r[1] or 0,
                    'total_collected': r[2] or 0,
                    'avg_days_to_payment': round(r[3] or 0),
                    'collection_rate': (r[2] / r[1] * 100) if r[1] else 0,
                }
        except Exception:
            return {'total_invoices': 0, 'total_billed': 0, 'total_collected': 0,
                    'avg_days_to_payment': 0, 'collection_rate': 0}

    def get_time_to_payment_by_attorney(self, year: int = None) -> List[Dict]:
        """Get average time-to-payment broken down by attorney."""
        from datetime import datetime
        current_year = datetime.now().year
        if year is None:
            year = current_year
        try:
            with get_connection() as conn:
                cursor = self._cursor(conn)
                cursor.execute("""
                    SELECT c.lead_attorney_name,
                           COUNT(i.id) as invoice_count,
                           COALESCE(SUM(i.total_amount), 0) as total_billed,
                           COALESCE(SUM(i.paid_amount), 0) as total_collected,
                           COALESCE(AVG(CASE WHEN i.paid_amount > 0
                               THEN GREATEST((CURRENT_DATE - i.due_date), 0) END), 0) as avg_days
                    FROM cached_invoices i
                    JOIN cached_cases c ON i.case_id = c.id AND i.firm_id = c.firm_id
                    WHERE i.firm_id = %s AND EXTRACT(YEAR FROM i.invoice_date) = %s
                      AND c.lead_attorney_name IS NOT NULL AND c.lead_attorney_name != ''
                    GROUP BY c.lead_attorney_name
                    ORDER BY avg_days DESC
                """, (self.firm_id, year))
                return [{'attorney_name': r[0], 'invoice_count': r[1],
                        'total_billed': r[2], 'total_collected': r[3],
                        'avg_days': round(r[4] or 0)}
                       for r in cursor.fetchall()]
        except Exception:
            return []

    def get_time_to_payment_by_case_type(self, year: int = None) -> List[Dict]:
        """Get average time-to-payment broken down by case type."""
        from datetime import datetime
        current_year = datetime.now().year
        if year is None:
            year = current_year
        try:
            with get_connection() as conn:
                cursor = self._cursor(conn)
                cursor.execute("""
                    SELECT COALESCE(c.practice_area, 'Unknown') as case_type,
                           COUNT(i.id) as invoice_count,
                           COALESCE(SUM(i.total_amount), 0) as total_billed,
                           COALESCE(SUM(i.paid_amount), 0) as total_collected,
                           COALESCE(AVG(CASE WHEN i.paid_amount > 0
                               THEN GREATEST((CURRENT_DATE - i.due_date), 0) END), 0) as avg_days
                    FROM cached_invoices i
                    JOIN cached_cases c ON i.case_id = c.id AND i.firm_id = c.firm_id
                    WHERE i.firm_id = %s AND EXTRACT(YEAR FROM i.invoice_date) = %s
                    GROUP BY c.practice_area
                    ORDER BY total_billed DESC
                """, (self.firm_id, year))
                return [{'case_type': r[0], 'invoice_count': r[1],
                        'total_billed': r[2], 'total_collected': r[3],
                        'avg_days': round(r[4] or 0)}
                       for r in cursor.fetchall()]
        except Exception:
            return []

    def get_payment_velocity_trend(self, year: int = None, months_back: int = 6) -> List[Dict]:
        """Get payment velocity trend over recent months."""
        from datetime import datetime
        current_year = datetime.now().year
        if year is None:
            year = current_year
        try:
            with get_connection() as conn:
                cursor = self._cursor(conn)
                cursor.execute("""
                    SELECT DATE_TRUNC('month', invoice_date) as month,
                           COUNT(*) as invoice_count,
                           COALESCE(SUM(total_amount), 0) as billed,
                           COALESCE(SUM(paid_amount), 0) as collected
                    FROM cached_invoices
                    WHERE firm_id = %s
                      AND invoice_date >= CURRENT_DATE - INTERVAL '%s months'
                    GROUP BY DATE_TRUNC('month', invoice_date)
                    ORDER BY month
                """ % ('%s', months_back), (self.firm_id,))
                return [{'month': str(r[0])[:10], 'invoice_count': r[1],
                        'billed': r[2], 'collected': r[3]}
                       for r in cursor.fetchall()]
        except Exception:
            return []
