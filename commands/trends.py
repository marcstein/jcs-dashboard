"""Historical trend analysis commands."""

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()


@click.group()
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
