#!/usr/bin/env python3
"""
MyCase Automation Agent

Main CLI interface for the MyCase automation system.
Provides commands for:
- Authentication
- Collections/dunning automation
- Deadline tracking and notifications
- Analytics and reporting
- Scheduled automation
"""
import sys
import json
from datetime import datetime, date
from typing import Optional

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from config import (
    CLIENT_ID,
    CLIENT_SECRET,
    DUNNING_INTERVALS,
    DATA_DIR,
)
from auth import MyCaseAuth
from api_client import MyCaseClient, get_client, MyCaseAPIError
from templates import TemplateManager, create_default_templates
from database import Database, get_db
from dunning import CollectionsManager
from deadlines import DeadlineManager
from analytics import AnalyticsManager, print_executive_summary
from kpi_tracker import KPITracker
from payment_plans import PaymentPlanManager
from intake_automation import IntakeManager
from task_sla import TaskSLAManager
from case_quality import CaseQualityManager


console = Console()


# ============================================================================
# CLI Group
# ============================================================================

@click.group()
@click.version_option(version="1.0.0")
def cli():
    """
    MyCase Automation Agent

    Automate client notices, collections, deadline tracking, and analytics
    for your law firm using the MyCase API.
    """
    pass


# ============================================================================
# Authentication Commands
# ============================================================================

@cli.group()
def auth():
    """Authentication commands."""
    pass


@auth.command("login")
def auth_login():
    """Authenticate with MyCase via OAuth."""
    auth_manager = MyCaseAuth()

    if auth_manager.is_authenticated():
        console.print("[green]Already authenticated![/green]")
        console.print(f"Firm UUID: {auth_manager.get_firm_uuid()}")

        if click.confirm("Re-authenticate?"):
            auth_manager.storage.clear()
        else:
            return

    console.print("\n[bold]Starting OAuth authorization flow...[/bold]")
    console.print("A browser window will open for you to authorize access.\n")

    try:
        tokens = auth_manager.authorize_interactive()
        console.print("\n[green]Authentication successful![/green]")
        console.print(f"Firm UUID: {tokens.get('firm_uuid')}")
        console.print(f"Scopes: {tokens.get('scope')}")
        console.print(f"Token expires in: {tokens.get('expires_in', 0) // 3600} hours")
    except Exception as e:
        console.print(f"\n[red]Authentication failed: {e}[/red]")
        sys.exit(1)


@auth.command("status")
def auth_status():
    """Check authentication status."""
    auth_manager = MyCaseAuth()

    if auth_manager.is_authenticated():
        tokens = auth_manager.storage.load()
        console.print("[green]Authenticated[/green]")
        console.print(f"Firm UUID: {tokens.get('firm_uuid')}")
        console.print(f"Expires at: {tokens.get('expires_at')}")
    else:
        console.print("[yellow]Not authenticated[/yellow]")
        console.print("Run: mycase-agent auth login")


@auth.command("logout")
def auth_logout():
    """Clear stored authentication tokens."""
    auth_manager = MyCaseAuth()
    auth_manager.storage.clear()
    console.print("[green]Logged out successfully[/green]")


# ============================================================================
# Collections Commands
# ============================================================================

@cli.group()
def collections():
    """Collections and dunning automation."""
    pass


@collections.command("report")
@click.option("--json-output", is_flag=True, help="Output as JSON")
@click.option("--export", is_flag=True, help="Export to CSV and Markdown files")
def collections_report(json_output: bool, export: bool):
    """Generate a collections aging report."""
    import csv

    manager = CollectionsManager()

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        progress.add_task("Fetching overdue invoices...", total=None)
        report = manager.get_collections_report()

    if json_output:
        console.print(json.dumps(report, indent=2, default=str))
        return

    # Export to files if requested
    if export:
        # Save CSV
        with open('collections_report.csv', 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['Invoice Number', 'Case Name', 'Contact Name', 'Days Overdue', 'Balance Due', 'Last Dunning Level'])
            for inv in report['invoices']:
                writer.writerow([
                    inv['invoice_number'],
                    inv['case_name'] or 'N/A',
                    inv['contact_name'],
                    inv['days_overdue'],
                    inv['balance_due'],
                    inv['last_dunning_level']
                ])

        # Save Markdown
        with open('collections_report.md', 'w') as f:
            f.write('# Collections Report\n')
            f.write(f'**Generated:** {report["generated_at"]}\n\n')

            f.write('## Summary\n')
            f.write('| Metric | Value |\n')
            f.write('|--------|-------|\n')
            f.write(f'| Total Overdue Invoices | {report["total_invoices"]} |\n')
            f.write(f'| Total Balance Due | ${report["total_balance_due"]:,.2f} |\n\n')

            f.write('## Aging Analysis\n')
            f.write('| Period | Count | Amount |\n')
            f.write('|--------|------:|-------:|\n')
            for period, data in report['aging'].items():
                f.write(f'| {period.replace("_", " ")} | {data["count"]} | ${data["amount"]:,.2f} |\n')
            f.write('\n')

            f.write('## By Case (Top 25 by Balance)\n')
            f.write('| Case | Invoices | Balance Due |\n')
            f.write('|------|:--------:|------------:|\n')
            sorted_cases = sorted(report['by_case'].items(), key=lambda x: -x[1]['amount'])[:25]
            for case, data in sorted_cases:
                case_display = case[:60] if len(case) > 60 else case
                f.write(f'| {case_display} | {data["count"]} | ${data["amount"]:,.2f} |\n')
            f.write('\n')

            f.write('## All Overdue Invoices\n')
            f.write('| Invoice # | Case | Contact | Days Overdue | Balance Due |\n')
            f.write('|-----------|------|---------|-------------:|------------:|\n')
            for inv in report['invoices']:
                case_display = (inv['case_name'] or 'N/A')[:40]
                contact_display = inv['contact_name'][:20]
                f.write(f'| {inv["invoice_number"]} | {case_display} | {contact_display} | {inv["days_overdue"]} | ${inv["balance_due"]:,.2f} |\n')

        console.print(f"[green]Exported {len(report['invoices'])} invoices to:[/green]")
        console.print("  - collections_report.csv")
        console.print("  - collections_report.md")
        return

    # Display formatted report
    console.print(Panel.fit(
        f"[bold]Collections Report[/bold]\n"
        f"Generated: {report['generated_at']}\n"
        f"Total Overdue: {report['total_invoices']} invoices\n"
        f"Total Balance: ${report['total_balance_due']:,.2f}",
        title="Summary"
    ))

    # Aging table
    aging_table = Table(title="Aging Analysis")
    aging_table.add_column("Period", style="cyan")
    aging_table.add_column("Count", justify="right")
    aging_table.add_column("Amount", justify="right", style="green")

    for period, data in report["aging"].items():
        aging_table.add_row(
            period.replace("_", " "),
            str(data["count"]),
            f"${data['amount']:,.2f}"
        )

    console.print(aging_table)

    # Top overdue invoices
    if report["invoices"]:
        inv_table = Table(title="Top Overdue Invoices")
        inv_table.add_column("Invoice")
        inv_table.add_column("Contact")
        inv_table.add_column("Case")
        inv_table.add_column("Days", justify="right")
        inv_table.add_column("Balance", justify="right", style="green")

        for inv in report["invoices"][:10]:
            inv_table.add_row(
                inv["invoice_number"],
                inv["contact_name"][:20],
                (inv["case_name"] or "N/A")[:20],
                str(inv["days_overdue"]),
                f"${inv['balance_due']:,.2f}"
            )

        console.print(inv_table)


@collections.command("dunning")
@click.option("--dry-run/--execute", default=True, help="Dry run or actually send")
@click.option("--sync-payments", is_flag=True, help="Sync payments before running")
def collections_dunning(dry_run: bool, sync_payments: bool):
    """Run dunning cycle for overdue invoices."""
    manager = CollectionsManager()

    if sync_payments:
        console.print("Syncing payments from MyCase...")
        new_payments = manager.sync_payments()
        console.print(f"Synced {new_payments} new payments")

    mode = "[yellow]DRY RUN[/yellow]" if dry_run else "[red]LIVE[/red]"
    console.print(f"\nRunning dunning cycle ({mode})...")
    console.print(f"Dunning intervals: {DUNNING_INTERVALS} days\n")

    # Get firm info for templates
    try:
        client = get_client()
        firm_info = client.get_firm()
    except Exception:
        firm_info = {}

    summary = manager.run_dunning_cycle(dry_run=dry_run, firm_info=firm_info)

    # Display results
    console.print(Panel.fit(
        f"[bold]Dunning Cycle Complete[/bold]\n\n"
        f"Total Overdue Invoices: {summary['total_overdue']}\n"
        f"Notices Sent: {summary['notices_sent']}\n"
        f"Skipped (already sent): {summary['skipped_already_sent']}\n"
        f"Skipped (payment received): {summary['skipped_payment_received']}\n"
        f"Skipped (not yet due): {summary['skipped_not_due']}\n"
        f"Errors: {summary['errors']}\n\n"
        f"Total Balance Due: ${summary['total_balance_due']:,.2f}",
        title="Summary"
    ))

    if summary['details']:
        table = Table(title="Details")
        table.add_column("Invoice")
        table.add_column("Contact")
        table.add_column("Days")
        table.add_column("Balance", justify="right")
        table.add_column("Action")
        table.add_column("Sent")

        for detail in summary['details'][:20]:
            table.add_row(
                detail["invoice_number"],
                detail["contact_name"][:15],
                str(detail["days_overdue"]),
                f"${detail['balance_due']:,.2f}",
                detail["action"][:25],
                "Yes" if detail["sent"] else "No"
            )

        console.print(table)


# ============================================================================
# Deadline Commands
# ============================================================================

@cli.group()
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


# ============================================================================
# Analytics Commands
# ============================================================================

@cli.group()
def analytics():
    """Analytics and reporting."""
    pass


@analytics.command("sync")
def analytics_sync():
    """Sync data for analytics."""
    manager = AnalyticsManager()

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Syncing invoices...", total=None)
        invoices = manager.sync_invoice_data()

        progress.update(task, description="Syncing case stages...")
        stages = manager.sync_case_stages()

    console.print(f"\n[green]Synced {invoices} invoices and {stages} case stages[/green]")


@analytics.command("summary")
@click.option("--json-output", is_flag=True, help="Output as JSON")
def analytics_summary(json_output: bool):
    """Generate executive summary report."""
    manager = AnalyticsManager()

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        progress.add_task("Generating summary...", total=None)
        summary = manager.generate_executive_summary()

    if json_output:
        console.print(json.dumps(summary, indent=2, default=str))
    else:
        print_executive_summary(summary)


@analytics.command("attorneys")
def analytics_attorneys():
    """Show attorney performance metrics."""
    manager = AnalyticsManager()

    metrics = manager.get_attorney_metrics()

    if not metrics:
        console.print("[yellow]No attorney data available. Run 'analytics sync' first.[/yellow]")
        return

    table = Table(title="Attorney Metrics")
    table.add_column("Attorney")
    table.add_column("Cases", justify="right")
    table.add_column("Billed", justify="right", style="green")
    table.add_column("Collected", justify="right", style="green")
    table.add_column("Avg Days", justify="right")
    table.add_column("Overdue", justify="right", style="red")

    for m in metrics:
        table.add_row(
            m.attorney_name[:20],
            str(m.total_cases),
            f"${m.total_billed:,.0f}",
            f"${m.total_collected:,.0f}",
            f"{m.avg_days_to_payment:.0f}",
            f"${m.overdue_amount:,.0f}"
        )

    console.print(table)


@analytics.command("payment-times")
@click.option("--by", type=click.Choice(["attorney", "case-type"]), default="attorney")
def analytics_payment_times(by: str):
    """Show time-to-payment statistics."""
    manager = AnalyticsManager()

    if by == "attorney":
        stats = manager.get_time_to_payment_by_attorney()
        title = "Time to Payment by Attorney"
    else:
        stats = manager.get_time_to_payment_by_case_type()
        title = "Time to Payment by Case Type"

    if not stats:
        console.print("[yellow]No payment data available. Run 'analytics sync' first.[/yellow]")
        return

    table = Table(title=title)
    table.add_column("Name" if by == "attorney" else "Case Type")
    table.add_column("Avg Days", justify="right")
    table.add_column("Min", justify="right")
    table.add_column("Max", justify="right")
    table.add_column("Invoices", justify="right")
    table.add_column("Collection %", justify="right")

    for name, s in stats.items():
        table.add_row(
            name[:25],
            f"{s.avg_days_to_payment:.0f}",
            str(s.min_days),
            str(s.max_days),
            str(s.total_invoices),
            f"{s.collection_rate:.1f}%"
        )

    console.print(table)


# ============================================================================
# Template Commands
# ============================================================================

@cli.group()
def templates():
    """Manage notice templates."""
    pass


@templates.command("init")
def templates_init():
    """Initialize default templates."""
    console.print("Creating default templates...")
    manager = create_default_templates()
    console.print("[green]Default templates created![/green]")

    for t in manager.list_templates():
        console.print(f"  - {t['name']} ({t['type']})")


@templates.command("list")
@click.option("--type", "template_type", help="Filter by template type")
def templates_list(template_type: Optional[str]):
    """List all templates."""
    manager = TemplateManager()
    templates = manager.list_templates(template_type=template_type)

    if not templates:
        console.print("[yellow]No templates found. Run 'templates init' to create defaults.[/yellow]")
        return

    table = Table(title="Notice Templates")
    table.add_column("Name", style="cyan")
    table.add_column("Type")
    table.add_column("Description")
    table.add_column("Updated")

    for t in templates:
        table.add_row(
            t["name"],
            t["type"],
            t["description"][:40],
            t.get("updated_at", "")[:10]
        )

    console.print(table)


@templates.command("show")
@click.argument("name")
def templates_show(name: str):
    """Show template content."""
    manager = TemplateManager()
    template = manager.get_template(name)

    if not template:
        console.print(f"[red]Template '{name}' not found[/red]")
        return

    metadata = manager._load_metadata().get(name, {})
    console.print(Panel(
        f"Type: {metadata.get('type')}\n"
        f"Description: {metadata.get('description')}\n"
        f"Variables: {', '.join(metadata.get('variables', []))}",
        title=f"Template: {name}"
    ))
    console.print("\n[bold]Content:[/bold]")
    console.print(template.source)


# ============================================================================
# Run Automation Command
# ============================================================================

@cli.command("run")
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


# ============================================================================
# KPI Commands (Melissa - Collections KPIs)
# ============================================================================

@cli.group()
def kpi():
    """KPI tracking and reporting (SOP-based metrics)."""
    pass


@kpi.command("daily")
@click.option("--date", "target_date", help="Date to report on (YYYY-MM-DD)")
@click.option("--save", is_flag=True, help="Save snapshot to database")
def kpi_daily(target_date: str, save: bool):
    """Generate Melissa's daily collections KPIs."""
    import os
    tracker = KPITracker()

    report_date = None
    if target_date:
        report_date = datetime.strptime(target_date, "%Y-%m-%d").date()
    else:
        report_date = date.today()

    report = tracker.generate_melissa_daily_report(report_date)
    console.print(report)

    # Always save the report to a file
    reports_dir = DATA_DIR / "reports"
    reports_dir.mkdir(exist_ok=True)
    report_filename = reports_dir / f"daily_collections_{report_date}.txt"
    
    with open(report_filename, 'w') as f:
        f.write(report)
    
    console.print(f"[green]Report saved to {report_filename}[/green]")

    if save:
        kpis = tracker.calculate_daily_collections_kpis(report_date)
        tracker.save_daily_kpi_snapshot(kpis)
        console.print("[green]Snapshot saved to database[/green]")


@kpi.command("weekly")
@click.option("--week-end", help="Week end date (YYYY-MM-DD)")
def kpi_weekly(week_end: str):
    """Generate Melissa's weekly collections KPIs."""
    tracker = KPITracker()

    end_date = None
    if week_end:
        end_date = datetime.strptime(week_end, "%Y-%m-%d").date()
    else:
        end_date = date.today()

    report = tracker.generate_melissa_weekly_report(end_date)
    console.print(report)
    
    # Always save the report to a file
    reports_dir = DATA_DIR / "reports"
    reports_dir.mkdir(exist_ok=True)
    report_filename = reports_dir / f"weekly_collections_{end_date}.txt"
    
    with open(report_filename, 'w') as f:
        f.write(report)
    
    console.print(f"[green]Report saved to {report_filename}[/green]")


@kpi.command("huddle")
def kpi_huddle():
    """Generate weekly A/R huddle report (Melissa + Tiffany + John)."""
    manager = PaymentPlanManager()
    report = manager.generate_collections_huddle_report()
    console.print(report)


# ============================================================================
# Payment Plan Commands
# ============================================================================

@cli.group()
def plans():
    """Payment plan tracking and compliance."""
    pass


@plans.command("sync")
def plans_sync():
    """Sync payment plans from MyCase invoices."""
    manager = PaymentPlanManager()

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        progress.add_task("Syncing payment plans...", total=None)
        count = manager.sync_payment_plans_from_invoices()

    console.print(f"[green]Synced {count} payment plans[/green]")


@plans.command("compliance")
def plans_compliance():
    """Run daily payment plan compliance check."""
    manager = PaymentPlanManager()

    summary = manager.run_daily_compliance_check()

    console.print(Panel.fit(
        f"[bold]Payment Plan Compliance[/bold]\n\n"
        f"Active Plans: {summary['total_active_plans']}\n"
        f"Compliant: {summary['compliant']}\n"
        f"Delinquent: {summary['delinquent']}\n"
        f"On Hold: {summary['on_hold']}\n"
        f"Compliance Rate: {summary['compliance_rate']:.1f}%",
        title="Summary"
    ))

    if summary['needs_outreach']:
        table = Table(title="Needs Outreach")
        table.add_column("Contact")
        table.add_column("Case")
        table.add_column("Days Late", justify="right")
        table.add_column("Balance", justify="right")

        for item in summary['needs_outreach'][:10]:
            table.add_row(
                item['contact_name'][:20],
                (item['case_name'] or 'N/A')[:25],
                str(item['days_delinquent']),
                f"${item['balance']:,.2f}"
            )
        console.print(table)

    if summary['needs_noiw']:
        console.print(f"\n[red]NOIW Pipeline: {len(summary['needs_noiw'])} cases 30+ days delinquent[/red]")


@plans.command("noiw-pipeline")
def plans_noiw():
    """Show NOIW (Notice of Intent to Withdraw) pipeline."""
    manager = PaymentPlanManager()
    pipeline = manager.get_noiw_pipeline()

    if not pipeline:
        console.print("[green]No cases in NOIW pipeline[/green]")
        return

    table = Table(title=f"NOIW Pipeline ({len(pipeline)} cases)")
    table.add_column("Urgency")
    table.add_column("Contact")
    table.add_column("Case")
    table.add_column("Days Late", justify="right")
    table.add_column("Balance", justify="right")

    for item in pipeline:
        urgency = "[red]CRITICAL[/red]" if item['urgency'] == 'critical' else "[yellow]HIGH[/yellow]"
        table.add_row(
            urgency,
            item['contact_name'][:20],
            (item['case_name'] or 'N/A')[:25],
            str(item['days_delinquent']),
            f"${item['balance_due']:,.2f}"
        )

    console.print(table)


@plans.command("holds")
def plans_holds():
    """Show collections holds for review."""
    manager = PaymentPlanManager()
    holds = manager.get_holds_for_review()

    if not holds:
        console.print("[green]No holds needing review[/green]")
        return

    table = Table(title="Collections Holds for Review")
    table.add_column("Case ID")
    table.add_column("Reason")
    table.add_column("Approved By")
    table.add_column("Review Date")

    for hold in holds:
        table.add_row(
            str(hold['case_id']),
            hold['reason'][:30],
            hold['approved_by'] or 'N/A',
            hold.get('review_date', 'Not set')
        )

    console.print(table)


# ============================================================================
# Intake Commands (Ty Christian SOP)
# ============================================================================

@cli.group()
def intake():
    """Intake tracking and conversion metrics."""
    pass


@intake.command("sync")
@click.option("--days", default=30, help="Days back to sync")
def intake_sync(days: int):
    """Sync leads from MyCase contacts."""
    manager = IntakeManager()

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        progress.add_task("Syncing leads...", total=None)
        count = manager.sync_leads_from_contacts(days_back=days)

    console.print(f"[green]Synced {count} leads[/green]")


@intake.command("weekly")
@click.option("--week-end", help="Week end date (YYYY-MM-DD)")
def intake_weekly(week_end: str):
    """Generate weekly intake report (Due Monday 10am)."""
    manager = IntakeManager()

    end_date = None
    if week_end:
        end_date = datetime.strptime(week_end, "%Y-%m-%d").date()

    report = manager.generate_weekly_intake_report(end_date)
    console.print(report)


@intake.command("monthly")
@click.option("--month", help="Month (YYYY-MM)")
def intake_monthly(month: str):
    """Generate monthly intake review report."""
    manager = IntakeManager()
    report = manager.generate_monthly_intake_report(month)
    console.print(report)


@intake.command("quality")
@click.argument("case_id", type=int, required=False)
def intake_quality(case_id: int):
    """Check conversion quality for a case or show all issues."""
    manager = IntakeManager()

    if case_id:
        checklist = manager.check_conversion_quality(case_id)
        console.print(Panel.fit(
            f"[bold]Conversion Quality Check[/bold]\n\n"
            f"Case: {checklist.case_name}\n"
            f"Score: {checklist.score:.1f}%",
            title=f"Case {case_id}"
        ))

        for name, passed in checklist.checks.items():
            status = "[green]✓[/green]" if passed else "[red]✗[/red]"
            console.print(f"  {status} {name.replace('_', ' ').title()}")

        if checklist.issues:
            console.print("\n[red]Issues:[/red]")
            for issue in checklist.issues:
                console.print(f"  • {issue}")
    else:
        issues = manager.get_conversion_quality_issues()
        if not issues:
            console.print("[green]No conversion quality issues[/green]")
            return

        table = Table(title=f"Conversion Quality Issues ({len(issues)} cases)")
        table.add_column("Case")
        table.add_column("Score", justify="right")
        table.add_column("Issues")

        for issue in issues[:20]:
            table.add_row(
                issue['case_name'][:30],
                f"{issue['quality_score']:.0f}%",
                (issue['issues'] or '')[:40]
            )

        console.print(table)


# ============================================================================
# Tasks/SLA Commands (Alison/Cole SOP)
# ============================================================================

@cli.group()
def tasks():
    """Task SLA tracking for legal assistants."""
    pass


@tasks.command("sync")
@click.option("--days", default=30, help="Days back to sync")
def tasks_sync(days: int):
    """Sync tasks from MyCase for SLA tracking."""
    manager = TaskSLAManager()

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


# ============================================================================
# Case Quality Commands (Tiffany/All SOPs)
# ============================================================================

@cli.group()
def quality():
    """Case quality verification and tracking."""
    pass


@quality.command("check")
@click.argument("case_id", type=int)
def quality_check(case_id: int):
    """Run quality check on a specific case."""
    manager = CaseQualityManager()
    checklist = manager.generate_day1_checklist_report(case_id)
    console.print(checklist)


@quality.command("audit")
@click.option("--days", default=7, help="Days back to audit")
def quality_audit(days: int):
    """Run quality audit on recent cases."""
    manager = CaseQualityManager()

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        progress.add_task("Running quality audit...", total=None)
        results = manager.run_new_case_quality_audit(days_back=days)

    console.print(Panel.fit(
        f"[bold]Quality Audit Results[/bold]\n\n"
        f"Cases Reviewed: {results.get('total_cases', 0)}\n"
        f"Avg Score: {results.get('avg_score', 0):.1f}%\n\n"
        f"Excellent: {results.get('excellent', 0)}\n"
        f"Good: {results.get('good', 0)}\n"
        f"Needs Attention: {results.get('needs_attention', 0)}\n"
        f"Critical: {results.get('critical', 0)}",
        title="Summary"
    ))

    if results.get('common_issues'):
        console.print("\n[bold]Common Issues:[/bold]")
        for issue, count in sorted(results['common_issues'].items(), key=lambda x: -x[1])[:5]:
            console.print(f"  • {issue}: {count} cases")


@quality.command("outreach")
@click.option("--days", default=30, help="Days back to report")
def quality_outreach(days: int):
    """Show attorney 3-day outreach compliance."""
    manager = CaseQualityManager()

    pending = manager.get_pending_outreach()
    compliance = manager.get_outreach_compliance_report(days_back=days)

    console.print(Panel.fit(
        f"[bold]3-Day Outreach Compliance[/bold]\n\n"
        f"Period: Last {days} days\n"
        f"Overall Rate: {compliance.get('overall_compliance_rate', 0):.1f}%\n"
        f"Avg Days to Contact: {compliance.get('avg_days_to_contact', 0):.1f}",
        title="Summary"
    ))

    if compliance.get('by_attorney'):
        table = Table(title="By Attorney")
        table.add_column("Attorney")
        table.add_column("Cases", justify="right")
        table.add_column("Compliance", justify="right")
        table.add_column("Avg Days", justify="right")

        for attorney, metrics in compliance['by_attorney'].items():
            status = "[green]" if metrics['compliance_rate'] >= 100 else "[yellow]"
            table.add_row(
                attorney[:20],
                str(metrics['total_cases']),
                f"{status}{metrics['compliance_rate']:.0f}%[/]",
                f"{metrics['avg_days_to_contact']:.1f}"
            )
        console.print(table)

    if pending:
        console.print(f"\n[yellow]Pending Outreach: {len(pending)} cases need attorney contact[/yellow]")
        for item in pending[:5]:
            days_old = (date.today() - item.case_created).days
            console.print(f"  • {item.case_name} ({item.attorney_name}) - {days_old} days old")


@quality.command("summary")
@click.option("--days", default=7, help="Days back to report")
def quality_summary(days: int):
    """Generate comprehensive quality summary report."""
    manager = CaseQualityManager()
    report = manager.generate_quality_summary_report(days_back=days)
    console.print(report)


@quality.command("issues")
@click.option("--severity", type=click.Choice(["high", "medium", "low"]), help="Filter by severity")
def quality_issues(severity: str):
    """Show open data integrity issues."""
    manager = CaseQualityManager()
    issues = manager.get_open_integrity_issues(severity=severity)

    if not issues:
        console.print("[green]No open data integrity issues[/green]")
        return

    table = Table(title=f"Data Integrity Issues ({len(issues)})")
    table.add_column("Severity")
    table.add_column("Case")
    table.add_column("Issue Type")
    table.add_column("Description")

    for issue in issues[:20]:
        sev = issue['severity']
        if sev == 'high':
            sev_display = "[red]HIGH[/red]"
        elif sev == 'medium':
            sev_display = "[yellow]MEDIUM[/yellow]"
        else:
            sev_display = "LOW"

        table.add_row(
            sev_display,
            (issue['case_name'] or str(issue['case_id']))[:20],
            issue['issue_type'][:15],
            (issue['description'] or '')[:30]
        )

    console.print(table)


# ============================================================================
# SOP Reports Command (All-in-one)
# ============================================================================

@cli.group()
def sop():
    """SOP-aligned reports for each role."""
    pass


@sop.command("melissa")
@click.option("--daily", is_flag=True, help="Generate daily report")
@click.option("--weekly", is_flag=True, help="Generate weekly report")
@click.option("--huddle", is_flag=True, help="Generate A/R huddle report")
def sop_melissa(daily: bool, weekly: bool, huddle: bool):
    """Generate Melissa (AR Specialist) reports."""
    tracker = KPITracker()
    plans_mgr = PaymentPlanManager()

    # Ensure reports directory exists
    reports_dir = DATA_DIR / "reports"
    reports_dir.mkdir(exist_ok=True)

    if daily or (not daily and not weekly and not huddle):
        report_date = date.today()
        report = tracker.generate_melissa_daily_report(report_date)
        console.print(report)
        
        # Save to file
        report_filename = reports_dir / f"daily_collections_{report_date}.txt"
        with open(report_filename, 'w') as f:
            f.write(report)
        console.print(f"[green]Report saved to {report_filename}[/green]")

    if weekly:
        report_date = date.today()
        report = tracker.generate_melissa_weekly_report(report_date)
        console.print(report)
        
        # Save to file
        report_filename = reports_dir / f"weekly_collections_{report_date}.txt"
        with open(report_filename, 'w') as f:
            f.write(report)
        console.print(f"[green]Report saved to {report_filename}[/green]")

    if huddle:
        report = plans_mgr.generate_collections_huddle_report()
        console.print(report)
        
        # Save to file
        report_date = date.today()
        report_filename = reports_dir / f"collections_huddle_{report_date}.txt"
        with open(report_filename, 'w') as f:
            f.write(report)
        console.print(f"[green]Report saved to {report_filename}[/green]")


@sop.command("ty")
@click.option("--weekly", is_flag=True, help="Weekly intake report")
@click.option("--monthly", is_flag=True, help="Monthly intake review")
def sop_ty(weekly: bool, monthly: bool):
    """Generate Ty (Intake Lead) reports."""
    manager = IntakeManager()

    if weekly or not monthly:
        report = manager.generate_weekly_intake_report()
        console.print(report)

    if monthly:
        report = manager.generate_monthly_intake_report()
        console.print(report)


@sop.command("alison")
@click.option("--days", default=7, help="Days back to report")
def sop_alison(days: int):
    """Generate Alison (Legal Assistant) task report."""
    manager = TaskSLAManager()
    report = manager.generate_legal_assistant_report(assignee_name="Alison", days_back=days)
    console.print(report)


@sop.command("cole")
@click.option("--days", default=7, help="Days back to report")
def sop_cole(days: int):
    """Generate Cole (Legal Assistant) task report."""
    manager = TaskSLAManager()
    report = manager.generate_legal_assistant_report(assignee_name="Cole", days_back=days)
    console.print(report)


@sop.command("tiffany")
@click.option("--ops-huddle", is_flag=True, help="Generate ops huddle report")
@click.option("--quality", is_flag=True, help="Generate quality summary")
def sop_tiffany(ops_huddle: bool, quality: bool):
    """Generate Tiffany (Senior Paralegal) reports."""
    if ops_huddle or not quality:
        task_mgr = TaskSLAManager()
        report = task_mgr.generate_ops_huddle_report()
        console.print(report)

    if quality:
        quality_mgr = CaseQualityManager()
        report = quality_mgr.generate_quality_summary_report()
        console.print(report)


# ============================================================================
# Scheduler Commands
# ============================================================================

@cli.group()
def scheduler():
    """Scheduled automation management."""
    pass


@scheduler.command("status")
def scheduler_status():
    """Show scheduler status and last run times."""
    from scheduler import Scheduler

    sched = Scheduler()
    status = sched.get_status()

    console.print(Panel.fit(
        f"[bold]Scheduler Status[/bold]\n\n"
        f"Enabled Tasks: {status['enabled_tasks']}/{status['total_tasks']}\n"
        f"Dry Run Mode: {status['dry_run_mode']}",
        title="Summary"
    ))

    # Group by frequency
    daily = [t for t in status['tasks'] if t['frequency'] == 'daily']
    weekly = [t for t in status['tasks'] if t['frequency'] == 'weekly']
    monthly = [t for t in status['tasks'] if t['frequency'] == 'monthly']

    for freq_name, tasks in [("Daily", daily), ("Weekly", weekly), ("Monthly", monthly)]:
        if not tasks:
            continue

        table = Table(title=f"{freq_name} Tasks")
        table.add_column("Status")
        table.add_column("Task")
        table.add_column("Time")
        table.add_column("Owner")
        table.add_column("Last Run")

        for task in tasks:
            status_icon = "[green]ON[/green]" if task['enabled'] else "[red]OFF[/red]"
            schedule = task['run_at']
            if task.get('day_of_week'):
                schedule = f"{task['day_of_week'][:3]} {schedule}"
            if task.get('day_of_month'):
                schedule = f"Day {task['day_of_month']} {schedule}"

            table.add_row(
                status_icon,
                task['name'],
                schedule,
                (task['owner'] or '-')[:15],
                task['last_run'][:19] if task['last_run'] != 'Never' else 'Never'
            )

        console.print(table)


@scheduler.command("list")
@click.option("--frequency", type=click.Choice(["daily", "weekly", "monthly"]))
def scheduler_list(frequency: str):
    """List all scheduled tasks."""
    from scheduler import Scheduler, TaskFrequency

    sched = Scheduler()
    freq = TaskFrequency(frequency) if frequency else None
    tasks = sched.list_tasks(freq)

    for task in tasks:
        enabled = "[green]enabled[/green]" if sched.is_task_enabled(task.name) else "[red]disabled[/red]"
        console.print(f"\n[bold]{task.name}[/bold] ({enabled})")
        console.print(f"  {task.description}")
        console.print(f"  Frequency: {task.frequency.value} @ {task.run_at.strftime('%H:%M')}")
        if task.day_of_week:
            console.print(f"  Day: {task.day_of_week.name}")
        if task.owner:
            console.print(f"  Owner: {task.owner}")
        console.print(f"  Command: {task.command}")


@scheduler.command("run")
@click.argument("task_name")
@click.option("--force", is_flag=True, help="Force run even if not scheduled")
def scheduler_run(task_name: str, force: bool):
    """Run a specific scheduled task."""
    from scheduler import Scheduler

    sched = Scheduler()
    task = sched.get_task(task_name)

    if not task:
        console.print(f"[red]Unknown task: {task_name}[/red]")
        console.print("\nAvailable tasks:")
        for t in sched.list_tasks():
            console.print(f"  - {t.name}")
        return

    console.print(f"Running task: [bold]{task.name}[/bold]")
    console.print(f"Command: {task.command}\n")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        progress.add_task(f"Executing {task.name}...", total=None)
        result = sched.run_task(task, force=force)

    if result['success']:
        console.print("[green]Task completed successfully[/green]")
    else:
        console.print(f"[red]Task failed: {result['error']}[/red]")

    if result['output']:
        console.print("\n[bold]Output:[/bold]")
        console.print(result['output'])


@scheduler.command("run-due")
@click.option("--frequency", type=click.Choice(["daily", "weekly", "monthly"]))
def scheduler_run_due(frequency: str):
    """Run all tasks that are currently due."""
    from scheduler import Scheduler, TaskFrequency

    sched = Scheduler()
    freq = TaskFrequency(frequency) if frequency else None

    console.print("Checking for due tasks...")
    results = sched.run_due_tasks(freq)

    if not results:
        console.print("[yellow]No tasks due to run[/yellow]")
        return

    table = Table(title=f"Task Results ({len(results)} tasks)")
    table.add_column("Status")
    table.add_column("Task")
    table.add_column("Duration")
    table.add_column("Error")

    for result in results:
        status = "[green]OK[/green]" if result['success'] else "[red]FAIL[/red]"
        started = datetime.fromisoformat(result['started_at'])
        finished = datetime.fromisoformat(result['finished_at']) if result['finished_at'] else datetime.now()
        duration = (finished - started).total_seconds()

        table.add_row(
            status,
            result['task'],
            f"{duration:.1f}s",
            (result['error'] or '-')[:30]
        )

    console.print(table)


@scheduler.command("enable")
@click.argument("task_name")
def scheduler_enable(task_name: str):
    """Enable a scheduled task."""
    from scheduler import Scheduler

    sched = Scheduler()
    if task_name not in sched.tasks:
        console.print(f"[red]Unknown task: {task_name}[/red]")
        return

    sched.enable_task(task_name)
    console.print(f"[green]Enabled task: {task_name}[/green]")


@scheduler.command("disable")
@click.argument("task_name")
def scheduler_disable(task_name: str):
    """Disable a scheduled task."""
    from scheduler import Scheduler

    sched = Scheduler()
    if task_name not in sched.tasks:
        console.print(f"[red]Unknown task: {task_name}[/red]")
        return

    sched.disable_task(task_name)
    console.print(f"[yellow]Disabled task: {task_name}[/yellow]")


@scheduler.group()
def cron():
    """Cron job management."""
    pass


@cron.command("show")
def cron_show():
    """Show cron entries that would be installed."""
    from scheduler import Scheduler

    sched = Scheduler()
    entries = sched.generate_cron_entries()
    console.print("[bold]Cron Entries:[/bold]\n")
    console.print(entries)


@cron.command("install")
@click.option("--dry-run/--execute", default=True, help="Dry run or actually install")
def cron_install(dry_run: bool):
    """Install cron entries for automated scheduling."""
    from scheduler import Scheduler

    sched = Scheduler()
    result = sched.install_cron(dry_run=dry_run)
    console.print(result)


@cron.command("remove")
def cron_remove():
    """Remove scheduler cron entries."""
    from scheduler import Scheduler

    sched = Scheduler()
    result = sched.remove_cron()
    console.print(result)


# ============================================================================
# Payment Promise Commands
# ============================================================================

@cli.group()
def promises():
    """Payment promise tracking."""
    pass


@promises.command("add")
@click.argument("contact_id", type=int)
@click.argument("amount", type=float)
@click.argument("promise_date", type=str)
@click.option("--case-id", type=int, help="Related case ID")
@click.option("--case-name", help="Related case name")
@click.option("--contact-name", help="Contact name")
@click.option("--invoice-id", type=int, help="Related invoice ID")
@click.option("--notes", help="Additional notes")
@click.option("--recorded-by", default="Staff", help="Staff member recording")
def promises_add(contact_id: int, amount: float, promise_date: str,
                 case_id: int, case_name: str, contact_name: str,
                 invoice_id: int, notes: str, recorded_by: str):
    """Record a payment promise. DATE format: YYYY-MM-DD"""
    from promises import PromiseTracker

    tracker = PromiseTracker()
    parsed_date = datetime.strptime(promise_date, "%Y-%m-%d").date()

    promise_id = tracker.record_promise(
        contact_id=contact_id,
        promised_amount=amount,
        promised_date=parsed_date,
        recorded_by=recorded_by,
        contact_name=contact_name,
        case_id=case_id,
        case_name=case_name,
        invoice_id=invoice_id,
        notes=notes,
    )

    console.print(f"[green]Promise #{promise_id} recorded:[/green]")
    console.print(f"  Amount: ${amount:,.2f}")
    console.print(f"  Due: {promise_date}")


@promises.command("list")
@click.option("--status", type=click.Choice(["pending", "kept", "broken", "all"]), default="pending")
@click.option("--contact-id", type=int, help="Filter by contact")
@click.option("--case-id", type=int, help="Filter by case")
def promises_list(status: str, contact_id: int, case_id: int):
    """List payment promises."""
    from promises import PromiseTracker

    tracker = PromiseTracker()

    if contact_id:
        promises_list = tracker.get_by_contact(contact_id)
    elif case_id:
        promises_list = tracker.get_by_case(case_id)
    elif status == "pending":
        promises_list = tracker.get_pending_promises()
    else:
        # Get all (would need a new method, for now just pending)
        promises_list = tracker.get_pending_promises()

    if not promises_list:
        console.print("[yellow]No promises found[/yellow]")
        return

    table = Table(title=f"Payment Promises ({len(promises_list)})")
    table.add_column("ID", justify="right")
    table.add_column("Contact")
    table.add_column("Case")
    table.add_column("Amount", justify="right")
    table.add_column("Due Date")
    table.add_column("Status")
    table.add_column("Days")

    for p in promises_list[:20]:
        status_color = {
            "pending": "yellow",
            "kept": "green",
            "broken": "red",
            "partial": "cyan",
        }.get(p.status.value, "white")

        days_display = ""
        if p.status.value == "pending":
            if p.days_until_due > 0:
                days_display = f"{p.days_until_due}d left"
            elif p.days_overdue > 0:
                days_display = f"[red]{p.days_overdue}d late[/red]"
            else:
                days_display = "[yellow]TODAY[/yellow]"

        table.add_row(
            str(p.id),
            p.contact_name[:20],
            (p.case_name or "-")[:20],
            f"${p.promised_amount:,.2f}",
            str(p.promised_date),
            f"[{status_color}]{p.status.value}[/{status_color}]",
            days_display,
        )

    console.print(table)


@promises.command("due-today")
def promises_due_today():
    """Show promises due today."""
    from promises import PromiseTracker

    tracker = PromiseTracker()
    due = tracker.get_due_today()

    if not due:
        console.print("[green]No promises due today[/green]")
        return

    console.print(f"[bold]{len(due)} promises due today:[/bold]\n")

    for p in due:
        console.print(f"  • {p.contact_name}: ${p.promised_amount:,.2f}")
        if p.case_name:
            console.print(f"    Case: {p.case_name}")


@promises.command("overdue")
def promises_overdue():
    """Show overdue promises."""
    from promises import PromiseTracker

    tracker = PromiseTracker()
    overdue = tracker.get_overdue()

    if not overdue:
        console.print("[green]No overdue promises[/green]")
        return

    table = Table(title=f"Overdue Promises ({len(overdue)})")
    table.add_column("Contact")
    table.add_column("Case")
    table.add_column("Amount", justify="right")
    table.add_column("Promise Date")
    table.add_column("Days Overdue", justify="right", style="red")

    for p in overdue:
        table.add_row(
            p.contact_name[:20],
            (p.case_name or "-")[:20],
            f"${p.promised_amount:,.2f}",
            str(p.promised_date),
            str(p.days_overdue),
        )

    console.print(table)


@promises.command("kept")
@click.argument("promise_id", type=int)
@click.argument("amount", type=float)
def promises_kept(promise_id: int, amount: float):
    """Mark a promise as kept."""
    from promises import PromiseTracker

    tracker = PromiseTracker()
    tracker.mark_kept(promise_id, amount)
    console.print(f"[green]Promise #{promise_id} marked as kept (${amount:,.2f})[/green]")


@promises.command("broken")
@click.argument("promise_id", type=int)
@click.option("--notes", help="Notes about why broken")
def promises_broken(promise_id: int, notes: str):
    """Mark a promise as broken."""
    from promises import PromiseTracker

    tracker = PromiseTracker()
    tracker.mark_broken(promise_id, notes)
    console.print(f"[red]Promise #{promise_id} marked as broken[/red]")


@promises.command("check")
def promises_check():
    """Run daily promise check and report."""
    from promises import PromiseTracker

    tracker = PromiseTracker()
    report = tracker.generate_daily_report()
    console.print(report)


@promises.command("stats")
@click.option("--days", default=30, help="Days back to analyze")
def promises_stats(days: int):
    """Show promise-keeping statistics."""
    from promises import PromiseTracker

    tracker = PromiseTracker()
    stats = tracker.get_promise_stats(days)

    console.print(Panel.fit(
        f"[bold]Promise Statistics ({days} Days)[/bold]\n\n"
        f"Total Promises: {stats['total_promises']}\n"
        f"Keep Rate: {stats['keep_rate']:.1f}%\n\n"
        f"Kept: {stats['kept']}\n"
        f"Broken: {stats['broken']}\n"
        f"Partial: {stats['partial']}\n"
        f"Pending: {stats['pending']}\n\n"
        f"Total Promised: ${stats['total_promised']:,.2f}\n"
        f"Total Collected: ${stats['total_collected']:,.2f}",
        title="Summary"
    ))


# ============================================================================
# Notification Commands
# ============================================================================

@cli.group()
def notify():
    """Notification management (Slack, Email, SMS)."""
    pass


@notify.command("status")
def notify_status():
    """Show notification system status."""
    from notifications import NotificationManager

    manager = NotificationManager()
    status = manager.get_status()

    console.print(Panel.fit(
        f"[bold]Notification System[/bold]\n\n"
        f"Dry Run Mode: {status['dry_run']}\n"
        f"Enabled Channels: {', '.join(status['enabled_channels'])}\n\n"
        f"Slack Configured: {'Yes' if status['slack_configured'] else 'No'}\n"
        f"Email (SendGrid) Configured: {'Yes' if status['email_configured'] else 'No'}\n"
        f"Email (SMTP/Gmail) Configured: {'Yes' if status.get('smtp_configured') else 'No'}\n"
        f"SMS Configured: {'Yes' if status['sms_configured'] else 'No'}\n\n"
        f"Recent Notifications: {status['recent_notifications']}",
        title="Status"
    ))


@notify.command("test-slack")
@click.option("--message", default="Test message from MyCase automation", help="Message to send")
def notify_test_slack(message: str):
    """Send a test Slack message."""
    from notifications import NotificationManager

    manager = NotificationManager()
    success = manager.send_slack(
        message=message,
        title="Test Alert",
        color="good",
    )

    if success:
        console.print("[green]Slack test sent successfully[/green]")
    else:
        console.print("[red]Failed to send Slack test[/red]")


@notify.command("test-email")
@click.argument("to_email")
@click.option("--subject", default="MyCase Test Email", help="Email subject")
def notify_test_email(to_email: str, subject: str):
    """Send a test email."""
    from notifications import NotificationManager

    manager = NotificationManager()
    success = manager.send_email(
        to_email=to_email,
        subject=subject,
        body_text="This is a test email from the MyCase automation system.",
    )

    if success:
        console.print(f"[green]Email sent to {to_email}[/green]")
    else:
        console.print("[red]Failed to send email[/red]")


@notify.command("send-report")
@click.argument("report_type", type=click.Choice(["daily_ar", "intake_weekly", "overdue_tasks"]))
def notify_send_report(report_type: str):
    """Send a report to Slack."""
    from notifications import NotificationManager

    manager = NotificationManager()

    # Get current data for the report
    if report_type == "daily_ar":
        from kpi_tracker import KPITracker
        tracker = KPITracker()
        kpis = tracker.calculate_daily_collections_kpis()

        summary = {
            "total_ar": kpis.get("total_ar", 0),
            "over_60_pct": kpis.get("over_60_pct", 0),
            "compliance_rate": kpis.get("payment_plan_compliance", 0),
            "noiw_count": kpis.get("noiw_pipeline", 0),
            "delinquent": kpis.get("delinquent_plans", 0),
        }
    elif report_type == "intake_weekly":
        from intake_automation import IntakeManager
        intake_mgr = IntakeManager()
        metrics = intake_mgr.get_weekly_intake_metrics()

        summary = {
            "new_cases": metrics.get("new_cases", 0),
            "contact_rate": metrics.get("same_day_contact_rate", 0),
            "dwi_count": metrics.get("dwi_count", 0),
            "traffic_count": metrics.get("traffic_count", 0),
        }
    else:
        from task_sla import TaskSLAManager
        task_mgr = TaskSLAManager()
        overdue = task_mgr.get_overdue_tasks()

        summary = {"count": len(overdue)}
        details = []
        # Group by assignee
        by_assignee = {}
        for t in overdue:
            name = t.assignee_name
            by_assignee[name] = by_assignee.get(name, 0) + 1

        for name, count in by_assignee.items():
            details.append({"assignee": name, "count": count})

    success = manager.send_slack_report(report_type, summary)

    if success:
        console.print(f"[green]{report_type} report sent to Slack[/green]")
    else:
        console.print("[red]Failed to send report[/red]")


@notify.command("log")
@click.option("--limit", default=20, help="Number of entries to show")
def notify_log(limit: int):
    """Show recent notification log."""
    from notifications import NotificationManager

    manager = NotificationManager()
    logs = manager.get_notification_log(limit)

    if not logs:
        console.print("[yellow]No notification history[/yellow]")
        return

    table = Table(title=f"Recent Notifications ({len(logs)})")
    table.add_column("Time")
    table.add_column("Channel")
    table.add_column("Title")
    table.add_column("Status")

    for log in reversed(logs[-limit:]):
        status = "[green]OK[/green]" if log["success"] else f"[red]FAIL: {log.get('error', '')[:20]}[/red]"
        table.add_row(
            log["timestamp"][:19],
            log["channel"],
            log["title"][:30],
            status,
        )

    console.print(table)


@notify.command("events-report")
@click.argument("to_email")
@click.option("--days", default=7, help="Number of days to include in report")
@click.option("--cc", default=None, help="CC email address")
@click.option("--dry-run", is_flag=True, help="Don't actually send, just preview")
@click.option("--preview", is_flag=True, help="Save HTML preview to file")
def notify_events_report(to_email: str, days: int, cc: str, dry_run: bool, preview: bool):
    """Send upcoming events report via email (SMTP/Gmail)."""
    from events_report import send_events_report, generate_events_report_html, generate_events_report_text
    from config import DATA_DIR

    if preview:
        html, summary = generate_events_report_html(days)
        output_file = DATA_DIR / "events_report_preview.html"
        with open(output_file, 'w') as f:
            f.write(html)
        console.print(f"[green]Preview saved to: {output_file}[/green]")
        console.print(f"Summary: {summary['total_events']} events over {days} days")
        return

    console.print(f"[blue]Generating events report for next {days} days...[/blue]")

    success = send_events_report(
        to_email=to_email,
        days=days,
        cc_email=cc,
        dry_run=dry_run,
    )

    if success:
        if dry_run:
            cc_msg = f" (CC: {cc})" if cc else ""
            console.print(f"[yellow]DRY RUN: Would send report to {to_email}{cc_msg}[/yellow]")
        else:
            cc_msg = f" (CC: {cc})" if cc else ""
            console.print(f"[green]Events report sent to {to_email}{cc_msg}[/green]")
    else:
        console.print("[red]Failed to send events report[/red]")


@notify.command("test-smtp")
@click.argument("to_email")
@click.option("--subject", default="MyCase SMTP Test Email", help="Email subject")
def notify_test_smtp(to_email: str, subject: str):
    """Send a test email via SMTP (Gmail)."""
    from notifications import NotificationManager

    manager = NotificationManager()
    success = manager.send_email_smtp(
        to_email=to_email,
        subject=subject,
        body_text="This is a test email from the MyCase automation system via Gmail SMTP.",
        body_html="<h1>Test Email</h1><p>This is a test email from the <b>MyCase automation system</b> via Gmail SMTP.</p>",
    )

    if success:
        console.print(f"[green]SMTP email sent to {to_email}[/green]")
    else:
        console.print("[red]Failed to send SMTP email. Check SMTP configuration.[/red]")


# ============================================================================
# Trend Analysis Commands
# ============================================================================

@cli.group()
def trends():
    """Historical trend analysis."""
    pass


@trends.command("record")
def trends_record():
    """Record today's KPI snapshot."""
    from trends import TrendTracker
    from kpi_tracker import KPITracker

    trend_tracker = TrendTracker()
    kpi_tracker = KPITracker()

    console.print("Recording daily KPI snapshot...")

    # Get current KPIs
    kpis = kpi_tracker.calculate_daily_collections_kpis()

    # Record key metrics
    trend_tracker.record_snapshot("ar_over_60_pct", kpis.get("over_60_pct", 0))
    trend_tracker.record_snapshot("payment_plan_compliance", kpis.get("payment_plan_compliance", 0))
    trend_tracker.record_snapshot("total_ar", kpis.get("total_ar", 0))
    trend_tracker.record_snapshot("overdue_tasks", kpis.get("overdue_tasks", 0))

    console.print("[green]KPI snapshot recorded[/green]")


@trends.command("report")
@click.option("--days", default=30, help="Days to analyze")
def trends_report(days: int):
    """Generate trend analysis report."""
    from trends import TrendTracker

    tracker = TrendTracker()
    report = tracker.generate_trend_report(days)
    console.print(report)


@trends.command("analyze")
@click.argument("metric_name")
@click.option("--days", default=30, help="Days to analyze")
def trends_analyze(metric_name: str, days: int):
    """Analyze trend for a specific metric."""
    from trends import TrendTracker

    tracker = TrendTracker()

    # Determine if higher is better
    lower_is_better = {"ar_over_60_pct", "overdue_tasks"}
    higher_is_better = metric_name not in lower_is_better

    trend = tracker.analyze_trend(metric_name, days, higher_is_better)

    direction_colors = {
        "improving": "green",
        "declining": "red",
        "stable": "yellow",
        "insufficient_data": "dim",
    }
    color = direction_colors.get(trend.direction.value, "white")

    console.print(Panel.fit(
        f"[bold]{metric_name.replace('_', ' ').title()}[/bold]\n\n"
        f"Current: {trend.current_value:.1f}\n"
        f"Previous: {trend.previous_value:.1f if trend.previous_value else 'N/A'}\n"
        f"Target: {trend.target:.1f if trend.target else 'N/A'}\n\n"
        f"Direction: [{color}]{trend.direction.value}[/{color}]\n"
        f"Change: {trend.change_pct:+.1f}%" if trend.change_pct else "" + "\n"
        f"On Target: {'Yes' if trend.on_target else 'No'}\n\n"
        f"Sparkline: {tracker.generate_sparkline(metric_name)}\n\n"
        f"{trend.insight}",
        title=f"Trend Analysis ({days} Days)"
    ))


@trends.command("compare")
@click.argument("metric_name")
@click.option("--period", type=click.Choice(["week", "month"]), default="week")
def trends_compare(metric_name: str, period: str):
    """Compare metric week-over-week or month-over-month."""
    from trends import TrendTracker

    tracker = TrendTracker()

    if period == "week":
        comparison = tracker.week_over_week(metric_name)
        period_name = "Week over Week"
    else:
        comparison = tracker.month_over_month(metric_name)
        period_name = "Month over Month"

    change_color = "green" if comparison["change_pct"] >= 0 else "red"

    console.print(Panel.fit(
        f"[bold]{metric_name.replace('_', ' ').title()}[/bold]\n"
        f"{period_name} Comparison\n\n"
        f"Previous Period: {comparison['period1']['average']:.1f}\n"
        f"Current Period: {comparison['period2']['average']:.1f}\n\n"
        f"Change: [{change_color}]{comparison['change_pct']:+.1f}%[/{change_color}]",
        title="Comparison"
    ))


@trends.command("dashboard")
def trends_dashboard():
    """Show trends dashboard with sparklines."""
    from trends import TrendTracker

    tracker = TrendTracker()
    dashboard = tracker.get_dashboard_data()

    if not dashboard["metrics"]:
        console.print("[yellow]No trend data available. Run 'trends record' first.[/yellow]")
        return

    table = Table(title="KPI Trends Dashboard")
    table.add_column("Metric")
    table.add_column("Current", justify="right")
    table.add_column("Target", justify="right")
    table.add_column("Trend")
    table.add_column("Sparkline")
    table.add_column("Change", justify="right")

    for m in dashboard["metrics"]:
        direction_icon = {
            "improving": "[green]+[/green]",
            "declining": "[red]-[/red]",
            "stable": "[yellow]=[/yellow]",
        }.get(m["direction"], "?")

        target_status = "[green]" if m["on_target"] else "[red]"
        change_str = f"{m['change_pct']:+.1f}%" if m["change_pct"] else "-"

        table.add_row(
            m["display_name"][:25],
            f"{m['current']:.1f}",
            f"{target_status}{m['target']:.1f}[/]" if m["target"] else "-",
            direction_icon,
            m["sparkline"],
            change_str,
        )

    console.print(table)


# ============================================================================
# Firm Analytics Commands
# ============================================================================

@cli.group()
def analytics():
    """Comprehensive firm analytics and reporting."""
    pass


@analytics.command("report")
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text",
              help="Output format")
def analytics_full_report(output_format: str):
    """Generate full analytics report with all metrics."""
    from firm_analytics import FirmAnalytics, print_full_report
    import json

    analytics_engine = FirmAnalytics()

    if output_format == "json":
        report = analytics_engine.generate_full_report()
        console.print(json.dumps(report, indent=2, default=str))
    else:
        print_full_report(analytics_engine)


@analytics.command("revenue-type")
def analytics_revenue_by_type():
    """Revenue breakdown by case type."""
    from firm_analytics import FirmAnalytics, format_currency, format_percent

    analytics_engine = FirmAnalytics()
    results = analytics_engine.get_revenue_by_case_type()

    table = Table(title="Revenue by Case Type")
    table.add_column("Case Type", style="cyan")
    table.add_column("Cases", justify="right")
    table.add_column("Billed", justify="right", style="green")
    table.add_column("Collected", justify="right", style="green")
    table.add_column("Rate", justify="right")

    for r in results:
        rate_style = "green" if r.collection_rate >= 85 else "yellow" if r.collection_rate >= 70 else "red"
        table.add_row(
            r.case_type,
            str(r.case_count),
            format_currency(r.total_billed),
            format_currency(r.total_collected),
            f"[{rate_style}]{format_percent(r.collection_rate)}[/{rate_style}]"
        )

    console.print(table)


@analytics.command("revenue-attorney")
def analytics_revenue_by_attorney():
    """Revenue breakdown by attorney."""
    from firm_analytics import FirmAnalytics, format_currency, format_percent

    analytics_engine = FirmAnalytics()
    results = analytics_engine.get_revenue_by_attorney()

    table = Table(title="Revenue by Attorney")
    table.add_column("Attorney", style="cyan")
    table.add_column("Cases", justify="right")
    table.add_column("Billed", justify="right", style="green")
    table.add_column("Collected", justify="right", style="green")
    table.add_column("Rate", justify="right")

    for r in results:
        rate_style = "green" if r.collection_rate >= 85 else "yellow" if r.collection_rate >= 70 else "red"
        table.add_row(
            r.attorney_name,
            str(r.case_count),
            format_currency(r.total_billed),
            format_currency(r.total_collected),
            f"[{rate_style}]{format_percent(r.collection_rate)}[/{rate_style}]"
        )

    console.print(table)


@analytics.command("revenue-monthly")
@click.option("--months", default=12, help="Number of months to show")
def analytics_revenue_monthly(months: int):
    """Revenue by attorney per month."""
    from firm_analytics import FirmAnalytics, format_currency

    analytics_engine = FirmAnalytics()
    results = analytics_engine.get_revenue_by_attorney_monthly(months)

    table = Table(title=f"Monthly Revenue by Attorney (Last {months} Months)")
    table.add_column("Month", style="cyan")
    table.add_column("Attorney", style="cyan")
    table.add_column("Billed", justify="right", style="green")
    table.add_column("Collected", justify="right", style="green")

    for r in results:
        table.add_row(r.month, r.attorney_name, format_currency(r.billed), format_currency(r.collected))

    console.print(table)


@analytics.command("case-length")
def analytics_case_length():
    """Average case length by type."""
    from firm_analytics import FirmAnalytics

    analytics_engine = FirmAnalytics()
    results = analytics_engine.get_avg_case_length_by_type()

    table = Table(title="Average Case Length by Type (Closed Cases)")
    table.add_column("Case Type", style="cyan")
    table.add_column("Avg Days", justify="right")
    table.add_column("Min", justify="right")
    table.add_column("Max", justify="right")
    table.add_column("Cases", justify="right")

    for r in results:
        table.add_row(r.category, f"{r.avg_days:.1f}", str(r.min_days), str(r.max_days), str(r.case_count))

    console.print(table)


@analytics.command("fees")
def analytics_fees():
    """Average fees charged and collected by case type."""
    from firm_analytics import FirmAnalytics, format_currency

    analytics_engine = FirmAnalytics()
    results = analytics_engine.get_avg_fee_charged_by_type()

    table = Table(title="Average Fees by Case Type")
    table.add_column("Case Type", style="cyan")
    table.add_column("Cases", justify="right")
    table.add_column("Avg Charged", justify="right", style="green")
    table.add_column("Avg Collected", justify="right", style="green")

    for r in results:
        table.add_row(r.case_type, str(r.total_cases), format_currency(r.avg_fee_charged),
                      format_currency(r.avg_fee_collected))

    console.print(table)


@analytics.command("new-cases")
def analytics_new_cases():
    """New cases in past 12 months."""
    from firm_analytics import FirmAnalytics

    analytics_engine = FirmAnalytics()
    results = analytics_engine.get_new_cases_past_12_months()

    console.print(f"\n[bold]New Cases - Past 12 Months[/bold]")
    console.print(f"Total: [green]{results['total']}[/green] cases\n")

    table = Table(title="Monthly Breakdown")
    table.add_column("Month", style="cyan")
    table.add_column("Cases", justify="right", style="green")

    for month, count in sorted(results['monthly'].items()):
        table.add_row(month, str(count))

    console.print(table)


@analytics.command("since-august")
@click.option("--year", default=2025, help="Year Ty started")
def analytics_since_august(year: int):
    """New cases since August (Ty start)."""
    from firm_analytics import FirmAnalytics

    analytics_engine = FirmAnalytics()
    results = analytics_engine.get_new_cases_since_august(year)

    console.print(f"\n[bold]New Cases Since {results['since_date']}[/bold]")
    console.print(f"Total: [green]{results['total']}[/green] cases\n")

    table = Table(title="By Case Type")
    table.add_column("Case Type", style="cyan")
    table.add_column("Cases", justify="right", style="green")

    for ct, count in results['by_case_type'].items():
        table.add_row(ct, str(count))

    console.print(table)


@analytics.command("fee-comparison")
@click.option("--year", default=2025, help="Year for August cutoff")
def analytics_fee_comparison(year: int):
    """Compare fees since August vs prior 12 months."""
    from firm_analytics import FirmAnalytics, format_currency

    analytics_engine = FirmAnalytics()
    results = analytics_engine.get_fee_comparison_august_vs_prior(year)

    console.print(f"\n[bold]Fee Comparison[/bold]")
    console.print(f"Since August: {results['period_since_august']}")
    console.print(f"Prior Period: {results['prior_period']}\n")

    table = Table(title="Average Fee Comparison by Case Type")
    table.add_column("Case Type", style="cyan")
    table.add_column("Since Aug", justify="right")
    table.add_column("Prior", justify="right")
    table.add_column("Change", justify="right")

    for ct, data in results['comparison'].items():
        aug_fee = data['since_august']['avg_fee']
        prior_fee = data['prior_12_months']['avg_fee']
        change = data['change_percent']
        change_style = "green" if change > 0 else "red" if change < 0 else "yellow"
        change_str = f"{change:+.1f}%" if change != 0 else "N/A"

        table.add_row(
            ct,
            format_currency(aug_fee),
            format_currency(prior_fee),
            f"[{change_style}]{change_str}[/{change_style}]"
        )

    console.print(table)


@analytics.command("jurisdiction")
def analytics_jurisdiction():
    """Cases and revenue by jurisdiction."""
    from firm_analytics import FirmAnalytics, format_currency, format_percent

    analytics_engine = FirmAnalytics()

    # Cases by jurisdiction
    cases = analytics_engine.get_cases_by_jurisdiction()
    console.print("\n[bold]Cases by Jurisdiction[/bold]\n")

    table1 = Table(title="Case Count by Jurisdiction")
    table1.add_column("Jurisdiction", style="cyan")
    table1.add_column("Cases", justify="right", style="green")

    for jurisdiction, count in list(cases.items())[:25]:
        table1.add_row(jurisdiction, str(count))

    console.print(table1)

    # Revenue by jurisdiction
    revenue = analytics_engine.get_revenue_by_jurisdiction()
    console.print("\n[bold]Revenue by Jurisdiction[/bold]\n")

    table2 = Table(title="Revenue by Jurisdiction")
    table2.add_column("Jurisdiction", style="cyan")
    table2.add_column("Cases", justify="right")
    table2.add_column("Billed", justify="right", style="green")
    table2.add_column("Collected", justify="right", style="green")
    table2.add_column("Rate", justify="right")

    for jurisdiction, data in list(revenue.items())[:20]:
        rate_style = "green" if data['collection_rate'] >= 85 else "yellow"
        table2.add_row(
            jurisdiction,
            str(data['cases']),
            format_currency(data['billed']),
            format_currency(data['collected']),
            f"[{rate_style}]{format_percent(data['collection_rate'])}[/{rate_style}]"
        )

    console.print(table2)


@analytics.command("zip-codes")
def analytics_zip_codes():
    """Clients and revenue by zip code (heat map data)."""
    from firm_analytics import FirmAnalytics, format_currency, format_percent

    analytics_engine = FirmAnalytics()

    # Clients by zip code
    clients = analytics_engine.get_clients_by_zip_code()

    if not clients:
        console.print("[yellow]No zip code data available. Run 'sync.py clients' first.[/yellow]")
        return

    console.print("\n[bold]Clients by Zip Code (Top 30)[/bold]\n")

    table1 = Table(title="Client Count by Zip Code")
    table1.add_column("Zip Code", style="cyan")
    table1.add_column("Clients", justify="right", style="green")

    for zip_code, count in list(clients.items())[:30]:
        table1.add_row(zip_code, str(count))

    console.print(table1)
    console.print(f"\nTotal zip codes: {len(clients)}")

    # Revenue by zip code
    revenue = analytics_engine.get_revenue_by_zip_code()
    console.print("\n[bold]Revenue by Zip Code (Top 25)[/bold]\n")

    table2 = Table(title="Revenue by Zip Code")
    table2.add_column("Zip Code", style="cyan")
    table2.add_column("Clients", justify="right")
    table2.add_column("Cases", justify="right")
    table2.add_column("Billed", justify="right", style="green")
    table2.add_column("Collected", justify="right", style="green")
    table2.add_column("Rate", justify="right")

    for zip_code, data in list(revenue.items())[:25]:
        rate_style = "green" if data['collection_rate'] >= 85 else "yellow"
        table2.add_row(
            zip_code,
            str(data['clients']),
            str(data['cases']),
            format_currency(data['billed']),
            format_currency(data['collected']),
            f"[{rate_style}]{format_percent(data['collection_rate'])}[/{rate_style}]"
        )

    console.print(table2)


@analytics.command("attorney-monthly")
@click.option("--months", default=6, help="Number of months to show")
def analytics_attorney_monthly(months: int):
    """New cases per month per attorney."""
    from firm_analytics import FirmAnalytics

    analytics_engine = FirmAnalytics()
    results = analytics_engine.get_new_cases_per_month_per_attorney(months)

    table = Table(title=f"New Cases per Month per Attorney (Last {months} Months)")
    table.add_column("Month", style="cyan")
    table.add_column("Attorney", style="cyan")
    table.add_column("Cases", justify="right", style="green")

    for r in results:
        table.add_row(r.month, r.attorney_name, str(r.case_count))

    console.print(table)


# ============================================================================
# User Management Commands
# ============================================================================

@cli.group()
def users():
    """Manage dashboard users."""
    pass


@users.command("create")
@click.argument("username")
@click.option("--password", prompt=True, hide_input=True, confirmation_prompt=True, help="User password")
@click.option("--email", default=None, help="User email address")
@click.option("--admin", is_flag=True, help="Make user an admin")
def users_create(username: str, password: str, email: str, admin: bool):
    """Create a new dashboard user."""
    from dashboard.auth import create_user

    role = "admin" if admin else "user"
    success = create_user(username, password, email, role)

    if success:
        console.print(f"[green]User '{username}' created successfully (role: {role})[/green]")
    else:
        console.print(f"[red]Failed to create user. Username '{username}' may already exist.[/red]")


@users.command("list")
def users_list():
    """List all dashboard users."""
    from dashboard.auth import list_users

    users_data = list_users()

    if not users_data:
        console.print("[yellow]No users found. Create one with: users create <username>[/yellow]")
        return

    table = Table(title="Dashboard Users")
    table.add_column("Username")
    table.add_column("Email")
    table.add_column("Role")
    table.add_column("Active")
    table.add_column("Last Login")

    for user in users_data:
        status = "[green]Yes[/green]" if user["is_active"] else "[red]No[/red]"
        last_login = user["last_login"] or "Never"
        table.add_row(
            user["username"],
            user["email"] or "-",
            user["role"],
            status,
            last_login[:19] if last_login != "Never" else last_login,
        )

    console.print(table)


@users.command("delete")
@click.argument("username")
@click.confirmation_option(prompt="Are you sure you want to delete this user?")
def users_delete(username: str):
    """Delete a dashboard user."""
    from dashboard.auth import delete_user

    success = delete_user(username)

    if success:
        console.print(f"[green]User '{username}' deleted successfully[/green]")
    else:
        console.print(f"[red]User '{username}' not found[/red]")


@users.command("password")
@click.argument("username")
@click.option("--password", prompt=True, hide_input=True, confirmation_prompt=True, help="New password")
def users_password(username: str, password: str):
    """Change a user's password."""
    from dashboard.auth import update_user_password

    success = update_user_password(username, password)

    if success:
        console.print(f"[green]Password updated for '{username}'[/green]")
    else:
        console.print(f"[red]User '{username}' not found[/red]")


# ============================================================================
# Dashboard Command
# ============================================================================

@cli.command("dashboard")
@click.option("--host", default="127.0.0.1", help="Host to bind to")
@click.option("--port", default=8000, help="Port to bind to")
@click.option("--reload", is_flag=True, help="Enable auto-reload for development")
def dashboard_cmd(host: str, port: int, reload: bool):
    """Launch the web dashboard."""
    from dashboard.app import run_server

    console.print(f"\n[bold]Starting MyCase Dashboard...[/bold]")
    console.print(f"Open [link=http://{host}:{port}]http://{host}:{port}[/link] in your browser")
    console.print(f"Default login: admin / admin\n")

    run_server(host=host, port=port, reload=reload)


# ============================================================================
# Main Entry Point
# ============================================================================

def main():
    """Main entry point."""
    cli()


if __name__ == "__main__":
    main()
