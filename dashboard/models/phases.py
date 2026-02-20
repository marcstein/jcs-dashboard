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
                cursor = self._cursor(conn)

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

    def get_phases_summary(self) -> Dict:
        """Get phase distribution summary for the dashboard."""
        try:
            with get_connection() as conn:
                cursor = self._cursor(conn)

                # Phase distribution with counts
                cursor.execute("""
                    SELECT cp.phase_name, cp.phase_number, COUNT(*) as count
                    FROM case_phases cp
                    JOIN cached_cases c ON cp.case_id = c.id AND cp.firm_id = c.firm_id
                    WHERE cp.firm_id = %s
                      AND c.status = 'open'
                    GROUP BY cp.phase_name, cp.phase_number
                    ORDER BY cp.phase_number ASC
                """, (self.firm_id,))

                phases = []
                total = 0
                for r in cursor.fetchall():
                    phases.append({
                        'phase_name': r[0],
                        'phase_number': r[1],
                        'count': r[2],
                    })
                    total += r[2]

                # Add percentages
                for p in phases:
                    p['percentage'] = round(p['count'] / total * 100, 1) if total > 0 else 0

                return {
                    'phases': phases,
                    'total_cases': total,
                }
        except Exception:
            return {'phases': [], 'total_cases': 0}

    def get_stalled_cases(self, days_in_phase: int = 30, threshold_days: int = None) -> List[Dict]:
        """Get cases stalled in current phase.

        Args:
            days_in_phase: Min days in phase (legacy parameter name).
            threshold_days: Alias for days_in_phase (used by routes).
        """
        threshold = threshold_days if threshold_days is not None else days_in_phase
        try:
            with get_connection() as conn:
                cursor = self._cursor(conn)

                cursor.execute("""
                    SELECT cp.case_id, c.name as case_name, cp.phase_name, cp.entered_phase_date,
                           (CURRENT_DATE - cp.entered_phase_date::date) as days_in_phase
                    FROM case_phases cp
                    JOIN cached_cases c ON cp.case_id = c.id AND cp.firm_id = c.firm_id
                    WHERE cp.firm_id = %s
                      AND c.status = 'open'
                      AND (CURRENT_DATE - cp.entered_phase_date::date) >= %s
                    ORDER BY days_in_phase DESC
                    LIMIT 50
                """, (self.firm_id, threshold))

                return [{'case_id': r[0], 'case_name': r[1], 'phase': r[2],
                         'entered': r[3], 'days_in_phase': int(r[4])}
                        for r in cursor.fetchall()]
        except Exception:
            return []

    def get_phase_velocity(self) -> List[Dict]:
        """Get average days spent in each phase (from phase_history)."""
        try:
            with get_connection() as conn:
                cursor = self._cursor(conn)

                cursor.execute("""
                    SELECT phase_name,
                           ROUND(AVG(days_in_phase)::numeric, 1) as avg_days,
                           MIN(days_in_phase) as min_days,
                           MAX(days_in_phase) as max_days,
                           COUNT(*) as transitions
                    FROM phase_history
                    WHERE firm_id = %s
                      AND days_in_phase IS NOT NULL
                      AND days_in_phase > 0
                    GROUP BY phase_name
                    ORDER BY phase_name
                """, (self.firm_id,))

                return [{'phase_name': r[0], 'avg_days': float(r[1]),
                         'min_days': int(r[2]), 'max_days': int(r[3]),
                         'transitions': r[4]}
                        for r in cursor.fetchall()]
        except Exception:
            return []

    def get_phase_by_case_type(self) -> List[Dict]:
        """Get phase distribution broken down by case type (practice_area)."""
        try:
            with get_connection() as conn:
                cursor = self._cursor(conn)

                cursor.execute("""
                    SELECT c.practice_area, cp.phase_name, COUNT(*) as count
                    FROM case_phases cp
                    JOIN cached_cases c ON cp.case_id = c.id AND cp.firm_id = c.firm_id
                    WHERE cp.firm_id = %s
                      AND c.status = 'open'
                      AND c.practice_area IS NOT NULL
                      AND c.practice_area != ''
                    GROUP BY c.practice_area, cp.phase_name
                    ORDER BY c.practice_area, cp.phase_name
                """, (self.firm_id,))

                results = []
                for r in cursor.fetchall():
                    results.append({
                        'case_type': r[0],
                        'phase_name': r[1],
                        'count': r[2],
                    })
                return results
        except Exception:
            return []

    def get_cases_in_phase(self, phase: str, limit: int = 50) -> List[Dict]:
        """Get list of cases currently in a specific phase."""
        try:
            with get_connection() as conn:
                cursor = self._cursor(conn)

                cursor.execute("""
                    SELECT cp.case_id, c.name as case_name, c.case_number,
                           c.practice_area, c.lead_attorney_name,
                           cp.entered_phase_date,
                           (CURRENT_DATE - cp.entered_phase_date::date) as days_in_phase
                    FROM case_phases cp
                    JOIN cached_cases c ON cp.case_id = c.id AND cp.firm_id = c.firm_id
                    WHERE cp.firm_id = %s
                      AND cp.phase_name ILIKE %s
                      AND c.status = 'open'
                    ORDER BY cp.entered_phase_date ASC
                    LIMIT %s
                """, (self.firm_id, f'%{phase}%', limit))

                return [{'case_id': r[0], 'case_name': r[1], 'case_number': r[2],
                         'practice_area': r[3], 'attorney': r[4],
                         'entered': r[5], 'days_in_phase': int(r[6])}
                        for r in cursor.fetchall()]
        except Exception:
            return []
