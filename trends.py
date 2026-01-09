"""
Historical Trend Analysis Module

Tracks and analyzes KPI trends over time:
- AR aging trends
- Collection rate trends
- Intake volume trends
- Quality score trends
- Comparison vs targets
"""
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import json

from database import Database, get_db
from config import DATA_DIR


class TrendDirection(Enum):
    """Direction of trend movement."""
    IMPROVING = "improving"
    DECLINING = "declining"
    STABLE = "stable"
    INSUFFICIENT_DATA = "insufficient_data"


@dataclass
class TrendPoint:
    """A single data point in a trend."""
    date: date
    value: float
    target: Optional[float] = None


@dataclass
class TrendAnalysis:
    """Analysis of a KPI trend."""
    metric_name: str
    current_value: float
    previous_value: Optional[float]
    target: Optional[float]
    direction: TrendDirection
    change_pct: Optional[float]
    data_points: List[TrendPoint]
    period_days: int
    on_target: bool
    insight: str


class TrendTracker:
    """
    Tracks and analyzes historical KPI trends.

    Stores daily snapshots and provides:
    - Week-over-week comparisons
    - Month-over-month trends
    - Target vs actual tracking
    - Trend direction analysis
    """

    def __init__(self, db: Database = None):
        self.db = db or get_db()
        self._ensure_tables()

        # Define KPI targets
        self.targets = {
            "ar_over_60_pct": 25.0,  # Target: <25% of AR over 60 days
            "payment_plan_compliance": 90.0,  # Target: ≥90%
            "quality_score": 90.0,  # Target: ≥90%
            "attorney_outreach_compliance": 100.0,  # Target: 100%
            "same_day_contact_rate": 100.0,  # Target: 100%
            "overdue_tasks": 0,  # Target: 0
        }

    def _ensure_tables(self):
        """Ensure required tables exist."""
        with self.db._get_connection() as conn:
            cursor = conn.cursor()

            # Daily KPI snapshots
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS kpi_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    snapshot_date DATE NOT NULL,
                    metric_name TEXT NOT NULL,
                    metric_value REAL NOT NULL,
                    target_value REAL,
                    metadata TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(snapshot_date, metric_name)
                )
            """)

            # Index for quick lookups
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_kpi_date
                ON kpi_snapshots(snapshot_date, metric_name)
            """)

            conn.commit()

    # ========== Snapshot Recording ==========

    def record_snapshot(
        self,
        metric_name: str,
        value: float,
        snapshot_date: date = None,
        target: float = None,
        metadata: Dict = None,
    ):
        """
        Record a KPI snapshot.

        Args:
            metric_name: Name of the metric
            value: Current value
            snapshot_date: Date of snapshot (default: today)
            target: Target value
            metadata: Additional context
        """
        snapshot_date = snapshot_date or date.today()
        target = target or self.targets.get(metric_name)

        with self.db._get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                INSERT OR REPLACE INTO kpi_snapshots
                (snapshot_date, metric_name, metric_value, target_value, metadata)
                VALUES (?, ?, ?, ?, ?)
            """, (
                snapshot_date.isoformat(),
                metric_name,
                value,
                target,
                json.dumps(metadata) if metadata else None,
            ))

            conn.commit()

    def record_daily_kpis(self, kpis: Dict[str, float], snapshot_date: date = None):
        """Record multiple KPIs at once."""
        for metric_name, value in kpis.items():
            self.record_snapshot(
                metric_name=metric_name,
                value=value,
                snapshot_date=snapshot_date,
            )

    # ========== Trend Retrieval ==========

    def get_trend_data(
        self,
        metric_name: str,
        days_back: int = 30,
    ) -> List[TrendPoint]:
        """Get historical data points for a metric."""
        cutoff = (date.today() - timedelta(days=days_back)).isoformat()

        with self.db._get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                SELECT snapshot_date, metric_value, target_value
                FROM kpi_snapshots
                WHERE metric_name = ?
                AND snapshot_date >= ?
                ORDER BY snapshot_date ASC
            """, (metric_name, cutoff))

            points = []
            for row in cursor.fetchall():
                points.append(TrendPoint(
                    date=datetime.strptime(row["snapshot_date"], "%Y-%m-%d").date(),
                    value=row["metric_value"],
                    target=row["target_value"],
                ))

            return points

    def get_latest_value(self, metric_name: str) -> Optional[float]:
        """Get the most recent value for a metric."""
        with self.db._get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                SELECT metric_value
                FROM kpi_snapshots
                WHERE metric_name = ?
                ORDER BY snapshot_date DESC
                LIMIT 1
            """, (metric_name,))

            row = cursor.fetchone()
            return row["metric_value"] if row else None

    def get_value_on_date(self, metric_name: str, on_date: date) -> Optional[float]:
        """Get the value for a metric on a specific date."""
        with self.db._get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                SELECT metric_value
                FROM kpi_snapshots
                WHERE metric_name = ?
                AND snapshot_date = ?
            """, (metric_name, on_date.isoformat()))

            row = cursor.fetchone()
            return row["metric_value"] if row else None

    # ========== Trend Analysis ==========

    def analyze_trend(
        self,
        metric_name: str,
        days_back: int = 30,
        higher_is_better: bool = True,
    ) -> TrendAnalysis:
        """
        Analyze the trend for a metric.

        Args:
            metric_name: Name of the metric
            days_back: Period to analyze
            higher_is_better: Whether higher values are better

        Returns:
            TrendAnalysis with direction, change, and insights
        """
        data_points = self.get_trend_data(metric_name, days_back)
        target = self.targets.get(metric_name)

        if len(data_points) < 2:
            return TrendAnalysis(
                metric_name=metric_name,
                current_value=data_points[0].value if data_points else 0,
                previous_value=None,
                target=target,
                direction=TrendDirection.INSUFFICIENT_DATA,
                change_pct=None,
                data_points=data_points,
                period_days=days_back,
                on_target=False,
                insight="Insufficient data for trend analysis",
            )

        current = data_points[-1].value
        previous = data_points[0].value

        # Calculate change
        if previous != 0:
            change_pct = ((current - previous) / abs(previous)) * 100
        else:
            change_pct = 100 if current > 0 else 0

        # Determine direction
        threshold = 5  # 5% change threshold for "stable"
        if abs(change_pct) < threshold:
            direction = TrendDirection.STABLE
        elif higher_is_better:
            direction = TrendDirection.IMPROVING if change_pct > 0 else TrendDirection.DECLINING
        else:
            direction = TrendDirection.IMPROVING if change_pct < 0 else TrendDirection.DECLINING

        # Check if on target
        on_target = False
        if target is not None:
            if higher_is_better:
                on_target = current >= target
            else:
                on_target = current <= target

        # Generate insight
        insight = self._generate_insight(
            metric_name, current, previous, target, direction, change_pct, higher_is_better
        )

        return TrendAnalysis(
            metric_name=metric_name,
            current_value=current,
            previous_value=previous,
            target=target,
            direction=direction,
            change_pct=change_pct,
            data_points=data_points,
            period_days=days_back,
            on_target=on_target,
            insight=insight,
        )

    def _generate_insight(
        self,
        metric_name: str,
        current: float,
        previous: float,
        target: Optional[float],
        direction: TrendDirection,
        change_pct: float,
        higher_is_better: bool,
    ) -> str:
        """Generate a human-readable insight about the trend."""
        metric_display = metric_name.replace("_", " ").title()

        if direction == TrendDirection.STABLE:
            insight = f"{metric_display} is stable at {current:.1f}"
        elif direction == TrendDirection.IMPROVING:
            insight = f"{metric_display} improved by {abs(change_pct):.1f}% ({previous:.1f} -> {current:.1f})"
        else:
            insight = f"{metric_display} declined by {abs(change_pct):.1f}% ({previous:.1f} -> {current:.1f})"

        if target is not None:
            gap = target - current if higher_is_better else current - target
            if gap > 0:
                insight += f". Gap to target: {gap:.1f}"
            else:
                insight += ". On target!"

        return insight

    def compare_periods(
        self,
        metric_name: str,
        period1_start: date,
        period1_end: date,
        period2_start: date,
        period2_end: date,
    ) -> Dict:
        """Compare two time periods for a metric."""
        with self.db._get_connection() as conn:
            cursor = conn.cursor()

            # Get average for period 1
            cursor.execute("""
                SELECT AVG(metric_value) as avg_value, COUNT(*) as count
                FROM kpi_snapshots
                WHERE metric_name = ?
                AND snapshot_date BETWEEN ? AND ?
            """, (metric_name, period1_start.isoformat(), period1_end.isoformat()))
            period1 = cursor.fetchone()

            # Get average for period 2
            cursor.execute("""
                SELECT AVG(metric_value) as avg_value, COUNT(*) as count
                FROM kpi_snapshots
                WHERE metric_name = ?
                AND snapshot_date BETWEEN ? AND ?
            """, (metric_name, period2_start.isoformat(), period2_end.isoformat()))
            period2 = cursor.fetchone()

        avg1 = period1["avg_value"] or 0
        avg2 = period2["avg_value"] or 0

        change = avg2 - avg1
        change_pct = (change / avg1 * 100) if avg1 != 0 else 0

        return {
            "metric_name": metric_name,
            "period1": {
                "start": period1_start.isoformat(),
                "end": period1_end.isoformat(),
                "average": avg1,
                "data_points": period1["count"],
            },
            "period2": {
                "start": period2_start.isoformat(),
                "end": period2_end.isoformat(),
                "average": avg2,
                "data_points": period2["count"],
            },
            "change": change,
            "change_pct": change_pct,
        }

    def week_over_week(self, metric_name: str) -> Dict:
        """Get week-over-week comparison."""
        today = date.today()

        this_week_start = today - timedelta(days=today.weekday())
        this_week_end = today

        last_week_start = this_week_start - timedelta(days=7)
        last_week_end = this_week_start - timedelta(days=1)

        return self.compare_periods(
            metric_name,
            last_week_start, last_week_end,
            this_week_start, this_week_end,
        )

    def month_over_month(self, metric_name: str) -> Dict:
        """Get month-over-month comparison."""
        today = date.today()

        this_month_start = today.replace(day=1)
        this_month_end = today

        last_month_end = this_month_start - timedelta(days=1)
        last_month_start = last_month_end.replace(day=1)

        return self.compare_periods(
            metric_name,
            last_month_start, last_month_end,
            this_month_start, this_month_end,
        )

    # ========== Dashboard & Reports ==========

    def get_all_trends(self, days_back: int = 30) -> Dict[str, TrendAnalysis]:
        """Get trend analysis for all tracked metrics."""
        # Define which metrics are "lower is better"
        lower_is_better = {"ar_over_60_pct", "overdue_tasks"}

        # Get unique metrics
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT DISTINCT metric_name FROM kpi_snapshots
            """)
            metrics = [row["metric_name"] for row in cursor.fetchall()]

        trends = {}
        for metric in metrics:
            higher_is_better = metric not in lower_is_better
            trends[metric] = self.analyze_trend(metric, days_back, higher_is_better)

        return trends

    def generate_trend_report(self, days_back: int = 30) -> str:
        """Generate a trend analysis report."""
        trends = self.get_all_trends(days_back)

        report = f"""
================================================================================
                    KPI TREND ANALYSIS - {date.today()}
                    Period: Last {days_back} Days
================================================================================

"""
        # Sort by status: off-target first, then by change magnitude
        sorted_trends = sorted(
            trends.values(),
            key=lambda t: (t.on_target, abs(t.change_pct or 0)),
        )

        # Off-target metrics first
        off_target = [t for t in sorted_trends if not t.on_target]
        on_target = [t for t in sorted_trends if t.on_target]

        if off_target:
            report += "NEEDS ATTENTION (Off Target)\n"
            report += "-" * 60 + "\n"
            for trend in off_target:
                status = self._get_trend_icon(trend.direction)
                report += f"\n{status} {trend.metric_name.replace('_', ' ').title()}\n"
                report += f"   Current: {trend.current_value:.1f}"
                if trend.target:
                    report += f" | Target: {trend.target:.1f}"
                if trend.change_pct is not None:
                    report += f" | Change: {trend.change_pct:+.1f}%"
                report += f"\n   {trend.insight}\n"

        if on_target:
            report += "\nON TARGET\n"
            report += "-" * 60 + "\n"
            for trend in on_target:
                status = self._get_trend_icon(trend.direction)
                report += f"{status} {trend.metric_name.replace('_', ' ').title()}: {trend.current_value:.1f}\n"

        # Week over week summary
        report += "\nWEEK OVER WEEK COMPARISON\n"
        report += "-" * 60 + "\n"
        for metric in list(trends.keys())[:5]:
            wow = self.week_over_week(metric)
            direction = "+" if wow["change_pct"] >= 0 else ""
            report += f"  {metric.replace('_', ' ').title()}: {direction}{wow['change_pct']:.1f}%\n"

        report += """
================================================================================
"""
        return report

    def _get_trend_icon(self, direction: TrendDirection) -> str:
        """Get icon for trend direction."""
        icons = {
            TrendDirection.IMPROVING: "[+]",
            TrendDirection.DECLINING: "[-]",
            TrendDirection.STABLE: "[=]",
            TrendDirection.INSUFFICIENT_DATA: "[?]",
        }
        return icons.get(direction, "[?]")

    def generate_sparkline(self, metric_name: str, days_back: int = 14) -> str:
        """Generate a text-based sparkline for a metric."""
        data = self.get_trend_data(metric_name, days_back)

        if len(data) < 2:
            return "─" * 14

        values = [p.value for p in data]
        min_val = min(values)
        max_val = max(values)

        if max_val == min_val:
            return "─" * len(values)

        # Map to sparkline characters
        chars = " ▁▂▃▄▅▆▇█"
        sparkline = ""

        for val in values:
            normalized = (val - min_val) / (max_val - min_val)
            index = int(normalized * (len(chars) - 1))
            sparkline += chars[index]

        return sparkline

    def get_dashboard_data(self) -> Dict:
        """Get data for a dashboard view."""
        trends = self.get_all_trends(30)

        dashboard = {
            "generated_at": datetime.now().isoformat(),
            "metrics": [],
        }

        for name, trend in trends.items():
            dashboard["metrics"].append({
                "name": name,
                "display_name": name.replace("_", " ").title(),
                "current": trend.current_value,
                "target": trend.target,
                "on_target": trend.on_target,
                "direction": trend.direction.value,
                "change_pct": trend.change_pct,
                "sparkline": self.generate_sparkline(name),
                "insight": trend.insight,
            })

        return dashboard


if __name__ == "__main__":
    tracker = TrendTracker()

    print("Testing Trend Tracker...")

    # Record some sample data
    today = date.today()

    for i in range(14):
        d = today - timedelta(days=13-i)

        # Simulate AR improving over time
        ar_pct = 85 - (i * 0.5)  # Going down (good)

        # Simulate compliance improving
        compliance = 10 + (i * 5)  # Going up (good)

        tracker.record_snapshot("ar_over_60_pct", ar_pct, d)
        tracker.record_snapshot("payment_plan_compliance", compliance, d)
        tracker.record_snapshot("quality_score", 55 + (i * 2), d)

    # Analyze trends
    print("\nAR Trend:")
    ar_trend = tracker.analyze_trend("ar_over_60_pct", 14, higher_is_better=False)
    print(f"  Direction: {ar_trend.direction.value}")
    print(f"  Change: {ar_trend.change_pct:.1f}%")
    print(f"  Insight: {ar_trend.insight}")

    print(f"\nSparkline: {tracker.generate_sparkline('ar_over_60_pct')}")

    # Generate report
    print(tracker.generate_trend_report(14))
