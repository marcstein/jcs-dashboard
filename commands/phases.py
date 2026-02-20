"""Case phase tracking and analytics commands."""

import json
import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn

console = Console()


@click.group()
def phases():
    """Case phase tracking and analytics."""
    pass


@phases.command("init")
def phases_init():
    """Initialize default phases, mappings, and workflows."""
    from case_phases import get_phase_db, CasePhaseManager

    db = get_phase_db()
    manager = CasePhaseManager(db)
    result = manager.initialize()

    console.print(Panel.fit(
        f"[bold]Initialization Complete[/bold]\n\n"
        f"Phases added: {result['phases_added']}\n"
        f"Stage mappings added: {result['mappings_added']}\n"
        f"Workflows added: {result['workflows_added']}",
        title="Case Phases"
    ))


@phases.command("list")
def phases_list():
    """List all 7 universal phases."""
    from case_phases import get_phase_db

    db = get_phase_db()
    phases_data = db.get_phases()

    if not phases_data:
        console.print("[yellow]No phases configured. Run 'phases init' first.[/yellow]")
        return

    table = Table(title="7 Universal Case Phases")
    table.add_column("#", justify="right", style="cyan")
    table.add_column("Phase", style="bold")
    table.add_column("Short Name")
    table.add_column("Owner")
    table.add_column("Duration", justify="center")
    table.add_column("Terminal")

    for p in phases_data:
        terminal = "[dim]Yes[/dim]" if p.is_terminal else ""
        duration = f"{p.typical_duration_min_days}-{p.typical_duration_max_days}d"
        table.add_row(
            str(p.display_order),
            p.name,
            p.short_name,
            p.primary_responsibility,
            duration,
            terminal
        )

    console.print(table)


@phases.command("mappings")
def phases_mappings():
    """List MyCase stage-to-phase mappings."""
    from case_phases import get_phase_db

    db = get_phase_db()
    mappings = db.get_stage_mappings()

    if not mappings:
        console.print("[yellow]No mappings configured. Run 'phases init' first.[/yellow]")
        return

    table = Table(title="Stage → Phase Mappings")
    table.add_column("MyCase Stage", style="cyan")
    table.add_column("Phase Code")
    table.add_column("Phase Name")

    for m in mappings:
        table.add_row(
            m['mycase_stage_name'],
            m['phase_code'],
            m.get('phase_short_name') or m.get('phase_name', '')
        )

    console.print(table)
    console.print(f"\n[dim]Total mappings: {len(mappings)}[/dim]")


@phases.command("workflows")
def phases_workflows():
    """List case-type specific workflows."""
    from case_phases import get_phase_db

    db = get_phase_db()
    workflows = db.get_workflows()

    if not workflows:
        console.print("[yellow]No workflows configured. Run 'phases init' first.[/yellow]")
        return

    for w in workflows:
        console.print(Panel.fit(
            f"[bold]{w.name}[/bold] [{w.code}]\n\n"
            f"Applies to: {', '.join(w.case_type_patterns)}\n"
            f"{w.description}\n\n"
            f"[bold]Stages:[/bold]\n" +
            "\n".join([f"  {s['order']}. {s['name']}" for s in w.stages]),
            title=f"Workflow: {w.code}"
        ))


@phases.command("sync")
@click.option("--stages-only", is_flag=True, help="Only sync stage definitions from MyCase")
def phases_sync(stages_only: bool):
    """Sync case phases from MyCase cache."""
    from case_phases import get_phase_db, CasePhaseManager
    from cache import get_cache
    from api_client import get_client

    db = get_phase_db()
    cache = get_cache()
    api_client = get_client()
    manager = CasePhaseManager(db, cache, api_client)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        if stages_only:
            task = progress.add_task("Syncing stages from MyCase API...", total=None)
            count = manager.sync_stages_from_mycase()
            console.print(f"\n[green]Synced {count} stages from MyCase[/green]")
            return

        task = progress.add_task("Syncing case phases...", total=None)
        result = manager.sync_case_phases()

    console.print(Panel.fit(
        f"[bold]Sync Complete[/bold]\n\n"
        f"Cases processed: {result['cases_processed']}\n"
        f"New phase entries: {result['new_entries']}\n"
        f"Phase transitions: {result['updated']}",
        title="Phase Sync"
    ))

    if result['unmapped_stages']:
        console.print(f"\n[yellow]Unmapped stages ({len(result['unmapped_stages'])}):[/yellow]")
        unique_stages = set(s['stage_name'] for s in result['unmapped_stages'])
        for stage in sorted(unique_stages)[:10]:
            console.print(f"  • {stage}")
        if len(unique_stages) > 10:
            console.print(f"  ... and {len(unique_stages) - 10} more")


@phases.command("report")
@click.option("--json-output", is_flag=True, help="Output as JSON")
def phases_report(json_output: bool):
    """Generate phase distribution report."""
    from case_phases import get_phase_db, CasePhaseManager
    from cache import get_cache

    db = get_phase_db()
    cache = get_cache()
    manager = CasePhaseManager(db, cache)

    # First sync to get current data
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        progress.add_task("Syncing and generating report...", total=None)
        manager.sync_case_phases()
        report = manager.get_phase_report()

    if json_output:
        console.print(json.dumps(report, indent=2, default=str))
        return

    console.print(Panel.fit(
        f"[bold]Phase Distribution Report[/bold]\n\n"
        f"Total Active Cases: {report['total_cases']}\n"
        f"Stalled Cases (>30 days): {report['stalled_cases']}",
        title="Summary"
    ))

    # Phase distribution table
    table = Table(title="Cases by Phase")
    table.add_column("Phase", style="bold")
    table.add_column("Cases", justify="right")
    table.add_column("Avg Days", justify="right")
    table.add_column("Typical", justify="center")
    table.add_column("Status")

    for p in report['phases']:
        if p['current_cases'] == 0:
            continue

        typical = f"{p['typical_min_days']}-{p['typical_max_days']}d"

        # Determine status based on avg days vs typical max
        if p['avg_days_in_phase'] and p['avg_days_in_phase'] > p['typical_max_days']:
            status = "[red]⚠ Over typical[/red]"
        elif p['avg_days_in_phase'] and p['avg_days_in_phase'] > p['typical_max_days'] * 0.8:
            status = "[yellow]Near limit[/yellow]"
        else:
            status = "[green]On track[/green]"

        table.add_row(
            p['short_name'],
            str(p['current_cases']),
            f"{p['avg_days_in_phase']:.0f}d" if p['avg_days_in_phase'] else "-",
            typical,
            status
        )

    console.print(table)


@phases.command("stalled")
@click.option("--days", default=30, help="Threshold days to consider stalled")
@click.option("--limit", default=20, help="Max cases to show")
def phases_stalled(days: int, limit: int):
    """List cases stalled in their current phase."""
    from case_phases import get_phase_db

    db = get_phase_db()
    stalled = db.get_stalled_cases(days)

    if not stalled:
        console.print(f"[green]No cases stalled more than {days} days![/green]")
        return

    table = Table(title=f"Stalled Cases (>{days} days in phase)")
    table.add_column("Days", justify="right", style="red")
    table.add_column("Case")
    table.add_column("Phase")
    table.add_column("Stage")
    table.add_column("Typical Max", justify="right")

    for case in stalled[:limit]:
        days_in = int(case['days_in_phase']) if case['days_in_phase'] else 0
        typical_max = case.get('typical_duration_max_days') or '-'
        table.add_row(
            str(days_in),
            (case['case_name'] or f"Case {case['case_id']}")[:30],
            case['phase_code'],
            (case['mycase_stage_name'] or '-')[:25],
            str(typical_max) + 'd' if typical_max != '-' else '-'
        )

    console.print(table)
    if len(stalled) > limit:
        console.print(f"\n[dim]Showing {limit} of {len(stalled)} stalled cases[/dim]")


@phases.command("case")
@click.argument("case_id", type=int)
def phases_case(case_id: int):
    """Show phase history for a specific case."""
    from case_phases import get_phase_db

    db = get_phase_db()
    history = db.get_case_phase_history(case_id)

    if not history:
        console.print(f"[yellow]No phase history for case {case_id}[/yellow]")
        return

    case_name = history[0].get('case_name') or f"Case {case_id}"
    console.print(f"\n[bold]Phase History: {case_name}[/bold]\n")

    table = Table()
    table.add_column("Phase")
    table.add_column("Stage")
    table.add_column("Entered")
    table.add_column("Exited")
    table.add_column("Duration", justify="right")

    for h in history:
        entered = h['entered_at'][:10] if h['entered_at'] else '-'
        exited = h['exited_at'][:10] if h['exited_at'] else '[dim]current[/dim]'
        duration = f"{h['duration_days']:.0f}d" if h['duration_days'] else '-'

        table.add_row(
            h['phase_name'] or h['phase_code'],
            h['mycase_stage_name'] or '-',
            entered,
            exited,
            duration
        )

    console.print(table)


@phases.command("notify-attorneys")
@click.option("--days", default=30, help="Threshold days to consider stalled")
@click.option("--slack/--no-slack", default=True, help="Send Slack notifications")
@click.option("--email/--no-email", default=False, help="Send email notifications")
def phases_notify_attorneys(days: int, slack: bool, email: bool):
    """Notify attorneys about their stalled cases."""
    from case_phases import get_phase_db
    from cache import get_cache
    from notifications import NotificationManager

    db = get_phase_db()
    cache = get_cache()
    notifier = NotificationManager()

    # Get stalled cases
    stalled = db.get_stalled_cases(days)

    if not stalled:
        console.print(f"[green]No cases stalled more than {days} days![/green]")
        return

    # Get attorney info for each case from cache
    with cache._get_connection() as conn:
        cursor = conn.cursor()

        # Group stalled cases by attorney
        by_attorney = {}
        for case in stalled:
            case_id = case['case_id']
            cursor.execute("""
                SELECT lead_attorney_id, lead_attorney_name
                FROM cached_cases
                WHERE id = ?
            """, (case_id,))
            row = cursor.fetchone()

            if row and row['lead_attorney_name']:
                attorney = row['lead_attorney_name']
                if attorney not in by_attorney:
                    by_attorney[attorney] = []
                by_attorney[attorney].append({
                    'case_id': case_id,
                    'case_name': case['case_name'] or f"Case {case_id}",
                    'phase': case['phase_name'] or case['phase_code'],
                    'days_in_phase': int(case['days_in_phase']) if case['days_in_phase'] else 0,
                    'stage': case.get('mycase_stage_name') or '-',
                    'typical_max': case.get('typical_duration_max_days'),
                })

    if not by_attorney:
        console.print("[yellow]No stalled cases with assigned attorneys found[/yellow]")
        return

    # Display summary
    console.print(f"\n[bold]Stalled Cases by Attorney[/bold] (>{days} days in phase)\n")

    for attorney, cases in sorted(by_attorney.items(), key=lambda x: len(x[1]), reverse=True):
        console.print(f"[bold]{attorney}[/bold]: {len(cases)} stalled cases")
        for c in cases[:3]:
            console.print(f"  - {c['case_name'][:30]} ({c['days_in_phase']}d in {c['phase']})")
        if len(cases) > 3:
            console.print(f"  [dim]...and {len(cases) - 3} more[/dim]")

    # Send notifications
    if slack:
        # Build Slack message
        total_stalled = sum(len(cases) for cases in by_attorney.values())
        summary = {
            'total_stalled': total_stalled,
            'threshold_days': days,
            'attorneys': [
                {
                    'name': attorney,
                    'count': len(cases),
                    'cases': [
                        {
                            'name': c['case_name'][:30],
                            'days': c['days_in_phase'],
                            'phase': c['phase'],
                        }
                        for c in cases[:5]
                    ]
                }
                for attorney, cases in sorted(by_attorney.items(), key=lambda x: len(x[1]), reverse=True)[:10]
            ]
        }
        success = notifier.send_slack_report("stalled_cases", summary)
        if success:
            console.print(f"\n[green]Slack notification sent ({total_stalled} stalled cases)[/green]")
        else:
            console.print("[red]Failed to send Slack notification[/red]")

    if email:
        # Send individual emails to each attorney (placeholder)
        console.print("[yellow]Email notifications not yet configured[/yellow]")
        console.print("Configure attorney emails in data/notifications_config.json")
