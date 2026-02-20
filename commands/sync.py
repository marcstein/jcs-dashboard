"""Data sync and batch run commands."""
import sys
from datetime import datetime, date

import click
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn

from auth import MyCaseAuth
from sync import get_sync_manager
from dunning import CollectionsManager
from deadlines import DeadlineManager
from analytics import AnalyticsManager
from db.cache import exclude_staff, include_staff, get_excluded_staff, get_excluded_staff_ids

console = Console()


@click.command("sync")
@click.option("--force", is_flag=True, help="Force full sync even if cache is fresh")
@click.option("--entity", "-e", multiple=True, help="Sync specific entities only")
def sync_data(force: bool, entity: tuple):
    """Sync all data from MyCase API to local cache.

    This performs a full sync using SyncManager which updates the
    sync_metadata table and is displayed on the dashboard.
    """
    console.print("\n[bold]Syncing MyCase Data to Cache[/bold]\n")

    # Check auth
    auth_manager = MyCaseAuth()
    if not auth_manager.is_authenticated():
        console.print("[red]Not authenticated. Run 'auth login' first.[/red]")
        sys.exit(1)

    manager = get_sync_manager()

    entities = list(entity) if entity else None
    results = manager.sync_all(force_full=force, entities=entities)

    # Display summary
    console.print("\n[bold]Sync Complete[/bold]")
    table = Table(title="Sync Results")
    table.add_column("Entity")
    table.add_column("New", justify="right")
    table.add_column("Updated", justify="right")
    table.add_column("Unchanged", justify="right")
    table.add_column("Duration", justify="right")

    total_new = 0
    total_updated = 0
    for entity_type, result in results.items():
        table.add_row(
            entity_type,
            str(result.inserted),
            str(result.updated),
            str(result.unchanged),
            f"{result.duration_seconds:.1f}s"
        )
        total_new += result.inserted
        total_updated += result.updated

    console.print(table)
    console.print(f"\n[green]Total: {total_new} new, {total_updated} updated[/green]")


@click.command("run")
@click.option("--collections/--no-collections", default=True, help="Run collections")
@click.option("--deadlines/--no-deadlines", default=True, help="Run deadline checks")
@click.option("--sync/--no-sync", default=True, help="Sync data first")
@click.option("--dry-run/--execute", default=True, help="Dry run or execute")
def run_all(collections: bool, deadlines: bool, sync: bool, dry_run: bool):
    """Run all automation tasks."""
    mode = "[yellow]DRY RUN[/yellow]" if dry_run else "[red]LIVE[/red]"
    console.print(f"\n[bold]Running MyCase Automation ({mode})[/bold]\n")

    # Check auth
    auth_manager = MyCaseAuth()
    if not auth_manager.is_authenticated():
        console.print("[red]Not authenticated. Run 'auth login' first.[/red]")
        sys.exit(1)

    # Sync data
    if sync:
        console.print("[bold]Syncing data...[/bold]")

        coll_manager = CollectionsManager()
        console.print("  Syncing payments...")
        payments = coll_manager.sync_payments()
        console.print(f"  Synced {payments} payments")

        dl_manager = DeadlineManager()
        console.print("  Syncing events and tasks...")
        events = dl_manager.sync_events_from_mycase()
        tasks = dl_manager.sync_tasks_as_deadlines()
        console.print(f"  Synced {events} events, {tasks} tasks")

        analytics_manager = AnalyticsManager()
        console.print("  Syncing invoice data...")
        invoices = analytics_manager.sync_invoice_data()
        console.print(f"  Synced {invoices} invoices")

    # Run collections
    if collections:
        console.print("\n[bold]Running Collections/Dunning...[/bold]")
        coll_manager = CollectionsManager()

        try:
            from api_client import get_client
            client = get_client()
            firm_info = client.get_firm()
        except Exception:
            firm_info = {}

        summary = coll_manager.run_dunning_cycle(dry_run=dry_run, firm_info=firm_info)
        console.print(f"  Overdue invoices: {summary['total_overdue']}")
        console.print(f"  Notices sent: {summary['notices_sent']}")

    # Run deadline notifications
    if deadlines:
        console.print("\n[bold]Running Deadline Notifications...[/bold]")
        dl_manager = DeadlineManager()

        summary = dl_manager.send_deadline_notifications(days_ahead=7, dry_run=dry_run)
        console.print(f"  Upcoming deadlines: {summary['deadlines_found']}")
        console.print(f"  Notifications sent: {summary['notifications_sent']}")

        overdue_summary = dl_manager.send_overdue_alerts(dry_run=dry_run)
        console.print(f"  Overdue alerts sent: {overdue_summary['alerts_sent']}")

    console.print("\n[green]Automation complete![/green]")


# ============================================================
# Staff Exclusion Commands
# ============================================================

@click.group("staff")
def staff_group():
    """Manage staff exclusions from sync."""
    pass


@staff_group.command("exclude")
@click.argument("staff_id", type=int)
@click.option("--name", "-n", default=None, help="Staff member name (for reference)")
@click.option("--reason", "-r", default="Manually removed", help="Reason for exclusion")
@click.option("--firm-id", default=None, help="Firm ID (auto-detected if not provided)")
def exclude_staff_cmd(staff_id: int, name: str, reason: str, firm_id: str):
    """Exclude a staff member from future syncs.

    Example: python agent.py staff exclude 12345 --name "John Doe" --reason "No longer with firm"
    """
    if not firm_id:
        firm_id = _detect_firm_id()
    exclude_staff(firm_id, staff_id, staff_name=name, reason=reason)
    console.print(f"[green]Excluded staff ID {staff_id} ({name or 'unknown'}) from sync[/green]")


@staff_group.command("include")
@click.argument("staff_id", type=int)
@click.option("--firm-id", default=None, help="Firm ID (auto-detected if not provided)")
def include_staff_cmd(staff_id: int, firm_id: str):
    """Re-include a previously excluded staff member in syncs.

    Example: python agent.py staff include 12345
    """
    if not firm_id:
        firm_id = _detect_firm_id()
    include_staff(firm_id, staff_id)
    console.print(f"[green]Re-included staff ID {staff_id} in sync[/green]")


@staff_group.command("excluded")
@click.option("--firm-id", default=None, help="Firm ID (auto-detected if not provided)")
def list_excluded_cmd(firm_id: str):
    """List all excluded staff members."""
    if not firm_id:
        firm_id = _detect_firm_id()
    excluded = get_excluded_staff(firm_id)

    if not excluded:
        console.print("[dim]No staff members are currently excluded from sync.[/dim]")
        return

    table = Table(title="Excluded Staff Members")
    table.add_column("Staff ID", justify="right")
    table.add_column("Name")
    table.add_column("Reason")
    table.add_column("Excluded At")

    for row in excluded:
        table.add_row(
            str(row.get("staff_id", "")),
            row.get("staff_name", "") or "—",
            row.get("reason", "") or "—",
            str(row.get("excluded_at", ""))[:19],
        )

    console.print(table)


def _detect_firm_id() -> str:
    """Auto-detect firm_id from cached_cases."""
    from db.connection import get_connection
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT DISTINCT firm_id FROM cached_cases LIMIT 1")
        row = cur.fetchone()
        if row:
            return row[0] if isinstance(row, tuple) else row['firm_id']
    console.print("[red]Could not detect firm_id. Use --firm-id flag.[/red]")
    sys.exit(1)
