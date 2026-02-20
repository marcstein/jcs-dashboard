"""SOP-aligned reports for each role."""

import click
from datetime import date
from pathlib import Path
from rich.console import Console

from kpi_tracker import KPITracker
from payment_plans import PaymentPlanManager
from intake_automation import IntakeManager
from task_sla import TaskSLAManager
from case_quality import CaseQualityManager

console = Console()
DATA_DIR = Path("data")


@click.group()
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
