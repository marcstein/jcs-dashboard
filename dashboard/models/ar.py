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
        try:
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
        except Exception:
            pass

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

    def get_ar_aging_breakdown(self, year: int = None, years: list = None, rolling_months: int = None) -> Dict:
        """Get AR aging breakdown for charts."""
        if years:
            summary = self.get_combined_years_summary(years)
        elif rolling_months:
            summary = self.get_rolling_6month_summary()
        else:
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
        try:
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
        except Exception:
            return []

    def get_payment_plans_summary(self) -> Dict:
        """Get payment plans summary from local database."""
        try:
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
        except Exception:
            return {'active_count': 0, 'active_total': 0, 'delinquent_count': 0, 'completed_month': 0}

    def get_noiw_pipeline(self, status_filter: str = None) -> List[Dict]:
        """Get NOIW pipeline cases from local database."""
        try:
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
        except Exception:
            return []

    def get_noiw_summary(self) -> Dict:
        """Get NOIW pipeline summary statistics."""
        try:
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
        except Exception:
            return {
                'by_status': {}, 'bucket_30_60': 0, 'bucket_60_90': 0,
                'bucket_90_180': 0, 'bucket_180_plus': 0,
                'total_active': 0, 'total_balance': 0,
            }

    def get_wonky_invoices(self) -> List[Dict]:
        """Get open wonky invoices from local database."""
        try:
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
        except Exception:
            return []

    def _compute_dunning_stage(self, days_overdue: int, case_status: str = 'open') -> int:
        """Map days overdue to dunning stage (1-4).

        Stage 4 (NOIW) requires 60+ days AND an open case.
        Closed cases cap at Stage 3.
        """
        if days_overdue >= 60 and case_status == 'open':
            return 4
        elif days_overdue >= 30:
            return 3
        elif days_overdue >= 15:
            return 2
        elif days_overdue >= 5:
            return 1
        return 0  # Not yet in dunning

    def get_dunning_preview(self, stage: int = None, include_sent: bool = True) -> List[Dict]:
        """Get dunning queue computed live from cached_invoices.

        All open invoices with balance > 0 and 5+ days overdue, across ALL years,
        dynamically assigned to dunning stages based on days overdue.
        LEFT JOINs with aging_invoice_uploads (latest batch) to get amount_now_due.
        LEFT JOINs with dunning_notices to detect already-sent notices per stage.

        Args:
            stage: Filter to specific dunning stage (1-4). None = all stages.
            include_sent: If True, include already-sent notices (with flag). If False, exclude them.
        """
        try:
            with get_connection() as conn:
                cursor = self._cursor(conn)
                cursor.execute("""
                    WITH latest_aging_batch AS (
                        SELECT upload_batch_id
                        FROM aging_invoice_uploads
                        WHERE firm_id = %s
                        GROUP BY upload_batch_id
                        ORDER BY MIN(uploaded_at) DESC
                        LIMIT 1
                    )
                    SELECT
                        i.id as invoice_id,
                        i.invoice_number,
                        c.name as case_name,
                        c.lead_attorney_name,
                        COALESCE(cl.first_name || ' ' || cl.last_name, ct.name) as contact_name,
                        i.balance_due,
                        (CURRENT_DATE - i.due_date::date) as days_overdue,
                        i.due_date,
                        COALESCE(cl.email, ct.email) as contact_email,
                        ag.amount_overdue as aging_amount_due,
                        ag.invoice_total as aging_invoice_total,
                        dn.notice_level as sent_notice_level,
                        dn.sent_at as sent_at,
                        COALESCE(c.status, 'open') as case_status
                    FROM cached_invoices i
                    LEFT JOIN cached_cases c ON i.case_id = c.id AND i.firm_id = c.firm_id
                    LEFT JOIN cached_clients cl
                        ON cl.id = (c.data_json::jsonb -> 'billing_contact' ->> 'id')::integer
                        AND cl.firm_id = i.firm_id
                    LEFT JOIN cached_contacts ct ON i.contact_id = ct.id AND i.firm_id = ct.firm_id
                    LEFT JOIN aging_invoice_uploads ag
                        ON ag.firm_id = i.firm_id
                        AND ag.invoice_number = i.invoice_number
                        AND ag.upload_batch_id = (SELECT upload_batch_id FROM latest_aging_batch)
                    LEFT JOIN LATERAL (
                        SELECT MAX(notice_level) AS notice_level, MAX(sent_at) AS sent_at
                        FROM dunning_notices
                        WHERE firm_id = i.firm_id AND invoice_id = i.id
                    ) dn ON true
                    WHERE i.firm_id = %s
                      AND i.balance_due > 0
                      AND (CURRENT_DATE - i.due_date::date) >= 5
                    ORDER BY (CURRENT_DATE - i.due_date::date) DESC, i.balance_due DESC
                """, (self.firm_id, self.firm_id))

                results = []
                for r in cursor.fetchall():
                    raw_days = r[6]
                    days = raw_days if isinstance(raw_days, int) else (raw_days.days if hasattr(raw_days, 'days') else int(raw_days or 0))
                    case_status = (r[13] or 'open').lower()  # col 13 = case_status
                    s = self._compute_dunning_stage(days, case_status=case_status)
                    if s == 0:
                        continue
                    if stage and s != stage:
                        continue
                    balance_due = r[5] or 0
                    aging_amount = float(r[9]) if r[9] is not None else None

                    # Check if notice was already sent at this stage level
                    sent_level = r[11]  # notice_level from dunning_notices
                    sent_at = r[12]     # sent_at timestamp
                    already_sent = (sent_level is not None and sent_level >= s)

                    if not include_sent and already_sent:
                        continue

                    results.append({
                        'invoice_id': r[1] or str(r[0]),
                        'invoice_db_id': r[0],  # numeric DB id for recording
                        'case_name': r[2] or '',
                        'attorney': r[3] or 'Unassigned',
                        'contact_name': r[4] or '',
                        'balance_due': balance_due,
                        'amount_now_due': aging_amount,  # None if no aging data
                        'total_remaining_balance': balance_due,
                        'days_delinquent': days,
                        'stage': s,
                        'last_notice_date': str(r[7]) if r[7] else '',
                        'contact_email': r[8] or '',
                        'already_sent': already_sent,
                        'sent_at': str(sent_at) if sent_at else None,
                    })
                return results
        except Exception as e:
            print(f"[dunning] ERROR in get_dunning_preview: {e}")
            import traceback
            traceback.print_exc()
            return []

    def get_dunning_summary(self) -> Dict:
        """Get dunning summary computed live from cached_invoices.

        Dynamically computes stage counts from all open invoices across all years.
        Stage 4 (NOIW) only counts open cases with 60+ days overdue.
        """
        try:
            with get_connection() as conn:
                cursor = self._cursor(conn)

                cursor.execute("""
                    SELECT
                        (CURRENT_DATE - i.due_date::date) as days_overdue,
                        i.balance_due,
                        COALESCE(c.status, 'open') as case_status
                    FROM cached_invoices i
                    LEFT JOIN cached_cases c ON i.case_id = c.id AND i.firm_id = c.firm_id
                    WHERE i.firm_id = %s
                      AND i.balance_due > 0
                      AND (CURRENT_DATE - i.due_date::date) >= 5
                """, (self.firm_id,))

                by_stage = {}
                total_count = 0
                total_amount = 0
                for r in cursor.fetchall():
                    days = r[0] if isinstance(r[0], int) else (r[0].days if hasattr(r[0], 'days') else int(r[0] or 0))
                    balance = r[1] or 0
                    case_status = (r[2] or 'open').lower()
                    s = self._compute_dunning_stage(days, case_status=case_status)
                    if s == 0:
                        continue
                    if s not in by_stage:
                        by_stage[s] = {'count': 0, 'total': 0}
                    by_stage[s]['count'] += 1
                    by_stage[s]['total'] += balance
                    total_count += 1
                    total_amount += balance

                return {
                    'by_stage': by_stage,
                    'total_count': total_count,
                    'total_amount': total_amount,
                }
        except Exception as e:
            print(f"[dunning] ERROR in get_dunning_summary: {e}")
            import traceback
            traceback.print_exc()
            return {'by_stage': {}, 'total_count': 0, 'total_amount': 0}

    def get_dunning_queue(self, stage: int = None) -> List[Dict]:
        """Get dunning queue (alias for get_dunning_preview)."""
        return self.get_dunning_preview(stage=stage)

    def get_dunning_history(self, limit: int = 20) -> List[Dict]:
        """Get recent dunning notice history from dunning_notices table."""
        try:
            with get_connection() as conn:
                cursor = self._cursor(conn)
                cursor.execute("""
                    SELECT dn.invoice_number, dn.notice_level, dn.amount_due,
                           dn.template_used, dn.sent_at, dn.delivery_status
                    FROM dunning_notices dn
                    WHERE dn.firm_id = %s
                    ORDER BY dn.sent_at DESC
                    LIMIT %s
                """, (self.firm_id, limit))
                return [{'invoice_number': r[0], 'notice_level': r[1],
                        'amount_due': r[2] or 0, 'template_used': r[3] or '',
                        'sent_at': str(r[4]) if r[4] else '',
                        'delivery_status': r[5] or ''}
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
                af_sql, af_params = self._attorney_case_filter("c")
                if self.attorney_name:
                    # Attorney-scoped: join through cases
                    cursor.execute(f"""
                        SELECT COUNT(*) as total_invoices,
                               COALESCE(SUM(i.total_amount), 0) as total_billed,
                               COALESCE(SUM(i.paid_amount), 0) as total_collected,
                               COALESCE(AVG(CASE WHEN i.paid_amount > 0
                                   THEN GREATEST((CURRENT_DATE - i.due_date), 0) END), 0) as avg_days_to_payment
                        FROM cached_invoices i
                        JOIN cached_cases c ON i.case_id = c.id AND i.firm_id = c.firm_id
                        WHERE i.firm_id = %s AND EXTRACT(YEAR FROM i.invoice_date) = %s
                          {af_sql}
                    """, (self.firm_id, year, *af_params))
                else:
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
                af_sql, af_params = self._attorney_case_filter("c")
                cursor.execute(f"""
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
                      {af_sql}
                    GROUP BY c.lead_attorney_name
                    ORDER BY avg_days DESC
                """, (self.firm_id, year, *af_params))
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
                af_sql, af_params = self._attorney_case_filter("c")
                cursor.execute(f"""
                    SELECT COALESCE(c.practice_area, 'Unknown') as case_type,
                           COUNT(i.id) as invoice_count,
                           COALESCE(SUM(i.total_amount), 0) as total_billed,
                           COALESCE(SUM(i.paid_amount), 0) as total_collected,
                           COALESCE(AVG(CASE WHEN i.paid_amount > 0
                               THEN GREATEST((CURRENT_DATE - i.due_date), 0) END), 0) as avg_days
                    FROM cached_invoices i
                    JOIN cached_cases c ON i.case_id = c.id AND i.firm_id = c.firm_id
                    WHERE i.firm_id = %s AND EXTRACT(YEAR FROM i.invoice_date) = %s
                      {af_sql}
                    GROUP BY c.practice_area
                    ORDER BY total_billed DESC
                """, (self.firm_id, year, *af_params))
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
                af_sql, af_params = self._attorney_case_filter("c")
                if self.attorney_name:
                    cursor.execute(f"""
                        SELECT DATE_TRUNC('month', i.invoice_date) as month,
                               COUNT(*) as invoice_count,
                               COALESCE(SUM(i.total_amount), 0) as billed,
                               COALESCE(SUM(i.paid_amount), 0) as collected
                        FROM cached_invoices i
                        JOIN cached_cases c ON i.case_id = c.id AND i.firm_id = c.firm_id
                        WHERE i.firm_id = %s
                          AND i.invoice_date >= CURRENT_DATE - INTERVAL '{months_back} months'
                          {af_sql}
                        GROUP BY DATE_TRUNC('month', i.invoice_date)
                        ORDER BY month
                    """, (self.firm_id, *af_params))
                else:
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

    def get_combined_years_summary(self, years: List[int] = None) -> Dict:
        """Get AR summary combining multiple years (e.g., 2025+2026)."""
        if years is None:
            years = [2025, 2026]
        try:
            with get_connection() as conn:
                cursor = self._cursor(conn)
                year_placeholders = ','.join(['%s'] * len(years))
                cursor.execute(f"""
                    SELECT
                        SUM(balance_due) as total_ar,
                        SUM(CASE WHEN CURRENT_DATE - due_date < 0 THEN balance_due ELSE 0 END) as ar_current,
                        SUM(CASE WHEN CURRENT_DATE - due_date BETWEEN 0 AND 30 THEN balance_due ELSE 0 END) as ar_0_30,
                        SUM(CASE WHEN CURRENT_DATE - due_date BETWEEN 31 AND 60 THEN balance_due ELSE 0 END) as ar_31_60,
                        SUM(CASE WHEN CURRENT_DATE - due_date BETWEEN 61 AND 90 THEN balance_due ELSE 0 END) as ar_61_90,
                        SUM(CASE WHEN CURRENT_DATE - due_date BETWEEN 91 AND 120 THEN balance_due ELSE 0 END) as ar_91_120,
                        SUM(CASE WHEN CURRENT_DATE - due_date > 120 THEN balance_due ELSE 0 END) as ar_120_plus,
                        SUM(CASE WHEN CURRENT_DATE - due_date > 90 THEN balance_due ELSE 0 END) as ar_90_plus,
                        COUNT(CASE WHEN balance_due > 0 AND CURRENT_DATE - due_date > 30 THEN 1 END) as delinquent
                    FROM cached_invoices
                    WHERE firm_id = %s
                      AND balance_due > 0
                      AND EXTRACT(YEAR FROM invoice_date) IN ({year_placeholders})
                """, (self.firm_id, *years))
                row = cursor.fetchone()

                cursor.execute(f"""
                    SELECT SUM(total_amount) as total_billed, SUM(paid_amount) as total_collected
                    FROM cached_invoices
                    WHERE firm_id = %s
                      AND EXTRACT(YEAR FROM invoice_date) IN ({year_placeholders})
                """, (self.firm_id, *years))
                billing_row = cursor.fetchone()
                total_billed = (billing_row[0] or 0) if billing_row else 0
                total_collected = (billing_row[1] or 0) if billing_row else 0

                if row and row[0]:
                    total_ar = row[0] or 0
                    ar_61_90 = row[4] or 0
                    ar_90_plus = row[7] or 0
                    over_60 = ar_61_90 + ar_90_plus
                    over_60_pct = (over_60 / total_billed * 100) if total_billed > 0 else 0
                    collection_rate = (total_collected / total_billed * 100) if total_billed > 0 else 0

                    return {
                        'total_ar': total_ar,
                        'total_billed': total_billed,
                        'total_collected': total_collected,
                        'collection_rate': collection_rate,
                        'ar_current': row[1] or 0,
                        'ar_0_30': row[2] or 0,
                        'ar_31_60': row[3] or 0,
                        'ar_61_90': ar_61_90,
                        'ar_91_120': row[5] or 0,
                        'ar_120_plus': row[6] or 0,
                        'ar_90_plus': ar_90_plus,
                        'aging_over_60_pct': over_60_pct,
                        'delinquent_accounts': row[8] or 0,
                    }
        except Exception:
            pass
        return {'total_ar': 0, 'total_billed': 0, 'total_collected': 0, 'collection_rate': 0,
                'ar_current': 0, 'ar_0_30': 0, 'ar_31_60': 0, 'ar_61_90': 0,
                'ar_91_120': 0, 'ar_120_plus': 0, 'ar_90_plus': 0,
                'aging_over_60_pct': 0, 'delinquent_accounts': 0}

    def get_rolling_6month_summary(self) -> Dict:
        """Get rolling 6-month AR summary with monthly averages."""
        try:
            with get_connection() as conn:
                cursor = self._cursor(conn)
                # Monthly breakdown for last 6 months
                cursor.execute("""
                    SELECT
                        TO_CHAR(DATE_TRUNC('month', invoice_date), 'YYYY-MM') as month,
                        COUNT(*) as invoice_count,
                        COALESCE(SUM(total_amount), 0) as billed,
                        COALESCE(SUM(paid_amount), 0) as collected,
                        COALESCE(SUM(balance_due), 0) as outstanding
                    FROM cached_invoices
                    WHERE firm_id = %s
                      AND invoice_date >= DATE_TRUNC('month', CURRENT_DATE) - INTERVAL '6 months'
                    GROUP BY DATE_TRUNC('month', invoice_date)
                    ORDER BY month
                """, (self.firm_id,))
                months = []
                total_billed = 0
                total_collected = 0
                total_outstanding = 0
                total_invoices = 0
                for r in cursor.fetchall():
                    months.append({
                        'month': r[0],
                        'invoice_count': r[1],
                        'billed': r[2],
                        'collected': r[3],
                        'outstanding': r[4],
                        'collection_rate': (r[3] / r[2] * 100) if r[2] > 0 else 0,
                    })
                    total_billed += r[2]
                    total_collected += r[3]
                    total_outstanding += r[4]
                    total_invoices += r[1]

                num_months = len(months) or 1
                avg_billed = total_billed / num_months
                avg_collected = total_collected / num_months
                avg_invoices = total_invoices / num_months
                overall_rate = (total_collected / total_billed * 100) if total_billed > 0 else 0

                # Current aging snapshot for invoices in the 6-month window
                cursor.execute("""
                    SELECT
                        SUM(balance_due) as total_ar,
                        SUM(CASE WHEN CURRENT_DATE - due_date < 0 THEN balance_due ELSE 0 END) as ar_current,
                        SUM(CASE WHEN CURRENT_DATE - due_date BETWEEN 0 AND 30 THEN balance_due ELSE 0 END) as ar_0_30,
                        SUM(CASE WHEN CURRENT_DATE - due_date BETWEEN 31 AND 60 THEN balance_due ELSE 0 END) as ar_31_60,
                        SUM(CASE WHEN CURRENT_DATE - due_date BETWEEN 61 AND 90 THEN balance_due ELSE 0 END) as ar_61_90,
                        SUM(CASE WHEN CURRENT_DATE - due_date BETWEEN 91 AND 120 THEN balance_due ELSE 0 END) as ar_91_120,
                        SUM(CASE WHEN CURRENT_DATE - due_date > 120 THEN balance_due ELSE 0 END) as ar_120_plus,
                        SUM(CASE WHEN CURRENT_DATE - due_date > 90 THEN balance_due ELSE 0 END) as ar_90_plus,
                        COUNT(CASE WHEN balance_due > 0 AND CURRENT_DATE - due_date > 30 THEN 1 END) as delinquent
                    FROM cached_invoices
                    WHERE firm_id = %s
                      AND balance_due > 0
                      AND invoice_date >= DATE_TRUNC('month', CURRENT_DATE) - INTERVAL '6 months'
                """, (self.firm_id,))
                aging = cursor.fetchone()

                return {
                    'months': months,
                    'num_months': num_months,
                    'total_billed': total_billed,
                    'total_collected': total_collected,
                    'total_outstanding': total_outstanding,
                    'total_invoices': total_invoices,
                    'avg_monthly_billed': avg_billed,
                    'avg_monthly_collected': avg_collected,
                    'avg_monthly_invoices': round(avg_invoices),
                    'collection_rate': overall_rate,
                    'overall_collection_rate': overall_rate,
                    'total_ar': (aging[0] or 0) if aging else 0,
                    'ar_current': (aging[1] or 0) if aging else 0,
                    'ar_0_30': (aging[2] or 0) if aging else 0,
                    'ar_31_60': (aging[3] or 0) if aging else 0,
                    'ar_61_90': (aging[4] or 0) if aging else 0,
                    'ar_91_120': (aging[5] or 0) if aging else 0,
                    'ar_120_plus': (aging[6] or 0) if aging else 0,
                    'ar_90_plus': (aging[7] or 0) if aging else 0,
                    'aging_over_60_pct': (((aging[4] or 0) + (aging[7] or 0)) / total_billed * 100) if total_billed > 0 else 0,
                    'delinquent_accounts': (aging[8] or 0) if aging else 0,
                }
        except Exception:
            return {
                'months': [], 'num_months': 0, 'total_billed': 0, 'total_collected': 0,
                'total_outstanding': 0, 'total_invoices': 0, 'avg_monthly_billed': 0,
                'avg_monthly_collected': 0, 'avg_monthly_invoices': 0,
                'collection_rate': 0, 'overall_collection_rate': 0,
                'total_ar': 0, 'ar_current': 0, 'ar_0_30': 0,
                'ar_31_60': 0, 'ar_61_90': 0, 'ar_91_120': 0,
                'ar_120_plus': 0, 'ar_90_plus': 0,
                'aging_over_60_pct': 0, 'delinquent_accounts': 0,
            }

    def get_open_invoices_list(self, min_days_overdue: int = 0) -> List[Dict]:
        """Get all open invoices with balance due across ALL years.

        Returns individual invoice rows with case, client, attorney, balance,
        and aging info. No year filter — shows everything still unpaid.
        """
        try:
            with get_connection() as conn:
                cursor = self._cursor(conn)
                cursor.execute("""
                    SELECT
                        i.id as invoice_id,
                        i.invoice_number,
                        c.name as case_name,
                        c.lead_attorney_name,
                        COALESCE(cl.first_name || ' ' || cl.last_name, ct.name) as contact_name,
                        i.total_amount,
                        i.paid_amount,
                        i.balance_due,
                        i.due_date,
                        i.invoice_date,
                        (CURRENT_DATE - i.due_date) as days_overdue,
                        EXTRACT(YEAR FROM i.invoice_date) as invoice_year,
                        c.practice_area,
                        c.status as case_status,
                        COALESCE(cl.email, ct.email) as contact_email
                    FROM cached_invoices i
                    LEFT JOIN cached_cases c ON i.case_id = c.id AND i.firm_id = c.firm_id
                    LEFT JOIN cached_clients cl
                        ON cl.id = (c.data_json::jsonb -> 'billing_contact' ->> 'id')::integer
                        AND cl.firm_id = i.firm_id
                    LEFT JOIN cached_contacts ct ON i.contact_id = ct.id AND i.firm_id = ct.firm_id
                    WHERE i.firm_id = %s
                      AND i.balance_due > 0
                      AND (CURRENT_DATE - i.due_date) >= %s
                    ORDER BY (CURRENT_DATE - i.due_date) DESC, i.balance_due DESC
                """, (self.firm_id, min_days_overdue))
                rows = cursor.fetchall()
                return [{
                    'invoice_id': r[0],
                    'invoice_number': r[1],
                    'case_name': r[2],
                    'attorney': r[3] or 'Unassigned',
                    'contact_name': r[4] or 'Unknown',
                    'total_amount': r[5] or 0,
                    'paid_amount': r[6] or 0,
                    'balance_due': r[7] or 0,
                    'due_date': str(r[8]) if r[8] else '',
                    'invoice_date': str(r[9]) if r[9] else '',
                    'days_overdue': r[10] or 0,
                    'invoice_year': int(r[11]) if r[11] else 0,
                    'practice_area': r[12] or 'Unknown',
                    'case_status': r[13] or 'Unknown',
                    'contact_email': r[14] or '',
                } for r in rows]
        except Exception:
            return []

    def get_open_invoices_by_attorney(self) -> List[Dict]:
        """Get open invoice summary grouped by attorney.

        Returns one row per attorney with totals for billed, paid, balance,
        invoice count, and average days overdue.
        """
        try:
            with get_connection() as conn:
                cursor = self._cursor(conn)
                cursor.execute("""
                    SELECT
                        COALESCE(c.lead_attorney_name, 'Unassigned') as attorney,
                        COUNT(*) as invoice_count,
                        SUM(i.total_amount) as total_billed,
                        SUM(i.paid_amount) as total_paid,
                        SUM(i.balance_due) as total_balance,
                        AVG(CURRENT_DATE - i.due_date) as avg_days_overdue
                    FROM cached_invoices i
                    LEFT JOIN cached_cases c ON i.case_id = c.id AND i.firm_id = c.firm_id
                    WHERE i.firm_id = %s
                      AND i.balance_due > 0
                    GROUP BY COALESCE(c.lead_attorney_name, 'Unassigned')
                    ORDER BY SUM(i.balance_due) DESC
                """, (self.firm_id,))
                rows = cursor.fetchall()
                return [{
                    'attorney': r[0],
                    'invoice_count': r[1],
                    'total_billed': r[2] or 0,
                    'total_paid': r[3] or 0,
                    'total_balance': r[4] or 0,
                    'avg_days_overdue': round(r[5] or 0),
                } for r in rows]
        except Exception:
            return []
