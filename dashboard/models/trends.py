"""
KPI Trends, Promises Data Access
"""
from typing import Dict, List, Optional

from db.connection import get_connection


class TrendsDataMixin:
    """Mixin providing KPI trend analysis and payment promises data methods."""

    def get_kpi_trends(self, metric_name: str, days_back: int = 90) -> List[Dict]:
        """Get KPI trends for a specific metric over time."""
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

    def get_trends_summary(self) -> Dict:
        """Get summary of all tracked KPI metrics with latest values and direction."""
        try:
            with get_connection() as conn:
                cursor = self._cursor(conn)

                # Get distinct metric names with their latest snapshot
                cursor.execute("""
                    SELECT DISTINCT ON (kpi_name)
                           kpi_name, kpi_value, snapshot_date
                    FROM kpi_snapshots
                    WHERE firm_id = %s
                    ORDER BY kpi_name, snapshot_date DESC
                """, (self.firm_id,))

                metrics = []
                for r in cursor.fetchall():
                    metric_name = r[0]
                    current_value = r[1]
                    snapshot_date = r[2]

                    # Get the value from 7 days ago for trend direction
                    cursor.execute("""
                        SELECT kpi_value
                        FROM kpi_snapshots
                        WHERE firm_id = %s
                          AND kpi_name = %s
                          AND snapshot_date <= CURRENT_DATE - INTERVAL '7 days'
                        ORDER BY snapshot_date DESC
                        LIMIT 1
                    """, (self.firm_id, metric_name))
                    prev_row = cursor.fetchone()
                    prev_value = prev_row[0] if prev_row else None

                    direction = 'stable'
                    if prev_value is not None and current_value is not None:
                        if current_value > prev_value:
                            direction = 'up'
                        elif current_value < prev_value:
                            direction = 'down'

                    metrics.append({
                        'name': metric_name,
                        'value': current_value,
                        'date': str(snapshot_date),
                        'previous_value': prev_value,
                        'direction': direction,
                    })

                return {
                    'metrics': metrics,
                    'total_metrics': len(metrics),
                }
        except Exception:
            return {'metrics': [], 'total_metrics': 0}

    def get_metric_comparison(self, metric: str) -> Dict:
        """Get week-over-week and month-over-month comparison for a metric."""
        try:
            with get_connection() as conn:
                cursor = self._cursor(conn)

                # Latest value
                cursor.execute("""
                    SELECT kpi_value, snapshot_date
                    FROM kpi_snapshots
                    WHERE firm_id = %s AND kpi_name = %s
                    ORDER BY snapshot_date DESC LIMIT 1
                """, (self.firm_id, metric))
                latest = cursor.fetchone()
                if not latest:
                    return {}

                current_value = latest[0]
                current_date = latest[1]

                # 7 days ago
                cursor.execute("""
                    SELECT kpi_value FROM kpi_snapshots
                    WHERE firm_id = %s AND kpi_name = %s
                      AND snapshot_date <= CURRENT_DATE - INTERVAL '7 days'
                    ORDER BY snapshot_date DESC LIMIT 1
                """, (self.firm_id, metric))
                wow_row = cursor.fetchone()
                wow_value = wow_row[0] if wow_row else None

                # 30 days ago
                cursor.execute("""
                    SELECT kpi_value FROM kpi_snapshots
                    WHERE firm_id = %s AND kpi_name = %s
                      AND snapshot_date <= CURRENT_DATE - INTERVAL '30 days'
                    ORDER BY snapshot_date DESC LIMIT 1
                """, (self.firm_id, metric))
                mom_row = cursor.fetchone()
                mom_value = mom_row[0] if mom_row else None

                def calc_change(current, previous):
                    if previous is None or previous == 0:
                        return None
                    return round((current - previous) / previous * 100, 1)

                return {
                    'metric_name': metric,
                    'current_value': current_value,
                    'current_date': str(current_date),
                    'wow_value': wow_value,
                    'wow_change': calc_change(current_value, wow_value),
                    'mom_value': mom_value,
                    'mom_change': calc_change(current_value, mom_value),
                }
        except Exception:
            return {}

    def get_trend_data(self, metric: str, days_back: int = 30) -> List[Dict]:
        """Get historical trend data points for a metric."""
        return self.get_kpi_trends(metric, days_back)

    # ---- Payment Promises ----

    def get_payment_promises_summary(self) -> Dict:
        """Get payment promises tracking summary (legacy name)."""
        return self.get_promises_summary()

    def get_promises_summary(self) -> Dict:
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
                    SELECT COUNT(*) as count, COALESCE(SUM(promised_amount), 0) as total
                    FROM payment_promises
                    WHERE firm_id = %s
                      AND status = 'kept'
                """, (self.firm_id,))
                kept = cursor.fetchone()

                total_resolved = (kept[0] if kept else 0) + (broken[0] if broken else 0)
                keep_rate = round(kept[0] / total_resolved * 100, 1) if total_resolved > 0 else 0

                return {
                    'pending_count': pending[0] if pending else 0,
                    'pending_total': float(pending[1]) if pending else 0,
                    'overdue_count': overdue[0] if overdue else 0,
                    'broken_count': broken[0] if broken else 0,
                    'kept_count': kept[0] if kept else 0,
                    'kept_total': float(kept[1]) if kept else 0,
                    'keep_rate': keep_rate,
                }
        except Exception:
            return {
                'pending_count': 0, 'pending_total': 0,
                'overdue_count': 0, 'broken_count': 0,
                'kept_count': 0, 'kept_total': 0, 'keep_rate': 0,
            }

    def get_promises_list(self, status: Optional[str] = None) -> List[Dict]:
        """Get list of payment promises, optionally filtered by status."""
        try:
            with get_connection() as conn:
                cursor = self._cursor(conn)

                if status:
                    cursor.execute("""
                        SELECT pp.id, pp.contact_id, pp.promised_amount, pp.promise_date,
                               pp.status, pp.created_at, pp.notes,
                               cc.name as contact_name
                        FROM payment_promises pp
                        LEFT JOIN cached_contacts cc ON pp.contact_id = cc.id AND pp.firm_id = cc.firm_id
                        WHERE pp.firm_id = %s AND pp.status = %s
                        ORDER BY pp.promise_date ASC
                        LIMIT 100
                    """, (self.firm_id, status))
                else:
                    cursor.execute("""
                        SELECT pp.id, pp.contact_id, pp.promised_amount, pp.promise_date,
                               pp.status, pp.created_at, pp.notes,
                               cc.name as contact_name
                        FROM payment_promises pp
                        LEFT JOIN cached_contacts cc ON pp.contact_id = cc.id AND pp.firm_id = cc.firm_id
                        WHERE pp.firm_id = %s
                        ORDER BY pp.promise_date ASC
                        LIMIT 100
                    """, (self.firm_id,))

                return [{'id': r[0], 'contact_id': r[1], 'amount': float(r[2]),
                         'promise_date': r[3], 'status': r[4],
                         'created_at': r[5], 'notes': r[6],
                         'contact_name': r[7] or 'Unknown'}
                        for r in cursor.fetchall()]
        except Exception:
            return []
