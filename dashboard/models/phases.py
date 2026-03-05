"""
Case Phase Distribution and Stalled Cases Data Access

Reads from PostgreSQL tables:
  - case_phase_history (firm_id, case_id, case_name, case_type, phase_code,
                        phase_name, entered_at, exited_at, duration_days)
  - phases (firm_id, code, name, display_order, ...)
  - cached_cases (for open/closed status join)
"""
from typing import Dict, List

from db.connection import get_connection


class PhasesDataMixin:
    """Mixin providing case phase distribution and stalled cases data methods."""

    def get_case_phases_distribution(self) -> Dict:
        """Get distribution of cases across the 7 universal phases."""
        try:
            with get_connection() as conn:
                cursor = self._cursor(conn)

                # Get latest phase per case, then count by phase
                cursor.execute("""
                    WITH latest AS (
                        SELECT DISTINCT ON (case_id) case_id, phase_code, phase_name
                        FROM case_phase_history
                        WHERE firm_id = %s
                        ORDER BY case_id, entered_at DESC
                    )
                    SELECT lp.phase_name, COUNT(*) as count
                    FROM latest lp
                    GROUP BY lp.phase_name
                    ORDER BY lp.phase_name
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

                af_sql, af_params = self._attorney_case_filter("c")

                # Latest phase per case, joined with cached_cases for open status,
                # and phases table for display_order
                cursor.execute(f"""
                    WITH latest AS (
                        SELECT DISTINCT ON (cph.case_id)
                               cph.case_id, cph.phase_code, cph.phase_name, cph.firm_id
                        FROM case_phase_history cph
                        WHERE cph.firm_id = %s
                        ORDER BY cph.case_id, cph.entered_at DESC
                    )
                    SELECT lp.phase_name,
                           COALESCE(p.display_order, 0) as phase_number,
                           COUNT(*) as count
                    FROM latest lp
                    JOIN cached_cases c ON lp.case_id = c.id AND lp.firm_id = c.firm_id
                    LEFT JOIN phases p ON lp.phase_code = p.code AND lp.firm_id = p.firm_id
                    WHERE c.status = 'open'
                      {af_sql}
                    GROUP BY lp.phase_name, p.display_order
                    ORDER BY COALESCE(p.display_order, 0) ASC
                """, (self.firm_id, *af_params))

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

                af_sql, af_params = self._attorney_case_filter("c")
                cursor.execute(f"""
                    WITH latest AS (
                        SELECT DISTINCT ON (cph.case_id)
                               cph.case_id, cph.case_name, cph.phase_name,
                               cph.entered_at, cph.firm_id
                        FROM case_phase_history cph
                        WHERE cph.firm_id = %s
                        ORDER BY cph.case_id, cph.entered_at DESC
                    )
                    SELECT lp.case_id, c.name as case_name, lp.phase_name,
                           lp.entered_at,
                           EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - lp.entered_at)) / 86400.0 as days_in_phase
                    FROM latest lp
                    JOIN cached_cases c ON lp.case_id = c.id AND lp.firm_id = c.firm_id
                    WHERE c.status = 'open'
                      AND EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - lp.entered_at)) / 86400.0 >= %s
                      {af_sql}
                    ORDER BY days_in_phase DESC
                    LIMIT 50
                """, (self.firm_id, threshold, *af_params))

                return [{'case_id': r[0], 'case_name': r[1], 'phase': r[2],
                         'entered': r[3], 'days_in_phase': int(r[4])}
                        for r in cursor.fetchall()]
        except Exception:
            return []

    def get_phase_velocity(self) -> List[Dict]:
        """Get average days spent in each phase (from case_phase_history where exited)."""
        try:
            with get_connection() as conn:
                cursor = self._cursor(conn)

                af_sql, af_params = self._attorney_case_filter("c")
                cursor.execute(f"""
                    SELECT cph.phase_name,
                           ROUND(AVG(cph.duration_days)::numeric, 1) as avg_days,
                           MIN(cph.duration_days)::int as min_days,
                           MAX(cph.duration_days)::int as max_days,
                           COUNT(*) as transitions
                    FROM case_phase_history cph
                    JOIN cached_cases c ON cph.case_id = c.id AND cph.firm_id = c.firm_id
                    WHERE cph.firm_id = %s
                      AND cph.duration_days IS NOT NULL
                      AND cph.duration_days > 0
                      {af_sql}
                    GROUP BY cph.phase_name
                    ORDER BY cph.phase_name
                """, (self.firm_id, *af_params))

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

                af_sql, af_params = self._attorney_case_filter("c")
                cursor.execute(f"""
                    WITH latest AS (
                        SELECT DISTINCT ON (cph.case_id)
                               cph.case_id, cph.phase_name, cph.firm_id
                        FROM case_phase_history cph
                        WHERE cph.firm_id = %s
                        ORDER BY cph.case_id, cph.entered_at DESC
                    )
                    SELECT c.practice_area, lp.phase_name, COUNT(*) as count
                    FROM latest lp
                    JOIN cached_cases c ON lp.case_id = c.id AND lp.firm_id = c.firm_id
                    WHERE c.status = 'open'
                      AND c.practice_area IS NOT NULL
                      AND c.practice_area != ''
                      {af_sql}
                    GROUP BY c.practice_area, lp.phase_name
                    ORDER BY c.practice_area, lp.phase_name
                """, (self.firm_id, *af_params))

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

                af_sql, af_params = self._attorney_case_filter("c")
                cursor.execute(f"""
                    WITH latest AS (
                        SELECT DISTINCT ON (cph.case_id)
                               cph.case_id, cph.phase_name, cph.entered_at, cph.firm_id
                        FROM case_phase_history cph
                        WHERE cph.firm_id = %s
                        ORDER BY cph.case_id, cph.entered_at DESC
                    )
                    SELECT lp.case_id, c.name as case_name, c.case_number,
                           c.practice_area, c.lead_attorney_name,
                           lp.entered_at,
                           EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - lp.entered_at)) / 86400.0 as days_in_phase
                    FROM latest lp
                    JOIN cached_cases c ON lp.case_id = c.id AND lp.firm_id = c.firm_id
                    WHERE lp.phase_name ILIKE %s
                      AND c.status = 'open'
                      {af_sql}
                    ORDER BY lp.entered_at ASC
                    LIMIT %s
                """, (self.firm_id, f'%{phase}%', *af_params, limit))

                return [{'case_id': r[0], 'case_name': r[1], 'case_number': r[2],
                         'practice_area': r[3], 'attorney': r[4],
                         'entered': r[5], 'days_in_phase': int(r[6])}
                        for r in cursor.fetchall()]
        except Exception:
            return []
