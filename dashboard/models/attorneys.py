"""
Attorney Productivity Data Access
"""
from datetime import datetime
from typing import Dict, List

import psycopg2.extensions
from db.connection import get_connection


class AttorneyDataMixin:
    """Mixin providing attorney productivity and invoice aging data methods."""

    def get_attorney_productivity(self) -> List[Dict]:
        """Get attorney productivity metrics (legacy - used by CLI)."""
        return self.get_attorney_productivity_data()

    def get_attorney_productivity_data(self, year: int = None) -> List[Dict]:
        """Get attorney productivity metrics for specified year."""
        current_year = datetime.now().year
        if year is None:
            year = current_year
        try:
            with get_connection() as conn:
                cursor = self._cursor(conn)

                # Get unique attorneys from cases
                cursor.execute("""
                    SELECT DISTINCT lead_attorney_name
                    FROM cached_cases
                    WHERE firm_id = %s
                      AND lead_attorney_name IS NOT NULL
                      AND lead_attorney_name != ''
                    ORDER BY lead_attorney_name
                """, (self.firm_id,))
                attorneys = [row[0] for row in cursor.fetchall()]

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

                cursor.execute("""
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
                    GROUP BY c.lead_attorney_name
                    ORDER BY c.lead_attorney_name
                """, (self.firm_id, year))

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

    def get_attorney_detail(self, attorney_name: str, year: int = None) -> Dict:
        """Get detailed attorney info including case list and invoice breakdown."""
        current_year = datetime.now().year
        if year is None:
            year = current_year
        try:
            with get_connection() as conn:
                cursor = self._cursor(conn)

                # Active cases
                cursor.execute("""
                    SELECT COUNT(*) FROM cached_cases
                    WHERE firm_id = %s AND lead_attorney_name ILIKE %s
                      AND status = 'open'
                """, (self.firm_id, f'%{attorney_name}%'))
                active_cases = cursor.fetchone()[0] or 0

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

                # Active cases list
                cursor.execute("""
                    SELECT id, name, practice_area, case_number, status, created_at
                    FROM cached_cases
                    WHERE firm_id = %s AND lead_attorney_name ILIKE %s
                      AND status = 'open'
                    ORDER BY created_at DESC
                """, (self.firm_id, f'%{attorney_name}%'))
                cases = [{
                    'id': r[0], 'name': r[1], 'case_type': r[2],
                    'case_number': r[3], 'status': r[4], 'created_at': r[5]
                } for r in cursor.fetchall()]

                # Outstanding invoices (call list)
                cursor.execute("""
                    SELECT i.id, i.invoice_number, c.name as case_name,
                           i.total_amount, i.balance_due, i.due_date,
                           (CURRENT_DATE - i.due_date) as days_past_due
                    FROM cached_invoices i
                    JOIN cached_cases c ON i.case_id = c.id AND i.firm_id = c.firm_id
                    WHERE i.firm_id = %s AND c.lead_attorney_name ILIKE %s
                      AND i.balance_due > 0
                      AND EXTRACT(YEAR FROM i.invoice_date) = %s
                    ORDER BY i.due_date ASC
                """, (self.firm_id, f'%{attorney_name}%', year))
                invoices = [{
                    'id': r[0], 'invoice_number': r[1], 'case_name': r[2] or 'Unknown',
                    'total_amount': r[3], 'balance_due': r[4], 'due_date': r[5],
                    'days_past_due': r[6]
                } for r in cursor.fetchall()]

                collection_rate = (total_collected / total_billed * 100) if total_billed > 0 else 0

                return {
                    'attorney_name': attorney_name,
                    'active_cases': active_cases,
                    'total_billed': total_billed,
                    'total_collected': total_collected,
                    'total_outstanding': total_outstanding,
                    'collection_rate': collection_rate,
                    'cases': cases,
                    'invoices': invoices,
                }
        except Exception as e:
            print(f"get_attorney_detail error for {attorney_name}: {e}")
            return {
                'attorney_name': attorney_name,
                'active_cases': 0, 'total_billed': 0, 'total_collected': 0,
                'total_outstanding': 0, 'collection_rate': 0,
                'cases': [], 'invoices': [],
            }
