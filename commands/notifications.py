"""Notification management (Slack, Email, SMS)."""

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console()


@click.group()
def notify():
    """Notification management (Slack, Email, SMS)."""
    pass


@notify.command("status")
def notify_status():
    """Show notification system status."""
    from notifications import NotificationManager

    manager = NotificationManager()
    status = manager.get_status()

    console.print(Panel.fit(
        f"[bold]Notification System[/bold]\n\n"
        f"Dry Run Mode: {status['dry_run']}\n"
        f"Enabled Channels: {', '.join(status['enabled_channels'])}\n\n"
        f"Slack Configured: {'Yes' if status['slack_configured'] else 'No'}\n"
        f"Email (SendGrid) Configured: {'Yes' if status['email_configured'] else 'No'}\n"
        f"Email (SMTP/Gmail) Configured: {'Yes' if status.get('smtp_configured') else 'No'}\n"
        f"SMS Configured: {'Yes' if status['sms_configured'] else 'No'}\n\n"
        f"Recent Notifications: {status['recent_notifications']}",
        title="Status"
    ))


@notify.command("test-slack")
@click.option("--message", default="Test message from MyCase automation", help="Message to send")
def notify_test_slack(message: str):
    """Send a test Slack message."""
    from notifications import NotificationManager

    manager = NotificationManager()
    success = manager.send_slack(
        message=message,
        title="Test Alert",
        color="good",
    )

    if success:
        console.print("[green]Slack test sent successfully[/green]")
    else:
        console.print("[red]Failed to send Slack test[/red]")


@notify.command("test-email")
@click.argument("to_email")
@click.option("--subject", default="MyCase Test Email", help="Email subject")
def notify_test_email(to_email: str, subject: str):
    """Send a test email."""
    from notifications import NotificationManager

    manager = NotificationManager()
    success = manager.send_email(
        to_email=to_email,
        subject=subject,
        body_text="This is a test email from the MyCase automation system.",
    )

    if success:
        console.print(f"[green]Email sent to {to_email}[/green]")
    else:
        console.print("[red]Failed to send email[/red]")


@notify.command("send-report")
@click.argument("report_type", type=click.Choice([
    "daily_ar", "intake_weekly", "overdue_tasks",
    "noiw_daily", "noiw_critical", "noiw_workflow"
]))
def notify_send_report(report_type: str):
    """Send a report to Slack."""
    from notifications import NotificationManager

    manager = NotificationManager()
    details = None

    # Get current data for the report
    if report_type == "daily_ar":
        from kpi_tracker import KPITracker
        tracker = KPITracker()
        kpis = tracker.calculate_daily_collections_kpis()

        summary = {
            "total_ar": kpis.get("total_ar", 0),
            "over_60_pct": kpis.get("over_60_pct", 0),
            "compliance_rate": kpis.get("payment_plan_compliance", 0),
            "noiw_count": kpis.get("noiw_pipeline", 0),
            "delinquent": kpis.get("delinquent_plans", 0),
        }

    elif report_type == "intake_weekly":
        from intake_automation import IntakeManager
        intake_mgr = IntakeManager()
        metrics = intake_mgr.get_weekly_intake_metrics()

        summary = {
            "new_cases": metrics.get("new_cases", 0),
            "contact_rate": metrics.get("same_day_contact_rate", 0),
            "dwi_count": metrics.get("dwi_count", 0),
            "traffic_count": metrics.get("traffic_count", 0),
        }

    elif report_type == "overdue_tasks":
        from task_sla import TaskSLAManager
        task_mgr = TaskSLAManager()
        overdue = task_mgr.get_overdue_tasks()

        summary = {"count": len(overdue)}
        details = []
        # Group by assignee
        by_assignee = {}
        for t in overdue:
            name = t.assignee_name
            by_assignee[name] = by_assignee.get(name, 0) + 1

        for name, count in by_assignee.items():
            details.append({"assignee": name, "count": count})

    elif report_type in ["noiw_daily", "noiw_critical", "noiw_workflow"]:
        # NOIW reports
        from payment_plans import PaymentPlanManager
        plans_mgr = PaymentPlanManager()
        noiw_data = plans_mgr.get_noiw_notification_data()

        if report_type == "noiw_daily":
            summary = noiw_data['summary']
        elif report_type == "noiw_critical":
            summary = {
                "case_count": len(noiw_data['critical_cases']),
                "total_balance": sum(c['balance_due'] for c in noiw_data['critical_cases']),
            }
            details = noiw_data['critical_cases']
        else:  # noiw_workflow
            summary = noiw_data['workflow_status']

    success = manager.send_slack_report(report_type, summary, details)

    if success:
        console.print(f"[green]{report_type} report sent to Slack[/green]")
    else:
        console.print("[red]Failed to send report[/red]")


@notify.command("log")
@click.option("--limit", default=20, help="Number of entries to show")
def notify_log(limit: int):
    """Show recent notification log."""
    from notifications import NotificationManager

    manager = NotificationManager()
    logs = manager.get_notification_log(limit)

    if not logs:
        console.print("[yellow]No notification history[/yellow]")
        return

    table = Table(title=f"Recent Notifications ({len(logs)})")
    table.add_column("Time")
    table.add_column("Channel")
    table.add_column("Title")
    table.add_column("Status")

    for log in reversed(logs[-limit:]):
        status = "[green]OK[/green]" if log["success"] else f"[red]FAIL: {log.get('error', '')[:20]}[/red]"
        table.add_row(
            log["timestamp"][:19],
            log["channel"],
            log["title"][:30],
            status,
        )

    console.print(table)


@notify.command("events-report")
@click.argument("to_email")
@click.option("--days", default=7, help="Number of days to include in report")
@click.option("--cc", default=None, help="CC email address")
@click.option("--dry-run", is_flag=True, help="Don't actually send, just preview")
@click.option("--preview", is_flag=True, help="Save HTML preview to file")
def notify_events_report(to_email: str, days: int, cc: str, dry_run: bool, preview: bool):
    """Send upcoming events report via email (SMTP/Gmail)."""
    from events_report import send_events_report, generate_events_report_html, generate_events_report_text
    from config import DATA_DIR

    if preview:
        html, summary = generate_events_report_html(days)
        output_file = DATA_DIR / "events_report_preview.html"
        with open(output_file, 'w') as f:
            f.write(html)
        console.print(f"[green]Preview saved to: {output_file}[/green]")
        console.print(f"Summary: {summary['total_events']} events over {days} days")
        return

    console.print(f"[blue]Generating events report for next {days} days...[/blue]")

    success = send_events_report(
        to_email=to_email,
        days=days,
        cc_email=cc,
        dry_run=dry_run,
    )

    if success:
        if dry_run:
            cc_msg = f" (CC: {cc})" if cc else ""
            console.print(f"[yellow]DRY RUN: Would send report to {to_email}{cc_msg}[/yellow]")
        else:
            cc_msg = f" (CC: {cc})" if cc else ""
            console.print(f"[green]Events report sent to {to_email}{cc_msg}[/green]")
    else:
        console.print("[red]Failed to send events report[/red]")


@notify.command("test-smtp")
@click.argument("to_email")
@click.option("--subject", default="MyCase SMTP Test Email", help="Email subject")
def notify_test_smtp(to_email: str, subject: str):
    """Send a test email via SMTP (Gmail)."""
    from notifications import NotificationManager

    manager = NotificationManager()
    success = manager.send_email_smtp(
        to_email=to_email,
        subject=subject,
        body_text="This is a test email from the MyCase automation system via Gmail SMTP.",
        body_html="<h1>Test Email</h1><p>This is a test email from the <b>MyCase automation system</b> via Gmail SMTP.</p>",
    )

    if success:
        console.print(f"[green]SMTP email sent to {to_email}[/green]")
    else:
        console.print("[red]Failed to send SMTP email. Check SMTP configuration.[/red]")
