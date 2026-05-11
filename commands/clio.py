"""Clio Manage integration commands — sync, auth, and cache management."""
import sys

import click
from rich.console import Console
from rich.table import Table

console = Console()


@click.group("clio")
def clio_group():
    """Clio Manage API integration — sync data, manage auth, inspect cache."""
    pass


# ── Connection Test ────────────────────────────────────────────

@clio_group.command("test")
@click.option("--firm-id", required=True, help="Firm ID with Clio credentials")
def test_connection(firm_id: str):
    """Test the Clio API connection."""
    from clio_client import ClioClient

    console.print(f"\n[bold]Testing Clio connection for firm: {firm_id}[/bold]\n")
    try:
        client = ClioClient(firm_id)
        result = client.test_connection()
        client.close()

        if result.get("connected"):
            console.print(f"[green]Connected![/green]")
            console.print(f"  User: {result.get('user_name')}")
            console.print(f"  Email: {result.get('user_email')}")
            console.print(f"  ID: {result.get('user_id')}")
        else:
            console.print(f"[red]Connection failed:[/red] {result.get('error')}")
            sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


# ── OAuth Flow ─────────────────────────────────────────────────

@clio_group.command("auth-url")
@click.option("--firm-id", required=True, help="Firm ID")
@click.option("--redirect-uri", default="https://app.lawmetrics.ai/oauth/clio/callback",
              help="OAuth redirect URI")
def auth_url(firm_id: str, redirect_uri: str):
    """Get the Clio OAuth authorization URL."""
    from clio_client import ClioAuth

    try:
        auth = ClioAuth(firm_id)
        url = auth.get_authorization_url(redirect_uri)
        console.print(f"\n[bold]Open this URL in a browser to authorize:[/bold]\n")
        console.print(f"  {url}\n")
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


@clio_group.command("exchange-code")
@click.option("--firm-id", required=True, help="Firm ID")
@click.option("--code", required=True, help="Authorization code from Clio redirect")
@click.option("--redirect-uri", default="https://app.lawmetrics.ai/oauth/clio/callback",
              help="OAuth redirect URI (must match auth-url)")
def exchange_code(firm_id: str, code: str, redirect_uri: str):
    """Exchange an authorization code for access + refresh tokens."""
    from clio_client import ClioAuth

    try:
        auth = ClioAuth(firm_id)
        token_data = auth.exchange_code(code, redirect_uri)
        console.print(f"\n[green]Tokens saved successfully![/green]")
        console.print(f"  Access token expires in: {token_data.get('expires_in', 0) // 3600} hours")
        console.print(f"  Refresh token: {'present' if token_data.get('refresh_token') else 'none'}")
    except Exception as e:
        console.print(f"[red]Token exchange failed:[/red] {e}")
        sys.exit(1)


@clio_group.command("refresh-token")
@click.option("--firm-id", required=True, help="Firm ID")
def refresh_token(firm_id: str):
    """Manually refresh the Clio access token."""
    from clio_client import ClioAuth

    try:
        auth = ClioAuth(firm_id)
        auth.refresh_access_token()
        console.print(f"[green]Token refreshed for firm {firm_id}[/green]")
    except Exception as e:
        console.print(f"[red]Refresh failed:[/red] {e}")
        sys.exit(1)


# ── Sync ───────────────────────────────────────────────────────

@clio_group.command("sync")
@click.option("--firm-id", required=True, help="Firm ID with Clio credentials")
@click.option("--force", is_flag=True, help="Force full sync (skip incremental)")
@click.option("--entity", "-e", multiple=True, help="Sync specific entities only")
def sync_data(firm_id: str, force: bool, entity: tuple):
    """Sync all data from Clio Manage API to local cache.

    Supports incremental sync using Clio's updated_since parameter.
    """
    from clio_sync import ClioSyncManager

    console.print(f"\n[bold]Syncing Clio data for firm: {firm_id}[/bold]")
    if force:
        console.print("[yellow]Full sync forced[/yellow]")
    console.print()

    try:
        with ClioSyncManager(firm_id) as manager:
            entities = list(entity) if entity else None
            results = manager.sync_all(force_full=force, entities=entities)

        # Display summary table
        table = Table(title="Clio Sync Results")
        table.add_column("Entity")
        table.add_column("Fetched", justify="right")
        table.add_column("In Cache", justify="right")
        table.add_column("Mode")
        table.add_column("Duration", justify="right")
        table.add_column("Status")

        total_fetched = 0
        total_cached = 0
        errors = 0

        for entity_type, result in results.items():
            total_fetched += result.records_fetched
            total_cached += result.records_in_cache

            status = "[green]OK[/green]"
            if result.error:
                status = f"[red]ERROR[/red]"
                errors += 1

            mode = "incremental" if result.incremental else "full"

            table.add_row(
                entity_type,
                str(result.records_fetched),
                str(result.records_in_cache),
                mode,
                f"{result.duration_seconds:.1f}s",
                status,
            )

        console.print(table)
        console.print(f"\n  Total fetched: {total_fetched}")
        console.print(f"  Total in cache: {total_cached}")
        if errors:
            console.print(f"  [red]Errors: {errors}[/red]")
        console.print()

    except Exception as e:
        console.print(f"[red]Sync failed:[/red] {e}")
        sys.exit(1)


# ── Cache Status ───────────────────────────────────────────────

@clio_group.command("status")
@click.option("--firm-id", required=True, help="Firm ID")
def cache_status(firm_id: str):
    """Show Clio cache status — record counts and last sync times."""
    from clio_sync import ClioSyncManager

    console.print(f"\n[bold]Clio Cache Status — {firm_id}[/bold]\n")

    try:
        with ClioSyncManager(firm_id) as manager:
            summary = manager.get_sync_summary()

        table = Table()
        table.add_column("Entity")
        table.add_column("Records", justify="right")
        table.add_column("Last Sync")
        table.add_column("Duration", justify="right")
        table.add_column("Error")

        total = 0
        for entity_type, info in summary.items():
            count = info["cached_records"]
            total += count
            last = str(info["last_sync"])[:19] if info["last_sync"] else "never"
            dur = f"{info['duration']:.1f}s" if info["duration"] else "-"
            err = info["last_error"][:40] if info["last_error"] else ""

            table.add_row(entity_type, str(count), last, dur, err)

        console.print(table)
        console.print(f"\n  Total cached records: {total}\n")

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


# ── Setup — seed Clio credentials into firms table ─────────────

@clio_group.command("setup")
@click.option("--firm-id", required=True, help="Firm ID")
@click.option("--client-id", required=True, help="Clio OAuth client_id")
@click.option("--client-secret", required=True, help="Clio OAuth client_secret")
def setup_clio(firm_id: str, client_id: str, client_secret: str):
    """Configure Clio API credentials for a firm."""
    from db.connection import get_connection

    console.print(f"\n[bold]Setting up Clio credentials for firm: {firm_id}[/bold]\n")

    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            UPDATE firms SET
                pms_type = 'clio',
                clio_client_id = %s,
                clio_client_secret = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
        """, (client_id, client_secret, firm_id))

        if cur.rowcount == 0:
            console.print(f"[red]Firm '{firm_id}' not found. Create it first with 'firms create'.[/red]")
            sys.exit(1)

        conn.commit()

    console.print(f"[green]Clio credentials saved for {firm_id}[/green]")
    console.print(f"  pms_type = clio")
    console.print(f"  client_id = {client_id[:8]}...")
    console.print(f"\nNext steps:")
    console.print(f"  1. Run: python agent.py clio auth-url --firm-id {firm_id}")
    console.print(f"  2. Open the URL, authorize, copy the code")
    console.print(f"  3. Run: python agent.py clio exchange-code --firm-id {firm_id} --code <CODE>")
    console.print(f"  4. Run: python agent.py clio sync --firm-id {firm_id}")
    console.print()
