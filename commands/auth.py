"""
Authentication commands for MyCase integration.

Handles OAuth login, logout, and authentication status checks.
"""
import sys

import click
from rich.console import Console

from auth import MyCaseAuth

console = Console()


@click.group()
def auth():
    """Authentication commands."""
    pass


@auth.command("login")
def auth_login():
    """Authenticate with MyCase via OAuth."""
    auth_manager = MyCaseAuth()

    if auth_manager.is_authenticated():
        console.print("[green]Already authenticated![/green]")
        console.print(f"Firm UUID: {auth_manager.get_firm_uuid()}")

        if click.confirm("Re-authenticate?"):
            auth_manager.storage.clear()
        else:
            return

    console.print("\n[bold]Starting OAuth authorization flow...[/bold]")
    console.print("A browser window will open for you to authorize access.\n")

    try:
        tokens = auth_manager.authorize_interactive()
        console.print("\n[green]Authentication successful![/green]")
        console.print(f"Firm UUID: {tokens.get('firm_uuid')}")
        console.print(f"Scopes: {tokens.get('scope')}")
        console.print(f"Token expires in: {tokens.get('expires_in', 0) // 3600} hours")
    except Exception as e:
        console.print(f"\n[red]Authentication failed: {e}[/red]")
        sys.exit(1)


@auth.command("status")
def auth_status():
    """Check authentication status."""
    auth_manager = MyCaseAuth()

    if auth_manager.is_authenticated():
        tokens = auth_manager.storage.load()
        console.print("[green]Authenticated[/green]")
        console.print(f"Firm UUID: {tokens.get('firm_uuid')}")
        console.print(f"Expires at: {tokens.get('expires_at')}")
    else:
        console.print("[yellow]Not authenticated[/yellow]")
        console.print("Run: mycase-agent auth login")


@auth.command("logout")
def auth_logout():
    """Clear stored authentication tokens."""
    auth_manager = MyCaseAuth()
    auth_manager.storage.clear()
    console.print("[green]Logged out successfully[/green]")
