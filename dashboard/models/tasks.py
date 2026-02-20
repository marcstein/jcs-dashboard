"""
Task SLA and Staff Task Data Access
"""
from typing import Dict, List

import psycopg2.extensions
from db.connection import get_connection


class TaskDataMixin:
    """Mixin providing task SLA, overdue tasks, and staff task data methods."""

    def get_overdue_tasks(self, limit: int = 20) -> List[Dict]:
        """Get overdue tasks from cache database."""
        try:
            with get_connection() as conn:
                cursor = self._cursor(conn)

                cursor.execute("""
                    SELECT t.id, t.name as task_name, c.name as case_name, t.assignee_name,
                           t.due_date, t.priority,
                           (CURRENT_DATE - t.due_date) as days_overdue
                    FROM cached_tasks t
                    LEFT JOIN cached_cases c ON t.case_id = c.id AND t.firm_id = c.firm_id
                    WHERE t.firm_id = %s
                      AND t.due_date < CURRENT_DATE
                      AND t.due_date >= CURRENT_DATE - INTERVAL '200 days'
                      AND (t.completed = false OR t.completed IS NULL)
                    ORDER BY t.due_date ASC
                    LIMIT %s
                """, (self.firm_id, limit))

                staff_lookup = self._get_staff_lookup()
                rows = cursor.fetchall()
                return [{
                    'task_id': row[0],
                    'task_name': row[1],
                    'case_name': row[2] or 'Unknown',
                    'assignee': self._resolve_assignee_ids_to_names(row[3], staff_lookup),
                    'due_date': row[4],
                    'days_overdue': row[6],
                    'priority': row[5],
                } for row in rows]
        except Exception as e:
            print(f"get_overdue_tasks error: {e}")
            return []

    def get_staff_tasks(self, staff_name: str, include_completed: bool = False) -> Dict:
        """Get detailed task list for a specific staff member.

        For attorneys, also includes tasks on cases where they are lead attorney.

        Returns dict with keys matching what the staff_tasks.html template expects:
        - staff_name, overdue_tasks, overdue_count
        - due_today (list), due_today_count
        - upcoming (list), upcoming_count
        - pending_tasks, completed_tasks
        """
        try:
            with get_connection() as conn:
                cursor = self._cursor(conn)

                staff_id = self._get_staff_id_by_name(staff_name)
                staff_lookup = self._get_staff_lookup()
                full_name = staff_lookup.get(staff_id, staff_name) if staff_id else staff_name
                is_attorney = self._is_attorney(staff_name)

                # Build assignee filter
                # For attorneys, also match tasks on their cases (via lead_attorney_name)
                assignee_filter = ""
                assignee_params = []
                if staff_id and is_attorney:
                    assignee_filter = """AND (
                        t.assignee_name LIKE %s OR t.assignee_name LIKE %s
                        OR t.assignee_name LIKE %s OR t.assignee_name = %s
                        OR c.lead_attorney_name ILIKE %s
                    )"""
                    assignee_params = [f'{staff_id},%', f'%,{staff_id},%', f'%,{staff_id}', staff_id, f'%{staff_name}%']
                elif staff_id:
                    assignee_filter = "AND (t.assignee_name LIKE %s OR t.assignee_name LIKE %s OR t.assignee_name LIKE %s OR t.assignee_name = %s)"
                    assignee_params = [f'{staff_id},%', f'%,{staff_id},%', f'%,{staff_id}', staff_id]

                # ── Overdue tasks (past due, not completed, within 200 days) ──
                cursor.execute(f"""
                    SELECT t.id, t.name, c.name as case_name, t.due_date,
                           (CURRENT_DATE - t.due_date) as days_overdue,
                           t.priority
                    FROM cached_tasks t
                    LEFT JOIN cached_cases c ON t.case_id = c.id AND t.firm_id = c.firm_id
                    WHERE t.firm_id = %s
                      AND t.due_date < CURRENT_DATE
                      AND t.due_date >= CURRENT_DATE - INTERVAL '200 days'
                      AND (t.completed = false OR t.completed IS NULL)
                      {assignee_filter}
                    ORDER BY t.due_date ASC
                """, [self.firm_id] + assignee_params)
                overdue_tasks = [{
                    'id': r[0], 'task_name': r[1], 'case_name': r[2] or 'Unknown',
                    'due_date': r[3], 'days_overdue': r[4], 'priority': r[5]
                } for r in cursor.fetchall()]

                # ── Due today ──
                cursor.execute(f"""
                    SELECT t.id, t.name, c.name as case_name, t.due_date, t.priority
                    FROM cached_tasks t
                    LEFT JOIN cached_cases c ON t.case_id = c.id AND t.firm_id = c.firm_id
                    WHERE t.firm_id = %s
                      AND t.due_date = CURRENT_DATE
                      AND (t.completed = false OR t.completed IS NULL)
                      {assignee_filter}
                    ORDER BY t.priority DESC NULLS LAST
                """, [self.firm_id] + assignee_params)
                due_today = [{
                    'id': r[0], 'task_name': r[1], 'case_name': r[2] or 'Unknown',
                    'due_date': r[3], 'priority': r[4]
                } for r in cursor.fetchall()]

                # ── Upcoming (next 7 days, excludes today) ──
                cursor.execute(f"""
                    SELECT t.id, t.name, c.name as case_name, t.due_date,
                           (t.due_date - CURRENT_DATE) as days_until,
                           t.priority
                    FROM cached_tasks t
                    LEFT JOIN cached_cases c ON t.case_id = c.id AND t.firm_id = c.firm_id
                    WHERE t.firm_id = %s
                      AND t.due_date > CURRENT_DATE
                      AND t.due_date <= CURRENT_DATE + INTERVAL '7 days'
                      AND (t.completed = false OR t.completed IS NULL)
                      {assignee_filter}
                    ORDER BY t.due_date ASC
                """, [self.firm_id] + assignee_params)
                upcoming = [{
                    'id': r[0], 'task_name': r[1], 'case_name': r[2] or 'Unknown',
                    'due_date': r[3], 'days_until': r[4], 'priority': r[5]
                } for r in cursor.fetchall()]

                # ── Pending (future, beyond 7 days) ──
                cursor.execute(f"""
                    SELECT t.id, t.name, c.name as case_name, t.due_date, t.priority
                    FROM cached_tasks t
                    LEFT JOIN cached_cases c ON t.case_id = c.id AND t.firm_id = c.firm_id
                    WHERE t.firm_id = %s
                      AND t.due_date > CURRENT_DATE + INTERVAL '7 days'
                      AND (t.completed = false OR t.completed IS NULL)
                      {assignee_filter}
                    ORDER BY t.due_date ASC
                """, [self.firm_id] + assignee_params)
                pending_tasks = [{
                    'id': r[0], 'task': r[1], 'case': r[2] or 'Unknown',
                    'due': r[3], 'priority': r[4]
                } for r in cursor.fetchall()]

                # ── Completed (last 7 days) ──
                completed_tasks = []
                if include_completed:
                    cursor.execute(f"""
                        SELECT t.id, t.name, c.name as case_name, t.completed_at, t.priority
                        FROM cached_tasks t
                        LEFT JOIN cached_cases c ON t.case_id = c.id AND t.firm_id = c.firm_id
                        WHERE t.firm_id = %s
                          AND t.completed = true
                          AND DATE(t.completed_at) >= CURRENT_DATE - INTERVAL '7 days'
                          {assignee_filter}
                        ORDER BY t.completed_at DESC
                    """, [self.firm_id] + assignee_params)
                    completed_tasks = [{
                        'id': r[0], 'task': r[1], 'case': r[2] or 'Unknown',
                        'completed_at': r[3], 'priority': r[4]
                    } for r in cursor.fetchall()]

                return {
                    'staff_name': full_name,
                    'overdue_tasks': overdue_tasks,
                    'overdue_count': len(overdue_tasks),
                    'due_today': due_today,
                    'due_today_count': len(due_today),
                    'upcoming': upcoming,
                    'upcoming_count': len(upcoming),
                    'pending_tasks': pending_tasks,
                    'completed_tasks': completed_tasks,
                }
        except Exception as e:
            print(f"get_staff_tasks error for {staff_name}: {e}")
            return {
                'staff_name': staff_name,
                'overdue_tasks': [], 'overdue_count': 0,
                'due_today': [], 'due_today_count': 0,
                'upcoming': [], 'upcoming_count': 0,
                'pending_tasks': [], 'completed_tasks': [],
            }
