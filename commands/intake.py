"""Intake tracking and conversion metrics commands."""

import click
from datetime import datetime
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from intake_automation import IntakeManager

console = Console()


@click.group()
def intake():
    """Intake tracking and conversion metrics."""
    pass


@intake.command("sync")
@click.option("--days", default=30, help="Days back to sync")
def intake_sync(days: int):
    """Sync leads from MyCase contacts."""
    manager = IntakeManager()

    from rich.progress import Progress, SpinnerColumn, TextColumn
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
