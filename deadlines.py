"""
Case Deadline Tracking and Attorney Notifications

Handles:
- Syncing case events/deadlines from MyCase
- Tracking important dates per case
- Sending attorney notifications for upcoming deadlines
- Overdue task alerts
"""
from datetime import datetime, date, timedelta
from typing import List, Dict, Optional
from dataclasses import dataclass

from api_client import MyCaseClient, get_client, MyCaseAPIError
from database import Database, get_db
from templates import TemplateManager


@dataclass
class CaseDeadline:
    """Represents a case deadline or important date."""
    deadline_id: Optional[int]  # Local DB ID
    case_id: int
    case_name: str
    case_number: Optional[str]
    deadline_name: str
    deadline_date: date
    deadline_type: str  # event, task, court_date, filing_deadline, etc.
    attorney_id: Optional[int]
    attorney_name: Optional[str]
    description: Optional[str]
    days_until: int
    notification_sent: bool


@dataclass
class OverdueTask:
    """Represents an overdue task."""
    task_id: int
    task_name: str
    case_id: int
    case_name: str
    due_date: date
    days_overdue: int
    assignee_id: int
    assignee_name: str
    status: str


class DeadlineManager:
    """
    Manages case deadline tracking and attorney notifications.
    """

    def __init__(
        self,
        client: MyCaseClient = None,
        db: Database = None,
        template_manager: TemplateManager = None,
    ):
        self.client = client or get_client()
        self.db = db or get_db()
        self.templates = template_manager or TemplateManager()

    def sync_events_from_mycase(self, days_ahead: int = 30) -> int:
        """
        Sync upcoming events from MyCase to local database.

        Args:
            days_ahead: Number of days ahead to sync

        Returns:
            Number of events synced
        """
        synced = 0
        today = date.today()
        end_date = today + timedelta(days=days_ahead)

        try:
            events = self.client.get_all_pages(
                self.client.get_events,
                start_date=datetime.combine(today, datetime.min.time()),
                end_date=datetime.combine(end_date, datetime.max.time()),
            )

            for event in events:
                event_date_str = event.get("start_at") or event.get("date")
                if not event_date_str:
                    continue

                event_date = datetime.fromisoformat(
                    event_date_str.replace("Z", "+00:00")
                ).date()

                # Get case info
                case = event.get("case", {})
                case_id = case.get("id")
                if not case_id:
                    continue

                # Get assignee/attorney info
                assignees = event.get("assignees", [])
                attorney = assignees[0] if assignees else {}

                self.db.upsert_deadline(
                    case_id=case_id,
                    deadline_name=event.get("name", "Unnamed Event"),
                    deadline_date=event_date,
                    case_name=case.get("name"),
                    deadline_type=event.get("event_type", "event"),
                    attorney_id=attorney.get("id"),
                    attorney_name=attorney.get("name"),
                )
                synced += 1

        except MyCaseAPIError as e:
            print(f"Error syncing events: {e}")

        return synced

    def sync_tasks_as_deadlines(self, days_ahead: int = 30) -> int:
        """
        Sync upcoming tasks from MyCase as deadlines.

        Args:
            days_ahead: Number of days ahead to sync

        Returns:
            Number of tasks synced
        """
        synced = 0
        today = date.today()

        try:
            # Get pending tasks
            tasks = self.client.get_all_pages(
                self.client.get_tasks,
                status="pending",
            )

            for task in tasks:
                due_date_str = task.get("due_date")
                if not due_date_str:
                    continue

                due_date = datetime.fromisoformat(
                    due_date_str.replace("Z", "+00:00")
                ).date()

                # Only sync if within range or overdue
                if due_date > today + timedelta(days=days_ahead):
                    continue

                # Get case info
                case = task.get("case") or {}
                case_id = case.get("id") if isinstance(case, dict) else case
                if not case_id:
                    continue

                # Get assignee info
                assignee = task.get("assignee") or {}

                self.db.upsert_deadline(
                    case_id=case_id,
                    deadline_name=f"Task: {task.get('name', 'Unnamed Task')}",
                    deadline_date=due_date,
                    case_name=case.get("name"),
                    deadline_type="task",
                    attorney_id=assignee.get("id"),
                    attorney_name=assignee.get("name"),
                )
                synced += 1

        except MyCaseAPIError as e:
            print(f"Error syncing tasks: {e}")

        return synced

    def get_upcoming_deadlines(
        self,
        days_ahead: int = 7,
        attorney_id: int = None,
        include_notified: bool = False,
    ) -> List[CaseDeadline]:
        """
        Get upcoming deadlines from local database.

        Args:
            days_ahead: Number of days to look ahead
            attorney_id: Filter by attorney
            include_notified: Include deadlines already notified

        Returns:
            List of CaseDeadline objects
        """
        deadlines = []
        today = date.today()

        db_deadlines = self.db.get_upcoming_deadlines(
            days_ahead=days_ahead,
            attorney_id=attorney_id,
        )

        for dl in db_deadlines:
            deadline_date = dl["deadline_date"]
            if isinstance(deadline_date, str):
                deadline_date = datetime.fromisoformat(deadline_date).date()

            if not include_notified and dl["notification_sent"]:
                continue

            days_until = (deadline_date - today).days

            deadlines.append(CaseDeadline(
                deadline_id=dl["id"],
                case_id=dl["case_id"],
                case_name=dl["case_name"] or "Unknown Case",
                case_number=None,  # Would need case lookup
                deadline_name=dl["deadline_name"],
                deadline_date=deadline_date,
                deadline_type=dl["deadline_type"] or "deadline",
                attorney_id=dl["attorney_id"],
                attorney_name=dl["attorney_name"],
                description=None,
                days_until=days_until,
                notification_sent=dl["notification_sent"],
            ))

        # Sort by date
        deadlines.sort(key=lambda x: x.deadline_date)

        return deadlines

    def get_overdue_tasks(self) -> List[OverdueTask]:
        """
        Get all overdue tasks from MyCase.

        Returns:
            List of OverdueTask objects
        """
        overdue_tasks = []
        today = date.today()

        try:
            tasks = self.client.get_all_pages(
                self.client.get_tasks,
                status="pending",
            )

            for task in tasks:
                due_date_str = task.get("due_date")
                if not due_date_str:
                    continue

                due_date = datetime.fromisoformat(
                    due_date_str.replace("Z", "+00:00")
                ).date()

                if due_date >= today:
                    continue  # Not overdue

                case = task.get("case", {})
                assignee = task.get("assignee", {})

                overdue_tasks.append(OverdueTask(
                    task_id=task.get("id"),
                    task_name=task.get("name", "Unnamed Task"),
                    case_id=case.get("id"),
                    case_name=case.get("name", "Unknown Case"),
                    due_date=due_date,
                    days_overdue=(today - due_date).days,
                    assignee_id=assignee.get("id"),
                    assignee_name=assignee.get("name", "Unassigned"),
                    status=task.get("status", "pending"),
                ))

        except MyCaseAPIError as e:
            print(f"Error fetching overdue tasks: {e}")

        # Sort by most overdue first
        overdue_tasks.sort(key=lambda x: x.days_overdue, reverse=True)

        return overdue_tasks

    def generate_deadline_notification(
        self,
        deadline: CaseDeadline,
        firm_info: Dict = None,
    ) -> Optional[str]:
        """
        Generate notification content for a deadline.

        Args:
            deadline: CaseDeadline object
            firm_info: Optional firm information

        Returns:
            Rendered notification text
        """
        context = {
            "attorney_name": deadline.attorney_name or "Attorney",
            "case_name": deadline.case_name,
            "case_number": deadline.case_number or "",
            "client_name": "",  # Would need contact lookup
            "deadline_name": deadline.deadline_name,
            "deadline_date": deadline.deadline_date,
            "days_until_due": deadline.days_until,
            "deadline_description": deadline.description,
            "related_tasks": [],  # Could be enhanced
        }

        return self.templates.render_template("attorney_deadline_reminder", context)

    def generate_overdue_alert(
        self,
        attorney_id: int,
        attorney_name: str,
        overdue_items: List[OverdueTask],
    ) -> Optional[str]:
        """
        Generate overdue alert for an attorney.

        Args:
            attorney_id: Attorney ID
            attorney_name: Attorney name
            overdue_items: List of overdue tasks

        Returns:
            Rendered alert text
        """
        items = [
            {
                "case_name": task.case_name,
                "name": task.task_name,
                "due_date": task.due_date,
                "days_overdue": task.days_overdue,
            }
            for task in overdue_items
            if task.assignee_id == attorney_id
        ]

        if not items:
            return None

        context = {
            "attorney_name": attorney_name,
            "overdue_items": items,
        }

        return self.templates.render_template("attorney_overdue_alert", context)

    def send_deadline_notifications(
        self,
        days_ahead: int = 7,
        dry_run: bool = True,
    ) -> Dict:
        """
        Send notifications for upcoming deadlines.

        Args:
            days_ahead: How many days ahead to notify
            dry_run: If True, simulate without sending

        Returns:
            Summary of notifications sent
        """
        summary = {
            "deadlines_found": 0,
            "notifications_sent": 0,
            "skipped_no_attorney": 0,
            "errors": 0,
            "details": [],
        }

        deadlines = self.get_upcoming_deadlines(days_ahead=days_ahead)
        summary["deadlines_found"] = len(deadlines)

        for deadline in deadlines:
            detail = {
                "case_name": deadline.case_name,
                "deadline_name": deadline.deadline_name,
                "deadline_date": str(deadline.deadline_date),
                "days_until": deadline.days_until,
                "attorney_name": deadline.attorney_name,
                "sent": False,
            }

            if not deadline.attorney_id:
                summary["skipped_no_attorney"] += 1
                detail["status"] = "skipped - no attorney assigned"
                summary["details"].append(detail)
                continue

            try:
                notification = self.generate_deadline_notification(deadline)

                if dry_run:
                    print(f"[DRY RUN] Would notify {deadline.attorney_name} about:")
                    print(f"  Case: {deadline.case_name}")
                    print(f"  Deadline: {deadline.deadline_name}")
                    print(f"  Due: {deadline.deadline_date} ({deadline.days_until} days)")
                    detail["sent"] = True
                    detail["status"] = "would send (dry run)"
                else:
                    # Record notification
                    self.db.record_attorney_notification(
                        attorney_id=deadline.attorney_id,
                        notification_type="deadline_reminder",
                        attorney_name=deadline.attorney_name,
                        case_id=deadline.case_id,
                        case_name=deadline.case_name,
                        deadline_id=deadline.deadline_id,
                        message=notification,
                    )

                    # Mark deadline as notified
                    if deadline.deadline_id:
                        self.db.mark_deadline_notified(deadline.deadline_id)

                    detail["sent"] = True
                    detail["status"] = "sent"

                summary["notifications_sent"] += 1

            except Exception as e:
                summary["errors"] += 1
                detail["status"] = f"error: {e}"

            summary["details"].append(detail)

        return summary

    def send_overdue_alerts(self, dry_run: bool = True) -> Dict:
        """
        Send alerts for overdue tasks.

        Args:
            dry_run: If True, simulate without sending

        Returns:
            Summary of alerts sent
        """
        summary = {
            "overdue_tasks": 0,
            "attorneys_notified": 0,
            "alerts_sent": 0,
            "errors": 0,
        }

        overdue_tasks = self.get_overdue_tasks()
        summary["overdue_tasks"] = len(overdue_tasks)

        # Group by attorney
        by_attorney: Dict[int, List[OverdueTask]] = {}
        for task in overdue_tasks:
            if task.assignee_id not in by_attorney:
                by_attorney[task.assignee_id] = []
            by_attorney[task.assignee_id].append(task)

        summary["attorneys_notified"] = len(by_attorney)

        for attorney_id, tasks in by_attorney.items():
            attorney_name = tasks[0].assignee_name if tasks else "Unknown"

            try:
                alert = self.generate_overdue_alert(attorney_id, attorney_name, tasks)

                if dry_run:
                    print(f"[DRY RUN] Would alert {attorney_name} about {len(tasks)} overdue tasks")
                    for task in tasks:
                        print(f"  - {task.task_name} ({task.days_overdue} days overdue)")
                else:
                    self.db.record_attorney_notification(
                        attorney_id=attorney_id,
                        notification_type="overdue_alert",
                        attorney_name=attorney_name,
                        message=alert,
                    )

                summary["alerts_sent"] += 1

            except Exception as e:
                summary["errors"] += 1
                print(f"Error sending alert to {attorney_name}: {e}")

        return summary

    def get_case_calendar(self, case_id: int) -> List[Dict]:
        """
        Get all upcoming dates for a specific case.

        Args:
            case_id: Case ID

        Returns:
            List of calendar items
        """
        calendar = []
        today = date.today()

        try:
            # Get events for this case
            events = self.client.get_events(
                case_id=case_id,
                start_date=datetime.combine(today, datetime.min.time()),
            )

            event_list = events.get("data", events) if isinstance(events, dict) else events

            for event in event_list:
                event_date_str = event.get("start_at") or event.get("date")
                if event_date_str:
                    event_date = datetime.fromisoformat(
                        event_date_str.replace("Z", "+00:00")
                    ).date()

                    calendar.append({
                        "type": "event",
                        "name": event.get("name"),
                        "date": event_date,
                        "days_until": (event_date - today).days,
                    })

            # Get tasks for this case
            tasks = self.client.get_tasks(case_id=case_id, status="pending")
            task_list = tasks.get("data", tasks) if isinstance(tasks, dict) else tasks

            for task in task_list:
                due_date_str = task.get("due_date")
                if due_date_str:
                    due_date = datetime.fromisoformat(
                        due_date_str.replace("Z", "+00:00")
                    ).date()

                    calendar.append({
                        "type": "task",
                        "name": task.get("name"),
                        "date": due_date,
                        "days_until": (due_date - today).days,
                    })

        except MyCaseAPIError as e:
            print(f"Error fetching case calendar: {e}")

        # Sort by date
        calendar.sort(key=lambda x: x["date"])

        return calendar


if __name__ == "__main__":
    from templates import create_default_templates

    # Ensure templates exist
    create_default_templates()

    manager = DeadlineManager()

    print("=== Deadline Manager Test ===")
    print("(Note: Requires valid API authentication)")

    try:
        # Sync events
        print("\nSyncing events from MyCase...")
        events_synced = manager.sync_events_from_mycase(days_ahead=30)
        print(f"Synced {events_synced} events")

        # Sync tasks
        print("\nSyncing tasks from MyCase...")
        tasks_synced = manager.sync_tasks_as_deadlines(days_ahead=30)
        print(f"Synced {tasks_synced} tasks")

        # Get upcoming deadlines
        print("\nUpcoming deadlines:")
        deadlines = manager.get_upcoming_deadlines(days_ahead=7)
        for dl in deadlines:
            print(f"  {dl.deadline_date}: {dl.deadline_name} ({dl.case_name})")

        # Send notifications (dry run)
        print("\nSending notifications (dry run)...")
        summary = manager.send_deadline_notifications(dry_run=True)
        print(f"Would send {summary['notifications_sent']} notifications")

    except Exception as e:
        print(f"Error: {e}")
        print("Make sure you've authenticated with: python auth.py")
