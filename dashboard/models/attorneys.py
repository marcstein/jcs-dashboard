"""
Attorney Productivity Data Access
"""
from typing import Dict, List

from db.connection import get_connection


class AttorneyDataMixin:
    """Mixin providing attorney productivity and invoice aging data methods."""

    def get_attorney_productivity(self) -> List[Dict]:
        """Get attorney productivity metrics (2025 cases only)."""
        try:
            with get_connection() as conn:
                cursor = conn.cursor()

                # Get unique attorneys from invoices for 2025
                cursor.execute("""
                    SELECT DISTINCT attorney_name
                    FROM cached_invoices
                    WHERE firm_id = %s
                      AND EXTRACT(YEAR FROM invoice_date) = 2025
                    ORDER BY attorney_name
                """, (self.firm_id,))
                attorneys = [row[0] for row in cursor.fetchall() if row[0]]

                result = []
                for attorney_name in attorneys:
                    # Active cases
                    cursor.execute("""
                        SELECT COUNT(DISTINCT case_id)
                        FROM cached_invoices
                        WHERE firm_id = %s
                          AND attorney_name = %s
                          AND EXTRACT(YEAR FROM invoice_date) = 2025
                    """, (self.firm_id, attorney_name))
                    active_cases = cursor.fetchone()[0] or 0

                    # Invoice count
                    cursor.execute("""
                        SELECT COUNT(*)
                        FROM cached_invoices
                        WHERE firm_id = %s
                          AND attorney_name = %s
                          AND EXTRACT(YEAR FROM invoice_date) = 2025
                    """, (self.firm_id, attorney_name))
                    invoice_count = cursor.fetchone()[0] or 0

                    # Total billed
                    cursor.execute("""
                        SELECT COALESCE(SUM(total_amount), 0)
                        FROM cached_invoices
                        WHERE firm_id = %s
                          AND attorney_name = %s
                          AND EXTRACT(YEAR FROM invoice_date) = 2025
                    """, (self.firm_id, attorney_name))
                    total_billed = cursor.fetchone()[0] or 0

                    # Total collected
                    cursor.execute("""
                        SELECT COALESCE(SUM(paid_amount), 0)
                        FROM cached_invoices
                        WHERE firm_id = %s
                          AND attorney_name = %s
                          AND EXTRACT(YEAR FROM invoice_date) = 2025
                    """, (self.firm_id, attorney_name))
                    total_collected = cursor.fetchone()[0] or 0

                    # AR by aging buckets
                    cursor.execute("""
                        SELECT
                            SUM(CASE WHEN CURRENT_DATE - due_date BETWEEN 60 AND 180 THEN balance_due ELSE 0 END) as aging_60_180,
                            SUM(CASE WHEN CURRENT_DATE - due_date > 180 THEN balance_due ELSE 0 END) as aging_180_plus
                        FROM cached_invoices
                        WHERE firm_id = %s
                          AND attorney_name = %s
                          AND EXTRACT(YEAR FROM invoice_date) = 2025
                          AND balance_due > 0
                    """, (self.firm_id, attorney_name))
                    aging_row = cursor.fetchone()
                    aging_60_180 = aging_row[0] or 0 if aging_row else 0
                    aging_180_plus = aging_row[1] or 0 if aging_row else 0

                    result.append({
                        'attorney_name': attorney_name,
                        'active_cases': active_cases,
                        'invoice_count': invoice_count,
                        'total_billed': total_billed,
                        'total_collected': total_collected,
                        'aging_60_180': aging_60_180,
                        'aging_180_plus': aging_180_plus,
                    })

                return result
        except Exception:
            return []
