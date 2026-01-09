"""
Task SLA Monitoring Module

Monitors task completion and SLAs for legal assistants per Alison/Cole SOPs:
- Task completion rates
- Client response times
- Case setup verification
- DUI/DWI deadline tracking (15-day DOR, 30-day PFR)
- Discovery routing
"""
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum

from api_client import MyCaseClient, get_client, MyCaseAPIError
from database import Database, get_db


class TaskPriority(Enum):
    CRITICAL = "critical"  # Custody, filing deadlines
    HIGH = "high"  # License filings, discovery
    NORMAL = "normal"  # Standard tasks
    LOW = "low"  # Administrative


class TaskCategory(Enum):
    CASE_SETUP = "case_setup"
    FILING = "filing"
    DISCOVERY = "discovery"
    CLIENT_COMMUNICATION = "client_communication"
    DUI_DWI = "dui_dwi"
    MUNICIPAL = "municipal"
    EXPUNGEMENT = "expungement"
    ADMINISTRATIVE = "administrative"


@dataclass
class TaskWithSLA:
    """Task with SLA tracking information."""
    id: int
    mycase_task_id: int
    name: str
    case_id: int
    case_name: str
    assignee_id: int
    assignee_name: str
    category: TaskCategory
    priority: TaskPriority
    due_date: date
    created_at: datetime
    completed_at: Optional[datetime]
    sla_hours: int  # Expected completion time in hours
    actual_hours: Optional[float]
    sla_met: Optional[bool]
    days_until_due: int
    is_overdue: bool


@dataclass
class AssigneeMetrics:
    """Performance metrics for a single assignee."""
    assignee_id: int
    assignee_name: str
    tasks_assigned: int = 0
    tasks_completed: int = 0
    tasks_overdue: int = 0
    completion_rate: float = 0.0
    avg_completion_hours: float = 0.0
    sla_hit_rate: float = 0.0
    by_category: Dict[str, int] = field(default_factory=dict)


@dataclass
class LicenseFilingDeadline:
    """DUI/DWI license filing deadline tracking."""
    case_id: int
    case_name: str
    client_name: str
    arrest_date: date
    filing_type: str  # "DOR" or "PFR"
    deadline_date: date
    days_remaining: int
    filed: bool
    filed_date: Optional[date]
    assignee_name: str
    is_urgent: bool


class TaskSLAManager:
    """
    Monitors task completion and SLAs for legal assistants.

    Based on Alison and Cole's SOPs:
    - 15-day DOR filing for DUIs (no refusal)
    - 30-day PFR filing for DUIs (refusal)
    - Same-day task acknowledgment
    - Discovery request filing within 24 hours of charging
    """

    # SLA definitions by task type (hours)
    DEFAULT_SLAS = {
        "case_setup": 24,  # 1 business day
        "entry_of_appearance": 24,
        "discovery_request": 24,
        "dor_filing": 360,  # 15 days (15 * 24)
        "pfr_filing": 720,  # 30 days
        "client_response": 4,  # Same day
        "municipal_continuance": 24,
        "expungement_filing": 48,
        "document_upload": 4,
    }

    def __init__(
        self,
        client: MyCaseClient = None,
        db: Database = None,
    ):
        self.client = client or get_client()
        self.db = db or get_db()
        self._ensure_tables()

    def _ensure_tables(self):
        """Ensure task tracking tables exist."""
        with self.db._get_connection() as conn:
            cursor = conn.cursor()

            # Task SLA tracking
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS task_sla_tracking (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    mycase_task_id INTEGER UNIQUE,
                    task_name TEXT,
                    case_id INTEGER,
                    case_name TEXT,
                    assignee_id INTEGER,
                    assignee_name TEXT,
                    category TEXT,
                    priority TEXT DEFAULT 'normal',
                    due_date DATE,
                    created_at TIMESTAMP,
                    completed_at TIMESTAMP,
                    sla_hours INTEGER,
                    actual_hours REAL,
                    sla_met BOOLEAN,
                    notes TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # DUI/DWI license deadline tracking
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS license_filing_deadlines (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    case_id INTEGER NOT NULL,
                    case_name TEXT,
                    client_name TEXT,
                    arrest_date DATE,
                    filing_type TEXT NOT NULL,
                    deadline_date DATE NOT NULL,
                    filed BOOLEAN DEFAULT FALSE,
                    filed_date DATE,
                    assignee_id INTEGER,
                    assignee_name TEXT,
                    notes TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(case_id, filing_type)
                )
            """)

            # Client response tracking
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS client_response_tracking (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    case_id INTEGER,
                    contact_id INTEGER,
                    contact_name TEXT,
                    message_type TEXT,
                    received_at TIMESTAMP,
                    responded_at TIMESTAMP,
                    response_hours REAL,
                    sla_met BOOLEAN,
                    assignee_id INTEGER,
                    assignee_name TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Case.net monitoring checklist
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS casenet_monitoring (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    case_id INTEGER NOT NULL,
                    case_name TEXT,
                    client_name TEXT,
                    status TEXT DEFAULT 'pre-charge',
                    last_checked DATE,
                    checked_by TEXT,
                    charged_date DATE,
                    entry_filed BOOLEAN DEFAULT FALSE,
                    discovery_requested BOOLEAN DEFAULT FALSE,
                    notes TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(case_id)
                )
            """)

            conn.commit()

    # ========== Task Sync and Tracking ==========

    def sync_tasks_from_mycase(self, days_back: int = 30) -> int:
        """
        Sync tasks from MyCase for SLA tracking.

        Returns count of tasks synced.
        """
        print(f"Syncing tasks from MyCase (last {days_back} days)...")

        try:
            # Build staff lookup table
            staff_lookup = {}
            try:
                all_staff = self.client.get_staff()
                for s in all_staff:
                    staff_lookup[s.get("id")] = f"{s.get('first_name', '')} {s.get('last_name', '')}".strip()
            except Exception:
                pass

            all_tasks = self.client.get_all_pages(self.client.get_tasks)
            tasks_synced = 0

            for task in all_tasks:
                task_id = task.get("id")
                task_name = task.get("name", "")

                # Get case info
                case = task.get("case", {})
                case_id = case.get("id") if case else None
                case_name = case.get("name") if case else None

                # Get assignee info from staff field (array of {id: ...})
                staff_list = task.get("staff", [])
                assignee_id = None
                assignee_name = "Unassigned"
                if staff_list and len(staff_list) > 0:
                    # Use first staff member as primary assignee
                    assignee_id = staff_list[0].get("id")
                    assignee_name = staff_lookup.get(assignee_id, "Unknown")

                # Determine category and SLA
                category = self._categorize_task(task_name, case_name)
                sla_hours = self._get_sla_hours(task_name, category)
                priority = self._determine_priority(task_name, category)

                # Parse dates
                due_date_str = task.get("due_date", "")
                created_str = task.get("created_at", "")
                completed_str = task.get("completed_at", "")

                due_date = None
                created_at = None
                completed_at = None

                if due_date_str:
                    try:
                        due_date = datetime.fromisoformat(due_date_str.replace("Z", "")).date()
                    except ValueError:
                        pass

                if created_str:
                    try:
                        created_at = datetime.fromisoformat(created_str.replace("Z", ""))
                    except ValueError:
                        created_at = datetime.now()

                if completed_str:
                    try:
                        completed_at = datetime.fromisoformat(completed_str.replace("Z", ""))
                    except ValueError:
                        pass

                # Calculate actual hours and SLA met
                actual_hours = None
                sla_met = None

                if completed_at and created_at:
                    actual_hours = (completed_at - created_at).total_seconds() / 3600
                    sla_met = actual_hours <= sla_hours

                self._upsert_task(
                    mycase_task_id=task_id,
                    task_name=task_name,
                    case_id=case_id,
                    case_name=case_name,
                    assignee_id=assignee_id,
                    assignee_name=assignee_name,
                    category=category,
                    priority=priority,
                    due_date=due_date,
                    created_at=created_at,
                    completed_at=completed_at,
                    sla_hours=sla_hours,
                    actual_hours=actual_hours,
                    sla_met=sla_met,
                )
                tasks_synced += 1

            print(f"Synced {tasks_synced} tasks")
            return tasks_synced

        except MyCaseAPIError as e:
            print(f"Error syncing tasks: {e}")
            return 0

    def _categorize_task(self, task_name: str, case_name: str = None) -> TaskCategory:
        """Categorize a task based on its name."""
        task_lower = task_name.lower()
        case_lower = (case_name or "").lower()

        if any(term in task_lower for term in ["setup", "open", "new matter", "intake"]):
            return TaskCategory.CASE_SETUP
        elif any(term in task_lower for term in ["discovery", "request", "interrogator"]):
            return TaskCategory.DISCOVERY
        elif any(term in task_lower for term in ["entry", "appearance", "file", "filing"]):
            return TaskCategory.FILING
        elif any(term in task_lower for term in ["dor", "pfr", "license", "dui", "dwi"]) or \
             any(term in case_lower for term in ["dui", "dwi"]):
            return TaskCategory.DUI_DWI
        elif any(term in task_lower for term in ["municipal", "muni", "continue", "continuance"]):
            return TaskCategory.MUNICIPAL
        elif any(term in task_lower for term in ["expung"]):
            return TaskCategory.EXPUNGEMENT
        elif any(term in task_lower for term in ["call", "email", "respond", "contact", "client"]):
            return TaskCategory.CLIENT_COMMUNICATION
        else:
            return TaskCategory.ADMINISTRATIVE

    def _determine_priority(self, task_name: str, category: TaskCategory) -> TaskPriority:
        """Determine task priority."""
        task_lower = task_name.lower()

        if any(term in task_lower for term in ["custody", "jail", "urgent", "emergency", "deadline"]):
            return TaskPriority.CRITICAL
        elif category == TaskCategory.DUI_DWI:
            return TaskPriority.HIGH
        elif category == TaskCategory.FILING:
            return TaskPriority.HIGH
        elif category == TaskCategory.DISCOVERY:
            return TaskPriority.HIGH
        else:
            return TaskPriority.NORMAL

    def _get_sla_hours(self, task_name: str, category: TaskCategory) -> int:
        """Get SLA hours for a task."""
        task_lower = task_name.lower()

        if "dor" in task_lower:
            return self.DEFAULT_SLAS["dor_filing"]
        elif "pfr" in task_lower:
            return self.DEFAULT_SLAS["pfr_filing"]
        elif "discovery" in task_lower:
            return self.DEFAULT_SLAS["discovery_request"]
        elif "entry" in task_lower or "appearance" in task_lower:
            return self.DEFAULT_SLAS["entry_of_appearance"]
        elif category == TaskCategory.CASE_SETUP:
            return self.DEFAULT_SLAS["case_setup"]
        elif category == TaskCategory.CLIENT_COMMUNICATION:
            return self.DEFAULT_SLAS["client_response"]
        elif category == TaskCategory.MUNICIPAL:
            return self.DEFAULT_SLAS["municipal_continuance"]
        elif category == TaskCategory.EXPUNGEMENT:
            return self.DEFAULT_SLAS["expungement_filing"]
        else:
            return 48  # Default 2 business days

    def _upsert_task(
        self,
        mycase_task_id: int,
        task_name: str,
        case_id: int,
        case_name: str,
        assignee_id: int,
        assignee_name: str,
        category: TaskCategory,
        priority: TaskPriority,
        due_date: date,
        created_at: datetime,
        completed_at: datetime,
        sla_hours: int,
        actual_hours: float,
        sla_met: bool,
    ):
        """Insert or update a task."""
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO task_sla_tracking
                (mycase_task_id, task_name, case_id, case_name, assignee_id, assignee_name,
                 category, priority, due_date, created_at, completed_at, sla_hours,
                 actual_hours, sla_met, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(mycase_task_id) DO UPDATE SET
                    task_name = excluded.task_name,
                    completed_at = excluded.completed_at,
                    actual_hours = excluded.actual_hours,
                    sla_met = excluded.sla_met,
                    updated_at = CURRENT_TIMESTAMP
            """, (mycase_task_id, task_name, case_id, case_name, assignee_id, assignee_name,
                  category.value, priority.value, due_date, created_at, completed_at,
                  sla_hours, actual_hours, sla_met))
            conn.commit()

    # ========== DUI/DWI License Deadlines ==========

    def add_license_deadline(
        self,
        case_id: int,
        arrest_date: date,
        filing_type: str,  # "DOR" or "PFR"
        case_name: str = None,
        client_name: str = None,
        assignee_id: int = None,
        assignee_name: str = None,
    ) -> int:
        """
        Add a DUI/DWI license filing deadline.

        DOR (no refusal): 15 days from arrest
        PFR (refusal): 30 days from arrest
        """
        if filing_type.upper() == "DOR":
            deadline_date = arrest_date + timedelta(days=15)
        elif filing_type.upper() == "PFR":
            deadline_date = arrest_date + timedelta(days=30)
        else:
            raise ValueError(f"Unknown filing type: {filing_type}")

        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO license_filing_deadlines
                (case_id, case_name, client_name, arrest_date, filing_type,
                 deadline_date, assignee_id, assignee_name)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (case_id, case_name, client_name, arrest_date, filing_type.upper(),
                  deadline_date, assignee_id, assignee_name))
            return cursor.lastrowid

    def mark_filing_complete(self, case_id: int, filing_type: str, filed_date: date = None):
        """Mark a license filing as complete."""
        filed_date = filed_date or date.today()
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE license_filing_deadlines
                SET filed = TRUE, filed_date = ?
                WHERE case_id = ? AND filing_type = ?
            """, (filed_date, case_id, filing_type.upper()))
            conn.commit()

    def get_upcoming_license_deadlines(self, days_ahead: int = 7) -> List[LicenseFilingDeadline]:
        """Get upcoming license filing deadlines."""
        today = date.today()
        cutoff = today + timedelta(days=days_ahead)

        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM license_filing_deadlines
                WHERE filed = FALSE
                AND deadline_date <= ?
                ORDER BY deadline_date ASC
            """, (cutoff,))

            deadlines = []
            for row in cursor.fetchall():
                deadline_date = datetime.strptime(row["deadline_date"], "%Y-%m-%d").date()
                arrest_date = datetime.strptime(row["arrest_date"], "%Y-%m-%d").date()
                days_remaining = (deadline_date - today).days

                deadlines.append(LicenseFilingDeadline(
                    case_id=row["case_id"],
                    case_name=row["case_name"] or "Unknown",
                    client_name=row["client_name"] or "Unknown",
                    arrest_date=arrest_date,
                    filing_type=row["filing_type"],
                    deadline_date=deadline_date,
                    days_remaining=days_remaining,
                    filed=False,
                    filed_date=None,
                    assignee_name=row["assignee_name"] or "Unassigned",
                    is_urgent=days_remaining <= 3,
                ))

            return deadlines

    def get_overdue_license_filings(self) -> List[LicenseFilingDeadline]:
        """Get overdue license filings."""
        today = date.today()

        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM license_filing_deadlines
                WHERE filed = FALSE
                AND deadline_date < ?
                ORDER BY deadline_date ASC
            """, (today,))

            deadlines = []
            for row in cursor.fetchall():
                deadline_date = datetime.strptime(row["deadline_date"], "%Y-%m-%d").date()
                arrest_date = datetime.strptime(row["arrest_date"], "%Y-%m-%d").date()
                days_remaining = (deadline_date - today).days  # Will be negative

                deadlines.append(LicenseFilingDeadline(
                    case_id=row["case_id"],
                    case_name=row["case_name"] or "Unknown",
                    client_name=row["client_name"] or "Unknown",
                    arrest_date=arrest_date,
                    filing_type=row["filing_type"],
                    deadline_date=deadline_date,
                    days_remaining=days_remaining,
                    filed=False,
                    filed_date=None,
                    assignee_name=row["assignee_name"] or "Unassigned",
                    is_urgent=True,
                ))

            return deadlines

    # ========== Case.net Monitoring ==========

    def add_casenet_watch(
        self,
        case_id: int,
        case_name: str = None,
        client_name: str = None,
    ) -> int:
        """Add a case to Case.net monitoring list."""
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR IGNORE INTO casenet_monitoring
                (case_id, case_name, client_name, status)
                VALUES (?, ?, ?, 'pre-charge')
            """, (case_id, case_name, client_name))
            return cursor.lastrowid

    def update_casenet_status(
        self,
        case_id: int,
        status: str,
        charged_date: date = None,
        checked_by: str = None,
    ):
        """Update Case.net monitoring status."""
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE casenet_monitoring
                SET status = ?, charged_date = ?, last_checked = DATE('now'),
                    checked_by = ?, updated_at = CURRENT_TIMESTAMP
                WHERE case_id = ?
            """, (status, charged_date, checked_by, case_id))
            conn.commit()

    def get_casenet_checklist(self) -> List[Dict]:
        """Get cases that need Case.net checking."""
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM casenet_monitoring
                WHERE status = 'pre-charge'
                AND (last_checked IS NULL OR last_checked < DATE('now'))
                ORDER BY created_at ASC
            """)
            return [dict(row) for row in cursor.fetchall()]

    def get_newly_charged_cases(self) -> List[Dict]:
        """Get cases that were recently charged and need entry/discovery."""
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM casenet_monitoring
                WHERE status = 'charged'
                AND (entry_filed = FALSE OR discovery_requested = FALSE)
                ORDER BY charged_date ASC
            """)
            return [dict(row) for row in cursor.fetchall()]

    # ========== Assignee Metrics ==========

    def get_assignee_metrics(
        self,
        assignee_id: int = None,
        days_back: int = 30,
    ) -> List[AssigneeMetrics]:
        """Get task performance metrics by assignee."""
        cutoff = date.today() - timedelta(days=days_back)

        with self.db._get_connection() as conn:
            cursor = conn.cursor()

            query = """
                SELECT
                    assignee_id,
                    assignee_name,
                    COUNT(*) as assigned,
                    SUM(CASE WHEN completed_at IS NOT NULL THEN 1 ELSE 0 END) as completed,
                    SUM(CASE WHEN due_date < DATE('now') AND completed_at IS NULL THEN 1 ELSE 0 END) as overdue,
                    AVG(actual_hours) as avg_hours,
                    AVG(CASE WHEN sla_met = 1 THEN 100 ELSE 0 END) as sla_rate
                FROM task_sla_tracking
                WHERE created_at >= ?
            """
            params = [cutoff]

            if assignee_id:
                query += " AND assignee_id = ?"
                params.append(assignee_id)

            query += " GROUP BY assignee_id, assignee_name"
            cursor.execute(query, params)

            metrics = []
            for row in cursor.fetchall():
                assigned = row["assigned"] or 0
                completed = row["completed"] or 0

                m = AssigneeMetrics(
                    assignee_id=row["assignee_id"],
                    assignee_name=row["assignee_name"] or "Unknown",
                    tasks_assigned=assigned,
                    tasks_completed=completed,
                    tasks_overdue=row["overdue"] or 0,
                    completion_rate=(completed / assigned * 100) if assigned > 0 else 0,
                    avg_completion_hours=row["avg_hours"] or 0,
                    sla_hit_rate=row["sla_rate"] or 0,
                )

                # Get breakdown by category
                cursor.execute("""
                    SELECT category, COUNT(*) as count
                    FROM task_sla_tracking
                    WHERE assignee_id = ? AND created_at >= ?
                    GROUP BY category
                """, (m.assignee_id, cutoff))
                m.by_category = {r["category"]: r["count"] for r in cursor.fetchall()}

                metrics.append(m)

            return metrics

    def get_overdue_tasks(self, assignee_id: int = None) -> List[TaskWithSLA]:
        """Get all overdue tasks."""
        today = date.today()

        with self.db._get_connection() as conn:
            cursor = conn.cursor()

            query = """
                SELECT * FROM task_sla_tracking
                WHERE due_date < ?
                AND completed_at IS NULL
            """
            params = [today]

            if assignee_id:
                query += " AND assignee_id = ?"
                params.append(assignee_id)

            query += " ORDER BY due_date ASC"
            cursor.execute(query, params)

            tasks = []
            for row in cursor.fetchall():
                due_date = datetime.strptime(row["due_date"], "%Y-%m-%d").date() if row["due_date"] else today
                created_at = datetime.fromisoformat(row["created_at"]) if row["created_at"] else datetime.now()

                tasks.append(TaskWithSLA(
                    id=row["id"],
                    mycase_task_id=row["mycase_task_id"],
                    name=row["task_name"],
                    case_id=row["case_id"],
                    case_name=row["case_name"] or "Unknown",
                    assignee_id=row["assignee_id"],
                    assignee_name=row["assignee_name"] or "Unassigned",
                    category=TaskCategory(row["category"]) if row["category"] else TaskCategory.ADMINISTRATIVE,
                    priority=TaskPriority(row["priority"]) if row["priority"] else TaskPriority.NORMAL,
                    due_date=due_date,
                    created_at=created_at,
                    completed_at=None,
                    sla_hours=row["sla_hours"] or 48,
                    actual_hours=None,
                    sla_met=None,
                    days_until_due=(due_date - today).days,
                    is_overdue=True,
                ))

            return tasks

    # ========== Report Generation ==========

    def generate_legal_assistant_report(
        self,
        assignee_name: str = None,
        days_back: int = 7,
    ) -> str:
        """Generate weekly KPI report for legal assistant (Alison/Cole)."""
        metrics_list = self.get_assignee_metrics(days_back=days_back)

        if assignee_name:
            metrics_list = [m for m in metrics_list if assignee_name.lower() in m.assignee_name.lower()]

        overdue_tasks = self.get_overdue_tasks()
        license_deadlines = self.get_upcoming_license_deadlines()
        overdue_filings = self.get_overdue_license_filings()
        casenet_needed = self.get_casenet_checklist()

        report = f"""
================================================================================
              LEGAL ASSISTANT TASK REPORT - Last {days_back} Days
================================================================================

"""
        for m in metrics_list:
            completion_status = "✓" if m.completion_rate >= 95 else "⚠"
            sla_status = "✓" if m.sla_hit_rate >= 90 else "⚠"

            report += f"""
### {m.assignee_name}

TASK COMPLETION
  Assigned: {m.tasks_assigned}
  Completed: {m.tasks_completed} ({m.completion_rate:.1f}%) {completion_status}
  Overdue: {m.tasks_overdue}

SLA PERFORMANCE
  SLA Hit Rate: {m.sla_hit_rate:.1f}% {sla_status}
  Avg Completion Time: {m.avg_completion_hours:.1f} hours

BY CATEGORY
"""
            for cat, count in sorted(m.by_category.items(), key=lambda x: -x[1]):
                report += f"  • {cat}: {count}\n"

        report += f"""

================================================================================
                        URGENT ITEMS
================================================================================

LICENSE FILING DEADLINES ({len(license_deadlines)} upcoming)
"""
        for dl in license_deadlines[:5]:
            urgency = "🔴" if dl.is_urgent else "🟡"
            report += f"  {urgency} {dl.client_name} - {dl.filing_type}: {dl.days_remaining} days ({dl.assignee_name})\n"

        if overdue_filings:
            report += f"""
OVERDUE LICENSE FILINGS ({len(overdue_filings)}) 🔴
"""
            for dl in overdue_filings:
                report += f"  🔴 {dl.client_name} - {dl.filing_type}: {abs(dl.days_remaining)} days OVERDUE\n"

        report += f"""
OVERDUE TASKS ({len(overdue_tasks)})
"""
        for task in overdue_tasks[:10]:
            report += f"  • {task.name[:40]} - {task.case_name[:20]} ({task.assignee_name})\n"

        report += f"""
CASE.NET CHECKS NEEDED ({len(casenet_needed)})
"""
        for case in casenet_needed[:10]:
            report += f"  • {case['case_name'] or case['case_id']} - {case['client_name']}\n"

        report += """
================================================================================
"""
        return report

    def generate_ops_huddle_report(self) -> str:
        """
        Generate paralegal ops huddle report per Tiffany's SOP.

        Topics:
        - Task completion across team
        - Pending escalations
        - Discovery status
        - Upcoming deadlines
        """
        all_metrics = self.get_assignee_metrics(days_back=7)
        overdue = self.get_overdue_tasks()
        license_urgent = self.get_upcoming_license_deadlines(days_ahead=3)
        newly_charged = self.get_newly_charged_cases()

        report = f"""
================================================================================
                    PARALEGAL OPS HUDDLE - {date.today()}
================================================================================

1. TEAM TASK COMPLETION (Last 7 Days)
"""
        total_assigned = sum(m.tasks_assigned for m in all_metrics)
        total_completed = sum(m.tasks_completed for m in all_metrics)
        overall_rate = (total_completed / total_assigned * 100) if total_assigned > 0 else 0

        report += f"   Overall: {total_completed}/{total_assigned} ({overall_rate:.1f}%)\n\n"

        for m in all_metrics:
            status = "✓" if m.completion_rate >= 95 else "⚠"
            report += f"   {m.assignee_name}: {m.tasks_completed}/{m.tasks_assigned} ({m.completion_rate:.1f}%) {status}\n"

        report += f"""

2. OVERDUE TASKS ({len(overdue)})
"""
        by_assignee = {}
        for task in overdue:
            name = task.assignee_name
            by_assignee[name] = by_assignee.get(name, 0) + 1

        for name, count in sorted(by_assignee.items(), key=lambda x: -x[1]):
            report += f"   • {name}: {count} overdue\n"

        report += f"""

3. URGENT LICENSE FILINGS ({len(license_urgent)})
"""
        for dl in license_urgent:
            report += f"   🔴 {dl.client_name} - {dl.filing_type}: {dl.days_remaining} days\n"

        report += f"""

4. NEWLY CHARGED - NEEDS ENTRY/DISCOVERY ({len(newly_charged)})
"""
        for case in newly_charged[:5]:
            needs = []
            if not case.get("entry_filed"):
                needs.append("Entry")
            if not case.get("discovery_requested"):
                needs.append("Discovery")
            report += f"   • {case['case_name']}: {', '.join(needs)}\n"

        report += """

5. ACTION ITEMS
   [ ] Review overdue tasks with assignees
   [ ] Verify urgent license filings in progress
   [ ] Confirm entry/discovery for newly charged cases
   [ ] Check Case.net for pre-charge updates

================================================================================
"""
        return report


if __name__ == "__main__":
    manager = TaskSLAManager()

    print("Testing Task SLA Manager...")
    print("(Requires valid MyCase API authentication)")

    try:
        # Sync tasks
        manager.sync_tasks_from_mycase()

        # Generate report
        report = manager.generate_legal_assistant_report()
        print(report)

        # Ops huddle
        huddle = manager.generate_ops_huddle_report()
        print(huddle)

    except Exception as e:
        print(f"Error: {e}")
        print("Make sure you've authenticated with: python auth.py")
