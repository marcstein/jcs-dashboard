"""Scheduled automation management."""

import click
from datetime import datetime
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

console = Console()


@click.group()
def scheduler():
    """Scheduled automation management."""
    pass


@scheduler.command("status")
def scheduler_status():
    """Show scheduler status and last run times."""
    from scheduler import Scheduler

    sched = Scheduler()
    status = sched.get_status()

    console.print(Panel.fit(
        f"[bold]Scheduler Status[/bold]\n\n"
        f"Enabled Tasks: {status['enabled_tasks']}/{status['total_tasks']}\n"
        f"Dry Run Mode: {status['dry_run_mode']}",
        title="Summary"
    ))

    # Group by frequency
    daily = [t for t in status['tasks'] if t['frequency'] == 'daily']
    weekly = [t for t in status['tasks'] if t['frequency'] == 'weekly']
    monthly = [t for t in status['tasks'] if t['frequency'] == 'monthly']

    for freq_name, tasks in [("Daily", daily), ("Weekly", weekly), ("Monthly", monthly)]:
        if not tasks:
            continue

        table = Table(title=f"{freq_name} Tasks")
        table.add_column("Status")
        table.add_column("Task")
        table.add_column("Time")
        table.add_column("Owner")
        table.add_column("Last Run")

        for task in tasks:
            status_icon = "[green]ON[/green]" if task['enabled'] else "[red]OFF[/red]"
            schedule = task['run_at']
            if task.get('day_of_week'):
                schedule = f"{task['day_of_week'][:3]} {schedule}"
            if task.get('day_of_month'):
                schedule = f"Day {task['day_of_month']} {schedule}"

            table.add_row(
                status_icon,
                task['name'],
                schedule,
                (task['owner'] or '-')[:15],
                task['last_run'][:19] if task['last_run'] != 'Never' else 'Never'
            )

        console.print(table)


@scheduler.command("list")
@click.option("--frequency", type=click.Choice(["daily", "weekly", "monthly"]))
def scheduler_list(frequency: str):
    """List all scheduled tasks."""
    from scheduler import Scheduler, TaskFrequency

    sched = Scheduler()
    freq = TaskFrequency(frequency) if frequency else None
    tasks = sched.list_tasks(freq)

    for task in tasks:
        enabled = "[green]enabled[/green]" if sched.is_task_enabled(task.name) else "[red]disabled[/red]"
        console.print(f"\n[bold]{task.name}[/bold] ({enabled})")
        console.print(f"  {task.description}")
        console.print(f"  Frequency: {task.frequency.value} @ {task.run_at.strftime('%H:%M')}")
        if task.day_of_week:
            console.print(f"  Day: {task.day_of_week.name}")
        if task.owner:
            console.print(f"  Owner: {task.owner}")
        console.print(f"  Command: {task.command}")


@scheduler.command("run")
@click.argument("task_name")
@click.option("--force", is_flag=True, help="Force run even if not scheduled")
def scheduler_run(task_name: str, force: bool):
    """Run a specific scheduled task."""
    from scheduler import Scheduler

    sched = Scheduler()
    task = sched.get_task(task_name)

    if not task:
        console.print(f"[red]Unknown task: {task_name}[/red]")
        console.print("\nAvailable tasks:")
        for t in sched.list_tasks():
            console.print(f"  - {t.name}")
        return

    console.print(f"Running task: [bold]{task.name}[/bold]")
    console.print(f"Command: {task.command}\n")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        progress.add_task(f"Executing {task.name}...", total=None)
        result = sched.run_task(task, force=force)

    if result['success']:
        console.print("[green]Task completed successfully[/green]")
    else:
        console.print(f"[red]Task failed: {result['error']}[/red]")

    if result['output']:
        console.print("\n[bold]Output:[/bold]")
        console.print(result['output'])


@scheduler.command("run-due")
@click.option("--frequency", type=click.Choice(["daily", "weekly", "monthly"]))
def scheduler_run_due(frequency: str):
    """Run all tasks that are currently due."""
    from scheduler import Scheduler, TaskFrequency

    sched = Scheduler()
    freq = TaskFrequency(frequency) if frequency else None

    console.print("Checking for due tasks...")
    results = sched.run_due_tasks(freq)

    if not results:
        console.print("[yellow]No tasks due to run[/yellow]")
        return

    table = Table(title=f"Task Results ({len(results)} tasks)")
    table.add_column("Status")
    table.add_column("Task")
    table.add_column("Duration")
    table.add_column("Error")

    for result in results:
        status = "[green]OK[/green]" if result['success'] else "[red]FAIL[/red]"
        started = datetime.fromisoformat(result['started_at'])
        finished = datetime.fromisoformat(result['finished_at']) if result['finished_at'] else datetime.now()
        duration = (finished - started).total_seconds()

        table.add_row(
            status,
            result['task'],
            f"{duration:.1f}s",
            (result['error'] or '-')[:30]
        )

    console.print(table)


@scheduler.command("enable")
@click.argument("task_name")
def scheduler_enable(task_name: str):
    """Enable a scheduled task."""
    from scheduler import Scheduler

    sched = Scheduler()
    if task_name not in sched.tasks:
        console.print(f"[red]Unknown task: {task_name}[/red]")
        return

    sched.enable_task(task_name)
    console.print(f"[green]Enabled task: {task_name}[/green]")


@scheduler.command("disable")
@click.argument("task_name")
def scheduler_disable(task_name: str):
    """Disable a scheduled task."""
    from scheduler import Scheduler

    sched = Scheduler()
    if task_name not in sched.tasks:
        console.print(f"[red]Unknown task: {task_name}[/red]")
        return

    sched.disable_task(task_name)
    console.print(f"[yellow]Disabled task: {task_name}[/yellow]")


@scheduler.group()
def cron():
    """Cron job management."""
    pass


@cron.command("show")
def cron_show():
    """Show cron entries that would be installed."""
    from scheduler import Scheduler

    sched = Scheduler()
    entries = sched.generate_cron_entries()
    console.print("[bold]Cron Entries:[/bold]\n")
    console.print(entries)


@cron.command("install")
@click.option("--dry-run/--execute", default=True, help="Dry run or actually install")
def cron_install(dry_run: bool):
    """Install cron entries for automated scheduling."""
    from scheduler import Scheduler

    sched = Scheduler()
    result = sched.install_cron(dry_run=dry_run)
    console.print(result)


@cron.command("remove")
def cron_remove():
    """Remove scheduler cron entries."""
    from scheduler import Scheduler

    sched = Scheduler()
    result = sched.remove_cron()
    console.print(result)
