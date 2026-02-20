"""
Template Management Commands

Commands for initializing, listing, and displaying notice templates.
"""
from typing import Optional

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from templates import TemplateManager, create_default_templates


console = Console()


@click.group()
def templates():
    """Manage notice templates."""
    pass


@templates.command("init")
def templates_init():
    """Initialize default templates."""
    console.print("Creating default templates...")
    manager = create_default_templates()
    console.print("[green]Default templates created![/green]")

    for t in manager.list_templates():
        console.print(f"  - {t['name']} ({t['type']})")


@templates.command("list")
@click.option("--type", "template_type", help="Filter by template type")
def templates_list(template_type: Optional[str]):
    """List all templates."""
    manager = TemplateManager()
    templates = manager.list_templates(template_type=template_type)

    if not templates:
        console.print("[yellow]No templates found. Run 'templates init' to create defaults.[/yellow]")
        return

    table = Table(title="Notice Templates")
    table.add_column("Name", style="cyan")
    table.add_column("Type")
    table.add_column("Description")
    table.add_column("Updated")

    for t in templates:
        table.add_row(
            t["name"],
            t["type"],
            t["description"][:40],
            t.get("updated_at", "")[:10]
        )

    console.print(table)


@templates.command("show")
@click.argument("name")
def templates_show(name: str):
    """Show template content."""
    manager = TemplateManager()
    template = manager.get_template(name)

    if not template:
        console.print(f"[red]Template '{name}' not found[/red]")
        return

    metadata = manager._load_metadata().get(name, {})
    console.print(Panel(
        f"Type: {metadata.get('type')}\n"
        f"Description: {metadata.get('description')}\n"
        f"Variables: {', '.join(metadata.get('variables', []))}",
        title=f"Template: {name}"
    ))
    console.print("\n[bold]Content:[/bold]")
    console.print(template.source)
