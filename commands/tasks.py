"""Task SLA tracking and legal assistant commands."""

import click
from datetime import date
from rich.console import Console
from rich.table import Table

from task_sla import TaskSLAManager

console = Console()


@click.group()
def tasks():
    """Task SLA tracking for legal assistants."""
    pass


@tasks.command("sync")
@click.option("--days", default=30, help="Days back to sync")
def tasks_sync(days: int):
    """Sync tasks from MyCase for SLA tracking."""
    manager = TaskSLAManager()

    from rich.progress import Progress, SpinnerColumn, TextColumn
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        progress.add_task("Syncing tasks...", total=None)
        count = manager.sync_tasks_from_mycase(days_back=days)

    console.print(f"[green]Synced {count} tasks[/green]")


@tasks.command("report")
@click.option("--assignee", help="Filter by assignee name")
@click.option("--days", default=7, help="Days back to report")
def tasks_report(assignee: str, days: int):
    """Generate legal assistant task report."""
    manager = TaskSLAManager()
    report = manager.generate_legal_assistant_report(assignee_name=assignee, days_back=days)
    console.print(report)


@tasks.command("overdue")
@click.option("--assignee", help="Filter by assignee name")
def tasks_overdue(assignee: str):
    """Show overdue tasks."""
    manager = TaskSLAManager()

    # Get assignee ID if name provided
    assignee_id = None
    # (Would need lookup - for now just filter by name in output)

    overdue = manager.get_overdue_tasks()

    if assignee:
        overdue = [t for t in overdue if assignee.lower() in t.assignee_name.lower()]

    if not overdue:
        console.print("[green]No overdue tasks[/green]")
        return

    table = Table(title=f"Overdue Tasks ({len(overdue)})")
    table.add_column("Task")
    table.add_column("Case")
    table.add_column("Assignee")
    table.add_column("Days Overdue", justify="right", style="red")

    for task in overdue[:20]:
        table.add_row(
            task.name[:30],
            task.case_name[:25],
            task.assignee_name[:15],
            str(abs(task.days_until_due))
        )

    console.print(table)


@tasks.command("license-deadlines")
@click.option("--days", default=7, help="Days ahead to show")
def tasks_license(days: int):
    """Show upcoming DUI/DWI license filing deadlines."""
    manager = TaskSLAManager()

    upcoming = manager.get_upcoming_license_deadlines(days_ahead=days)
    overdue = manager.get_overdue_license_filings()

    if overdue:
        table = Table(title=f"[red]OVERDUE License Filings ({len(overdue)})[/red]")
        table.add_column("Client")
        table.add_column("Type")
        table.add_column("Days Overdue", style="red")
        table.add_column("Assignee")

        for dl in overdue:
            table.add_row(
                dl.client_name[:25],
                dl.filing_type,
                str(abs(dl.days_remaining)),
                dl.assignee_name[:15]
            )
        console.print(table)

    if upcoming:
        table = Table(title=f"Upcoming License Deadlines ({len(upcoming)})")
        table.add_column("Urgent")
        table.add_column("Client")
        table.add_column("Type")
        table.add_column("Days Left", justify="right")
        table.add_column("Deadline")

        for dl in upcoming:
            urgent = "[red]!!![/red]" if dl.is_urgent else ""
            style = "red" if dl.is_urgent else ""
            table.add_row(
                urgent,
                dl.client_name[:25],
                dl.filing_type,
                str(dl.days_remaining),
                str(dl.deadline_date),
                style=style
            )
        console.print(table)
    elif not overdue:
        console.print(f"[green]No license deadlines in next {days} days[/green]")


@tasks.command("license-notify")
@click.option("--sms/--no-sms", default=False, help="Send SMS for critical deadlines")
@click.option("--slack/--no-slack", default=True, help="Send Slack notification")
@click.option("--days", default=3, help="Days threshold for critical")
def tasks_license_notify(sms: bool, slack: bool, days: int):
    """Send notifications for critical license deadlines (within 3 days or overdue)."""
    from notifications import NotificationManager, NotificationPriority

    manager = TaskSLAManager()
    notifier = NotificationManager()

    # Get critical deadlines (within threshold) and overdue
    upcoming = manager.get_upcoming_license_deadlines(days_ahead=days)
    overdue = manager.get_overdue_license_filings()

    critical = [d for d in upcoming if d.is_urgent or d.days_remaining <= days]
    all_critical = overdue + critical

    if not all_critical:
        console.print(f"[green]No critical license deadlines (within {days} days)[/green]")
        return

    console.print(f"[yellow]Found {len(all_critical)} critical license deadlines[/yellow]")

    # Send Slack notification
    if slack:
        summary = {
            "total": len(all_critical),
            "overdue": len(overdue),
            "critical": len(critical),
            "cases": [
                {
                    "client": d.client_name,
                    "type": d.filing_type,
                    "days": d.days_remaining,
                    "assignee": d.assignee_name,
                }
                for d in all_critical[:10]
            ],
        }
        success = notifier.send_slack_report("license_deadline", summary)
        if success:
            console.print("[green]Slack notification sent[/green]")
        else:
            console.print("[red]Failed to send Slack notification[/red]")

    # Send SMS for each critical deadline
    if sms:
        # Get staff phone numbers from config
        sms_config = notifier._load_sms_config()
        staff_numbers = sms_config.get("staff_numbers", {})

        if not staff_numbers:
            console.print("[yellow]No staff SMS numbers configured[/yellow]")
            console.print("Add to data/notifications_config.json:")
            console.print('  "sms": {"staff_numbers": {"Alison": "+1234567890"}}')
            return

        sent_count = 0
        for deadline in all_critical:
            # Find assignee's number
            assignee = deadline.assignee_name
            number = None
            for name, phone in staff_numbers.items():
                if name.lower() in assignee.lower():
                    number = phone
                    break

            if not number:
                console.print(f"[yellow]No phone for {assignee}[/yellow]")
                continue

            # Build message
            if deadline.days_remaining < 0:
                msg = f"OVERDUE: {deadline.filing_type} for {deadline.client_name} was due {abs(deadline.days_remaining)} days ago!"
            else:
                msg = f"URGENT: {deadline.filing_type} for {deadline.client_name} due in {deadline.days_remaining} days ({deadline.deadline_date})"

            success = notifier.send_sms(
                to_number=number,
                message=msg,
                priority=NotificationPriority.CRITICAL
            )
            if success:
                sent_count += 1
                console.print(f"[green]SMS sent to {assignee}[/green]")

        console.print(f"[bold]Sent {sent_count} SMS notifications[/bold]")


@tasks.command("ops-huddle")
def tasks_ops_huddle():
    """Generate paralegal ops huddle report (Tiffany SOP)."""
    manager = TaskSLAManager()
    report = manager.generate_ops_huddle_report()
    console.print(report)


@tasks.command("casenet")
def tasks_casenet():
    """Show Case.net monitoring checklist."""
    manager = TaskSLAManager()

    checklist = manager.get_casenet_checklist()
    newly_charged = manager.get_newly_charged_cases()

    if checklist:
        table = Table(title=f"Case.net Checks Needed ({len(checklist)})")
        table.add_column("Case")
        table.add_column("Client")
        table.add_column("Last Checked")

        for case in checklist[:20]:
            table.add_row(
                (case['case_name'] or str(case['case_id']))[:30],
                (case['client_name'] or 'N/A')[:25],
                case.get('last_checked', 'Never')
            )
        console.print(table)

    if newly_charged:
        table = Table(title=f"[yellow]Newly Charged - Needs Entry/Discovery ({len(newly_charged)})[/yellow]")
        table.add_column("Case")
        table.add_column("Entry Filed")
        table.add_column("Discovery Requested")

        for case in newly_charged[:10]:
            entry = "[green]Yes[/green]" if case.get('entry_filed') else "[red]No[/red]"
            discovery = "[green]Yes[/green]" if case.get('discovery_requested') else "[red]No[/red]"
            table.add_row(
                (case['case_name'] or str(case['case_id']))[:30],
                entry,
                discovery
            )
        console.print(table)
