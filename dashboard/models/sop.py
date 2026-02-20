"""
SOP Report Data Access
"""
from typing import Dict

from db.connection import get_connection


class SOPDataMixin:
    """Mixin providing SOP report data methods for each staff member."""

    def get_melissa_sop_data(self, year: int = None) -> Dict:
        """Get Melissa (AR Specialist) SOP metrics for specified year."""
        summary = self.get_daily_collections_summary(year=year)
        plans = self.get_payment_plans_summary()
        noiw = self.get_noiw_pipeline()

        # Calculate targets and compliance
        aging_target = 25.0
        aging_actual = summary.get('aging_over_60_pct', 0)
        aging_compliant = aging_actual <= aging_target

        plan_compliance_target = 90.0
        active_plans = plans.get('active_count', 0)
        delinquent_plans = plans.get('delinquent_count', 0)
        if active_plans > 0:
            plan_compliance = ((active_plans - delinquent_plans) / active_plans) * 100
        else:
            plan_compliance = 100.0
        plan_compliant = plan_compliance >= plan_compliance_target

        return {
            'total_ar': summary.get('total_ar', 0),
            'total_billed': summary.get('total_billed', 0),
            'cash_received': summary.get('cash_received', 0),
            'payment_count': summary.get('payment_count', 0),
            # A/R Breakdown by aging bucket
            'total_collected': summary.get('total_collected', 0),
            'collection_rate': summary.get('collection_rate', 0),
            'ar_current': summary.get('ar_current', 0),
            'ar_0_30': summary.get('ar_0_30', 0),
            'ar_31_60': summary.get('ar_31_60', 0),
            'ar_61_90': summary.get('ar_61_90', 0),
            'ar_91_120': summary.get('ar_91_120', 0),
            'ar_120_plus': summary.get('ar_120_plus', 0),
            'ar_90_plus': summary.get('ar_90_plus', 0),
            # Compliance metrics
            'aging_over_60_pct': aging_actual,
            'aging_target': aging_target,
            'aging_compliant': aging_compliant,
            'active_plans': active_plans,
            'delinquent_plans': delinquent_plans,
            'plan_compliance': plan_compliance,
            'plan_compliance_target': plan_compliance_target,
            'plan_compliant': plan_compliant,
            'noiw_count': len(noiw),
            'noiw_total': sum(n.get('balance_due', 0) for n in noiw),
        }

    def get_ty_sop_data(self) -> Dict:
        """Get Ty (Intake Lead) SOP metrics from cache database (2025 data only)."""
        try:
            with get_connection() as conn:
                cursor = self._cursor(conn)

                # New cases in last 7 days (on 2025 cases)
                cursor.execute("""
                    SELECT COUNT(*) as count
                    FROM cached_cases
                    WHERE firm_id = %s
                      AND EXTRACT(YEAR FROM created_at) = 2025
                      AND DATE(created_at) >= CURRENT_DATE - INTERVAL '7 days'
                """, (self.firm_id,))
                row = cursor.fetchone()
                new_cases_week = row[0] if row else 0

                # New cases in last 30 days (2025 cases)
                cursor.execute("""
                    SELECT COUNT(*) as count
                    FROM cached_cases
                    WHERE firm_id = %s
                      AND EXTRACT(YEAR FROM created_at) = 2025
                      AND DATE(created_at) >= CURRENT_DATE - INTERVAL '30 days'
                """, (self.firm_id,))
                row = cursor.fetchone()
                new_cases_month = row[0] if row else 0

                # Case type breakdown (2025)
                cursor.execute("""
                    SELECT practice_area, COUNT(*) as count
                    FROM cached_cases
                    WHERE firm_id = %s
                      AND EXTRACT(YEAR FROM created_at) = 2025
                    GROUP BY practice_area
                    ORDER BY count DESC
                    LIMIT 5
                """, (self.firm_id,))
                case_types = [{'type': r[0] or 'Unknown', 'count': r[1]}
                             for r in cursor.fetchall()]

                # Cases with lead attorney assigned (quality check - 2025)
                cursor.execute("""
                    SELECT
                        COUNT(*) as total,
                        SUM(CASE WHEN lead_attorney_name IS NOT NULL AND lead_attorney_name != '' THEN 1 ELSE 0 END) as with_attorney
                    FROM cached_cases
                    WHERE firm_id = %s
                      AND EXTRACT(YEAR FROM created_at) = 2025
                """, (self.firm_id,))
                row = cursor.fetchone()
                total_new = row[0] if row else 0
                with_attorney = row[1] if row else 0
                attorney_rate = (with_attorney / total_new * 100) if total_new > 0 else 100

                return {
                    'new_cases_week': new_cases_week,
                    'new_cases_month': new_cases_month,
                    'case_types': case_types,
                    'attorney_assignment_rate': attorney_rate,
                    'attorney_target': 100,
                    'attorney_compliant': attorney_rate >= 99.5,  # Allow for 0.5% variance
                }
        except Exception:
            # Return empty defaults if tables don't exist yet
            return {
                'new_cases_week': 0,
                'new_cases_month': 0,
                'case_types': [],
                'attorney_assignment_rate': 100,
                'attorney_target': 100,
                'attorney_compliant': True,
            }

    def get_tiffany_sop_data(self) -> Dict:
        """Get Tiffany (Senior Paralegal) SOP metrics from cache database (2025 cases only)."""
        try:
            with get_connection() as conn:
                cursor = self._cursor(conn)

                # Overdue tasks on 2025 cases (exclude > 200 days as stale)
                cursor.execute("""
                    SELECT COUNT(*) as count
                    FROM cached_tasks t
                    JOIN cached_cases c ON t.case_id = c.id
                    WHERE t.firm_id = %s
                      AND t.due_date < CURRENT_DATE
                      AND t.due_date >= CURRENT_DATE - INTERVAL '200 days'
                      AND (t.completed = false OR t.completed IS NULL)
                      AND EXTRACT(YEAR FROM c.created_at) = 2025
                """, (self.firm_id,))
                row = cursor.fetchone()
                overdue_count = row[0] if row else 0

                # Critical overdue (more than 7 days, less than 200) on 2025 cases
                cursor.execute("""
                    SELECT COUNT(*) as count
                    FROM cached_tasks t
                    JOIN cached_cases c ON t.case_id = c.id
                    WHERE t.firm_id = %s
                      AND t.due_date < CURRENT_DATE - INTERVAL '7 days'
                      AND t.due_date >= CURRENT_DATE - INTERVAL '200 days'
                      AND (t.completed = false OR t.completed IS NULL)
                      AND EXTRACT(YEAR FROM c.created_at) = 2025
                """, (self.firm_id,))
                row = cursor.fetchone()
                overdue_critical = row[0] if row else 0

                # Tasks by assignee (top offenders) on 2025 cases (exclude > 200 days)
                staff_lookup = self._get_staff_lookup()
                cursor.execute("""
                    SELECT t.assignee_name, COUNT(*) as count
                    FROM cached_tasks t
                    JOIN cached_cases c ON t.case_id = c.id
                    WHERE t.firm_id = %s
                      AND t.due_date < CURRENT_DATE
                      AND t.due_date >= CURRENT_DATE - INTERVAL '200 days'
                      AND (t.completed = false OR t.completed IS NULL)
                      AND EXTRACT(YEAR FROM c.created_at) = 2025
                    GROUP BY t.assignee_name
                    ORDER BY count DESC
                    LIMIT 5
                """, (self.firm_id,))
                top_offenders = []
                for r in cursor.fetchall():
                    name = self._resolve_assignee_ids_to_names(r[0], staff_lookup)
                    top_offenders.append({'name': name, 'count': r[1]})

                # Tasks completed in last 7 days on 2025 cases
                cursor.execute("""
                    SELECT COUNT(*) as count
                    FROM cached_tasks t
                    JOIN cached_cases c ON t.case_id = c.id
                    WHERE t.firm_id = %s
                      AND t.completed = true
                      AND DATE(t.completed_at) >= CURRENT_DATE - INTERVAL '7 days'
                      AND EXTRACT(YEAR FROM c.created_at) = 2025
                """, (self.firm_id,))
                row = cursor.fetchone()
                completed_week = row[0] if row else 0

                # Total pending tasks on 2025 cases (not completed, not overdue - upcoming work)
                cursor.execute("""
                    SELECT COUNT(*) as count
                    FROM cached_tasks t
                    JOIN cached_cases c ON t.case_id = c.id
                    WHERE t.firm_id = %s
                      AND (t.completed = false OR t.completed IS NULL)
                      AND t.due_date >= CURRENT_DATE
                      AND EXTRACT(YEAR FROM c.created_at) = 2025
                """, (self.firm_id,))
                row = cursor.fetchone()
                pending_count = row[0] if row else 0

                # Total active tasks on 2025 cases (all non-completed)
                cursor.execute("""
                    SELECT COUNT(*) as count
                    FROM cached_tasks t
                    JOIN cached_cases c ON t.case_id = c.id
                    WHERE t.firm_id = %s
                      AND (t.completed = false OR t.completed IS NULL)
                      AND EXTRACT(YEAR FROM c.created_at) = 2025
                """, (self.firm_id,))
                row = cursor.fetchone()
                total_open = row[0] if row else 0

                # Quality score - try from database if available
                quality_score = None  # Use None to indicate "no data" vs 0
                quality_audits_count = 0
                try:
                    with get_connection() as audit_conn:
                        audit_cursor = self._cursor(audit_conn)
                        audit_cursor.execute("""
                            SELECT AVG(quality_score) as avg_score, COUNT(*) as audit_count
                            FROM case_quality_audits
                            WHERE firm_id = %s
                              AND DATE(audit_date) >= CURRENT_DATE - INTERVAL '30 days'
                        """, (self.firm_id,))
                        qrow = audit_cursor.fetchone()
                        if qrow and qrow[1] and qrow[1] > 0:
                            quality_score = qrow[0]
                            quality_audits_count = qrow[1]
                except Exception:
                    pass

                quality_target = 90.0
                quality_compliant = (quality_score or 0) >= quality_target if quality_score is not None else True

                return {
                    'overdue_count': overdue_count,
                    'overdue_critical': overdue_critical,
                    'top_offenders': top_offenders,
                    'completed_week': completed_week,
                    'pending_count': pending_count,
                    'total_open': total_open,
                    'quality_score': quality_score,
                    'quality_audits_count': quality_audits_count,
                    'quality_target': quality_target,
                    'quality_compliant': quality_compliant,
                }
        except Exception:
            # Return empty defaults if tables don't exist yet
            return {
                'overdue_count': 0,
                'overdue_critical': 0,
                'top_offenders': [],
                'completed_week': 0,
                'pending_count': 0,
                'total_open': 0,
                'quality_score': None,
                'quality_audits_count': 0,
                'quality_target': 90.0,
                'quality_compliant': True,
            }

    def get_legal_assistant_sop_data(self, assignee_name: str = None) -> Dict:
        """Get Legal Assistant (Alison/Cole) SOP metrics from cache database (2025 cases only).

        For attorneys, also includes tasks on cases where they are lead attorney.
        """
        try:
            with get_connection() as conn:
                cursor = self._cursor(conn)

                # Get staff ID for the assignee name
                staff_id = None
                is_attorney = False
                if assignee_name:
                    staff_id = self._get_staff_id_by_name(assignee_name)
                    is_attorney = self._is_attorney(assignee_name)

                # Build assignee filter - search for staff ID in comma-separated assignee_name field
                # For attorneys, also match tasks on their cases (via lead_attorney_name)
                assignee_filter = ""
                params = [self.firm_id]
                if staff_id and is_attorney:
                    assignee_filter = """AND (
                        t.assignee_name LIKE %s OR t.assignee_name LIKE %s
                        OR t.assignee_name LIKE %s OR t.assignee_name = %s
                        OR c.lead_attorney_name ILIKE %s
                    )"""
                    params.extend([f'{staff_id},%', f'%,{staff_id},%', f'%,{staff_id}', staff_id, f'%{assignee_name}%'])
                elif staff_id:
                    # Match staff ID anywhere in the comma-separated list
                    assignee_filter = "AND (t.assignee_name LIKE %s OR t.assignee_name LIKE %s OR t.assignee_name LIKE %s OR t.assignee_name = %s)"
                    params.extend([f'{staff_id},%', f'%,{staff_id},%', f'%,{staff_id}', staff_id])

                # Overdue tasks for this assignee on 2025 cases (exclude > 200 days as stale)
                cursor.execute(f"""
                    SELECT COUNT(*) as count
                    FROM cached_tasks t
                    JOIN cached_cases c ON t.case_id = c.id
                    WHERE t.firm_id = %s
                      AND t.due_date < CURRENT_DATE
                      AND t.due_date >= CURRENT_DATE - INTERVAL '200 days'
                      AND (t.completed = false OR t.completed IS NULL)
                      AND EXTRACT(YEAR FROM c.created_at) = 2025
                      {assignee_filter}
                """, params)
                row = cursor.fetchone()
                overdue_count = row[0] if row else 0

                # Helper to build params for each query
                def _build_params():
                    p = [self.firm_id]
                    if staff_id and is_attorney:
                        p.extend([f'{staff_id},%', f'%,{staff_id},%', f'%,{staff_id}', staff_id, f'%{assignee_name}%'])
                    elif staff_id:
                        p.extend([f'{staff_id},%', f'%,{staff_id},%', f'%,{staff_id}', staff_id])
                    return p

                # Tasks due today on 2025 cases
                cursor.execute(f"""
                    SELECT COUNT(*) as count
                    FROM cached_tasks t
                    JOIN cached_cases c ON t.case_id = c.id
                    WHERE t.firm_id = %s
                      AND t.due_date = CURRENT_DATE
                      AND (t.completed = false OR t.completed IS NULL)
                      AND EXTRACT(YEAR FROM c.created_at) = 2025
                      {assignee_filter}
                """, _build_params())
                row = cursor.fetchone()
                due_today = row[0] if row else 0

                # Completed in last 7 days on 2025 cases
                cursor.execute(f"""
                    SELECT COUNT(*) as count
                    FROM cached_tasks t
                    JOIN cached_cases c ON t.case_id = c.id
                    WHERE t.firm_id = %s
                      AND t.completed = true
                      AND DATE(t.completed_at) >= CURRENT_DATE - INTERVAL '7 days'
                      AND EXTRACT(YEAR FROM c.created_at) = 2025
                      {assignee_filter}
                """, _build_params())
                row = cursor.fetchone()
                completed_week = row[0] if row else 0

                # License deadlines (DOR/PFR tasks) on 2025 cases
                cursor.execute(f"""
                    SELECT t.name as task_name, c.name as case_name, t.due_date,
                           (t.due_date - CURRENT_DATE) as days_until
                    FROM cached_tasks t
                    LEFT JOIN cached_cases c ON t.case_id = c.id
                    WHERE t.firm_id = %s
                      AND (t.name LIKE '%DOR%' OR t.name LIKE '%PFR%' OR t.name LIKE '%License%')
                      AND (t.completed = false OR t.completed IS NULL)
                      AND t.due_date >= CURRENT_DATE
                      AND EXTRACT(YEAR FROM c.created_at) = 2025
                      {assignee_filter}
                    ORDER BY t.due_date ASC
                    LIMIT 5
                """, _build_params())
                license_deadlines = [{'task': r[0], 'case': r[1] or 'Unknown',
                                     'due': r[2], 'days_until': r[3]}
                                    for r in cursor.fetchall()]

                return {
                    'assignee': assignee_name or 'All',
                    'overdue_count': overdue_count,
                    'due_today': due_today,
                    'completed_week': completed_week,
                    'license_deadlines': license_deadlines,
                }
        except Exception:
            # Return empty defaults if tables don't exist yet
            return {
                'assignee': assignee_name or 'All',
                'overdue_count': 0,
                'due_today': 0,
                'completed_week': 0,
                'license_deadlines': [],
            }
