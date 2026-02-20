"""Case quality verification and tracking commands."""

import click
from datetime import date
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from case_quality import CaseQualityManager

console = Console()


@click.group()
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
