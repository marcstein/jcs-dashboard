"""Intake tracking, conversion metrics, and CRM pipeline commands."""

import click
import os
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


@intake.command("send-reminders")
@click.option("--firm-id", default=None, help="Firm ID (defaults to FIRM_ID env)")
@click.option("--dry-run", is_flag=True, help="Preview without sending")
def send_reminders(firm_id: str, dry_run: bool):
    """Process and send due consultation reminders (email + SMS)."""
    firm_id = firm_id or os.getenv("FIRM_ID", "jcs_law")

    from db.intake import get_pending_reminders, mark_reminder_sent
    from notifications import NotificationManager

    reminders = get_pending_reminders(firm_id)

    if not reminders:
        console.print("[dim]No pending reminders to send.[/dim]")
        return

    console.print(f"[bold]{len(reminders)} reminder(s) due[/bold]\n")
    nm = NotificationManager(firm_id=firm_id)

    sent = 0
    failed = 0
    for r in reminders:
        name = f"{r['first_name']} {r['last_name']}"
        rtype = r["reminder_type"]
        channel = r["channel"]
        consult_date = r["consultation_date"]
        start = r["start_time"]
        attorney = r["attorney_name"] or "your attorney"
        ctype = r["consultation_type"] or "phone"

        # Format the time display
        if hasattr(start, 'strftime'):
            time_str = start.strftime("%I:%M %p")
        else:
            time_str = str(start)

        if hasattr(consult_date, 'strftime'):
            date_str = consult_date.strftime("%A, %B %d, %Y")
        else:
            date_str = str(consult_date)

        if channel == "email":
            subject = f"Reminder: Consultation {'Tomorrow' if '24h' in rtype else 'in 1 Hour'}"
            body = (
                f"Dear {r['first_name']},\n\n"
                f"This is a reminder about your upcoming {ctype} consultation:\n\n"
                f"  Date: {date_str}\n"
                f"  Time: {time_str}\n"
                f"  Attorney: {attorney}\n"
            )
            if r.get("meeting_url"):
                body += f"  Meeting Link: {r['meeting_url']}\n"
            if r.get("location"):
                body += f"  Location: {r['location']}\n"
            body += (
                f"\nIf you need to reschedule, please contact us as soon as possible.\n\n"
                f"Best regards"
            )

            if dry_run:
                console.print(f"  [yellow]DRY-RUN[/yellow] Email to {r['email']}: {subject}")
                sent += 1
                continue

            if r.get("email"):
                ok = nm.send_email(r["email"], subject, body)
                if ok:
                    mark_reminder_sent(r["id"])
                    console.print(f"  [green]✓[/green] Email sent to {r['email']} ({rtype})")
                    sent += 1
                else:
                    mark_reminder_sent(r["id"], error_message="SendGrid send failed")
                    console.print(f"  [red]✗[/red] Email failed for {name}")
                    failed += 1
            else:
                mark_reminder_sent(r["id"], error_message="No email address")
                failed += 1

        elif channel == "sms":
            msg = (
                f"Reminder: Your {ctype} consultation is "
                f"{'tomorrow' if '24h' in rtype else 'in 1 hour'} "
                f"at {time_str} with {attorney}."
            )
            if r.get("meeting_url"):
                msg += f" Link: {r['meeting_url']}"

            if dry_run:
                console.print(f"  [yellow]DRY-RUN[/yellow] SMS to {r['phone']}: {msg[:60]}...")
                sent += 1
                continue

            if r.get("phone"):
                ok = nm.send_sms(r["phone"], msg)
                if ok:
                    mark_reminder_sent(r["id"])
                    console.print(f"  [green]✓[/green] SMS sent to {r['phone']} ({rtype})")
                    sent += 1
                else:
                    mark_reminder_sent(r["id"], error_message="Twilio send failed")
                    console.print(f"  [red]✗[/red] SMS failed for {name}")
                    failed += 1
            else:
                mark_reminder_sent(r["id"], error_message="No phone number")
                failed += 1

    console.print(f"\n[bold]Done:[/bold] {sent} sent, {failed} failed")


@intake.command("reminder-stats")
@click.option("--firm-id", default=None, help="Firm ID")
@click.option("--days", default=30, help="Days to look back")
def reminder_stats(firm_id: str, days: int):
    """Show consultation reminder statistics."""
    firm_id = firm_id or os.getenv("FIRM_ID", "jcs_law")

    from db.intake import get_reminder_stats
    stats = get_reminder_stats(firm_id, days)

    console.print(Panel.fit(
        f"[bold]Total:[/bold] {stats['total']}\n"
        f"[green]Sent:[/green] {stats['sent']}  "
        f"[red]Failed:[/red] {stats['failed']}  "
        f"[yellow]Pending:[/yellow] {stats['pending']}  "
        f"[dim]Cancelled:[/dim] {stats['cancelled']}\n"
        f"[blue]Email:[/blue] {stats['email_total']}  "
        f"[cyan]SMS:[/cyan] {stats['sms_total']}",
        title=f"Reminder Stats (last {days} days)"
    ))
