"""
Task SLA and Staff Task Data Access
"""
from typing import Dict, List

from db.connection import get_connection


class TaskDataMixin:
    """Mixin providing task SLA, overdue tasks, and staff task data methods."""

    def get_overdue_tasks(self, limit: int = 20) -> List[Dict]:
        """Get overdue tasks from cache database (2025 cases only)."""
        try:
            with get_connection() as conn:
                cursor = conn.cursor()

                # Filter to tasks on 2025 cases, exclude tasks > 200 days overdue (stale)
                cursor.execute("""
                    SELECT t.id, t.name as task_name, c.name as case_name, t.assignee_name,
                           t.due_date, t.priority,
                           CAST(EXTRACT(DAY FROM CURRENT_DATE - t.due_date) AS INTEGER) as days_overdue
                    FROM cached_tasks t
                    LEFT JOIN cached_cases c ON t.case_id = c.id
                    WHERE t.firm_id = %s
                      AND t.due_date < CURRENT_DATE
                      AND t.due_date >= CURRENT_DATE - INTERVAL '200 days'
                      AND (t.completed = false OR t.completed IS NULL)
                      AND EXTRACT(YEAR FROM c.created_at) = 2025
                    ORDER BY t.due_date ASC
                    LIMIT %s
                """, (self.firm_id, limit))

                rows = cursor.fetchall()
                return [{
                    'task_id': row[0],
                    'task_name': row[1],
                    'case_name': row[2] or 'Unknown',
                    'assignee': row[3],
                    'due_date': row[4],
                    'days_overdue': row[5],
                    'priority': row[6],
                } for row in rows]
        except Exception:
            return []

    def get_staff_tasks(self, staff_name: str, include_completed: bool = False) -> Dict:
        """Get detailed task list for a specific staff member (2025 cases only)."""
        try:
            with get_connection() as conn:
                cursor = conn.cursor()

                staff_id = self._get_staff_id_by_name(staff_name)
                staff_lookup = self._get_staff_lookup()

                # Get full name from lookup
                full_name = staff_lookup.get(staff_id, staff_name) if staff_id else staff_name

                # Build assignee filter
                assignee_filter = ""
                params = [self.firm_id]
                if staff_id:
                    assignee_filter = "AND (t.assignee_name LIKE %s OR t.assignee_name LIKE %s OR t.assignee_name LIKE %s OR t.assignee_name = %s)"
                    params.extend([f'{staff_id},%', f'%,{staff_id},%', f'%,{staff_id}', staff_id])

                # Get overdue tasks on 2025 cases (exclude > 200 days as stale)
                cursor.execute(f"""
                    SELECT t.id, t.name as task_name, c.name as case_name, t.due_date,
                           CAST(EXTRACT(DAY FROM CURRENT_DATE - t.due_date) AS INTEGER) as days_overdue,
                           t.priority
                    FROM cached_tasks t
                    JOIN cached_cases c ON t.case_id = c.id
                    WHERE t.firm_id = %s
                      AND t.due_date < CURRENT_DATE
                      AND t.due_date >= CURRENT_DATE - INTERVAL '200 days'
                      AND (t.completed = false OR t.completed IS NULL)
                      AND EXTRACT(YEAR FROM c.created_at) = 2025
                      {assignee_filter}
                    ORDER BY t.due_date ASC
                """, params)
                overdue_tasks = [{'id': r[0], 'task': r[1], 'case': r[2] or 'Unknown', 'due': r[3], 'days_overdue': r[4], 'priority': r[5]}
                               for r in cursor.fetchall()]

                # Reset params
                params = [self.firm_id]
                if staff_id:
                    params.extend([f'{staff_id},%', f'%,{staff_id},%', f'%,{staff_id}', staff_id])

                # Get pending (not overdue) tasks on 2025 cases
                cursor.execute(f"""
                    SELECT t.id, t.name as task_name, c.name as case_name, t.due_date, t.priority
                    FROM cached_tasks t
                    JOIN cached_cases c ON t.case_id = c.id
                    WHERE t.firm_id = %s
                      AND t.due_date >= CURRENT_DATE
                      AND (t.completed = false OR t.completed IS NULL)
                      AND EXTRACT(YEAR FROM c.created_at) = 2025
                      {assignee_filter}
                    ORDER BY t.due_date ASC
                """, params)
                pending_tasks = [{'id': r[0], 'task': r[1], 'case': r[2] or 'Unknown', 'due': r[3], 'priority': r[4]}
                               for r in cursor.fetchall()]

                # Reset params
                params = [self.firm_id]
                if staff_id:
                    params.extend([f'{staff_id},%', f'%,{staff_id},%', f'%,{staff_id}', staff_id])

                # Get completed tasks if requested
                completed_tasks = []
                if include_completed:
                    cursor.execute(f"""
                        SELECT t.id, t.name as task_name, c.name as case_name, t.completed_at, t.priority
                        FROM cached_tasks t
                        JOIN cached_cases c ON t.case_id = c.id
                        WHERE t.firm_id = %s
                          AND t.completed = true
                          AND DATE(t.completed_at) >= CURRENT_DATE - INTERVAL '7 days'
                          AND EXTRACT(YEAR FROM c.created_at) = 2025
                          {assignee_filter}
                        ORDER BY t.completed_at DESC
                    """, params)
                    completed_tasks = [{'id': r[0], 'task': r[1], 'case': r[2] or 'Unknown', 'completed_at': r[3], 'priority': r[4]}
                                     for r in cursor.fetchall()]

                return {
                    'staff_name': full_name,
                    'overdue_tasks': overdue_tasks,
                    'pending_tasks': pending_tasks,
                    'completed_tasks': completed_tasks,
                }
        except Exception:
            return {
                'staff_name': staff_name,
                'overdue_tasks': [],
                'pending_tasks': [],
                'completed_tasks': [],
            }
