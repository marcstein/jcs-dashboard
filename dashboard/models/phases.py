"""
Case Phase Distribution and Stalled Cases Data Access
"""
from typing import Dict, List

from db.connection import get_connection


class PhasesDataMixin:
    """Mixin providing case phase distribution and stalled cases data methods."""

    def get_case_phases_distribution(self) -> Dict:
        """Get distribution of cases across the 7 universal phases (2025 cases only)."""
        try:
            with get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT phase_name, COUNT(*) as count
                    FROM case_phases
                    WHERE firm_id = %s
                      AND EXTRACT(YEAR FROM created_at) = 2025
                    GROUP BY phase_name
                    ORDER BY phase_number ASC
                """, (self.firm_id,))

                distribution = {}
                for row in cursor.fetchall():
                    distribution[row[0]] = row[1]

                return distribution
        except Exception:
            return {}

    def get_stalled_cases(self, days_in_phase: int = 30) -> List[Dict]:
        """Get cases stalled in current phase (2025 cases only)."""
        try:
            with get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute(f"""
                    SELECT cp.case_id, c.name as case_name, cp.phase_name, cp.entered_phase_date,
                           EXTRACT(DAY FROM CURRENT_DATE - cp.entered_phase_date) as days_in_phase
                    FROM case_phases cp
                    JOIN cached_cases c ON cp.case_id = c.id
                    WHERE cp.firm_id = %s
                      AND EXTRACT(YEAR FROM c.created_at) = 2025
                      AND EXTRACT(DAY FROM CURRENT_DATE - cp.entered_phase_date) >= %s
                    ORDER BY days_in_phase DESC
                    LIMIT 20
                """, (self.firm_id, days_in_phase))

                return [{'case_id': r[0], 'case_name': r[1], 'phase': r[2], 'entered': r[3], 'days_in_phase': int(r[4])}
                       for r in cursor.fetchall()]
        except Exception:
            return []
