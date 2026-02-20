"""
KPI Trend Snapshots — PostgreSQL Multi-Tenant

Daily KPI snapshots for historical trend analysis.
"""
import logging
from datetime import date
from typing import List, Dict, Optional

from db.connection import get_connection

logger = logging.getLogger(__name__)


TRENDS_SCHEMA = """
CREATE TABLE IF NOT EXISTS kpi_snapshots (
    id SERIAL PRIMARY KEY,
    firm_id VARCHAR(36) NOT NULL,
    snapshot_date DATE NOT NULL,
    metric_name TEXT NOT NULL,
    metric_value REAL NOT NULL,
    target_value REAL,
    metadata TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(firm_id, snapshot_date, metric_name)
);
CREATE INDEX IF NOT EXISTS idx_kpi_date ON kpi_snapshots(firm_id, snapshot_date, metric_name);
"""


def ensure_trends_tables():
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(TRENDS_SCHEMA)
    logger.info("Trends tables ensured")


def record_snapshot(
    firm_id: str,
    metric_name: str,
    metric_value: float,
    target_value: float = None,
    metadata: str = None,
    snapshot_date: date = None,
) -> int:
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO kpi_snapshots
                (firm_id, snapshot_date, metric_name, metric_value, target_value, metadata)
            VALUES (%s, COALESCE(%s, CURRENT_DATE), %s, %s, %s, %s)
            ON CONFLICT (firm_id, snapshot_date, metric_name) DO UPDATE SET
                metric_value = EXCLUDED.metric_value,
                target_value = EXCLUDED.target_value,
                metadata = EXCLUDED.metadata
            RETURNING id
            """,
            (firm_id, snapshot_date, metric_name, metric_value, target_value, metadata),
        )
        row = cur.fetchone()
        return row["id"] if row else 0


def get_metric_history(
    firm_id: str, metric_name: str, days: int = 30
) -> List[Dict]:
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT * FROM kpi_snapshots
            WHERE firm_id = %s AND metric_name = %s
              AND snapshot_date >= CURRENT_DATE - %s * INTERVAL '1 day'
            ORDER BY snapshot_date ASC
            """,
            (firm_id, metric_name, days),
        )
        return [dict(r) for r in cur.fetchall()]


def get_latest_snapshot(firm_id: str) -> List[Dict]:
    """Get the most recent value for each metric."""
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT DISTINCT ON (metric_name) metric_name, metric_value, target_value, snapshot_date
            FROM kpi_snapshots
            WHERE firm_id = %s
            ORDER BY metric_name, snapshot_date DESC
            """,
            (firm_id,),
        )
        return [dict(r) for r in cur.fetchall()]


def get_comparison(firm_id: str, metric_name: str, period: str = "week") -> Dict:
    """Get week-over-week or month-over-month comparison."""
    interval = "7 days" if period == "week" else "30 days"
    with get_connection() as conn:
        cur = conn.cursor()
        # Current value
        cur.execute(
            """
            SELECT metric_value FROM kpi_snapshots
            WHERE firm_id = %s AND metric_name = %s
            ORDER BY snapshot_date DESC LIMIT 1
            """,
            (firm_id, metric_name),
        )
        current_row = cur.fetchone()
        current = current_row["metric_value"] if current_row else None

        # Previous period value
        cur.execute(
            f"""
            SELECT metric_value FROM kpi_snapshots
            WHERE firm_id = %s AND metric_name = %s
              AND snapshot_date <= CURRENT_DATE - INTERVAL '{interval}'
            ORDER BY snapshot_date DESC LIMIT 1
            """,
            (firm_id, metric_name),
        )
        prev_row = cur.fetchone()
        previous = prev_row["metric_value"] if prev_row else None

        change = None
        if current is not None and previous is not None and previous != 0:
            change = round((current - previous) / previous * 100, 1)

        return {
            "metric": metric_name,
            "current": current,
            "previous": previous,
            "change_pct": change,
            "period": period,
        }
