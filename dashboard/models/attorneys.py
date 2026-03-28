"""
Attorney Productivity Data Access
"""
from datetime import datetime
from typing import Dict, List, Optional

import psycopg2.extensions
from db.connection import get_connection
from db.attorney_targets import get_all_attorney_targets, get_attorney_target, compute_annual_target


class AttorneyDataMixin:
    """Mixin providing attorney productivity and invoice aging data methods."""

    def get_attorney_productivity(self) -> List[Dict]:
        """Get attorney productivity metrics (legacy - used by CLI)."""
        return self.get_attorney_productivity_data()

    def _get_attorney_list(self, cursor) -> List[str]:
        """Get list of attorneys to show, filtered by self.attorney_name if set."""
        if self.attorney_name:
            # Attorney-role user: only show their own data
            cursor.execute("""
                SELECT DISTINCT lead_attorney_name
                FROM cached_cases
                WHERE firm_id = %s
                  AND lead_attorney_name = %s
            """, (self.firm_id, self.attorney_name))
        else:
            cursor.execute("""
                SELECT DISTINCT lead_attorney_name
                FROM cached_cases
                WHERE firm_id = %s
                  AND lead_attorney_name IS NOT NULL
                  AND lead_attorney_name != ''
                ORDER BY lead_attorney_name
            """, (self.firm_id,))
        return [row[0] for row in cursor.fetchall()]

    def _attorney_aging_filter(self) -> tuple:
        """Return (sql_fragment, params) for filtering aging queries to logged-in attorney."""
        if self.attorney_name:
            return " AND c.lead_attorney_name = %s", (self.attorney_name,)
        return "", ()

    def get_attorney_productivity_data(self, year: int = None) -> List[Dict]:
        """Get attorney productivity metrics for specified year."""
        current_year = datetime.now().year
        if year is None:
            year = current_year
        try:
            with get_connection() as conn:
                cursor = self._cursor(conn)

                attorneys = self._get_attorney_list(cursor)

                result = []
                for attorney_name in attorneys:
                    # Active (open) cases
                    cursor.execute("""
                        SELECT COUNT(*)
                        FROM cached_cases
                        WHERE firm_id = %s
                          AND lead_attorney_name = %s
                          AND status = 'open'
                    """, (self.firm_id, attorney_name))
                    active_cases = cursor.fetchone()[0] or 0

                    # Closed this month
                    cursor.execute("""
                        SELECT COUNT(*)
                        FROM cached_cases
                        WHERE firm_id = %s
                          AND lead_attorney_name = %s
                          AND status = 'closed'
                          AND DATE(updated_at) >= DATE_TRUNC('month', CURRENT_DATE)
                    """, (self.firm_id, attorney_name))
                    closed_mtd = cursor.fetchone()[0] or 0

                    # Closed year-to-date
                    cursor.execute("""
                        SELECT COUNT(*)
                        FROM cached_cases
                        WHERE firm_id = %s
                          AND lead_attorney_name = %s
                          AND status = 'closed'
                          AND EXTRACT(YEAR FROM updated_at) = %s
                    """, (self.firm_id, attorney_name, year))
                    closed_ytd = cursor.fetchone()[0] or 0

                    # Billing via JOIN through cases (invoices don't have attorney_name)
                    cursor.execute("""
                        SELECT COALESCE(SUM(i.total_amount), 0),
                               COALESCE(SUM(i.paid_amount), 0),
                               COALESCE(SUM(i.balance_due), 0)
                        FROM cached_invoices i
                        JOIN cached_cases c ON i.case_id = c.id AND i.firm_id = c.firm_id
                        WHERE i.firm_id = %s
                          AND c.lead_attorney_name = %s
                          AND EXTRACT(YEAR FROM i.invoice_date) = %s
                    """, (self.firm_id, attorney_name, year))
                    brow = cursor.fetchone()
                    total_billed = brow[0] or 0
                    total_collected = brow[1] or 0
                    total_outstanding = brow[2] or 0

                    collection_rate = (total_collected / total_billed * 100) if total_billed > 0 else 0

                    result.append({
                        'attorney_id': attorney_name,
                        'attorney_name': attorney_name,
                        'active_cases': active_cases,
                        'closed_mtd': closed_mtd,
                        'closed_ytd': closed_ytd,
                        'total_billed': total_billed,
                        'total_collected': total_collected,
                        'total_outstanding': total_outstanding,
                        'collection_rate': collection_rate,
                    })

                return sorted(result, key=lambda x: x['active_cases'], reverse=True)
        except Exception as e:
            print(f"get_attorney_productivity_data error: {e}")
            return []

    def get_attorney_invoice_aging(self, year: int = None) -> List[Dict]:
        """Get invoice aging breakdown by attorney for specified year."""
        current_year = datetime.now().year
        if year is None:
            year = current_year
        try:
            with get_connection() as conn:
                cursor = self._cursor(conn)

                af_sql, af_params = self._attorney_aging_filter()
                cursor.execute(f"""
                    SELECT c.lead_attorney_name,
                           SUM(CASE WHEN i.balance_due = 0 THEN 1 ELSE 0 END) as paid_full,
                           SUM(CASE WHEN i.balance_due > 0 AND (CURRENT_DATE - i.due_date) BETWEEN 1 AND 30 THEN 1 ELSE 0 END) as dpd_1_30,
                           SUM(CASE WHEN i.balance_due > 0 AND (CURRENT_DATE - i.due_date) BETWEEN 31 AND 60 THEN 1 ELSE 0 END) as dpd_31_60,
                           SUM(CASE WHEN i.balance_due > 0 AND (CURRENT_DATE - i.due_date) BETWEEN 61 AND 90 THEN 1 ELSE 0 END) as dpd_61_90,
                           SUM(CASE WHEN i.balance_due > 0 AND (CURRENT_DATE - i.due_date) BETWEEN 91 AND 120 THEN 1 ELSE 0 END) as dpd_91_120,
                           SUM(CASE WHEN i.balance_due > 0 AND (CURRENT_DATE - i.due_date) BETWEEN 121 AND 180 THEN 1 ELSE 0 END) as dpd_121_180,
                           SUM(CASE WHEN i.balance_due > 0 AND (CURRENT_DATE - i.due_date) > 180 THEN 1 ELSE 0 END) as dpd_over_180
                    FROM cached_invoices i
                    JOIN cached_cases c ON i.case_id = c.id AND i.firm_id = c.firm_id
                    WHERE i.firm_id = %s
                      AND EXTRACT(YEAR FROM i.invoice_date) = %s
                      AND c.lead_attorney_name IS NOT NULL AND c.lead_attorney_name != ''
                      {af_sql}
                    GROUP BY c.lead_attorney_name
                    ORDER BY c.lead_attorney_name
                """, (self.firm_id, year, *af_params))

                return [{
                    'attorney_id': r[0],
                    'attorney_name': r[0],
                    'paid_full': r[1] or 0,
                    'dpd_1_30': r[2] or 0,
                    'dpd_31_60': r[3] or 0,
                    'dpd_61_90': r[4] or 0,
                    'dpd_91_120': r[5] or 0,
                    'dpd_121_180': r[6] or 0,
                    'dpd_over_180': r[7] or 0,
                } for r in cursor.fetchall()]
        except Exception as e:
            print(f"get_attorney_invoice_aging error: {e}")
            return []

    def get_attorney_productivity_combined(self, years: list = None) -> List[Dict]:
        """Get attorney productivity metrics combining multiple years."""
        if years is None:
            years = [2025, 2026]
        try:
            with get_connection() as conn:
                cursor = self._cursor(conn)

                attorneys = self._get_attorney_list(cursor)

                year_placeholders = ','.join(['%s'] * len(years))
                result = []
                for attorney_name in attorneys:
                    cursor.execute("""
                        SELECT COUNT(*) FROM cached_cases
                        WHERE firm_id = %s AND lead_attorney_name = %s AND status = 'open'
                    """, (self.firm_id, attorney_name))
                    active_cases = cursor.fetchone()[0] or 0

                    cursor.execute("""
                        SELECT COUNT(*) FROM cached_cases
                        WHERE firm_id = %s AND lead_attorney_name = %s
                          AND status = 'closed'
                          AND DATE(updated_at) >= DATE_TRUNC('month', CURRENT_DATE)
                    """, (self.firm_id, attorney_name))
                    closed_mtd = cursor.fetchone()[0] or 0

                    cursor.execute(f"""
                        SELECT COUNT(*) FROM cached_cases
                        WHERE firm_id = %s AND lead_attorney_name = %s
                          AND status = 'closed'
                          AND EXTRACT(YEAR FROM updated_at) IN ({year_placeholders})
                    """, (self.firm_id, attorney_name, *years))
                    closed_ytd = cursor.fetchone()[0] or 0

                    cursor.execute(f"""
                        SELECT COALESCE(SUM(i.total_amount), 0),
                               COALESCE(SUM(i.paid_amount), 0),
                               COALESCE(SUM(i.balance_due), 0)
                        FROM cached_invoices i
                        JOIN cached_cases c ON i.case_id = c.id AND i.firm_id = c.firm_id
                        WHERE i.firm_id = %s AND c.lead_attorney_name = %s
                          AND EXTRACT(YEAR FROM i.invoice_date) IN ({year_placeholders})
                    """, (self.firm_id, attorney_name, *years))
                    brow = cursor.fetchone()
                    total_billed = brow[0] or 0
                    total_collected = brow[1] or 0
                    total_outstanding = brow[2] or 0
                    collection_rate = (total_collected / total_billed * 100) if total_billed > 0 else 0

                    result.append({
                        'attorney_id': attorney_name,
                        'attorney_name': attorney_name,
                        'active_cases': active_cases,
                        'closed_mtd': closed_mtd,
                        'closed_ytd': closed_ytd,
                        'total_billed': total_billed,
                        'total_collected': total_collected,
                        'total_outstanding': total_outstanding,
                        'collection_rate': collection_rate,
                    })

                return sorted(result, key=lambda x: x['active_cases'], reverse=True)
        except Exception as e:
            print(f"get_attorney_productivity_combined error: {e}")
            return []

    def get_attorney_invoice_aging_combined(self, years: list = None) -> List[Dict]:
        """Get invoice aging breakdown by attorney combining multiple years."""
        if years is None:
            years = [2025, 2026]
        try:
            with get_connection() as conn:
                cursor = self._cursor(conn)
                year_placeholders = ','.join(['%s'] * len(years))

                af_sql, af_params = self._attorney_aging_filter()
                cursor.execute(f"""
                    SELECT c.lead_attorney_name,
                           SUM(CASE WHEN i.balance_due = 0 THEN 1 ELSE 0 END) as paid_full,
                           SUM(CASE WHEN i.balance_due > 0 AND (CURRENT_DATE - i.due_date) BETWEEN 1 AND 30 THEN 1 ELSE 0 END) as dpd_1_30,
                           SUM(CASE WHEN i.balance_due > 0 AND (CURRENT_DATE - i.due_date) BETWEEN 31 AND 60 THEN 1 ELSE 0 END) as dpd_31_60,
                           SUM(CASE WHEN i.balance_due > 0 AND (CURRENT_DATE - i.due_date) BETWEEN 61 AND 90 THEN 1 ELSE 0 END) as dpd_61_90,
                           SUM(CASE WHEN i.balance_due > 0 AND (CURRENT_DATE - i.due_date) BETWEEN 91 AND 120 THEN 1 ELSE 0 END) as dpd_91_120,
                           SUM(CASE WHEN i.balance_due > 0 AND (CURRENT_DATE - i.due_date) BETWEEN 121 AND 180 THEN 1 ELSE 0 END) as dpd_121_180,
                           SUM(CASE WHEN i.balance_due > 0 AND (CURRENT_DATE - i.due_date) > 180 THEN 1 ELSE 0 END) as dpd_over_180
                    FROM cached_invoices i
                    JOIN cached_cases c ON i.case_id = c.id AND i.firm_id = c.firm_id
                    WHERE i.firm_id = %s
                      AND EXTRACT(YEAR FROM i.invoice_date) IN ({year_placeholders})
                      AND c.lead_attorney_name IS NOT NULL AND c.lead_attorney_name != ''
                      {af_sql}
                    GROUP BY c.lead_attorney_name
                    ORDER BY c.lead_attorney_name
                """, (self.firm_id, *years, *af_params))

                return [{
                    'attorney_id': r[0],
                    'attorney_name': r[0],
                    'paid_full': r[1] or 0,
                    'dpd_1_30': r[2] or 0,
                    'dpd_31_60': r[3] or 0,
                    'dpd_61_90': r[4] or 0,
                    'dpd_91_120': r[5] or 0,
                    'dpd_121_180': r[6] or 0,
                    'dpd_over_180': r[7] or 0,
                } for r in cursor.fetchall()]
        except Exception as e:
            print(f"get_attorney_invoice_aging_combined error: {e}")
            return []

    def get_attorney_productivity_rolling(self, months: int = 6) -> List[Dict]:
        """Get attorney productivity for the rolling N-month window."""
        try:
            with get_connection() as conn:
                cursor = self._cursor(conn)

                attorneys = self._get_attorney_list(cursor)

                result = []
                for attorney_name in attorneys:
                    cursor.execute("""
                        SELECT COUNT(*) FROM cached_cases
                        WHERE firm_id = %s AND lead_attorney_name = %s AND status = 'open'
                    """, (self.firm_id, attorney_name))
                    active_cases = cursor.fetchone()[0] or 0

                    cursor.execute("""
                        SELECT COUNT(*) FROM cached_cases
                        WHERE firm_id = %s AND lead_attorney_name = %s
                          AND status = 'closed'
                          AND DATE(updated_at) >= DATE_TRUNC('month', CURRENT_DATE)
                    """, (self.firm_id, attorney_name))
                    closed_mtd = cursor.fetchone()[0] or 0

                    cursor.execute("""
                        SELECT COUNT(*) FROM cached_cases
                        WHERE firm_id = %s AND lead_attorney_name = %s
                          AND status = 'closed'
                          AND updated_at >= DATE_TRUNC('month', CURRENT_DATE) - INTERVAL '1 month' * %s
                    """, (self.firm_id, attorney_name, months))
                    closed_period = cursor.fetchone()[0] or 0

                    cursor.execute("""
                        SELECT COALESCE(SUM(i.total_amount), 0),
                               COALESCE(SUM(i.paid_amount), 0),
                               COALESCE(SUM(i.balance_due), 0)
                        FROM cached_invoices i
                        JOIN cached_cases c ON i.case_id = c.id AND i.firm_id = c.firm_id
                        WHERE i.firm_id = %s AND c.lead_attorney_name = %s
                          AND i.invoice_date >= DATE_TRUNC('month', CURRENT_DATE) - INTERVAL '1 month' * %s
                    """, (self.firm_id, attorney_name, months))
                    brow = cursor.fetchone()
                    total_billed = brow[0] or 0
                    total_collected = brow[1] or 0
                    total_outstanding = brow[2] or 0
                    collection_rate = (total_collected / total_billed * 100) if total_billed > 0 else 0

                    result.append({
                        'attorney_id': attorney_name,
                        'attorney_name': attorney_name,
                        'active_cases': active_cases,
                        'closed_mtd': closed_mtd,
                        'closed_ytd': closed_period,
                        'total_billed': total_billed,
                        'total_collected': total_collected,
                        'total_outstanding': total_outstanding,
                        'collection_rate': collection_rate,
                    })

                return sorted(result, key=lambda x: x['active_cases'], reverse=True)
        except Exception as e:
            print(f"get_attorney_productivity_rolling error: {e}")
            return []

    def get_attorney_invoice_aging_rolling(self, months: int = 6) -> List[Dict]:
        """Get invoice aging breakdown by attorney for rolling N-month window."""
        try:
            with get_connection() as conn:
                cursor = self._cursor(conn)

                af_sql, af_params = self._attorney_aging_filter()
                cursor.execute(f"""
                    SELECT c.lead_attorney_name,
                           SUM(CASE WHEN i.balance_due = 0 THEN 1 ELSE 0 END) as paid_full,
                           SUM(CASE WHEN i.balance_due > 0 AND (CURRENT_DATE - i.due_date) BETWEEN 1 AND 30 THEN 1 ELSE 0 END) as dpd_1_30,
                           SUM(CASE WHEN i.balance_due > 0 AND (CURRENT_DATE - i.due_date) BETWEEN 31 AND 60 THEN 1 ELSE 0 END) as dpd_31_60,
                           SUM(CASE WHEN i.balance_due > 0 AND (CURRENT_DATE - i.due_date) BETWEEN 61 AND 90 THEN 1 ELSE 0 END) as dpd_61_90,
                           SUM(CASE WHEN i.balance_due > 0 AND (CURRENT_DATE - i.due_date) BETWEEN 91 AND 120 THEN 1 ELSE 0 END) as dpd_91_120,
                           SUM(CASE WHEN i.balance_due > 0 AND (CURRENT_DATE - i.due_date) BETWEEN 121 AND 180 THEN 1 ELSE 0 END) as dpd_121_180,
                           SUM(CASE WHEN i.balance_due > 0 AND (CURRENT_DATE - i.due_date) > 180 THEN 1 ELSE 0 END) as dpd_over_180
                    FROM cached_invoices i
                    JOIN cached_cases c ON i.case_id = c.id AND i.firm_id = c.firm_id
                    WHERE i.firm_id = %s
                      AND i.invoice_date >= DATE_TRUNC('month', CURRENT_DATE) - INTERVAL '1 month' * %s
                      AND c.lead_attorney_name IS NOT NULL AND c.lead_attorney_name != ''
                      {af_sql}
                    GROUP BY c.lead_attorney_name
                    ORDER BY c.lead_attorney_name
                """, (self.firm_id, months, *af_params))

                return [{
                    'attorney_id': r[0],
                    'attorney_name': r[0],
                    'paid_full': r[1] or 0,
                    'dpd_1_30': r[2] or 0,
                    'dpd_31_60': r[3] or 0,
                    'dpd_61_90': r[4] or 0,
                    'dpd_91_120': r[5] or 0,
                    'dpd_121_180': r[6] or 0,
                    'dpd_over_180': r[7] or 0,
                } for r in cursor.fetchall()]
        except Exception as e:
            print(f"get_attorney_invoice_aging_rolling error: {e}")
            return []

    def get_attorney_detail(self, attorney_name: str, year: int = None) -> Dict:
        """Get detailed attorney info including case list and invoice breakdown.

        Returns a dict structured for the attorney_detail.html template:
          - attorney_name, productivity (dict), aging (dict),
            call_list (list), call_list_count (int), active_cases (list)
        """
        current_year = datetime.now().year
        if year is None:
            year = current_year

        empty_result = {
            'attorney_name': attorney_name,
            'productivity': {
                'active_cases': 0, 'closed_mtd': 0, 'closed_ytd': 0,
                'total_billed': 0, 'total_collected': 0, 'total_outstanding': 0,
                'collection_rate': 0,
            },
            'aging': {
                'paid_full': 0, 'paid_full_pct': 0, 'current': 0,
                'dpd_1_30': 0, 'dpd_31_60': 0, 'dpd_61_90': 0,
                'dpd_91_120': 0, 'dpd_121_180': 0, 'dpd_over_180': 0,
                'amount_60_to_180': 0,
            },
            'call_list': [],
            'call_list_count': 0,
            'active_cases': [],
        }

        try:
            with get_connection() as conn:
                cursor = self._cursor(conn)

                # Active cases count
                cursor.execute("""
                    SELECT COUNT(*) FROM cached_cases
                    WHERE firm_id = %s AND lead_attorney_name ILIKE %s
                      AND status = 'open'
                """, (self.firm_id, f'%{attorney_name}%'))
                active_count = cursor.fetchone()[0] or 0

                # Closed MTD
                cursor.execute("""
                    SELECT COUNT(*) FROM cached_cases
                    WHERE firm_id = %s AND lead_attorney_name ILIKE %s
                      AND status = 'closed'
                      AND DATE(updated_at) >= DATE_TRUNC('month', CURRENT_DATE)
                """, (self.firm_id, f'%{attorney_name}%'))
                closed_mtd = cursor.fetchone()[0] or 0

                # Closed YTD
                cursor.execute("""
                    SELECT COUNT(*) FROM cached_cases
                    WHERE firm_id = %s AND lead_attorney_name ILIKE %s
                      AND status = 'closed'
                      AND EXTRACT(YEAR FROM updated_at) = %s
                """, (self.firm_id, f'%{attorney_name}%', year))
                closed_ytd = cursor.fetchone()[0] or 0

                # Billing totals via JOIN
                cursor.execute("""
                    SELECT COALESCE(SUM(i.total_amount), 0),
                           COALESCE(SUM(i.paid_amount), 0),
                           COALESCE(SUM(i.balance_due), 0)
                    FROM cached_invoices i
                    JOIN cached_cases c ON i.case_id = c.id AND i.firm_id = c.firm_id
                    WHERE i.firm_id = %s AND c.lead_attorney_name ILIKE %s
                      AND EXTRACT(YEAR FROM i.invoice_date) = %s
                """, (self.firm_id, f'%{attorney_name}%', year))
                row = cursor.fetchone()
                total_billed = row[0] or 0
                total_collected = row[1] or 0
                total_outstanding = row[2] or 0
                collection_rate = (total_collected / total_billed * 100) if total_billed > 0 else 0

                # Invoice aging breakdown
                cursor.execute("""
                    SELECT
                        SUM(CASE WHEN i.balance_due = 0 THEN 1 ELSE 0 END) as paid_full,
                        SUM(CASE WHEN i.balance_due > 0 AND i.due_date >= CURRENT_DATE THEN 1 ELSE 0 END) as current_inv,
                        SUM(CASE WHEN i.balance_due > 0 AND (CURRENT_DATE - i.due_date) BETWEEN 1 AND 30 THEN 1 ELSE 0 END) as dpd_1_30,
                        SUM(CASE WHEN i.balance_due > 0 AND (CURRENT_DATE - i.due_date) BETWEEN 31 AND 60 THEN 1 ELSE 0 END) as dpd_31_60,
                        SUM(CASE WHEN i.balance_due > 0 AND (CURRENT_DATE - i.due_date) BETWEEN 61 AND 90 THEN 1 ELSE 0 END) as dpd_61_90,
                        SUM(CASE WHEN i.balance_due > 0 AND (CURRENT_DATE - i.due_date) BETWEEN 91 AND 120 THEN 1 ELSE 0 END) as dpd_91_120,
                        SUM(CASE WHEN i.balance_due > 0 AND (CURRENT_DATE - i.due_date) BETWEEN 121 AND 180 THEN 1 ELSE 0 END) as dpd_121_180,
                        SUM(CASE WHEN i.balance_due > 0 AND (CURRENT_DATE - i.due_date) > 180 THEN 1 ELSE 0 END) as dpd_over_180,
                        COUNT(*) as total_invoices,
                        COALESCE(SUM(CASE WHEN i.balance_due > 0 AND (CURRENT_DATE - i.due_date) BETWEEN 61 AND 180 THEN i.balance_due ELSE 0 END), 0) as amount_60_to_180
                    FROM cached_invoices i
                    JOIN cached_cases c ON i.case_id = c.id AND i.firm_id = c.firm_id
                    WHERE i.firm_id = %s AND c.lead_attorney_name ILIKE %s
                      AND EXTRACT(YEAR FROM i.invoice_date) = %s
                """, (self.firm_id, f'%{attorney_name}%', year))
                arow = cursor.fetchone()
                paid_full = (arow[0] or 0)
                total_invoices = (arow[8] or 0)
                paid_full_pct = round(paid_full / total_invoices * 100) if total_invoices > 0 else 0

                # Active cases list
                cursor.execute("""
                    SELECT id, name, practice_area, case_number, status, created_at
                    FROM cached_cases
                    WHERE firm_id = %s AND lead_attorney_name ILIKE %s
                      AND status = 'open'
                    ORDER BY created_at DESC
                """, (self.firm_id, f'%{attorney_name}%'))
                cases = [{
                    'id': r[0], 'name': r[1], 'practice_area': r[2],
                    'case_number': r[3], 'status': r[4], 'date_opened': r[5]
                } for r in cursor.fetchall()]

                # Call list: 60-180 DPD invoices
                cursor.execute("""
                    SELECT i.id, i.invoice_number, c.name as case_name,
                           i.total_amount, i.balance_due, i.due_date,
                           (CURRENT_DATE - i.due_date) as days_overdue
                    FROM cached_invoices i
                    JOIN cached_cases c ON i.case_id = c.id AND i.firm_id = c.firm_id
                    WHERE i.firm_id = %s AND c.lead_attorney_name ILIKE %s
                      AND i.balance_due > 0
                      AND (CURRENT_DATE - i.due_date) BETWEEN 60 AND 180
                      AND EXTRACT(YEAR FROM i.invoice_date) = %s
                    ORDER BY i.due_date ASC
                """, (self.firm_id, f'%{attorney_name}%', year))
                call_list = [{
                    'id': r[0], 'invoice_number': r[1], 'case_name': r[2] or 'Unknown',
                    'total_amount': r[3], 'balance_due': r[4], 'due_date': r[5],
                    'days_overdue': r[6], 'contact_name': None,
                    'contact_phone': None, 'contact_email': None,
                    'collectible': True,
                } for r in cursor.fetchall()]

                return {
                    'attorney_name': attorney_name,
                    'productivity': {
                        'active_cases': active_count,
                        'closed_mtd': closed_mtd,
                        'closed_ytd': closed_ytd,
                        'total_billed': total_billed,
                        'total_collected': total_collected,
                        'total_outstanding': total_outstanding,
                        'collection_rate': collection_rate,
                    },
                    'aging': {
                        'paid_full': paid_full,
                        'paid_full_pct': paid_full_pct,
                        'current': (arow[1] or 0),
                        'dpd_1_30': (arow[2] or 0),
                        'dpd_31_60': (arow[3] or 0),
                        'dpd_61_90': (arow[4] or 0),
                        'dpd_91_120': (arow[5] or 0),
                        'dpd_121_180': (arow[6] or 0),
                        'dpd_over_180': (arow[7] or 0),
                        'amount_60_to_180': (arow[9] or 0),
                    },
                    'call_list': call_list,
                    'call_list_count': len(call_list),
                    'active_cases': cases,
                }
        except Exception as e:
            print(f"get_attorney_detail error for {attorney_name}: {e}")
            return empty_result

    def get_attorney_performance_metrics(self) -> List[Dict]:
        """Get gamified performance metrics for all attorneys with targets.

        Returns rolling 12-month billings as a percentage of target.
        No dollar amounts exposed — only percentages and trend data.
        """
        try:
            targets = get_all_attorney_targets(self.firm_id)
            if not targets:
                return []

            target_map = {}
            for t in targets:
                annual_target = compute_annual_target(t)
                target_map[t["attorney_name"]] = {
                    "annual_target": annual_target,
                    "salary": float(t["annual_salary"]),
                    "marketing_pct": float(t["marketing_pct"]),
                    "multiplier": float(t["target_multiplier"]),
                }

            with get_connection() as conn:
                cursor = self._cursor(conn)
                results = []

                for attorney_name, target_info in target_map.items():
                    # If attorney role, only show their own data
                    if self.attorney_name and self.attorney_name != attorney_name:
                        continue

                    annual_target = target_info["annual_target"]

                    # Rolling 12-month billings
                    cursor.execute("""
                        SELECT COALESCE(SUM(i.total_amount), 0)
                        FROM cached_invoices i
                        JOIN cached_cases c ON i.case_id = c.id AND i.firm_id = c.firm_id
                        WHERE i.firm_id = %s AND c.lead_attorney_name = %s
                          AND i.invoice_date >= CURRENT_DATE - INTERVAL '12 months'
                    """, (self.firm_id, attorney_name))
                    rolling_12m = float(cursor.fetchone()[0] or 0)

                    # Rolling 6-month billings (annualized for trend)
                    cursor.execute("""
                        SELECT COALESCE(SUM(i.total_amount), 0)
                        FROM cached_invoices i
                        JOIN cached_cases c ON i.case_id = c.id AND i.firm_id = c.firm_id
                        WHERE i.firm_id = %s AND c.lead_attorney_name = %s
                          AND i.invoice_date >= CURRENT_DATE - INTERVAL '6 months'
                    """, (self.firm_id, attorney_name))
                    rolling_6m = float(cursor.fetchone()[0] or 0)
                    annualized_6m = rolling_6m * 2  # project to annual pace

                    # Last 3 months (for current momentum)
                    cursor.execute("""
                        SELECT COALESCE(SUM(i.total_amount), 0)
                        FROM cached_invoices i
                        JOIN cached_cases c ON i.case_id = c.id AND i.firm_id = c.firm_id
                        WHERE i.firm_id = %s AND c.lead_attorney_name = %s
                          AND i.invoice_date >= CURRENT_DATE - INTERVAL '3 months'
                    """, (self.firm_id, attorney_name))
                    rolling_3m = float(cursor.fetchone()[0] or 0)
                    annualized_3m = rolling_3m * 4  # project to annual pace

                    # Monthly breakdown for sparkline (last 12 months)
                    cursor.execute("""
                        SELECT DATE_TRUNC('month', i.invoice_date) AS month,
                               COALESCE(SUM(i.total_amount), 0) AS billed
                        FROM cached_invoices i
                        JOIN cached_cases c ON i.case_id = c.id AND i.firm_id = c.firm_id
                        WHERE i.firm_id = %s AND c.lead_attorney_name = %s
                          AND i.invoice_date >= DATE_TRUNC('month', CURRENT_DATE) - INTERVAL '11 months'
                        GROUP BY DATE_TRUNC('month', i.invoice_date)
                        ORDER BY month
                    """, (self.firm_id, attorney_name))
                    monthly_data = cursor.fetchall()

                    monthly_target = annual_target / 12
                    monthly_pcts = []
                    for row in monthly_data:
                        m_billed = float(row[1] or 0)
                        m_pct = round(m_billed / monthly_target * 100, 1) if monthly_target > 0 else 0
                        monthly_pcts.append(m_pct)

                    # Active cases
                    cursor.execute("""
                        SELECT COUNT(*) FROM cached_cases
                        WHERE firm_id = %s AND lead_attorney_name = %s AND status = 'open'
                    """, (self.firm_id, attorney_name))
                    active_cases = cursor.fetchone()[0] or 0

                    # Cases closed in last 12 months
                    cursor.execute("""
                        SELECT COUNT(*) FROM cached_cases
                        WHERE firm_id = %s AND lead_attorney_name = %s
                          AND status = 'closed'
                          AND updated_at >= CURRENT_DATE - INTERVAL '12 months'
                    """, (self.firm_id, attorney_name))
                    closed_12m = cursor.fetchone()[0] or 0

                    # Performance percentage
                    pct_of_target = round(rolling_12m / annual_target * 100, 1) if annual_target > 0 else 0

                    # Trend: compare annualized 3-month pace vs 12-month actual
                    if rolling_12m > 0:
                        momentum = round((annualized_3m / annual_target * 100) - pct_of_target, 1)
                    else:
                        momentum = 0

                    # Determine performance tier
                    if pct_of_target >= 100:
                        tier = "on_target"
                        tier_label = "On Target"
                        tier_color = "#22c55e"  # green
                    elif pct_of_target >= 85:
                        tier = "near_target"
                        tier_label = "Near Target"
                        tier_color = "#84cc16"  # lime
                    elif pct_of_target >= 70:
                        tier = "building"
                        tier_label = "Building"
                        tier_color = "#eab308"  # yellow
                    elif pct_of_target >= 50:
                        tier = "developing"
                        tier_label = "Developing"
                        tier_color = "#f97316"  # orange
                    else:
                        tier = "attention"
                        tier_label = "Needs Attention"
                        tier_color = "#ef4444"  # red

                    # Trend direction
                    if momentum > 5:
                        trend = "accelerating"
                        trend_icon = "↑↑"
                    elif momentum > 0:
                        trend = "improving"
                        trend_icon = "↑"
                    elif momentum > -5:
                        trend = "steady"
                        trend_icon = "→"
                    elif momentum > -15:
                        trend = "slowing"
                        trend_icon = "↓"
                    else:
                        trend = "declining"
                        trend_icon = "↓↓"

                    results.append({
                        "attorney_name": attorney_name,
                        "pct_of_target": pct_of_target,
                        "tier": tier,
                        "tier_label": tier_label,
                        "tier_color": tier_color,
                        "trend": trend,
                        "trend_icon": trend_icon,
                        "momentum": momentum,
                        "active_cases": active_cases,
                        "closed_12m": closed_12m,
                        "monthly_pcts": monthly_pcts,
                        "annualized_pace_pct": round(annualized_3m / annual_target * 100, 1) if annual_target > 0 else 0,
                    })

                return sorted(results, key=lambda x: x["pct_of_target"], reverse=True)

        except Exception as e:
            print(f"get_attorney_performance_metrics error: {e}")
            return []

    def get_single_attorney_performance(self, attorney_name: str) -> Optional[Dict]:
        """Get performance metric for a single attorney. Used by detail page."""
        target = get_attorney_target(self.firm_id, attorney_name)
        if not target:
            return None

        # Temporarily set attorney_name filter to fetch just this one
        saved = self.attorney_name
        self.attorney_name = attorney_name
        results = self.get_attorney_performance_metrics()
        self.attorney_name = saved

        return results[0] if results else None
