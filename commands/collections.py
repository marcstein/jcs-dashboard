#!/usr/bin/env python3
"""
Collections and dunning automation commands.

Provides CLI commands for:
- Collections aging reports
- Dunning cycle automation
- Dunning notice preview and staging
- Email configuration testing
"""
import csv
from datetime import date, timedelta

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from config import DUNNING_INTERVALS
from api_client import get_client
from dunning import CollectionsManager
from dashboard.models import DashboardData
from dunning_emails import DunningEmailManager, DUNNING_STAGES, DunningInvoice


console = Console()


@click.group()
def collections():
    """Collections and dunning automation."""
    pass


@collections.command("report")
@click.option("--json-output", is_flag=True, help="Output as JSON")
@click.option("--export", is_flag=True, help="Export to CSV and Markdown files")
def collections_report(json_output: bool, export: bool):
    """Generate a collections aging report."""
    import json

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


@collections.command("preview")
@click.option("--stage", type=int, help="Filter by stage (1-4)")
@click.option("--limit", default=50, help="Max invoices to show")
@click.option("--export", is_flag=True, help="Export to CSV")
def collections_preview(stage: int, limit: int, export: bool):
    """Preview dunning notices that would be sent.

    Stages:
    1 = Friendly Reminder (5-14 days overdue)
    2 = Formal Reminder (15-29 days overdue)
    3 = Urgent Notice (30-44 days overdue)
    4 = Final Notice (45+ days overdue)
    """
    data = DashboardData()
    summary = data.get_dunning_summary()
    queue = data.get_dunning_queue(stage=stage)

    # Show summary
    console.print("\n[bold]Dunning Queue Summary[/bold]\n")

    summary_table = Table(show_header=True, header_style="bold")
    summary_table.add_column("Stage")
    summary_table.add_column("Name")
    summary_table.add_column("Days Overdue")
    summary_table.add_column("Count", justify="right")
    summary_table.add_column("Balance Due", justify="right")

    stage_colors = {1: "green", 2: "yellow", 3: "orange3", 4: "red"}

    for stage_num, stage_data in summary['stages'].items():
        color = stage_colors.get(stage_num, "white")
        marker = " <--" if stage == stage_num else ""
        summary_table.add_row(
            f"[{color}]Stage {stage_num}[/{color}]",
            stage_data['name'],
            f"{stage_data['days']} days",
            str(stage_data['count']),
            f"${stage_data['balance']:,.2f}{marker}"
        )

    summary_table.add_row(
        "[bold]TOTAL[/bold]",
        "",
        "",
        f"[bold]{summary['total_count']}[/bold]",
        f"[bold]${summary['total_balance']:,.2f}[/bold]"
    )

    console.print(summary_table)

    if not queue:
        if stage:
            console.print(f"\n[yellow]No invoices in Stage {stage}[/yellow]")
        else:
            console.print("\n[green]No invoices currently in the dunning queue![/green]")
        return

    # Export to CSV if requested
    if export:
        filename = f"dunning_preview_stage{stage or 'all'}.csv"
        with open(filename, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['Invoice', 'Case', 'Attorney', 'Balance Due', 'Days Overdue', 'Stage', 'Stage Name', 'Due Date'])
            for inv in queue:
                writer.writerow([
                    inv['invoice_number'],
                    inv['case_name'],
                    inv['attorney'],
                    inv['balance_due'],
                    inv['days_overdue'],
                    inv['dunning_stage'],
                    inv['stage_name'],
                    inv['due_date']
                ])
        console.print(f"\n[green]Exported {len(queue)} invoices to {filename}[/green]")
        return

    # Show queue
    filter_msg = f" (Stage {stage} only)" if stage else ""
    console.print(f"\n[bold]Dunning Queue{filter_msg}[/bold]\n")

    table = Table(show_header=True, header_style="bold")
    table.add_column("Invoice")
    table.add_column("Case")
    table.add_column("Attorney")
    table.add_column("Balance", justify="right")
    table.add_column("Days", justify="right")
    table.add_column("Stage")

    shown = 0
    for inv in queue[:limit]:
        color = stage_colors.get(inv['dunning_stage'], "white")
        table.add_row(
            inv['invoice_number'],
            (inv['case_name'] or 'N/A')[:25],
            (inv['attorney'] or 'N/A')[:15],
            f"${inv['balance_due']:,.2f}",
            f"[{color}]{inv['days_overdue']}[/{color}]",
            f"[{color}]{inv['stage_name']}[/{color}]"
        )
        shown += 1

    console.print(table)

    if len(queue) > limit:
        console.print(f"\n[dim]Showing {shown} of {len(queue)} invoices. Use --limit to show more.[/dim]")

    console.print(f"\n[bold]Next Steps:[/bold]")
    console.print("  - View in dashboard: http://127.0.0.1:3000/dunning")
    console.print("  - Run dry-run: uv run python agent.py collections dunning --dry-run")
    console.print("  - Send for real: uv run python agent.py collections dunning --execute")


@collections.command("test-email")
@click.option("--stage", type=int, default=1, help="Stage to test (1-4)")
@click.option("--to", "to_email", default="marc.stein@gmail.com", help="Email to send test to")
def collections_test_email(stage: int, to_email: str):
    """Send a test dunning email to verify email configuration."""
    if stage < 1 or stage > 4:
        console.print("[red]Stage must be 1-4[/red]")
        return

    manager = DunningEmailManager(test_mode=True, test_email=to_email)

    stage_info = DUNNING_STAGES[stage - 1]
    console.print(f"\n[bold]Testing Stage {stage}: {stage_info.name}[/bold]")
    console.print(f"Sending to: {to_email}")

    # Get a sample invoice for this stage
    invoices = manager.get_invoices_for_stage(stage_info, limit=1)

    if not invoices:
        console.print(f"[yellow]No invoices found in Stage {stage} ({stage_info.min_days}-{stage_info.max_days} days overdue)[/yellow]")
        console.print("Creating a sample invoice for testing...")

        # Create a fake invoice for testing
        invoices = [DunningInvoice(
            invoice_id=99999,
            invoice_number="TEST-001",
            case_id=99999,
            case_name="SAMPLE.CLIENT - Test Case",
            client_name="Sample Client",
            client_email=to_email,
            total_amount=5000.00,
            paid_amount=1000.00,
            balance_due=4000.00,
            due_date=date.today() - timedelta(days=stage_info.min_days + 2),
            days_overdue=stage_info.min_days + 2,
        )]

    inv = invoices[0]
    console.print(f"  Invoice: {inv.invoice_number}")
    console.print(f"  Balance: ${inv.balance_due:,.2f}")
    console.print(f"  Days Overdue: {inv.days_overdue}")

    success, message = manager.send_dunning_notice(stage, inv)

    if success:
        console.print(f"\n[green]Success: {message}[/green]")
        console.print(f"\nCheck your inbox at {to_email}")
    else:
        console.print(f"\n[red]Failed: {message}[/red]")
        console.print("\nMake sure you have email configured in .env:")
        console.print("  - SMTP_USER and SMTP_PASS for Gmail")
        console.print("  - Or SENDGRID_API_KEY for SendGrid")
