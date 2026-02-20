"""Payment promise tracking."""

import click
from datetime import datetime
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console()


@click.group()
def promises():
    """Payment promise tracking."""
    pass


@promises.command("add")
@click.argument("contact_id", type=int)
@click.argument("amount", type=float)
@click.argument("promise_date", type=str)
@click.option("--case-id", type=int, help="Related case ID")
@click.option("--case-name", help="Related case name")
@click.option("--contact-name", help="Contact name")
@click.option("--invoice-id", type=int, help="Related invoice ID")
@click.option("--notes", help="Additional notes")
@click.option("--recorded-by", default="Staff", help="Staff member recording")
def promises_add(contact_id: int, amount: float, promise_date: str,
                 case_id: int, case_name: str, contact_name: str,
                 invoice_id: int, notes: str, recorded_by: str):
    """Record a payment promise. DATE format: YYYY-MM-DD"""
    from promises import PromiseTracker

    tracker = PromiseTracker()
    parsed_date = datetime.strptime(promise_date, "%Y-%m-%d").date()

    promise_id = tracker.record_promise(
        contact_id=contact_id,
        promised_amount=amount,
        promised_date=parsed_date,
        recorded_by=recorded_by,
        contact_name=contact_name,
        case_id=case_id,
        case_name=case_name,
        invoice_id=invoice_id,
        notes=notes,
    )

    console.print(f"[green]Promise #{promise_id} recorded:[/green]")
    console.print(f"  Amount: ${amount:,.2f}")
    console.print(f"  Due: {promise_date}")


@promises.command("list")
@click.option("--status", type=click.Choice(["pending", "kept", "broken", "all"]), default="pending")
@click.option("--contact-id", type=int, help="Filter by contact")
@click.option("--case-id", type=int, help="Filter by case")
def promises_list(status: str, contact_id: int, case_id: int):
    """List payment promises."""
    from promises import PromiseTracker

    tracker = PromiseTracker()

    if contact_id:
        promises_list = tracker.get_by_contact(contact_id)
    elif case_id:
        promises_list = tracker.get_by_case(case_id)
    elif status == "pending":
        promises_list = tracker.get_pending_promises()
    else:
        # Get all (would need a new method, for now just pending)
        promises_list = tracker.get_pending_promises()

    if not promises_list:
        console.print("[yellow]No promises found[/yellow]")
        return

    table = Table(title=f"Payment Promises ({len(promises_list)})")
    table.add_column("ID", justify="right")
    table.add_column("Contact")
    table.add_column("Case")
    table.add_column("Amount", justify="right")
    table.add_column("Due Date")
    table.add_column("Status")
    table.add_column("Days")

    for p in promises_list[:20]:
        status_color = {
            "pending": "yellow",
            "kept": "green",
            "broken": "red",
            "partial": "cyan",
        }.get(p.status.value, "white")

        days_display = ""
        if p.status.value == "pending":
            if p.days_until_due > 0:
                days_display = f"{p.days_until_due}d left"
            elif p.days_overdue > 0:
                days_display = f"[red]{p.days_overdue}d late[/red]"
            else:
                days_display = "[yellow]TODAY[/yellow]"

        table.add_row(
            str(p.id),
            p.contact_name[:20],
            (p.case_name or "-")[:20],
            f"${p.promised_amount:,.2f}",
            str(p.promised_date),
            f"[{status_color}]{p.status.value}[/{status_color}]",
            days_display,
        )

    console.print(table)


@promises.command("due-today")
def promises_due_today():
    """Show promises due today."""
    from promises import PromiseTracker

    tracker = PromiseTracker()
    due = tracker.get_due_today()

    if not due:
        console.print("[green]No promises due today[/green]")
        return

    console.print(f"[bold]{len(due)} promises due today:[/bold]\n")

    for p in due:
        console.print(f"  • {p.contact_name}: ${p.promised_amount:,.2f}")
        if p.case_name:
            console.print(f"    Case: {p.case_name}")


@promises.command("overdue")
def promises_overdue():
    """Show overdue promises."""
    from promises import PromiseTracker

    tracker = PromiseTracker()
    overdue = tracker.get_overdue()

    if not overdue:
        console.print("[green]No overdue promises[/green]")
        return

    table = Table(title=f"Overdue Promises ({len(overdue)})")
    table.add_column("Contact")
    table.add_column("Case")
    table.add_column("Amount", justify="right")
    table.add_column("Promise Date")
    table.add_column("Days Overdue", justify="right", style="red")

    for p in overdue:
        table.add_row(
            p.contact_name[:20],
            (p.case_name or "-")[:20],
            f"${p.promised_amount:,.2f}",
            str(p.promised_date),
            str(p.days_overdue),
        )

    console.print(table)


@promises.command("kept")
@click.argument("promise_id", type=int)
@click.argument("amount", type=float)
def promises_kept(promise_id: int, amount: float):
    """Mark a promise as kept."""
    from promises import PromiseTracker

    tracker = PromiseTracker()
    tracker.mark_kept(promise_id, amount)
    console.print(f"[green]Promise #{promise_id} marked as kept (${amount:,.2f})[/green]")


@promises.command("broken")
@click.argument("promise_id", type=int)
@click.option("--notes", help="Notes about why broken")
def promises_broken(promise_id: int, notes: str):
    """Mark a promise as broken."""
    from promises import PromiseTracker

    tracker = PromiseTracker()
    tracker.mark_broken(promise_id, notes)
    console.print(f"[red]Promise #{promise_id} marked as broken[/red]")


@promises.command("check")
def promises_check():
    """Run daily promise check and report."""
    from promises import PromiseTracker

    tracker = PromiseTracker()
    report = tracker.generate_daily_report()
    console.print(report)


@promises.command("stats")
@click.option("--days", default=30, help="Days back to analyze")
def promises_stats(days: int):
    """Show promise-keeping statistics."""
    from promises import PromiseTracker

    tracker = PromiseTracker()
    stats = tracker.get_promise_stats(days)

    console.print(Panel.fit(
        f"[bold]Promise Statistics ({days} Days)[/bold]\n\n"
        f"Total Promises: {stats['total_promises']}\n"
        f"Keep Rate: {stats['keep_rate']:.1f}%\n\n"
        f"Kept: {stats['kept']}\n"
        f"Broken: {stats['broken']}\n"
        f"Partial: {stats['partial']}\n"
        f"Pending: {stats['pending']}\n\n"
        f"Total Promised: ${stats['total_promised']:,.2f}\n"
        f"Total Collected: ${stats['total_collected']:,.2f}",
        title="Summary"
    ))
