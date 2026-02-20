"""
Analytics and Reporting Commands

Commands for generating reports, analytics summaries, and performance metrics.
"""
import json
from typing import Optional

import click
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn

from analytics import AnalyticsManager, print_executive_summary


console = Console()


@click.group()
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
