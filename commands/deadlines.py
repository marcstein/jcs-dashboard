"""
Deadline Tracking Commands

Commands for syncing, listing, and managing case deadlines and overdue tasks.
"""
from typing import Optional

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from deadlines import DeadlineManager


console = Console()


@click.group()
def deadlines():
    """Deadline tracking and notifications."""
    pass


@deadlines.command("sync")
@click.option("--days", default=30, help="Days ahead to sync")
def deadlines_sync(days: int):
    """Sync deadlines from MyCase."""
    manager = DeadlineManager()

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Syncing events...", total=None)
        events = manager.sync_events_from_mycase(days_ahead=days)

        progress.update(task, description="Syncing tasks...")
        tasks = manager.sync_tasks_as_deadlines(days_ahead=days)

    console.print(f"\n[green]Synced {events} events and {tasks} tasks[/green]")


@deadlines.command("list")
@click.option("--days", default=7, help="Days ahead to show")
def deadlines_list(days: int):
    """List upcoming deadlines."""
    manager = DeadlineManager()

    deadlines = manager.get_upcoming_deadlines(days_ahead=days, include_notified=True)

    if not deadlines:
        console.print(f"[yellow]No deadlines in the next {days} days[/yellow]")
        return

    table = Table(title=f"Upcoming Deadlines (Next {days} Days)")
    table.add_column("Date", style="cyan")
    table.add_column("Days", justify="right")
    table.add_column("Case")
    table.add_column("Deadline")
    table.add_column("Attorney")
    table.add_column("Notified")

    for dl in deadlines:
        style = "red" if dl.days_until <= 1 else ("yellow" if dl.days_until <= 3 else "")
        table.add_row(
            str(dl.deadline_date),
            str(dl.days_until),
            dl.case_name[:25],
            dl.deadline_name[:25],
            dl.attorney_name or "N/A",
            "Yes" if dl.notification_sent else "No",
            style=style
        )

    console.print(table)


@deadlines.command("notify")
@click.option("--days", default=7, help="Days ahead to notify")
@click.option("--dry-run/--execute", default=True, help="Dry run or actually send")
def deadlines_notify(days: int, dry_run: bool):
    """Send deadline notifications to attorneys."""
    manager = DeadlineManager()

    mode = "[yellow]DRY RUN[/yellow]" if dry_run else "[red]LIVE[/red]"
    console.print(f"\nSending notifications ({mode})...\n")

    summary = manager.send_deadline_notifications(days_ahead=days, dry_run=dry_run)

    console.print(Panel.fit(
        f"[bold]Notification Summary[/bold]\n\n"
        f"Deadlines Found: {summary['deadlines_found']}\n"
        f"Notifications Sent: {summary['notifications_sent']}\n"
        f"Skipped (no attorney): {summary['skipped_no_attorney']}\n"
        f"Errors: {summary['errors']}",
        title="Summary"
    ))


@deadlines.command("overdue")
@click.option("--notify/--no-notify", default=False, help="Send overdue alerts")
@click.option("--dry-run/--execute", default=True, help="Dry run or actually send")
def deadlines_overdue(notify: bool, dry_run: bool):
    """List or notify about overdue tasks."""
    manager = DeadlineManager()

    overdue = manager.get_overdue_tasks()

    if not overdue:
        console.print("[green]No overdue tasks![/green]")
        return

    table = Table(title="Overdue Tasks")
    table.add_column("Days", justify="right", style="red")
    table.add_column("Task")
    table.add_column("Case")
    table.add_column("Assignee")
    table.add_column("Due Date")

    for task in overdue[:20]:
        table.add_row(
            str(task.days_overdue),
            task.task_name[:30],
            task.case_name[:25],
            task.assignee_name,
            str(task.due_date)
        )

    console.print(table)

    if notify:
        mode = "[yellow]DRY RUN[/yellow]" if dry_run else "[red]LIVE[/red]"
        console.print(f"\nSending overdue alerts ({mode})...")
        summary = manager.send_overdue_alerts(dry_run=dry_run)
        console.print(f"Sent {summary['alerts_sent']} alerts to {summary['attorneys_notified']} attorneys")
