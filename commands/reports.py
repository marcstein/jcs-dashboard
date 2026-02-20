"""Comprehensive firm analytics and reporting commands."""

import json
import click
from rich.console import Console
from rich.table import Table

console = Console()


@click.group()
def reports():
    """Comprehensive firm analytics and reporting."""
    pass


@reports.command("report")
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text",
              help="Output format")
def reports_full_report(output_format: str):
    """Generate full analytics report with all metrics."""
    from firm_analytics import FirmAnalytics, print_full_report

    analytics_engine = FirmAnalytics()

    if output_format == "json":
        report = analytics_engine.generate_full_report()
        console.print(json.dumps(report, indent=2, default=str))
    else:
        print_full_report(analytics_engine)


@reports.command("revenue-type")
def reports_revenue_by_type():
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


@reports.command("revenue-attorney")
def reports_revenue_by_attorney():
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


@reports.command("revenue-monthly")
@click.option("--months", default=12, help="Number of months to show")
def reports_revenue_monthly(months: int):
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


@reports.command("case-length")
def reports_case_length():
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


@reports.command("fees")
def reports_fees():
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


@reports.command("new-cases")
def reports_new_cases():
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


@reports.command("since-august")
@click.option("--year", default=2025, help="Year Ty started")
def reports_since_august(year: int):
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


@reports.command("fee-comparison")
@click.option("--year", default=2025, help="Year for August cutoff")
def reports_fee_comparison(year: int):
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


@reports.command("jurisdiction")
def reports_jurisdiction():
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


@reports.command("zip-codes")
def reports_zip_codes():
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


@reports.command("attorney-monthly")
@click.option("--months", default=6, help="Number of months to show")
def reports_attorney_monthly(months: int):
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
