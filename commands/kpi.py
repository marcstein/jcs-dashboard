"""KPI tracking and reporting commands."""
from datetime import datetime, date

import click
from rich.console import Console

from config import DATA_DIR
from kpi_tracker import KPITracker
from payment_plans import PaymentPlanManager

console = Console()


@click.group()
def kpi():
    """KPI tracking and reporting (SOP-based metrics)."""
    pass


@kpi.command("daily")
@click.option("--date", "target_date", help="Date to report on (YYYY-MM-DD)")
@click.option("--save", is_flag=True, help="Save snapshot to database")
def kpi_daily(target_date: str, save: bool):
    """Generate Melissa's daily collections KPIs."""
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
