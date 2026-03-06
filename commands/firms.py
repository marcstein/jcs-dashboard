"""
commands/firms.py — Firm Management CLI

Manage law firms on the LawMetrics.ai platform:
- List, create, show firm records
- Configure notification settings (SendGrid, Slack, Twilio)
- Migrate existing env-var config into database
- Run database migrations

Usage:
    python agent.py firms list
    python agent.py firms create "Smith & Associates" --id smith_law
    python agent.py firms show jcs_law
    python agent.py firms set-config jcs_law --sendgrid-key SG.xxx
    python agent.py firms migrate-env jcs_law
    python agent.py firms run-migration
"""
import os
import json
import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console()


@click.group()
def firms():
    """Manage law firms on the platform."""
    pass


@firms.command("list")
@click.option("--all", "show_all", is_flag=True, help="Include inactive/cancelled firms")
def list_firms(show_all):
    """List all registered firms."""
    from db.firms import list_firms as _list_firms

    firms_list = _list_firms(active_only=not show_all)

    if not firms_list:
        console.print("[yellow]No firms found.[/yellow]")
        return

    table = Table(title="Registered Firms")
    table.add_column("ID", style="cyan")
    table.add_column("Name", style="bold")
    table.add_column("Status", style="green")
    table.add_column("Tier")
    table.add_column("MyCase", justify="center")
    table.add_column("Last Sync")

    for f in firms_list:
        mc_icon = "✓" if f.get("mycase_connected") else "✗"
        mc_style = "green" if f.get("mycase_connected") else "red"
        last_sync = str(f.get("last_sync_at") or "Never")[:19]
        table.add_row(
            f["id"],
            f["name"],
            f.get("subscription_status", "?"),
            f.get("subscription_tier", "?"),
            f"[{mc_style}]{mc_icon}[/{mc_style}]",
            last_sync,
        )

    console.print(table)


@firms.command("create")
@click.argument("name")
@click.option("--id", "firm_id", required=True, help="Unique firm identifier (e.g., smith_law)")
@click.option("--tier", default="standard", help="Subscription tier")
def create_firm(name, firm_id, tier):
    """Create a new firm record."""
    from db.firms import upsert_firm

    result = upsert_firm(
        firm_id=firm_id,
        name=name,
        subscription_status="trial",
        subscription_tier=tier,
    )

    if result:
        console.print(f"[green]✓ Created firm: {name} (ID: {firm_id})[/green]")
    else:
        console.print(f"[red]✗ Failed to create firm[/red]")


@firms.command("show")
@click.argument("firm_id")
def show_firm(firm_id):
    """Show detailed firm configuration."""
    from firm_settings import FirmSettings

    try:
        settings = FirmSettings(firm_id)
    except ValueError as e:
        console.print(f"[red]✗ {e}[/red]")
        return

    info = settings.get_firm_info()
    dunning = settings.get_dunning_config()
    sync = settings.get_sync_config()
    schedule = settings.get_schedule_config()

    # Basic info panel
    lines = [
        f"[bold]Name:[/bold] {info['name']}",
        f"[bold]ID:[/bold] {info['id']}",
        f"[bold]Status:[/bold] {settings.get_subscription_status()} ({settings.get_subscription_tier()})",
        f"[bold]Phone:[/bold] {info['phone'] or '—'}",
        f"[bold]Email:[/bold] {info['email'] or '—'}",
        f"[bold]Website:[/bold] {info['website'] or '—'}",
    ]
    console.print(Panel("\n".join(lines), title=f"Firm: {info['name']}", border_style="blue"))

    # Notification config
    nc_lines = [
        f"[bold]SendGrid:[/bold] {'✓ Configured' if settings.get_sendgrid_key() else '✗ Not set'}",
        f"[bold]Dunning From:[/bold] {dunning['from_email'] or '—'} ({dunning['from_name']})",
        f"[bold]Slack:[/bold] {'✓ Configured' if settings.get_slack_webhook() else '✗ Not set'}",
        f"[bold]Twilio:[/bold] {'✓ Configured' if settings.has_twilio() else '✗ Not set'}",
    ]
    console.print(Panel("\n".join(nc_lines), title="Notifications", border_style="yellow"))

    # MyCase
    mc = settings.get_mycase_credentials()
    mc_lines = [
        f"[bold]Connected:[/bold] {'✓ Yes' if mc['connected'] else '✗ No'}",
        f"[bold]Client ID:[/bold] {mc['client_id'][:8] + '...' if mc['client_id'] else '—'}",
        f"[bold]Token Expires:[/bold] {mc['token_expires_at'] or '—'}",
    ]
    console.print(Panel("\n".join(mc_lines), title="MyCase Integration", border_style="cyan"))

    # Sync
    sync_lines = [
        f"[bold]Frequency:[/bold] Every {sync['frequency_minutes']} minutes",
        f"[bold]Last Sync:[/bold] {sync['last_sync_at'] or 'Never'}",
        f"[bold]Last Status:[/bold] {sync['last_sync_status'] or '—'}",
    ]
    console.print(Panel("\n".join(sync_lines), title="Sync", border_style="green"))

    # Schedule
    sched_lines = [
        f"[bold]Sync Time:[/bold] {schedule['sync_time']}",
        f"[bold]Dunning Time:[/bold] {schedule['dunning_time']}",
        f"[bold]Reports Time:[/bold] {schedule['reports_time']}",
        f"[bold]Timezone:[/bold] {schedule['timezone']}",
    ]
    console.print(Panel("\n".join(sched_lines), title="Schedule", border_style="magenta"))


@firms.command("set-config")
@click.argument("firm_id")
@click.option("--sendgrid-key", help="SendGrid API key")
@click.option("--dunning-email", help="Dunning notice from email")
@click.option("--dunning-name", help="Dunning notice from name")
@click.option("--slack-webhook", help="Slack webhook URL")
@click.option("--twilio-sid", help="Twilio account SID")
@click.option("--twilio-token", help="Twilio auth token")
@click.option("--twilio-number", help="Twilio from phone number")
@click.option("--firm-phone", help="Firm phone number")
@click.option("--firm-email", help="Firm email address")
@click.option("--firm-website", help="Firm website URL")
@click.option("--subdomain", help="Firm subdomain (e.g. 'jcs' for jcs.lawmetrics.ai)")
def set_config(firm_id, sendgrid_key, dunning_email, dunning_name,
               slack_webhook, twilio_sid, twilio_token, twilio_number,
               firm_phone, firm_email, firm_website, subdomain):
    """Update firm notification and branding configuration."""
    from firm_settings import FirmSettings, clear_settings_cache
    from db.connection import get_connection

    try:
        settings = FirmSettings(firm_id)
    except ValueError as e:
        console.print(f"[red]✗ {e}[/red]")
        return

    # Update notification_config JSONB
    nc_updates = {}
    if sendgrid_key:
        nc_updates["sendgrid_api_key"] = sendgrid_key
    if dunning_email:
        nc_updates["dunning_from_email"] = dunning_email
    if dunning_name:
        nc_updates["dunning_from_name"] = dunning_name
    if slack_webhook:
        nc_updates["slack_webhook_url"] = slack_webhook
    if twilio_sid:
        nc_updates["twilio_account_sid"] = twilio_sid
    if twilio_token:
        nc_updates["twilio_auth_token"] = twilio_token
    if twilio_number:
        nc_updates["twilio_from_number"] = twilio_number

    if nc_updates:
        settings.update_notification_config(**nc_updates)
        console.print(f"[green]✓ Updated notification config: {', '.join(nc_updates.keys())}[/green]")

    # Update firm branding columns directly
    branding_updates = {}
    if firm_phone:
        branding_updates["firm_phone"] = firm_phone
    if firm_email:
        branding_updates["firm_email"] = firm_email
    if firm_website:
        branding_updates["firm_website"] = firm_website

    if branding_updates:
        with get_connection() as conn:
            cur = conn.cursor()
            set_clauses = [f"{k} = %s" for k in branding_updates.keys()]
            set_clauses.append("updated_at = CURRENT_TIMESTAMP")
            cur.execute(
                f"UPDATE firms SET {', '.join(set_clauses)} WHERE id = %s",
                list(branding_updates.values()) + [firm_id],
            )
            conn.commit()
        console.print(f"[green]✓ Updated branding: {', '.join(branding_updates.keys())}[/green]")

    # Update subdomain
    subdomain_updated = False
    if subdomain:
        from db.firms import set_firm_subdomain
        try:
            set_firm_subdomain(firm_id, subdomain)
            console.print(f"[green]✓ Subdomain set: {subdomain}.lawmetrics.ai[/green]")
            subdomain_updated = True
        except ValueError as e:
            console.print(f"[red]✗ Subdomain error: {e}[/red]")

    if not nc_updates and not branding_updates and not subdomain_updated:
        console.print("[yellow]No options provided. Use --help to see available options.[/yellow]")
        return

    clear_settings_cache(firm_id)
    console.print(f"[green]✓ Firm '{firm_id}' configuration updated[/green]")


@firms.command("migrate-env")
@click.argument("firm_id")
@click.option("--dry-run", is_flag=True, help="Show what would be migrated without saving")
def migrate_env(firm_id, dry_run):
    """Migrate current .env variables into the firm's database record."""
    from db.firms import get_firm

    firm = get_firm(firm_id)
    if not firm:
        console.print(f"[red]✗ Firm '{firm_id}' not found. Create it first.[/red]")
        return

    # Build notification_config from env vars
    env_mappings = {
        "sendgrid_api_key": "SENDGRID_API_KEY",
        "sendgrid_from_email": "DUNNING_FROM_EMAIL",
        "sendgrid_from_name": "DUNNING_FROM_NAME",
        "slack_webhook_url": "SLACK_WEBHOOK_URL",
        "twilio_account_sid": "TWILIO_ACCOUNT_SID",
        "twilio_auth_token": "TWILIO_AUTH_TOKEN",
        "twilio_from_number": "TWILIO_FROM_NUMBER",
        "smtp_server": "SMTP_SERVER",
        "smtp_port": "SMTP_PORT",
        "smtp_username": "SMTP_USERNAME",
        "smtp_password": "SMTP_PASSWORD",
        "smtp_from_email": "SMTP_FROM_EMAIL",
        "dunning_from_email": "DUNNING_FROM_EMAIL",
        "dunning_from_name": "DUNNING_FROM_NAME",
    }

    notification_config = {}
    for config_key, env_var in env_mappings.items():
        val = os.getenv(env_var, "")
        if val:
            notification_config[config_key] = val

    # Other firm-specific env vars
    mycase_client_id = os.getenv("MYCASE_CLIENT_ID", "")
    mycase_client_secret = os.getenv("MYCASE_CLIENT_SECRET", "")

    table = Table(title=f"Environment Migration for '{firm_id}'")
    table.add_column("Config Key", style="cyan")
    table.add_column("Env Var", style="dim")
    table.add_column("Value", style="green")

    for config_key, env_var in env_mappings.items():
        val = os.getenv(env_var, "")
        display = val[:20] + "..." if len(val) > 20 else val
        if val:
            table.add_row(config_key, env_var, display)

    if mycase_client_id:
        table.add_row("mycase_client_id", "MYCASE_CLIENT_ID", mycase_client_id[:8] + "...")
    if mycase_client_secret:
        table.add_row("mycase_client_secret", "MYCASE_CLIENT_SECRET", mycase_client_secret[:8] + "...")

    console.print(table)

    if dry_run:
        console.print("[yellow]Dry run — no changes saved.[/yellow]")
        return

    # Save to database
    from db.connection import get_connection

    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            UPDATE firms SET
                notification_config = %s::jsonb,
                mycase_client_id = COALESCE(NULLIF(%s, ''), mycase_client_id),
                mycase_client_secret = COALESCE(NULLIF(%s, ''), mycase_client_secret),
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
        """, (
            json.dumps(notification_config),
            mycase_client_id,
            mycase_client_secret,
            firm_id,
        ))
        conn.commit()

    console.print(f"[green]✓ Migrated {len(notification_config)} config values to firm '{firm_id}'[/green]")


@firms.command("run-migration")
@click.option("--migration", default="001", help="Migration number to run")
def run_migration(migration):
    """Run a database migration script."""
    if migration == "001":
        from db.migrations import run_migration_001
        migrate = run_migration_001
        console.print("[cyan]Running migration 001: Consolidate firms table...[/cyan]")
        success = migrate()
        if success:
            console.print("[green]✓ Migration 001 completed successfully[/green]")
        else:
            console.print("[red]✗ Migration 001 failed[/red]")
    else:
        console.print(f"[red]Unknown migration: {migration}[/red]")
