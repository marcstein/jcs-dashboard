"""User management commands."""

import click
from rich.console import Console
from rich.table import Table

console = Console()


@click.group()
def users():
    """Manage dashboard users."""
    pass


@users.command("create")
@click.argument("username")
@click.option("--password", prompt=True, hide_input=True, confirmation_prompt=True, help="User password")
@click.option("--email", default=None, help="User email address")
@click.option("--admin", is_flag=True, help="Make user an admin")
def users_create(username: str, password: str, email: str, admin: bool):
    """Create a new dashboard user."""
    from dashboard.auth import create_user

    role = "admin" if admin else "user"
    success = create_user(username, password, email, role)

    if success:
        console.print(f"[green]User '{username}' created successfully (role: {role})[/green]")
    else:
        console.print(f"[red]Failed to create user. Username '{username}' may already exist.[/red]")


@users.command("list")
def users_list():
    """List all dashboard users."""
    from dashboard.auth import list_users

    users_data = list_users()

    if not users_data:
        console.print("[yellow]No users found. Create one with: users create <username>[/yellow]")
        return

    table = Table(title="Dashboard Users")
    table.add_column("Username")
    table.add_column("Email")
    table.add_column("Role")
    table.add_column("Active")
    table.add_column("Last Login")

    for user in users_data:
        status = "[green]Yes[/green]" if user["is_active"] else "[red]No[/red]"
        last_login = user["last_login"] or "Never"
        table.add_row(
            user["username"],
            user["email"] or "-",
            user["role"],
            status,
            last_login[:19] if last_login != "Never" else last_login,
        )

    console.print(table)


@users.command("delete")
@click.argument("username")
@click.confirmation_option(prompt="Are you sure you want to delete this user?")
def users_delete(username: str):
    """Delete a dashboard user."""
    from dashboard.auth import delete_user

    success = delete_user(username)

    if success:
        console.print(f"[green]User '{username}' deleted successfully[/green]")
    else:
        console.print(f"[red]User '{username}' not found[/red]")


@users.command("password")
@click.argument("username")
@click.option("--password", prompt=True, hide_input=True, confirmation_prompt=True, help="New password")
def users_password(username: str, password: str):
    """Change a user's password."""
    from dashboard.auth import update_user_password

    success = update_user_password(username, password)

    if success:
        console.print(f"[green]Password updated for '{username}'[/green]")
    else:
        console.print(f"[red]User '{username}' not found[/red]")
