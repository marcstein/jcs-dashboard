"""Payment plan tracking and compliance commands."""
import csv
from datetime import date

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from payment_plans import PaymentPlanManager
from notifications import NotificationManager

console = Console()


@click.group()
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
@click.option("--min-days", default=30, help="Minimum days overdue")
@click.option("--min-balance", default=0, type=float, help="Minimum balance due")
@click.option("--limit", default=50, help="Max cases to show")
@click.option("--include-closed", is_flag=True, help="Include closed cases")
@click.option("--export", is_flag=True, help="Export to CSV file")
def plans_noiw(min_days: int, min_balance: float, limit: int, include_closed: bool, export: bool):
    """Show NOIW (Notice of Intent to Withdraw) pipeline."""
    manager = PaymentPlanManager()
    pipeline = manager.get_noiw_pipeline(
        min_days=min_days,
        open_cases_only=not include_closed
    )

    # Filter by minimum balance
    if min_balance > 0:
        pipeline = [p for p in pipeline if p['balance_due'] >= min_balance]

    if not pipeline:
        console.print("[green]No cases in NOIW pipeline[/green]")
        return

    # Calculate summary stats
    total_balance = sum(p['balance_due'] for p in pipeline)
    critical_count = sum(1 for p in pipeline if p['urgency'] == 'critical')
    high_count = len(pipeline) - critical_count

    # Age buckets
    bucket_30_60 = sum(1 for p in pipeline if 30 <= p['days_delinquent'] < 60)
    bucket_60_90 = sum(1 for p in pipeline if 60 <= p['days_delinquent'] < 90)
    bucket_90_180 = sum(1 for p in pipeline if 90 <= p['days_delinquent'] < 180)
    bucket_180_plus = sum(1 for p in pipeline if p['days_delinquent'] >= 180)

    # Show summary
    console.print(Panel.fit(
        f"[bold]NOIW Pipeline Summary[/bold]\n\n"
        f"Total Cases: {len(pipeline)}\n"
        f"Total Balance: ${total_balance:,.2f}\n\n"
        f"[red]CRITICAL (60+ days):[/red] {critical_count}\n"
        f"[yellow]HIGH (30-59 days):[/yellow] {high_count}\n\n"
        f"Age Distribution:\n"
        f"  30-60 days:  {bucket_30_60}\n"
        f"  60-90 days:  {bucket_60_90}\n"
        f"  90-180 days: {bucket_90_180}\n"
        f"  180+ days:   {bucket_180_plus}",
        title="NOIW Pipeline"
    ))

    # Export to CSV if requested
    if export:
        filename = f"noiw_pipeline_{date.today().isoformat()}.csv"
        with open(filename, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=[
                'contact_name', 'case_name', 'days_delinquent', 'balance_due',
                'urgency', 'case_id', 'invoice_id', 'case_status'
            ])
            writer.writeheader()
            writer.writerows(pipeline)
        console.print(f"\n[green]Exported {len(pipeline)} cases to {filename}[/green]")
        return

    # Show table
    table = Table(title=f"Top {min(limit, len(pipeline))} Cases")
    table.add_column("Urgency")
    table.add_column("Contact")
    table.add_column("Case")
    table.add_column("Days Late", justify="right")
    table.add_column("Balance", justify="right")

    for item in pipeline[:limit]:
        urgency = "[red]CRITICAL[/red]" if item['urgency'] == 'critical' else "[yellow]HIGH[/yellow]"
        table.add_row(
            urgency,
            item['contact_name'][:20],
            (item['case_name'] or 'N/A')[:30],
            str(item['days_delinquent']),
            f"${item['balance_due']:,.2f}"
        )

    console.print(table)

    if len(pipeline) > limit:
        console.print(f"\n[dim]Showing {limit} of {len(pipeline)} cases. Use --limit to show more.[/dim]")


@plans.command("noiw-sync")
def plans_noiw_sync():
    """Sync NOIW tracking from the pipeline."""
    manager = PaymentPlanManager()

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        progress.add_task("Syncing NOIW tracking...", total=None)
        result = manager.sync_noiw_from_pipeline()

    console.print(Panel.fit(
        f"[bold]NOIW Sync Complete[/bold]\n\n"
        f"Pipeline cases: {result['pipeline_count']}\n"
        f"New tracking entries: {result['new_entries']}\n"
        f"Updated entries: {result['updated']}",
        title="NOIW Sync"
    ))


@plans.command("noiw-status")
def plans_noiw_status():
    """Show NOIW workflow status summary."""
    manager = PaymentPlanManager()
    summary = manager.get_noiw_workflow_summary()

    if summary['total_tracked'] == 0:
        console.print("[yellow]No NOIW cases being tracked. Run 'plans noiw-sync' first.[/yellow]")
        return

    console.print(Panel.fit(
        f"[bold]NOIW Workflow Summary[/bold]\n\n"
        f"Total Cases Tracked: {summary['total_tracked']}\n"
        f"Total Balance: ${summary['total_balance']:,.2f}",
        title="NOIW Tracking"
    ))

    table = Table(title="Cases by Status")
    table.add_column("Status")
    table.add_column("Count", justify="right")
    table.add_column("Balance", justify="right")

    status_colors = {
        'pending': 'yellow',
        'warning_sent': 'cyan',
        'final_notice': 'magenta',
        'attorney_review': 'red',
        'on_hold': 'dim',
        'payment_arranged': 'green',
        'withdrawn': 'red',
        'resolved': 'green',
    }

    for status, data in summary['by_status'].items():
        if data['count'] > 0:
            color = status_colors.get(status, 'white')
            table.add_row(
                f"[{color}]{status.replace('_', ' ').title()}[/{color}]",
                str(data['count']),
                f"${data['total_balance']:,.2f}"
            )

    console.print(table)


@plans.command("noiw-update")
@click.argument("case_id", type=int)
@click.argument("invoice_id", type=int)
@click.argument("status", type=click.Choice([
    'warning_sent', 'final_notice', 'attorney_review',
    'on_hold', 'payment_arranged', 'withdrawn', 'resolved'
]))
@click.option("--notes", help="Add notes to the update")
@click.option("--assigned-to", help="Assign to staff member")
def plans_noiw_update(case_id: int, invoice_id: int, status: str, notes: str, assigned_to: str):
    """Update NOIW status for a case."""
    manager = PaymentPlanManager()

    # Check if tracking exists
    existing = manager.get_noiw_status(case_id, invoice_id)
    if not existing:
        console.print(f"[red]No NOIW tracking found for case {case_id}, invoice {invoice_id}[/red]")
        console.print("[dim]Run 'plans noiw-sync' first to create tracking entries.[/dim]")
        return

    success = manager.update_noiw_status(
        case_id=case_id,
        invoice_id=invoice_id,
        new_status=status,
        notes=notes,
        assigned_to=assigned_to
    )

    if success:
        console.print(f"[green]Updated NOIW status to '{status}' for case {case_id}[/green]")
        if notes:
            console.print(f"[dim]Notes: {notes}[/dim]")
    else:
        console.print("[red]Failed to update NOIW status[/red]")


@plans.command("noiw-list")
@click.argument("status", type=click.Choice([
    'pending', 'warning_sent', 'final_notice', 'attorney_review',
    'on_hold', 'payment_arranged', 'withdrawn', 'resolved'
]))
@click.option("--limit", default=25, help="Max cases to show")
def plans_noiw_list(status: str, limit: int):
    """List NOIW cases by status."""
    manager = PaymentPlanManager()
    cases = manager.get_noiw_cases_by_status(status)

    if not cases:
        console.print(f"[yellow]No cases with status '{status}'[/yellow]")
        return

    table = Table(title=f"NOIW Cases - {status.replace('_', ' ').title()} ({len(cases)})")
    table.add_column("Case ID")
    table.add_column("Contact")
    table.add_column("Days Late", justify="right")
    table.add_column("Balance", justify="right")
    table.add_column("Assigned To")

    for case in cases[:limit]:
        table.add_row(
            str(case['case_id']),
            (case['contact_name'] or 'Unknown')[:20],
            str(case['days_delinquent']),
            f"${case['balance_due']:,.2f}",
            case['assigned_to'] or '-'
        )

    console.print(table)

    if len(cases) > limit:
        console.print(f"\n[dim]Showing {limit} of {len(cases)} cases.[/dim]")


@plans.command("noiw-notify")
@click.argument("report_type", type=click.Choice(['daily', 'critical', 'workflow']))
@click.option("--dry-run", is_flag=True, help="Preview without sending")
def plans_noiw_notify(report_type: str, dry_run: bool):
    """Send NOIW notification to Slack."""
    manager = PaymentPlanManager()
    notif_mgr = NotificationManager()

    # Get NOIW data
    noiw_data = manager.get_noiw_notification_data()

    if report_type == 'daily':
        summary = noiw_data['summary']
        report_name = 'noiw_daily'
        details = None
    elif report_type == 'critical':
        summary = {
            "case_count": len(noiw_data['critical_cases']),
            "total_balance": sum(c['balance_due'] for c in noiw_data['critical_cases']),
        }
        details = noiw_data['critical_cases']
        report_name = 'noiw_critical'
    else:  # workflow
        summary = noiw_data['workflow_status']
        details = None
        report_name = 'noiw_workflow'

    # Show preview
    console.print(Panel.fit(
        f"[bold]NOIW Notification Preview[/bold]\n\n"
        f"Report Type: {report_type}\n"
        f"Cases: {summary.get('total_cases', summary.get('case_count', summary.get('total_tracked', 0)))}\n"
        f"Balance: ${summary.get('total_balance', 0):,.2f}",
        title="Preview"
    ))

    if dry_run:
        console.print("[yellow]DRY RUN - notification not sent[/yellow]")
        return

    success = notif_mgr.send_slack_report(report_name, summary, details)

    if success:
        console.print(f"[green]NOIW {report_type} notification sent to Slack[/green]")
    else:
        console.print("[red]Failed to send notification[/red]")


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
