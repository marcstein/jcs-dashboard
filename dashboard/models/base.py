"""
Dashboard Data Access Layer - Base Class
Read-only access to cached data from PostgreSQL database.
NO live API calls - all data comes from daily sync.
"""
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional

# Add parent directory to path to import existing modules
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from db.connection import get_connection
import dashboard.config as config


class DashboardData:
    """Read-only data access for dashboard using cached database data."""

    def __init__(self, firm_id: str = None):
        self.firm_id = firm_id or 'default'
        self.reports_dir = config.REPORTS_DIR

    def _get_staff_lookup(self) -> Dict[str, str]:
        """Build a staff ID to name lookup dictionary."""
        lookup = {}
        try:
            with get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT id, name FROM cached_staff WHERE firm_id = %s",
                    (self.firm_id,)
                )
                for row in cursor.fetchall():
                    lookup[str(row[0])] = row[1]
        except Exception:
            pass
        return lookup

    def _get_staff_id_by_name(self, name: str) -> Optional[str]:
        """Get staff ID from name (partial match)."""
        try:
            with get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT id FROM cached_staff WHERE firm_id = %s AND name ILIKE %s",
                    (self.firm_id, f'%{name}%')
                )
                row = cursor.fetchone()
                if row:
                    return str(row[0])
        except Exception:
            pass
        return None

    def _resolve_assignee_ids_to_names(self, assignee_ids_str: str, staff_lookup: Dict[str, str]) -> str:
        """Convert comma-separated staff IDs to names, return first name only."""
        if not assignee_ids_str:
            return 'Unassigned'
        ids = assignee_ids_str.split(',')
        names = []
        for id_str in ids[:1]:  # Only get first assignee for display
            name = staff_lookup.get(id_str.strip(), None)
            if name:
                names.append(name)
        return names[0] if names else 'Unknown'

    def get_recent_reports(self, limit: int = 10) -> list:
        """Get list of recent reports from filesystem."""
        reports = []
        if self.reports_dir.exists():
            for file in sorted(self.reports_dir.glob('*.txt'), reverse=True)[:limit]:
                reports.append({
                    'name': file.name,
                    'path': str(file),
                    'size': file.stat().st_size,
                    'modified': datetime.fromtimestamp(file.stat().st_mtime),
                })
        return reports

    def get_report_content(self, filename: str) -> Optional[str]:
        """Get content of a specific report."""
        report_path = self.reports_dir / filename
        if report_path.exists() and report_path.is_file():
            try:
                return report_path.read_text()
            except Exception as e:
                print(f"Error reading report: {e}")
        return None

    def get_last_sync_time(self) -> Optional[datetime]:
        """Get the timestamp of the last data sync."""
        # First check the cache database sync_metadata
        try:
            with get_connection() as conn:
                cursor = conn.cursor()
                # Check both full and incremental sync times, use the most recent
                cursor.execute("""
                    SELECT MAX(COALESCE(last_incremental_sync, last_full_sync)) as last_sync
                    FROM sync_metadata
                    WHERE firm_id = %s
                """, (self.firm_id,))
                row = cursor.fetchone()
                if row and row[0]:
                    return row[0]
        except Exception:
            pass  # Fall through to legacy method

        # Fallback to legacy invoice_snapshots
        with get_connection() as conn:
            cursor = conn.cursor()

            # Check most recent snapshot date
            cursor.execute("""
                SELECT MAX(snapshot_date) as last_sync
                FROM invoice_snapshots
                WHERE firm_id = %s
            """, (self.firm_id,))
            row = cursor.fetchone()
            if row and row[0]:
                return row[0]
        return None
