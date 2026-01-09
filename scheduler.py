"""
Scheduled Automation Module

Handles automated execution of:
- Daily tasks: dunning cycles, compliance checks, deadline notifications
- Weekly tasks: SOP reports for each role
- Cron job management and installation
"""
import os
import sys
import json
import subprocess
from datetime import datetime, date, time, timedelta
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass, field
from pathlib import Path
from enum import Enum

from config import BASE_DIR, DATA_DIR, LOGS_DIR


class TaskFrequency(Enum):
    """Frequency of scheduled tasks."""
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class DayOfWeek(Enum):
    """Days of the week for weekly tasks."""
    MONDAY = 0
    TUESDAY = 1
    WEDNESDAY = 2
    THURSDAY = 3
    FRIDAY = 4
    SATURDAY = 5
    SUNDAY = 6


@dataclass
class ScheduledTask:
    """Definition of a scheduled task."""
    name: str
    description: str
    frequency: TaskFrequency
    command: str  # CLI command to run
    run_at: time = field(default_factory=lambda: time(8, 0))  # Default 8:00 AM
    day_of_week: Optional[DayOfWeek] = None  # For weekly tasks
    day_of_month: Optional[int] = None  # For monthly tasks
    enabled: bool = True
    notify_on_failure: bool = True
    owner: Optional[str] = None  # Staff member this report is for


# ============================================================================
# Task Definitions
# ============================================================================

DAILY_TASKS = [
    ScheduledTask(
        name="sync_data",
        description="Sync all data from MyCase (invoices, tasks, events)",
        frequency=TaskFrequency.DAILY,
        command="run --sync --no-collections --no-deadlines --dry-run",
        run_at=time(5, 0),  # 5:00 AM - before events report at 6 AM
    ),
    ScheduledTask(
        name="events_report",
        description="Send daily upcoming events report to managing partner",
        frequency=TaskFrequency.DAILY,
        command="notify events-report john@jcsattorney.com --days 7 --cc marc.stein@gmail.com",
        run_at=time(6, 0),  # 6:00 AM - weekdays only (cron handles day filter)
        owner="John Schleiffarth",
    ),
    ScheduledTask(
        name="payment_plan_compliance",
        description="Run payment plan compliance check",
        frequency=TaskFrequency.DAILY,
        command="plans compliance",
        run_at=time(7, 0),
        owner="Melissa Scarlett",
    ),
    ScheduledTask(
        name="dunning_cycle",
        description="Run dunning cycle for overdue invoices",
        frequency=TaskFrequency.DAILY,
        command="collections dunning --dry-run",  # Start with dry-run, can change to --execute
        run_at=time(7, 30),
        owner="Melissa Scarlett",
    ),
    ScheduledTask(
        name="deadline_notifications",
        description="Send deadline notifications to attorneys",
        frequency=TaskFrequency.DAILY,
        command="deadlines notify --days 7 --dry-run",
        run_at=time(8, 0),
    ),
    ScheduledTask(
        name="overdue_task_alerts",
        description="Send overdue task alerts",
        frequency=TaskFrequency.DAILY,
        command="deadlines overdue --notify --dry-run",
        run_at=time(8, 30),
    ),
    ScheduledTask(
        name="license_deadline_check",
        description="Check DUI/DWI license filing deadlines",
        frequency=TaskFrequency.DAILY,
        command="tasks license-deadlines --days 7",
        run_at=time(8, 0),
        owner="Alison Ehrhard",
    ),
    ScheduledTask(
        name="quality_audit",
        description="Run quality audit on recent cases",
        frequency=TaskFrequency.DAILY,
        command="quality audit --days 1",
        run_at=time(9, 0),
        owner="Tiffany Willis",
    ),
]

WEEKLY_TASKS = [
    # Monday reports
    ScheduledTask(
        name="melissa_weekly_ar",
        description="Melissa's Weekly A/R Report",
        frequency=TaskFrequency.WEEKLY,
        command="sop melissa --weekly",
        run_at=time(9, 0),
        day_of_week=DayOfWeek.MONDAY,
        owner="Melissa Scarlett",
    ),
    ScheduledTask(
        name="ty_weekly_intake",
        description="Ty's Weekly Intake Report (Due Monday 10am)",
        frequency=TaskFrequency.WEEKLY,
        command="sop ty --weekly",
        run_at=time(9, 30),
        day_of_week=DayOfWeek.MONDAY,
        owner="Ty Christian",
    ),
    ScheduledTask(
        name="ar_huddle_report",
        description="A/R Huddle Report (Melissa + Tiffany + John)",
        frequency=TaskFrequency.WEEKLY,
        command="kpi huddle",
        run_at=time(9, 0),
        day_of_week=DayOfWeek.WEDNESDAY,
        owner="Melissa Scarlett",
    ),
    # Daily ops huddle prep (runs every weekday morning)
    ScheduledTask(
        name="ops_huddle_prep",
        description="Paralegal Ops Huddle Report",
        frequency=TaskFrequency.DAILY,
        command="tasks ops-huddle",
        run_at=time(7, 45),
        owner="Tiffany Willis",
    ),
    # Friday reports
    ScheduledTask(
        name="weekly_quality_summary",
        description="Weekly Quality Summary Report",
        frequency=TaskFrequency.WEEKLY,
        command="quality summary --days 7",
        run_at=time(16, 0),  # 4:00 PM Friday
        day_of_week=DayOfWeek.FRIDAY,
        owner="Tiffany Willis",
    ),
    ScheduledTask(
        name="noiw_pipeline_review",
        description="NOIW Pipeline Review",
        frequency=TaskFrequency.WEEKLY,
        command="plans noiw-pipeline",
        run_at=time(14, 0),  # 2:00 PM Friday
        day_of_week=DayOfWeek.FRIDAY,
        owner="Melissa Scarlett",
    ),
]

MONTHLY_TASKS = [
    ScheduledTask(
        name="monthly_intake_review",
        description="Monthly Intake Review Report",
        frequency=TaskFrequency.MONTHLY,
        command="sop ty --monthly",
        run_at=time(10, 0),
        day_of_month=1,  # First of the month
        owner="Ty Christian",
    ),
    ScheduledTask(
        name="monthly_collections_report",
        description="Monthly Collections Report",
        frequency=TaskFrequency.MONTHLY,
        command="collections report --export",
        run_at=time(10, 0),
        day_of_month=1,
        owner="Melissa Scarlett",
    ),
]

ALL_TASKS = DAILY_TASKS + WEEKLY_TASKS + MONTHLY_TASKS


# ============================================================================
# Scheduler Class
# ============================================================================

class Scheduler:
    """
    Manages scheduled task execution and cron job installation.
    """

    def __init__(self):
        self.tasks = {task.name: task for task in ALL_TASKS}
        self.config_file = DATA_DIR / "scheduler_config.json"
        self.log_file = LOGS_DIR / "scheduler.log"
        self.last_run_file = DATA_DIR / "scheduler_last_run.json"

    def _load_config(self) -> Dict:
        """Load scheduler configuration."""
        if self.config_file.exists():
            with open(self.config_file) as f:
                return json.load(f)
        return {"enabled_tasks": list(self.tasks.keys()), "dry_run": True}

    def _save_config(self, config: Dict):
        """Save scheduler configuration."""
        with open(self.config_file, "w") as f:
            json.dump(config, f, indent=2)

    def _load_last_run(self) -> Dict:
        """Load last run timestamps."""
        if self.last_run_file.exists():
            with open(self.last_run_file) as f:
                return json.load(f)
        return {}

    def _save_last_run(self, last_run: Dict):
        """Save last run timestamps."""
        with open(self.last_run_file, "w") as f:
            json.dump(last_run, f, indent=2)

    def _log(self, message: str):
        """Log a message to the scheduler log."""
        timestamp = datetime.now().isoformat()
        log_entry = f"[{timestamp}] {message}\n"

        with open(self.log_file, "a") as f:
            f.write(log_entry)

        print(log_entry.strip())

    def get_task(self, name: str) -> Optional[ScheduledTask]:
        """Get a task by name."""
        return self.tasks.get(name)

    def list_tasks(self, frequency: Optional[TaskFrequency] = None) -> List[ScheduledTask]:
        """List all scheduled tasks."""
        tasks = list(self.tasks.values())
        if frequency:
            tasks = [t for t in tasks if t.frequency == frequency]
        return sorted(tasks, key=lambda t: (t.frequency.value, t.run_at))

    def enable_task(self, name: str) -> bool:
        """Enable a task."""
        config = self._load_config()
        if name not in config["enabled_tasks"]:
            config["enabled_tasks"].append(name)
            self._save_config(config)
        return True

    def disable_task(self, name: str) -> bool:
        """Disable a task."""
        config = self._load_config()
        if name in config["enabled_tasks"]:
            config["enabled_tasks"].remove(name)
            self._save_config(config)
        return True

    def is_task_enabled(self, name: str) -> bool:
        """Check if a task is enabled."""
        config = self._load_config()
        return name in config.get("enabled_tasks", [])

    def should_run_task(self, task: ScheduledTask, now: datetime = None) -> bool:
        """
        Determine if a task should run now.

        Args:
            task: The task to check
            now: Current datetime (defaults to now)

        Returns:
            True if the task should run
        """
        if now is None:
            now = datetime.now()

        if not self.is_task_enabled(task.name):
            return False

        # Check last run
        last_run = self._load_last_run()
        last_run_str = last_run.get(task.name)

        if last_run_str:
            last_run_dt = datetime.fromisoformat(last_run_str)

            # Don't run more than once per period
            if task.frequency == TaskFrequency.DAILY:
                if last_run_dt.date() >= now.date():
                    return False
            elif task.frequency == TaskFrequency.WEEKLY:
                # Check if already run this week
                week_start = now.date() - timedelta(days=now.weekday())
                if last_run_dt.date() >= week_start:
                    return False
            elif task.frequency == TaskFrequency.MONTHLY:
                # Check if already run this month
                if (last_run_dt.year == now.year and
                    last_run_dt.month == now.month):
                    return False

        # Check day of week for weekly tasks
        if task.frequency == TaskFrequency.WEEKLY:
            if task.day_of_week and now.weekday() != task.day_of_week.value:
                return False

        # Check day of month for monthly tasks
        if task.frequency == TaskFrequency.MONTHLY:
            if task.day_of_month and now.day != task.day_of_month:
                return False

        # Check if we're past the run time
        if now.time() >= task.run_at:
            return True

        return False

    def run_task(self, task: ScheduledTask, force: bool = False) -> Dict:
        """
        Run a scheduled task.

        Args:
            task: The task to run
            force: Run even if not scheduled

        Returns:
            Result dictionary
        """
        result = {
            "task": task.name,
            "success": False,
            "started_at": datetime.now().isoformat(),
            "finished_at": None,
            "output": "",
            "error": None,
        }

        if not force and not self.should_run_task(task):
            result["error"] = "Task not scheduled to run now"
            return result

        self._log(f"Starting task: {task.name} - {task.description}")

        try:
            # Build the command
            python_path = sys.executable
            agent_path = BASE_DIR / "agent.py"
            full_command = f"{python_path} {agent_path} {task.command}"

            # Run the command
            process = subprocess.run(
                full_command,
                shell=True,
                capture_output=True,
                text=True,
                cwd=str(BASE_DIR),
                timeout=300,  # 5 minute timeout
            )

            result["output"] = process.stdout
            if process.stderr:
                result["output"] += f"\n\nSTDERR:\n{process.stderr}"

            result["success"] = process.returncode == 0

            if not result["success"]:
                result["error"] = f"Command exited with code {process.returncode}"

        except subprocess.TimeoutExpired:
            result["error"] = "Task timed out after 5 minutes"
            self._log(f"Task {task.name} timed out")
        except Exception as e:
            result["error"] = str(e)
            self._log(f"Task {task.name} failed: {e}")

        result["finished_at"] = datetime.now().isoformat()

        # Record last run
        last_run = self._load_last_run()
        last_run[task.name] = result["started_at"]
        self._save_last_run(last_run)

        status = "SUCCESS" if result["success"] else "FAILED"
        self._log(f"Task {task.name} finished: {status}")

        return result

    def run_due_tasks(self, frequency: Optional[TaskFrequency] = None) -> List[Dict]:
        """
        Run all tasks that are due.

        Args:
            frequency: Only run tasks of this frequency

        Returns:
            List of result dictionaries
        """
        results = []
        now = datetime.now()

        for task in self.list_tasks(frequency):
            if self.should_run_task(task, now):
                result = self.run_task(task, force=True)
                results.append(result)

        return results

    def run_all_daily(self) -> List[Dict]:
        """Run all daily tasks (for cron)."""
        return self.run_due_tasks(TaskFrequency.DAILY)

    def run_all_weekly(self) -> List[Dict]:
        """Run all weekly tasks that are due today (for cron)."""
        return self.run_due_tasks(TaskFrequency.WEEKLY)

    def generate_cron_entries(self) -> str:
        """
        Generate crontab entries for all scheduled tasks.

        Returns:
            Crontab entry string
        """
        python_path = sys.executable
        scheduler_path = BASE_DIR / "scheduler.py"

        entries = [
            "# MyCase Automation Scheduler",
            "# Generated by scheduler.py",
            f"# Python: {python_path}",
            f"# Base directory: {BASE_DIR}",
            "",
            "# Run scheduler check every 15 minutes during business hours",
            f"*/15 6-18 * * 1-5 cd {BASE_DIR} && {python_path} {scheduler_path} run-due >> {LOGS_DIR}/cron.log 2>&1",
            "",
            "# Daily data sync at 6:00 AM",
            f"0 6 * * * cd {BASE_DIR} && {python_path} {scheduler_path} run-task sync_data >> {LOGS_DIR}/cron.log 2>&1",
            "",
        ]

        return "\n".join(entries)

    def install_cron(self, dry_run: bool = True) -> str:
        """
        Install cron entries for the scheduler.

        Args:
            dry_run: If True, show what would be installed without installing

        Returns:
            Status message
        """
        entries = self.generate_cron_entries()

        if dry_run:
            return f"Would install the following cron entries:\n\n{entries}"

        try:
            # Get existing crontab
            result = subprocess.run(
                ["crontab", "-l"],
                capture_output=True,
                text=True,
            )
            existing = result.stdout if result.returncode == 0 else ""

            # Check if already installed
            if "MyCase Automation Scheduler" in existing:
                return "Cron entries already installed. Remove first with 'scheduler cron remove'"

            # Append new entries
            new_crontab = existing + "\n" + entries

            # Install
            process = subprocess.Popen(
                ["crontab", "-"],
                stdin=subprocess.PIPE,
                text=True,
            )
            process.communicate(input=new_crontab)

            if process.returncode == 0:
                return "Cron entries installed successfully"
            else:
                return f"Failed to install cron entries (exit code {process.returncode})"

        except Exception as e:
            return f"Error installing cron: {e}"

    def remove_cron(self) -> str:
        """
        Remove scheduler cron entries.

        Returns:
            Status message
        """
        try:
            # Get existing crontab
            result = subprocess.run(
                ["crontab", "-l"],
                capture_output=True,
                text=True,
            )

            if result.returncode != 0:
                return "No crontab found"

            existing = result.stdout

            # Remove our entries
            lines = existing.split("\n")
            new_lines = []
            skip = False

            for line in lines:
                if "# MyCase Automation Scheduler" in line:
                    skip = True
                    continue
                if skip and line.startswith("#"):
                    continue
                if skip and not line.strip():
                    skip = False
                    continue
                if skip and "scheduler.py" in line:
                    continue
                skip = False
                new_lines.append(line)

            new_crontab = "\n".join(new_lines)

            # Install cleaned crontab
            process = subprocess.Popen(
                ["crontab", "-"],
                stdin=subprocess.PIPE,
                text=True,
            )
            process.communicate(input=new_crontab)

            return "Cron entries removed"

        except Exception as e:
            return f"Error removing cron: {e}"

    def get_status(self) -> Dict:
        """Get scheduler status including last run times."""
        config = self._load_config()
        last_run = self._load_last_run()

        status = {
            "enabled_tasks": len(config.get("enabled_tasks", [])),
            "total_tasks": len(self.tasks),
            "dry_run_mode": config.get("dry_run", True),
            "tasks": [],
        }

        for task in self.list_tasks():
            task_status = {
                "name": task.name,
                "description": task.description,
                "frequency": task.frequency.value,
                "run_at": task.run_at.strftime("%H:%M"),
                "enabled": self.is_task_enabled(task.name),
                "last_run": last_run.get(task.name, "Never"),
                "owner": task.owner,
            }

            if task.day_of_week:
                task_status["day_of_week"] = task.day_of_week.name
            if task.day_of_month:
                task_status["day_of_month"] = task.day_of_month

            status["tasks"].append(task_status)

        return status


# ============================================================================
# CLI Entry Points (for cron/direct execution)
# ============================================================================

def main():
    """CLI for scheduler when run directly."""
    import argparse

    parser = argparse.ArgumentParser(description="MyCase Scheduler")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # run-due: Run all due tasks
    subparsers.add_parser("run-due", help="Run all tasks that are due now")

    # run-task: Run a specific task
    run_task_parser = subparsers.add_parser("run-task", help="Run a specific task")
    run_task_parser.add_argument("task_name", help="Name of the task to run")
    run_task_parser.add_argument("--force", action="store_true", help="Force run even if not scheduled")

    # status: Show scheduler status
    subparsers.add_parser("status", help="Show scheduler status")

    # list: List all tasks
    list_parser = subparsers.add_parser("list", help="List all scheduled tasks")
    list_parser.add_argument("--frequency", choices=["daily", "weekly", "monthly"])

    args = parser.parse_args()
    scheduler = Scheduler()

    if args.command == "run-due":
        results = scheduler.run_due_tasks()
        for result in results:
            status = "OK" if result["success"] else "FAIL"
            print(f"[{status}] {result['task']}")
            if result["error"]:
                print(f"  Error: {result['error']}")

    elif args.command == "run-task":
        task = scheduler.get_task(args.task_name)
        if not task:
            print(f"Unknown task: {args.task_name}")
            sys.exit(1)
        result = scheduler.run_task(task, force=args.force)
        print(result["output"])
        if result["error"]:
            print(f"Error: {result['error']}")
            sys.exit(1)

    elif args.command == "status":
        status = scheduler.get_status()
        print(f"Enabled: {status['enabled_tasks']}/{status['total_tasks']} tasks")
        print(f"Dry Run Mode: {status['dry_run_mode']}")
        print("\nTasks:")
        for task in status["tasks"]:
            enabled = "ON" if task["enabled"] else "OFF"
            print(f"  [{enabled}] {task['name']} ({task['frequency']} @ {task['run_at']})")
            print(f"        Last run: {task['last_run']}")

    elif args.command == "list":
        freq = TaskFrequency(args.frequency) if args.frequency else None
        tasks = scheduler.list_tasks(freq)
        for task in tasks:
            print(f"{task.name}: {task.description}")
            print(f"  Frequency: {task.frequency.value} @ {task.run_at}")
            if task.owner:
                print(f"  Owner: {task.owner}")
            print()

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
