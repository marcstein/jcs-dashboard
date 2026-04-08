"""
Revenue Data Access Layer
- New cases by month (count)
- New case value by month (sum of invoice total_amount per case, attributed
  to the month the case was created)
- 12-month rolling history with month-over-month deltas
"""
from datetime import date
from typing import Dict, List

from db.connection import get_connection


class RevenueDataMixin:
    """Mixin providing new-revenue and new-case metrics for the admin dashboard."""

    def get_revenue_monthly_series(self, months: int = 12) -> List[Dict]:
        """Return a list of dicts, one per month, covering the last `months`
        months (oldest first).

        Each row: {
            'month_start': date,
            'month_label': 'Mar 2026',
            'new_case_count': int,
            'new_case_value': float,   # sum of invoice total_amount for cases created that month
        }

        Months with no cases are returned as zeros so the chart series is dense.
        """
        with get_connection() as conn:
            cursor = self._cursor(conn)
            # Build a 12-month series anchored to the first day of the current month,
            # then LEFT JOIN to per-month aggregates.
            cursor.execute(
                """
                WITH months AS (
                    SELECT generate_series(
                        DATE_TRUNC('month', CURRENT_DATE) - (%s - 1) * INTERVAL '1 month',
                        DATE_TRUNC('month', CURRENT_DATE),
                        INTERVAL '1 month'
                    )::date AS month_start
                ),
                new_cases AS (
                    SELECT
                        DATE_TRUNC('month', c.created_at)::date AS month_start,
                        COUNT(*) AS new_case_count
                    FROM cached_cases c
                    WHERE c.firm_id = %s
                      AND c.created_at IS NOT NULL
                      AND c.created_at >= DATE_TRUNC('month', CURRENT_DATE) - (%s - 1) * INTERVAL '1 month'
                    GROUP BY 1
                ),
                case_values AS (
                    SELECT
                        DATE_TRUNC('month', c.created_at)::date AS month_start,
                        COALESCE(SUM(i.total_amount), 0) AS new_case_value
                    FROM cached_cases c
                    LEFT JOIN cached_invoices i
                        ON i.case_id = c.id AND i.firm_id = c.firm_id
                    WHERE c.firm_id = %s
                      AND c.created_at IS NOT NULL
                      AND c.created_at >= DATE_TRUNC('month', CURRENT_DATE) - (%s - 1) * INTERVAL '1 month'
                    GROUP BY 1
                )
                SELECT
                    m.month_start,
                    COALESCE(nc.new_case_count, 0) AS new_case_count,
                    COALESCE(cv.new_case_value, 0) AS new_case_value
                FROM months m
                LEFT JOIN new_cases nc ON nc.month_start = m.month_start
                LEFT JOIN case_values cv ON cv.month_start = m.month_start
                ORDER BY m.month_start ASC
                """,
                (months, self.firm_id, months, self.firm_id, months),
            )
            rows = cursor.fetchall()

        series = []
        for row in rows:
            month_start = row[0]
            series.append({
                "month_start": month_start,
                "month_label": month_start.strftime("%b %Y"),
                "month_key": month_start.strftime("%Y-%m"),
                "new_case_count": int(row[1] or 0),
                "new_case_value": float(row[2] or 0),
            })
        return series

    def get_revenue_summary(self, months: int = 12) -> Dict:
        """Return summary KPIs derived from the monthly series.

        Includes:
        - current month value/count
        - prior month value/count
        - month-over-month deltas (absolute + percent)
        - 12-month totals and averages
        """
        series = self.get_revenue_monthly_series(months=months)
        if not series:
            return {
                "series": [],
                "current": {"month_label": "", "new_case_count": 0, "new_case_value": 0.0},
                "previous": {"month_label": "", "new_case_count": 0, "new_case_value": 0.0},
                "mom_count_delta": 0,
                "mom_count_pct": 0.0,
                "mom_value_delta": 0.0,
                "mom_value_pct": 0.0,
                "ytd_total_value": 0.0,
                "ytd_total_count": 0,
                "trailing_total_value": 0.0,
                "trailing_total_count": 0,
                "avg_monthly_value": 0.0,
                "avg_monthly_count": 0.0,
            }

        current = series[-1]
        previous = series[-2] if len(series) >= 2 else {
            "month_label": "",
            "new_case_count": 0,
            "new_case_value": 0.0,
        }

        def _pct_change(curr, prev):
            if prev in (None, 0, 0.0):
                return None  # undefined when prior period is zero
            return round((curr - prev) / prev * 100, 1)

        # Year-to-date totals (current calendar year)
        current_year = date.today().year
        ytd_value = sum(
            r["new_case_value"] for r in series
            if r["month_start"].year == current_year
        )
        ytd_count = sum(
            r["new_case_count"] for r in series
            if r["month_start"].year == current_year
        )

        trailing_value = sum(r["new_case_value"] for r in series)
        trailing_count = sum(r["new_case_count"] for r in series)

        return {
            "series": series,
            "current": current,
            "previous": previous,
            "mom_count_delta": current["new_case_count"] - previous["new_case_count"],
            "mom_count_pct": _pct_change(current["new_case_count"], previous["new_case_count"]),
            "mom_value_delta": current["new_case_value"] - previous["new_case_value"],
            "mom_value_pct": _pct_change(current["new_case_value"], previous["new_case_value"]),
            "ytd_total_value": ytd_value,
            "ytd_total_count": ytd_count,
            "trailing_total_value": trailing_value,
            "trailing_total_count": trailing_count,
            "avg_monthly_value": round(trailing_value / len(series), 2) if series else 0.0,
            "avg_monthly_count": round(trailing_count / len(series), 2) if series else 0.0,
        }

    def get_revenue_by_practice_area(self, months: int = 12) -> List[Dict]:
        """Return new-case value broken out by practice area for the trailing window."""
        with get_connection() as conn:
            cursor = self._cursor(conn)
            cursor.execute(
                """
                SELECT
                    COALESCE(NULLIF(c.practice_area, ''), 'Unspecified') AS practice_area,
                    COUNT(DISTINCT c.id) AS new_case_count,
                    COALESCE(SUM(i.total_amount), 0) AS new_case_value
                FROM cached_cases c
                LEFT JOIN cached_invoices i
                    ON i.case_id = c.id AND i.firm_id = c.firm_id
                WHERE c.firm_id = %s
                  AND c.created_at IS NOT NULL
                  AND c.created_at >= DATE_TRUNC('month', CURRENT_DATE) - (%s - 1) * INTERVAL '1 month'
                GROUP BY 1
                ORDER BY new_case_value DESC
                """,
                (self.firm_id, months),
            )
            rows = cursor.fetchall()

        return [
            {
                "practice_area": r[0],
                "new_case_count": int(r[1] or 0),
                "new_case_value": float(r[2] or 0),
            }
            for r in rows
        ]
