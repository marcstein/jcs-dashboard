"""Dashboard command for launching the web interface."""

import click
from rich.console import Console

console = Console()


@click.command("dashboard")
@click.option("--host", default="127.0.0.1", help="Host to bind to")
@click.option("--port", default=8000, help="Port to bind to")
@click.option("--reload", is_flag=True, help="Enable auto-reload for development")
def dashboard_cmd(host: str, port: int, reload: bool):
    """Launch the web dashboard."""
    from dashboard.app import run_server

    console.print(f"\n[bold]Starting MyCase Dashboard...[/bold]")
    console.print(f"Open [link=http://{host}:{port}]http://{host}:{port}[/link] in your browser")
    console.print(f"Default login: admin / admin\n")

    run_server(host=host, port=port, reload=reload)
