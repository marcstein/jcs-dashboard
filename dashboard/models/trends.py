"""
KPI Trends and Promises Data Access
"""
from typing import Dict, List

from db.connection import get_connection


class TrendsDataMixin:
    """Mixin providing KPI trend analysis and payment promises data methods."""

    def get_kpi_trends(self, metric_name: str, days_back: int = 90) -> List[Dict]:
        """Get KPI trends for a specific metric over time (2025 data only)."""
        try:
            with get_connection() as conn:
                cursor = self._cursor(conn)

                cursor.execute("""
                    SELECT snapshot_date, kpi_value
                    FROM kpi_snapshots
                    WHERE firm_id = %s
                      AND kpi_name = %s
                      AND snapshot_date >= CURRENT_DATE - INTERVAL %s
                    ORDER BY snapshot_date
                """, (self.firm_id, metric_name, f'{days_back} days'))

                return [{'date': str(r[0]), 'value': r[1]} for r in cursor.fetchall()]
        except Exception:
            return []

    def get_payment_promises_summary(self) -> Dict:
        """Get payment promises tracking summary."""
        try:
            with get_connection() as conn:
                cursor = self._cursor(conn)

                # Pending promises
                cursor.execute("""
                    SELECT COUNT(*) as count, COALESCE(SUM(promised_amount), 0) as total
                    FROM payment_promises
                    WHERE firm_id = %s
                      AND status = 'pending'
                """, (self.firm_id,))
                pending = cursor.fetchone()

                # Overdue promises
                cursor.execute("""
                    SELECT COUNT(*) as count
                    FROM payment_promises
                    WHERE firm_id = %s
                      AND status = 'pending'
                      AND promise_date < CURRENT_DATE
                """, (self.firm_id,))
                overdue = cursor.fetchone()

                # Broken promises
                cursor.execute("""
                    SELECT COUNT(*) as count
                    FROM payment_promises
                    WHERE firm_id = %s
                      AND status = 'broken'
                """, (self.firm_id,))
                broken = cursor.fetchone()

                # Kept promises
                cursor.execute("""
                    SELECT COUNT(*) as count
                    FROM payment_promises
                    WHERE firm_id = %s
                      AND status = 'kept'
                """, (self.firm_id,))
                kept = cursor.fetchone()

                return {
                    'pending_count': pending[0] if pending else 0,
                    'pending_total': pending[1] if pending else 0,
                    'overdue_count': overdue[0] if overdue else 0,
                    'broken_count': broken[0] if broken else 0,
                    'kept_count': kept[0] if kept else 0,
                }
        except Exception:
            return {
                'pending_count': 0,
                'pending_total': 0,
                'overdue_count': 0,
                'broken_count': 0,
                'kept_count': 0,
            }
