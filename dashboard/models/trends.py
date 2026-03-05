"""
KPI Trends, Promises Data Access
"""
from datetime import date
from typing import Dict, List, Optional

from db.connection import get_connection


class TrendsDataMixin:
    """Mixin providing KPI trend analysis and payment promises data methods."""

    # ---- Attorney-scoped live metric computation ----

    def _compute_attorney_metrics(self) -> List[Dict]:
        """Compute KPI metrics live from underlying tables for an attorney-scoped view.

        Since kpi_snapshots are firm-wide aggregates, attorneys get live values
        computed from their own cases/invoices. No historical trend data is available.
        """
        metrics = []
        today = str(date.today())
        try:
            with get_connection() as conn:
                cursor = self._cursor(conn)

                # Total A/R for this attorney's cases
                cursor.execute("""
                    SELECT COALESCE(SUM(i.balance_due), 0)
                    FROM cached_invoices i
                    JOIN cached_cases c ON i.case_id = c.id AND i.firm_id = c.firm_id
                    WHERE i.firm_id = %s
                      AND i.balance_due > 0
                      AND c.lead_attorney_name = %s
                """, (self.firm_id, self.attorney_name))
                total_ar = float(cursor.fetchone()[0] or 0)
                metrics.append({
                    'name': 'total_ar',
                    'value': total_ar,
                    'date': today,
                    'previous_value': None,
                    'direction': 'stable',
                })

                # A/R over 60 days percentage
                cursor.execute("""
                    SELECT
                        COALESCE(SUM(i.balance_due), 0) as total,
                        COALESCE(SUM(CASE WHEN CURRENT_DATE - i.due_date > 60
                                     THEN i.balance_due ELSE 0 END), 0) as over_60
                    FROM cached_invoices i
                    JOIN cached_cases c ON i.case_id = c.id AND i.firm_id = c.firm_id
                    WHERE i.firm_id = %s
                      AND i.balance_due > 0
                      AND c.lead_attorney_name = %s
                """, (self.firm_id, self.attorney_name))
                row = cursor.fetchone()
                ar_total = float(row[0] or 0)
                ar_over_60 = float(row[1] or 0)
                ar_over_60_pct = round(ar_over_60 / ar_total * 100, 1) if ar_total > 0 else 0
                metrics.append({
                    'name': 'ar_over_60_pct',
                    'value': ar_over_60_pct,
                    'date': today,
                    'previous_value': None,
                    'direction': 'stable',
                })

                # Overdue tasks on this attorney's cases
                cursor.execute("""
                    SELECT COUNT(*)
                    FROM cached_tasks t
                    JOIN cached_cases c ON t.case_id = c.id AND t.firm_id = c.firm_id
                    WHERE t.firm_id = %s
                      AND t.due_date < CURRENT_DATE
                      AND t.due_date >= CURRENT_DATE - INTERVAL '200 days'
                      AND (t.completed = false OR t.completed IS NULL)
                      AND c.lead_attorney_name = %s
                """, (self.firm_id, self.attorney_name))
                overdue_tasks = cursor.fetchone()[0] or 0
                metrics.append({
                    'name': 'overdue_tasks',
                    'value': overdue_tasks,
                    'date': today,
                    'previous_value': None,
                    'direction': 'stable',
                })

        except Exception:
            pass
        return metrics

    # ---- Firm-wide KPI snapshot methods ----

    def get_kpi_trends(self, metric_name: str, days_back: int = 90) -> List[Dict]:
        """Get KPI trends for a specific metric over time."""
        # No historical per-attorney data available
        if self.attorney_name:
            return []
        try:
            with get_connection() as conn:
                cursor = self._cursor(conn)

                cursor.execute("""
                    SELECT snapshot_date, metric_value
                    FROM kpi_snapshots
                    WHERE firm_id = %s
                      AND metric_name = %s
                      AND snapshot_date >= CURRENT_DATE - INTERVAL %s
                    ORDER BY snapshot_date
                """, (self.firm_id, metric_name, f'{days_back} days'))

                return [{'date': str(r[0]), 'value': r[1]} for r in cursor.fetchall()]
        except Exception:
            return []

    def get_trends_summary(self) -> Dict:
        """Get summary of all tracked KPI metrics with latest values and direction."""
        # Attorney-scoped: compute live from underlying data
        if self.attorney_name:
            metrics = self._compute_attorney_metrics()
            return {'metrics': metrics, 'total_metrics': len(metrics)}

        try:
            with get_connection() as conn:
                cursor = self._cursor(conn)

                # Get distinct metric names with their latest snapshot
                cursor.execute("""
                    SELECT DISTINCT ON (metric_name)
                           metric_name, metric_value, snapshot_date
                    FROM kpi_snapshots
                    WHERE firm_id = %s
                    ORDER BY metric_name, snapshot_date DESC
                """, (self.firm_id,))

                metrics = []
                for r in cursor.fetchall():
                    metric_name = r[0]
                    current_value = r[1]
                    snapshot_date = r[2]

                    # Get the value from 7 days ago for trend direction
                    cursor.execute("""
                        SELECT metric_value
                        FROM kpi_snapshots
                        WHERE firm_id = %s
                          AND metric_name = %s
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
        # No historical per-attorney data for comparisons
        if self.attorney_name:
            return {}

        try:
            with get_connection() as conn:
                cursor = self._cursor(conn)

                # Latest value
                cursor.execute("""
                    SELECT metric_value, snapshot_date
                    FROM kpi_snapshots
                    WHERE firm_id = %s AND metric_name = %s
                    ORDER BY snapshot_date DESC LIMIT 1
                """, (self.firm_id, metric))
                latest = cursor.fetchone()
                if not latest:
                    return {}

                current_value = latest[0]
                current_date = latest[1]

                # 7 days ago
                cursor.execute("""
                    SELECT metric_value FROM kpi_snapshots
                    WHERE firm_id = %s AND metric_name = %s
                      AND snapshot_date <= CURRENT_DATE - INTERVAL '7 days'
                    ORDER BY snapshot_date DESC LIMIT 1
                """, (self.firm_id, metric))
                wow_row = cursor.fetchone()
                wow_value = wow_row[0] if wow_row else None

                # 30 days ago
                cursor.execute("""
                    SELECT metric_value FROM kpi_snapshots
                    WHERE firm_id = %s AND metric_name = %s
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
