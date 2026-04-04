"""
CLI commands for phone integration management.

Usage:
    python agent.py phone setup --firm-id jcs_law --provider ringcentral
    python agent.py phone list --firm-id jcs_law
    python agent.py phone normalize --firm-id jcs_law
    python agent.py phone coverage --firm-id jcs_law
    python agent.py phone test-lookup --firm-id jcs_law "+13145551234"
    python agent.py phone events --firm-id jcs_law
    python agent.py phone stats --firm-id jcs_law
"""
import click
from rich.console import Console
from rich.table import Table

console = Console()

FIRM_ID_OPTION = click.option(
    '--firm-id', required=True, help='Firm identifier'
)


@click.group()
def phone():
    """Phone integration management (Caller ID Screen Pop)."""
    pass


@phone.command()
@FIRM_ID_OPTION
@click.option('--provider', required=True,
              type=click.Choice(['ringcentral', 'quo', 'vonage']),
              help='VoIP provider')
@click.option('--webhook-secret', prompt=True, hide_input=True,
              help='Webhook verification secret')
def setup(firm_id, provider, webhook_secret):
    """Configure a VoIP provider integration for a firm."""
    from db.phone import ensure_phone_tables, upsert_phone_integration

    ensure_phone_tables()
    int_id = upsert_phone_integration(
        firm_id=firm_id,
        provider=provider,
        webhook_secret=webhook_secret,
        is_active=True,
    )

    console.print(f"\n[green]✓[/green] {provider} integration configured (id={int_id})")
    console.print(f"  Webhook URL: [cyan]/api/phone/webhook/{firm_id}/{provider}[/cyan]")
    console.print(f"\n  Configure this URL in your {provider} admin dashboard.")
    console.print(f"  The webhook will receive incoming call events and trigger screen pops.")


@phone.command('list')
@FIRM_ID_OPTION
def list_integrations(firm_id):
    """List phone integrations for a firm."""
    from db.phone import ensure_phone_tables, get_active_integrations

    ensure_phone_tables()
    integrations = get_active_integrations(firm_id)

    if not integrations:
        console.print("[yellow]No active integrations found.[/yellow]")
        console.print("Run [cyan]phone setup --firm-id {firm_id} --provider <provider>[/cyan] to configure one.")
        return

    table = Table(title=f"Phone Integrations — {firm_id}")
    table.add_column("Provider", style="cyan")
    table.add_column("Active", style="green")
    table.add_column("Webhook URL", style="dim")
    table.add_column("Configured", style="dim")

    for i in integrations:
        table.add_row(
            i['provider'],
            "✓" if i['is_active'] else "✗",
            f"/api/phone/webhook/{firm_id}/{i['provider']}",
            str(i['created_at'].strftime('%Y-%m-%d') if i.get('created_at') else 'N/A'),
        )

    console.print(table)


@phone.command()
@FIRM_ID_OPTION
def normalize(firm_id):
    """Normalize phone numbers in cached_clients for a firm."""
    from db.phone import ensure_phone_tables, populate_normalized_phones

    ensure_phone_tables()
    console.print(f"Normalizing phone numbers for [cyan]{firm_id}[/cyan]...")

    result = populate_normalized_phones(firm_id)

    console.print(f"\n[green]✓[/green] Normalization complete")
    console.print(f"  Clients processed: {result['total_clients']}")
    console.print(f"  Records updated:   {result['updated']}")


@phone.command()
@FIRM_ID_OPTION
def coverage(firm_id):
    """Check phone number coverage in cached_clients."""
    from db.phone import ensure_phone_tables
    from db.connection import get_connection

    ensure_phone_tables()

    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT
                COUNT(*) as total,
                COUNT(cell_phone) FILTER (WHERE cell_phone IS NOT NULL AND cell_phone != '') as has_cell,
                COUNT(work_phone) FILTER (WHERE work_phone IS NOT NULL AND work_phone != '') as has_work,
                COUNT(home_phone) FILTER (WHERE home_phone IS NOT NULL AND home_phone != '') as has_home,
                COUNT(*) FILTER (WHERE
                    (cell_phone IS NOT NULL AND cell_phone != '') OR
                    (work_phone IS NOT NULL AND work_phone != '') OR
                    (home_phone IS NOT NULL AND home_phone != '')
                ) as has_any,
                COUNT(phone_normalized) FILTER (WHERE phone_normalized IS NOT NULL) as normalized
            FROM cached_clients
            WHERE firm_id = %s
        """, (firm_id,))
        r = dict(cur.fetchone())

    total = r['total']
    console.print(f"\n[bold]Phone Number Coverage — {firm_id}[/bold]\n")

    table = Table()
    table.add_column("Metric", style="cyan")
    table.add_column("Count", justify="right")
    table.add_column("Percentage", justify="right")

    for label, key in [
        ("Total Clients", "total"),
        ("Has Cell Phone", "has_cell"),
        ("Has Work Phone", "has_work"),
        ("Has Home Phone", "has_home"),
        ("Has Any Phone", "has_any"),
        ("Normalized (indexed)", "normalized"),
    ]:
        count = r[key]
        pct = f"{100 * count / total:.1f}%" if total > 0 else "N/A"
        table.add_row(label, str(count), pct)

    console.print(table)

    has_any = r['has_any']
    if total > 0:
        pct = 100 * has_any / total
        if pct >= 80:
            console.print(f"\n[green]✓[/green] {pct:.1f}% coverage — screen pop match rate should be excellent")
        elif pct >= 60:
            console.print(f"\n[yellow]![/yellow] {pct:.1f}% coverage — decent, but some callers won't be identified")
        else:
            console.print(f"\n[red]✗[/red] {pct:.1f}% coverage — low. Many callers will show as Unknown")

    if r['normalized'] == 0 and has_any > 0:
        console.print("\n[yellow]Phone numbers not yet normalized. Run:[/yellow]")
        console.print(f"  [cyan]python agent.py phone normalize --firm-id {firm_id}[/cyan]")


@phone.command('test-lookup')
@FIRM_ID_OPTION
@click.argument('phone_number')
def test_lookup(firm_id, phone_number):
    """Test client lookup by phone number."""
    from db.phone import ensure_phone_tables
    from phone.normalize import normalize_phone, format_display
    from phone.lookup import lookup_client_by_phone, get_client_active_cases

    ensure_phone_tables()

    normalized = normalize_phone(phone_number)
    console.print(f"Input:      {phone_number}")
    console.print(f"Normalized: {normalized}")
    console.print(f"Display:    {format_display(normalized)}")

    if not normalized:
        console.print("[red]Could not normalize phone number[/red]")
        return

    client = lookup_client_by_phone(firm_id, normalized)
    if client:
        console.print(f"\n[green]✓ Match found:[/green]")
        console.print(f"  Name:  {client.get('name', 'N/A')}")
        console.print(f"  ID:    {client.get('id')}")
        console.print(f"  Email: {client.get('email', 'N/A')}")

        cases = get_client_active_cases(firm_id, client['id'])
        if cases:
            console.print(f"\n  Active Cases ({len(cases)}):")
            for c in cases:
                console.print(f"    - {c['name']} ({c['case_number']}) — {c.get('practice_area', 'N/A')}")
        else:
            console.print("  No active cases")
    else:
        console.print(f"\n[yellow]No match found[/yellow] for {normalized} at firm {firm_id}")


@phone.command()
@FIRM_ID_OPTION
@click.option('--limit', default=25, help='Number of events to show')
def events(firm_id, limit):
    """Show recent call events."""
    from db.phone import ensure_phone_tables, get_call_events

    ensure_phone_tables()
    events_list = get_call_events(firm_id, limit=limit)

    if not events_list:
        console.print("[yellow]No call events recorded yet.[/yellow]")
        return

    table = Table(title=f"Recent Call Events — {firm_id}")
    table.add_column("Time", style="dim")
    table.add_column("Caller", style="cyan")
    table.add_column("Client", style="green")
    table.add_column("Cases")
    table.add_column("Provider", style="dim")
    table.add_column("Pop", justify="center")

    for e in events_list:
        time_str = e['created_at'].strftime('%m/%d %I:%M %p') if e.get('created_at') else ''
        table.add_row(
            time_str,
            e.get('caller_number', ''),
            e.get('matched_client_name') or '[dim]Unknown[/dim]',
            str(e.get('matched_case_count', 0)),
            e.get('provider', ''),
            "[green]✓[/green]" if e.get('pop_delivered') else "[dim]—[/dim]",
        )

    console.print(table)


@phone.command()
@FIRM_ID_OPTION
@click.option('--days', default=30, help='Number of days to analyze')
def stats(firm_id, days):
    """Show call event statistics."""
    from db.phone import ensure_phone_tables, get_call_stats

    ensure_phone_tables()
    s = get_call_stats(firm_id, days=days)

    console.print(f"\n[bold]Call Statistics — {firm_id} (last {days} days)[/bold]\n")
    console.print(f"  Total Calls:    {s['total_calls']}")
    console.print(f"  Matched:        [green]{s['matched_calls']}[/green]")
    console.print(f"  Unmatched:      [yellow]{s['unmatched_calls']}[/yellow]")
    console.print(f"  Match Rate:     {s['match_rate_pct'] or 0}%")
    console.print(f"  Unique Callers: {s['unique_callers']}")
    console.print(f"  Pops Delivered: {s['pops_delivered']}")
