#!/usr/bin/env python3
"""
Trust transfer report commands.

Generates reports showing how much of each case's flat fee
should be transferred from trust to operating, based on case phase.
"""
import csv
from datetime import datetime

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text

from config import FIRM_ID
from trust_transfer import (
    generate_trust_transfer_report,
    export_trust_report_csv,
    FEE_SCHEDULES,
    PHASE_ORDER,
    PHASE_LABELS,
)

console = Console()


@click.group()
def trust():
    """Trust-to-operating transfer reports."""
    pass


@trust.command("report")
@click.option("--firm-id", default=FIRM_ID, help="Firm ID")
@click.option("--export", "export_csv", is_flag=True, help="Export to CSV")
@click.option("--attorney", default=None, help="Filter by lead attorney name")
@click.option("--phase", default=None, help="Filter by current phase code")
@click.option("--limit", default=None, type=int, help="Limit number of rows")
def trust_report(firm_id, export_csv, attorney, phase, limit):
    """Generate trust-to-operating transfer report."""
    console.print("\n[bold]Trust-to-Operating Transfer Report[/bold]")
    console.print(f"Firm: {firm_id} | Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")

    report = generate_trust_transfer_report(firm_id)
    lines = report["lines"]
    summary = report["summary"]

    # Apply filters
    if attorney:
        lines = [l for l in lines if attorney.lower() in l.lead_attorney.lower()]
    if phase:
        lines = [l for l in lines if l.current_phase == phase]
    if limit:
        lines = lines[:limit]

    if not lines:
        console.print("[yellow]No cases found matching criteria.[/yellow]")
        return

    # Summary panel
    s = summary
    summary_text = (
        f"Cases: [bold]{s['case_count']}[/bold]  |  "
        f"Total Fees: [bold]${s['total_fees']:,.0f}[/bold]  |  "
        f"Earned: [bold green]${s['total_earned']:,.0f}[/bold green] ({s['earned_pct']}%)  |  "
        f"In Operating: [bold]${s['total_in_operating']:,.0f}[/bold]  |  "
        f"[bold yellow]Recommended Transfer: ${s['total_to_transfer']:,.0f}[/bold yellow]  |  "
        f"Remaining Trust: ${s['total_remaining_trust']:,.0f}"
    )
    console.print(Panel(summary_text, title="Summary", border_style="blue"))

    # Breakdown by case type schedule
    sched_table = Table(title="By Case Type", show_lines=False, padding=(0, 1))
    sched_table.add_column("Schedule", style="cyan")
    sched_table.add_column("Cases", justify="right")
    sched_table.add_column("Total Fees", justify="right")
    sched_table.add_column("Earned", justify="right")
    sched_table.add_column("To Transfer", justify="right", style="yellow")

    for label, data in s["by_schedule"].items():
        sched_table.add_row(
            label,
            str(data["count"]),
            f"${data['total_fee']:,.0f}",
            f"${data['earned']:,.0f}",
            f"${data['to_transfer']:,.0f}",
        )
    console.print(sched_table)
    console.print()

    # Breakdown by phase
    phase_table = Table(title="By Current Phase", show_lines=False, padding=(0, 1))
    phase_table.add_column("Phase", style="cyan")
    phase_table.add_column("Cases", justify="right")
    phase_table.add_column("Total Fees", justify="right")
    phase_table.add_column("Earned", justify="right")
    phase_table.add_column("To Transfer", justify="right", style="yellow")

    for phase_label in PHASE_LABELS.values():
        if phase_label in s["by_phase"]:
            data = s["by_phase"][phase_label]
            phase_table.add_row(
                phase_label,
                str(data["count"]),
                f"${data['total_fee']:,.0f}",
                f"${data['earned']:,.0f}",
                f"${data['to_transfer']:,.0f}",
            )
    console.print(phase_table)
    console.print()

    # Detail table
    detail = Table(title="Case Detail", show_lines=False, padding=(0, 1), row_styles=["", "dim"])
    detail.add_column("Case", max_width=30)
    detail.add_column("Client", max_width=20)
    detail.add_column("Attorney", max_width=15)
    detail.add_column("Type", max_width=12)
    detail.add_column("Phase", max_width=10)
    detail.add_column("Fee", justify="right")
    detail.add_column("Earned %", justify="right")
    detail.add_column("Earned $", justify="right")
    detail.add_column("In Oper.", justify="right")
    detail.add_column("Transfer", justify="right", style="bold yellow")
    detail.add_column("In Trust", justify="right")

    for l in lines:
        transfer_style = "bold yellow" if l.recommended_transfer > 0 else ""
        detail.add_row(
            l.case_name[:30],
            l.client_name[:20],
            l.lead_attorney[:15],
            l.case_type[:12] if l.case_type else "",
            l.phase_label,
            f"${l.total_fee:,.0f}",
            f"{l.earned_pct}%",
            f"${l.earned_amount:,.0f}",
            f"${l.in_operating:,.0f}",
            f"${l.recommended_transfer:,.0f}" if l.recommended_transfer > 0 else "-",
            f"${l.remaining_in_trust:,.0f}",
        )

    console.print(detail)

    # Export
    if export_csv:
        filepath = f"reports/trust_transfer_{datetime.now().strftime('%Y%m%d')}.csv"
        export_trust_report_csv(report, filepath)
        console.print(f"\n[green]Exported to {filepath}[/green]")

    console.print()


@trust.command("schedules")
def show_schedules():
    """Show the fee allocation schedules by case type."""
    console.print("\n[bold]Trust Transfer Fee Schedules[/bold]\n")
    console.print("Percentage of flat fee earned at each phase (cumulative):\n")

    for key, schedule in FEE_SCHEDULES.items():
        table = Table(title=schedule["label"], show_lines=False, padding=(0, 1))
        table.add_column("Phase", style="cyan")
        table.add_column("This Phase %", justify="right")
        table.add_column("Cumulative %", justify="right", style="bold")

        cumulative = 0
        for phase_code in PHASE_ORDER:
            pct = schedule["phases"].get(phase_code, 0)
            cumulative += pct
            table.add_row(
                PHASE_LABELS.get(phase_code, phase_code),
                f"{pct}%" if pct > 0 else "-",
                f"{cumulative}%",
            )

        console.print(table)
        patterns = ", ".join(schedule["case_type_patterns"])
        console.print(f"  Matches: {patterns}\n")
