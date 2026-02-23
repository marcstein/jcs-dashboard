"""Field override management — persist manual edits through cache syncs."""

import sys
import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console()


def _detect_firm_id() -> str:
    """Auto-detect firm_id from cached_cases."""
    from db.connection import get_connection
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT DISTINCT firm_id FROM cached_cases LIMIT 1")
        row = cur.fetchone()
        if row:
            return row[0] if isinstance(row, tuple) else row['firm_id']
    console.print("[red]Could not detect firm_id. Use --firm-id flag.[/red]")
    sys.exit(1)


@click.group()
def overrides():
    """Manage field overrides that persist through cache syncs."""
    pass


@overrides.command("set")
@click.argument("entity_type", type=click.Choice(["staff", "contacts", "clients"]))
@click.argument("entity_id", type=int)
@click.argument("field_name")
@click.argument("value")
@click.option("--original", help="Original value being replaced (for record-keeping)")
@click.option("--reason", help="Why this override exists")
@click.option("--firm-id", help="Firm ID (auto-detected if omitted)")
def override_set(entity_type, entity_id, field_name, value,
                 original, reason, firm_id):
    """Set a field override. Example: overrides set staff 12345 email tony@jcslaw.com"""
    from db.cache import set_field_override, ensure_cache_tables
    if not firm_id:
        firm_id = _detect_firm_id()
    ensure_cache_tables()

    set_field_override(
        firm_id=firm_id,
        entity_type=entity_type,
        entity_id=entity_id,
        field_name=field_name,
        override_value=value,
        original_value=original,
        reason=reason,
        updated_by="cli",
    )

    # Also update the cached record right now
    _apply_override_to_cache(firm_id, entity_type, entity_id, field_name, value)

    console.print(Panel(
        f"[green]Override set:[/green] {entity_type}[{entity_id}].{field_name} = {value}\n"
        + (f"[dim]Original: {original}[/dim]\n" if original else "")
        + (f"[dim]Reason: {reason}[/dim]" if reason else ""),
        title="Field Override Saved",
    ))


@overrides.command("remove")
@click.argument("entity_type", type=click.Choice(["staff", "contacts", "clients"]))
@click.argument("entity_id", type=int)
@click.argument("field_name")
@click.option("--firm-id", help="Firm ID (auto-detected if omitted)")
def override_remove(entity_type, entity_id, field_name, firm_id):
    """Remove a field override (API value will flow through on next sync)."""
    from db.cache import remove_field_override
    if not firm_id:
        firm_id = _detect_firm_id()

    removed = remove_field_override(firm_id, entity_type, entity_id, field_name)
    if removed:
        console.print(f"[green]Override removed:[/green] {entity_type}[{entity_id}].{field_name}")
        console.print("[dim]The API value will be restored on the next cache sync.[/dim]")
    else:
        console.print(f"[yellow]No override found for {entity_type}[{entity_id}].{field_name}[/yellow]")


@overrides.command("list")
@click.option("--entity-type", "-t", type=click.Choice(["staff", "contacts", "clients"]),
              help="Filter by entity type")
@click.option("--firm-id", help="Firm ID (auto-detected if omitted)")
def override_list(entity_type, firm_id):
    """List all active field overrides."""
    from db.cache import list_field_overrides, ensure_cache_tables
    if not firm_id:
        firm_id = _detect_firm_id()
    ensure_cache_tables()

    items = list_field_overrides(firm_id, entity_type)
    if not items:
        console.print("[yellow]No field overrides configured.[/yellow]")
        return

    # Try to resolve names for staff/contacts
    names = _resolve_entity_names(firm_id, items)

    table = Table(title="Field Overrides", show_lines=True)
    table.add_column("Entity Type", style="cyan")
    table.add_column("ID", style="bright_white")
    table.add_column("Name", style="bright_white")
    table.add_column("Field", style="green")
    table.add_column("Override Value", style="bold green")
    table.add_column("Original", style="dim")
    table.add_column("Reason", style="dim")

    for item in items:
        etype = item.get("entity_type", "")
        eid = item.get("entity_id", "")
        name = names.get((etype, eid), "")
        table.add_row(
            etype,
            str(eid),
            name,
            item.get("field_name", ""),
            item.get("override_value", ""),
            item.get("original_value", "") or "",
            item.get("reason", "") or "",
        )

    console.print(table)
    console.print(f"\n[dim]{len(items)} override(s) active — these values persist through cache syncs.[/dim]")


def _apply_override_to_cache(firm_id, entity_type, entity_id, field_name, value):
    """Apply an override immediately to the cached record."""
    from db.connection import get_connection
    table_map = {
        "staff": "cached_staff",
        "contacts": "cached_contacts",
        "clients": "cached_clients",
    }
    table = table_map.get(entity_type)
    if not table:
        return

    with get_connection() as conn:
        cur = conn.cursor()
        # Safe because field_name comes from CLI argument, not user web input,
        # and table is from our hardcoded map
        cur.execute(
            f"UPDATE {table} SET {field_name} = %s WHERE firm_id = %s AND id = %s",
            (value, firm_id, entity_id),
        )
        if cur.rowcount > 0:
            console.print(f"[dim]  → Also updated {table} record immediately.[/dim]")


def _resolve_entity_names(firm_id, items):
    """Look up names for entity IDs."""
    from db.connection import get_connection
    names = {}
    staff_ids = [i["entity_id"] for i in items if i["entity_type"] == "staff"]
    contact_ids = [i["entity_id"] for i in items if i["entity_type"] == "contacts"]
    client_ids = [i["entity_id"] for i in items if i["entity_type"] == "clients"]

    with get_connection() as conn:
        cur = conn.cursor()
        if staff_ids:
            placeholders = ",".join(["%s"] * len(staff_ids))
            cur.execute(
                f"SELECT id, name FROM cached_staff WHERE firm_id = %s AND id IN ({placeholders})",
                [firm_id] + staff_ids,
            )
            for row in cur.fetchall():
                rid = row[0] if isinstance(row, tuple) else row["id"]
                rname = row[1] if isinstance(row, tuple) else row["name"]
                names[("staff", rid)] = rname or ""
        if contact_ids:
            placeholders = ",".join(["%s"] * len(contact_ids))
            cur.execute(
                f"SELECT id, name FROM cached_contacts WHERE firm_id = %s AND id IN ({placeholders})",
                [firm_id] + contact_ids,
            )
            for row in cur.fetchall():
                rid = row[0] if isinstance(row, tuple) else row["id"]
                rname = row[1] if isinstance(row, tuple) else row["name"]
                names[("contacts", rid)] = rname or ""
        if client_ids:
            placeholders = ",".join(["%s"] * len(client_ids))
            cur.execute(
                f"SELECT id, CONCAT(first_name, ' ', last_name) as name FROM cached_clients WHERE firm_id = %s AND id IN ({placeholders})",
                [firm_id] + client_ids,
            )
            for row in cur.fetchall():
                rid = row[0] if isinstance(row, tuple) else row["id"]
                rname = row[1] if isinstance(row, tuple) else row["name"]
                names[("clients", rid)] = rname or ""

    return names
