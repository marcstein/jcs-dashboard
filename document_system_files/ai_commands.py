"""
AI-Enhanced CLI Commands

Integrates AI skills and document generation into the agent.py CLI.
Add these command groups to your agent.py by importing and registering them.

Usage in agent.py:
    from ai_commands import ai_cli, templates_cli, docs_cli

    cli.add_command(ai_cli, name="ai")
    cli.add_command(templates_cli, name="templates")
    cli.add_command(docs_cli, name="docs")
"""

import json
import os
import sys
from datetime import datetime, date
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.markdown import Markdown
from rich.progress import Progress, SpinnerColumn, TextColumn

from config import DATA_DIR
from templates_db import (
    TemplatesDatabase, Template, TemplateCategory, TemplateStatus,
    get_templates_db
)


console = Console()


# ============================================================================
# Skill Manager Initialization
# ============================================================================

def get_skill_manager():
    """Initialize and return the skill manager with all skills registered."""
    from skills import (
        SkillManager,
        CaseTriageSkill,
        CollectionsRiskSkill,
        BriefingSkill,
    )
    from skills.document_generation import DocumentGenerationSkill

    if not os.getenv("ANTHROPIC_API_KEY"):
        console.print("[yellow]Warning: ANTHROPIC_API_KEY not set. AI features disabled.[/yellow]")
        return None

    manager = SkillManager()
    manager.register(CaseTriageSkill())
    manager.register(CollectionsRiskSkill())
    manager.register(BriefingSkill())
    manager.register(DocumentGenerationSkill())

    return manager


# ============================================================================
# AI Commands Group
# ============================================================================

@click.group()
def ai_cli():
    """AI-enhanced analysis and assessment commands."""
    pass


@ai_cli.command("triage")
@click.argument("case_id")
@click.option("--json-output", is_flag=True, help="Output as JSON")
def ai_triage_case(case_id: str, json_output: bool):
    """
    AI-assess a case's health status.

    Uses GREEN/YELLOW/RED classification to identify cases
    needing attention based on phase duration, tasks, financials,
    and communication recency.
    """
    manager = get_skill_manager()
    if not manager:
        console.print("[red]AI features require ANTHROPIC_API_KEY[/red]")
        return

    # Load case data from cache
    case_data = _get_case_data_from_cache(case_id)
    if not case_data:
        console.print(f"[red]Case {case_id} not found in cache[/red]")
        return

    with console.status("Running AI assessment..."):
        result = manager.execute("case_triage", case_data)

    if json_output:
        console.print(json.dumps(result.to_dict(), indent=2))
        return

    # Display with rich formatting
    color = {"GREEN": "green", "YELLOW": "yellow", "RED": "red"}[result.classification.value]
    score_display = f"{result.score}/100" if result.score else "N/A"

    console.print(Panel(
        f"[{color} bold]{result.classification.value}[/{color} bold] - Score: {score_display}\n\n{result.summary}",
        title=f"Case {case_id} Assessment"
    ))

    if result.issues:
        table = Table(title="Issues Found", show_header=True)
        table.add_column("Severity", style="bold")
        table.add_column("Description")

        for issue in result.issues:
            severity = issue.get("severity", "medium")
            sev_color = {"high": "red", "medium": "yellow", "low": "green"}.get(severity, "white")
            table.add_row(f"[{sev_color}]{severity.upper()}[/{sev_color}]", issue.get("description", ""))

        console.print(table)

    if result.recommendations:
        console.print("\n[bold]Recommendations:[/bold]")
        for rec in result.recommendations:
            priority = rec.get("priority", "MEDIUM")
            pri_color = {"HIGH": "red", "MEDIUM": "yellow", "LOW": "green"}.get(priority, "white")
            console.print(f"  [{pri_color}]{priority}[/{pri_color}] {rec.get('action', '')} → {rec.get('owner', 'TBD')}")

    if result.escalation_required:
        console.print(f"\n[red bold]⚠️ ESCALATION REQUIRED:[/red bold] {result.escalation_reason}")


@ai_cli.command("collections-risk")
@click.argument("contact_id")
@click.option("--json-output", is_flag=True, help="Output as JSON")
def ai_collections_risk(contact_id: str, json_output: bool):
    """
    AI-assess collection risk for a contact.

    Uses Severity × Likelihood matrix to score risk (1-25)
    and recommend dunning stage and communication approach.
    """
    manager = get_skill_manager()
    if not manager:
        console.print("[red]AI features require ANTHROPIC_API_KEY[/red]")
        return

    # Load collection data from cache
    collection_data = _get_collection_data_from_cache(contact_id)
    if not collection_data:
        console.print(f"[red]Contact {contact_id} not found in cache[/red]")
        return

    with console.status("Assessing collection risk..."):
        result = manager.execute("collections_risk", collection_data)

    if json_output:
        console.print(json.dumps(result.to_dict(), indent=2))
        return

    # Display
    color = {"GREEN": "green", "YELLOW": "yellow", "RED": "red"}[result.classification.value]
    meta = result.metadata

    console.print(Panel(
        f"[{color} bold]Risk Score: {result.score}/25[/{color} bold]\n\n{result.summary}",
        title=f"Collection Risk - Contact {contact_id}"
    ))

    # Risk breakdown
    table = Table(show_header=False, box=None)
    table.add_column("Metric", style="bold")
    table.add_column("Value")

    sev = meta.get("severity", {})
    lik = meta.get("likelihood", {})

    table.add_row("Severity", f"{sev.get('score', '?')}/5 ({sev.get('label', 'Unknown')})")
    table.add_row("Likelihood", f"{lik.get('score', '?')}/5 ({lik.get('label', 'Unknown')})")
    table.add_row("Recommended Stage", str(meta.get("recommended_stage", "?")))
    table.add_row("Communication Tone", meta.get("communication_tone", "Unknown"))
    table.add_row("Payment Plan Recommended", "Yes" if meta.get("payment_plan_recommended") else "No")
    table.add_row("NOIW Recommended", "[red]Yes[/red]" if meta.get("noiw_recommended") else "No")

    console.print(table)

    if result.recommendations:
        console.print("\n[bold]Recommended Actions:[/bold]")
        for action in result.recommendations:
            console.print(f"  • {action.get('action', '')} ({action.get('timing', '')}, via {action.get('channel', '')})")


@ai_cli.command("briefing")
@click.argument("staff_name")
@click.option("--export", is_flag=True, help="Export to markdown file")
@click.option("--json-output", is_flag=True, help="Output as JSON")
def ai_briefing(staff_name: str, export: bool, json_output: bool):
    """
    Generate AI-enhanced daily briefing for a staff member.

    Creates a prioritized briefing with:
    - RED alerts requiring immediate attention
    - YELLOW focus items for today
    - Metrics snapshot
    - Action items with owners and deadlines
    """
    manager = get_skill_manager()
    if not manager:
        console.print("[red]AI features require ANTHROPIC_API_KEY[/red]")
        return

    # Load staff briefing data
    staff_data = _get_staff_briefing_data(staff_name)
    if not staff_data:
        console.print(f"[red]Staff member '{staff_name}' not found[/red]")
        return

    with console.status(f"Generating briefing for {staff_name}..."):
        result = manager.execute("briefing", staff_data)

    if json_output:
        console.print(json.dumps(result.to_dict(), indent=2))
        return

    from skills.briefing import format_briefing_markdown
    briefing_md = format_briefing_markdown(result)

    if export:
        # Export to file
        export_dir = DATA_DIR / "briefings"
        export_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{staff_name.lower().replace(' ', '_')}_{date.today()}.md"
        export_path = export_dir / filename

        export_path.write_text(briefing_md)
        console.print(f"[green]Exported to {export_path}[/green]")
    else:
        console.print(Markdown(briefing_md))


@ai_cli.command("batch-triage")
@click.option("--phase", type=int, help="Filter by phase number (1-7)")
@click.option("--limit", default=20, help="Maximum cases to assess")
@click.option("--export", is_flag=True, help="Export to CSV")
def ai_batch_triage(phase: Optional[int], limit: int, export: bool):
    """
    Batch triage all cases (or cases in a specific phase).

    Runs AI assessment on multiple cases and provides
    a summary of RED/YELLOW/GREEN distribution.
    """
    manager = get_skill_manager()
    if not manager:
        console.print("[red]AI features require ANTHROPIC_API_KEY[/red]")
        return

    # Get cases from cache
    cases = _get_cases_for_batch_triage(phase, limit)
    if not cases:
        console.print("[yellow]No cases found for assessment[/yellow]")
        return

    results = []
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console
    ) as progress:
        task = progress.add_task(f"Assessing {len(cases)} cases...", total=len(cases))

        for case_data in cases:
            result = manager.execute("case_triage", case_data)
            results.append({
                "case_id": case_data.get("case_id"),
                "case_name": case_data.get("case_name"),
                "classification": result.classification.value,
                "score": result.score,
                "issues_count": len(result.issues),
                "escalation": result.escalation_required,
            })
            progress.advance(task)

    # Display summary
    classifications = [r["classification"] for r in results]
    summary_table = Table(title="Batch Triage Summary")
    summary_table.add_column("Classification", style="bold")
    summary_table.add_column("Count")
    summary_table.add_column("Percentage")

    for cls in ["GREEN", "YELLOW", "RED"]:
        count = classifications.count(cls)
        pct = (count / len(classifications) * 100) if classifications else 0
        color = {"GREEN": "green", "YELLOW": "yellow", "RED": "red"}[cls]
        summary_table.add_row(f"[{color}]{cls}[/{color}]", str(count), f"{pct:.1f}%")

    console.print(summary_table)

    # Show RED cases
    red_cases = [r for r in results if r["classification"] == "RED"]
    if red_cases:
        console.print("\n[red bold]Cases Requiring Immediate Attention:[/red bold]")
        for r in red_cases:
            console.print(f"  • {r['case_name']} (ID: {r['case_id']}) - {r['issues_count']} issues")

    if export:
        import csv
        export_path = DATA_DIR / f"batch_triage_{date.today()}.csv"
        with open(export_path, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=results[0].keys())
            writer.writeheader()
            writer.writerows(results)
        console.print(f"\n[green]Exported to {export_path}[/green]")


# ============================================================================
# Templates Commands Group
# ============================================================================

@click.group()
def templates_cli():
    """Legal document template management."""
    pass


@templates_cli.command("list")
@click.option("--category", help="Filter by category (plea, motion, nda, contract, etc.)")
@click.option("--court", help="Filter by court type")
@click.option("--jurisdiction", help="Filter by jurisdiction")
@click.option("--limit", default=50, help="Maximum templates to show")
def templates_list(category: Optional[str], court: Optional[str], jurisdiction: Optional[str], limit: int):
    """List available document templates."""
    db = get_templates_db()

    templates = db.list_templates(
        category=category,
        court_type=court,
        jurisdiction=jurisdiction,
        limit=limit
    )

    if not templates:
        console.print("[yellow]No templates found[/yellow]")
        return

    table = Table(title=f"Document Templates ({len(templates)})")
    table.add_column("ID", style="dim")
    table.add_column("Name", style="bold")
    table.add_column("Category")
    table.add_column("Court")
    table.add_column("Jurisdiction")
    table.add_column("Uses", justify="right")

    for t in templates:
        table.add_row(
            str(t.id),
            t.name,
            t.category.value,
            t.court_type or "-",
            t.jurisdiction or "-",
            str(t.usage_count)
        )

    console.print(table)


@templates_cli.command("search")
@click.argument("query")
@click.option("--limit", default=20, help="Maximum results")
def templates_search(query: str, limit: int):
    """Search templates by name, description, or tags."""
    db = get_templates_db()

    templates = db.search_templates(query, limit=limit)

    if not templates:
        console.print(f"[yellow]No templates found matching '{query}'[/yellow]")
        return

    table = Table(title=f"Search Results for '{query}'")
    table.add_column("ID", style="dim")
    table.add_column("Name", style="bold")
    table.add_column("Category")
    table.add_column("Description")

    for t in templates:
        table.add_row(
            str(t.id),
            t.name,
            t.category.value,
            t.description[:60] + "..." if len(t.description) > 60 else t.description
        )

    console.print(table)


@templates_cli.command("add")
@click.argument("file_path", type=click.Path(exists=True))
@click.option("--name", required=True, help="Template name")
@click.option("--category", required=True, type=click.Choice([c.value for c in TemplateCategory]), help="Template category")
@click.option("--description", default="", help="Template description")
@click.option("--court", help="Court type (e.g., Municipal, District)")
@click.option("--jurisdiction", help="Jurisdiction (e.g., Ohio, Hamilton County)")
@click.option("--case-types", help="Comma-separated case types (e.g., DWI,Traffic)")
@click.option("--tags", help="Comma-separated tags")
def templates_add(
    file_path: str,
    name: str,
    category: str,
    description: str,
    court: Optional[str],
    jurisdiction: Optional[str],
    case_types: Optional[str],
    tags: Optional[str]
):
    """
    Add a new document template.

    Example:
        agent.py templates add plea_dwi.docx --name "DWI Plea - Municipal" \\
            --category plea --court "Municipal" --jurisdiction "Hamilton County" \\
            --case-types "DWI" --tags "first-offense,standard"
    """
    db = get_templates_db()

    # Read file content for hashing
    file_path = Path(file_path)
    file_content = file_path.read_bytes()

    # Copy to templates directory
    templates_dir = DATA_DIR / "document_templates"
    templates_dir.mkdir(parents=True, exist_ok=True)

    dest_path = templates_dir / file_path.name
    dest_path.write_bytes(file_content)

    # Create template record
    template = Template(
        name=name,
        category=TemplateCategory(category),
        description=description,
        court_type=court,
        jurisdiction=jurisdiction,
        case_types=case_types.split(",") if case_types else [],
        file_path=str(dest_path),
        tags=tags.split(",") if tags else [],
        created_by="admin",
    )

    # Extract variables from the template (look for {{variable}} patterns)
    content = file_content.decode('utf-8', errors='ignore')
    variables = list(set(re.findall(r'\{\{([^}]+)\}\}', content)))
    template.variables = variables

    template_id = db.add_template(template, file_content)

    console.print(f"[green]Template added with ID {template_id}[/green]")
    console.print(f"Variables detected: {', '.join(variables) if variables else 'None'}")


@templates_cli.command("show")
@click.argument("template_id", type=int)
def templates_show(template_id: int):
    """Show detailed information about a template."""
    db = get_templates_db()

    template = db.get_template(template_id)
    if not template:
        console.print(f"[red]Template {template_id} not found[/red]")
        return

    console.print(Panel(
        f"[bold]{template.name}[/bold]\n\n"
        f"Category: {template.category.value}\n"
        f"Court: {template.court_type or 'Any'}\n"
        f"Jurisdiction: {template.jurisdiction or 'Any'}\n"
        f"Case Types: {', '.join(template.case_types) or 'Any'}\n"
        f"Status: {template.status.value}\n"
        f"Version: {template.version}\n"
        f"Usage Count: {template.usage_count}\n\n"
        f"Description:\n{template.description or 'No description'}\n\n"
        f"Variables:\n{', '.join(template.variables) or 'None'}\n\n"
        f"Tags: {', '.join(template.tags) or 'None'}",
        title=f"Template #{template_id}"
    ))

    # Show recent usage
    history = db.get_generation_history(template_id=template_id, limit=5)
    if history:
        console.print("\n[bold]Recent Usage:[/bold]")
        for h in history:
            console.print(f"  • {h['generated_at'][:10]} - Case: {h['case_name'] or 'N/A'} - {h['purpose'] or 'N/A'}")


# ============================================================================
# Document Generation Commands Group
# ============================================================================

@click.group()
def docs_cli():
    """AI-powered document generation."""
    pass


@docs_cli.command("generate")
@click.argument("template_name")
@click.option("--case-id", type=int, help="MyCase case ID for context")
@click.option("--client", help="Client name")
@click.option("--court", help="Court name")
@click.option("--purpose", help="Document purpose/description")
@click.option("--context", help="Additional context for AI")
@click.option("--var", multiple=True, help="Variable value in format: name=value")
@click.option("--output-dir", type=click.Path(), help="Output directory")
@click.option("--no-ai", is_flag=True, help="Simple substitution without AI")
def docs_generate(
    template_name: str,
    case_id: Optional[int],
    client: Optional[str],
    court: Optional[str],
    purpose: Optional[str],
    context: Optional[str],
    var: tuple,
    output_dir: Optional[str],
    no_ai: bool
):
    """
    Generate a document from a template.

    Example:
        agent.py docs generate "DWI Plea - Municipal" --case-id 12345 \\
            --court "Hamilton County Municipal Court" \\
            --context "First offense, BAC 0.09, cooperative defendant"
    """
    from skills.document_generation import DocumentGenerator

    templates_db = get_templates_db()

    # Get skill manager (unless --no-ai)
    skill_manager = None if no_ai else get_skill_manager()

    # Parse explicit variables
    explicit_vars = {}
    for v in var:
        if "=" in v:
            key, value = v.split("=", 1)
            explicit_vars[key.strip()] = value.strip()

    # Get cache database for case context
    cache_db = None
    if case_id:
        try:
            from cache import get_cache_db
            cache_db = get_cache_db()
        except ImportError:
            pass

    generator = DocumentGenerator(
        templates_db=templates_db,
        cache_db=cache_db,
        skill_manager=skill_manager
    )

    with console.status("Generating document..."):
        try:
            result = generator.generate(
                template_name=template_name,
                case_id=case_id,
                client_name=client,
                court=court,
                purpose=purpose,
                additional_context=context,
                explicit_variables=explicit_vars,
                output_dir=Path(output_dir) if output_dir else None
            )
        except ValueError as e:
            console.print(f"[red]Error: {e}[/red]")
            return
        except Exception as e:
            console.print(f"[red]Generation failed: {e}[/red]")
            return

    # Display result
    qa = result.get("quality_assessment", {})
    classification = qa.get("classification", "YELLOW")
    color = {"GREEN": "green", "YELLOW": "yellow", "RED": "red"}.get(classification, "white")

    console.print(Panel(
        f"[{color} bold]Quality: {classification}[/{color} bold]\n\n"
        f"Template: {result['template_used']}\n"
        f"Output: {result['output_path']}\n\n"
        f"Variables filled: {len(result.get('variables_filled', {}))}",
        title="Document Generated"
    ))

    if qa.get("escalation_required"):
        console.print(f"[yellow]⚠️ Review recommended: {qa.get('escalation_reason', 'AI flagged for review')}[/yellow]")

    if qa.get("issues"):
        console.print("\n[bold]Review Notes:[/bold]")
        for issue in qa["issues"]:
            if isinstance(issue, dict):
                console.print(f"  • [{issue.get('priority', 'MEDIUM')}] {issue.get('issue', '')}")
            else:
                console.print(f"  • {issue}")

    console.print(f"\n[green]Document saved to: {result['output_path']}[/green]")


@docs_cli.command("history")
@click.option("--case-id", type=int, help="Filter by case ID")
@click.option("--template-id", type=int, help="Filter by template ID")
@click.option("--limit", default=20, help="Maximum records")
def docs_history(case_id: Optional[int], template_id: Optional[int], limit: int):
    """Show document generation history."""
    db = get_templates_db()

    history = db.get_generation_history(
        template_id=template_id,
        case_id=case_id,
        limit=limit
    )

    if not history:
        console.print("[yellow]No generation history found[/yellow]")
        return

    table = Table(title="Document Generation History")
    table.add_column("Date", style="dim")
    table.add_column("Template")
    table.add_column("Case")
    table.add_column("Client")
    table.add_column("Purpose")

    for h in history:
        table.add_row(
            h["generated_at"][:10] if h["generated_at"] else "-",
            h["template_name"] or "-",
            h["case_name"] or "-",
            h["client_name"] or "-",
            (h["purpose"] or "-")[:30]
        )

    console.print(table)


# ============================================================================
# Helper Functions
# ============================================================================

def _get_case_data_from_cache(case_id: str) -> Optional[dict]:
    """Load case data from cache database for AI assessment."""
    try:
        from cache import get_cache_db
        cache = get_cache_db()

        with cache._get_connection() as conn:
            cursor = conn.cursor()

            # Get case
            cursor.execute("SELECT * FROM cases WHERE id = ?", (case_id,))
            case_row = cursor.fetchone()
            if not case_row:
                return None

            case_data = dict(case_row)

            # Get tasks
            cursor.execute("""
                SELECT COUNT(*) as total,
                       SUM(CASE WHEN completed = 1 THEN 1 ELSE 0 END) as completed,
                       SUM(CASE WHEN due_date < date('now') AND completed = 0 THEN 1 ELSE 0 END) as overdue
                FROM tasks WHERE case_id = ?
            """, (case_id,))
            tasks = dict(cursor.fetchone())
            case_data["tasks"] = tasks

            # Get invoices
            cursor.execute("""
                SELECT SUM(total) as total_billed,
                       SUM(balance) as outstanding,
                       MAX(julianday('now') - julianday(due_date)) as oldest_days
                FROM invoices WHERE case_id = ? AND balance > 0
            """, (case_id,))
            financial = dict(cursor.fetchone())
            case_data["financial"] = financial

            return case_data

    except Exception as e:
        console.print(f"[yellow]Warning: Could not load case data: {e}[/yellow]")
        return None


def _get_collection_data_from_cache(contact_id: str) -> Optional[dict]:
    """Load collection data from cache database for risk assessment."""
    try:
        from cache import get_cache_db
        cache = get_cache_db()

        with cache._get_connection() as conn:
            cursor = conn.cursor()

            # Get contact
            cursor.execute("SELECT * FROM contacts WHERE id = ?", (contact_id,))
            contact_row = cursor.fetchone()
            if not contact_row:
                return None

            contact_data = dict(contact_row)

            # Get invoices
            cursor.execute("""
                SELECT *,
                       julianday('now') - julianday(due_date) as days_past_due
                FROM invoices
                WHERE contact_id = ? AND balance > 0
                ORDER BY due_date ASC
            """, (contact_id,))
            invoices = [dict(row) for row in cursor.fetchall()]

            contact_data["invoices"] = invoices
            contact_data["total_outstanding"] = sum(i["balance"] for i in invoices)
            contact_data["oldest_invoice_days"] = max((i["days_past_due"] for i in invoices), default=0)

            return contact_data

    except Exception as e:
        console.print(f"[yellow]Warning: Could not load collection data: {e}[/yellow]")
        return None


def _get_staff_briefing_data(staff_name: str) -> Optional[dict]:
    """Load staff briefing data from cache database."""
    # Map common names to roles
    staff_roles = {
        "melissa": {"name": "Melissa Scarlett", "role": "AR Specialist"},
        "ty": {"name": "Ty Christian", "role": "Intake Lead"},
        "tiffany": {"name": "Tiffany Willis", "role": "Senior Paralegal"},
        "alison": {"name": "Alison Ehrhard", "role": "Legal Assistant"},
        "cole": {"name": "Cole Chadderdon", "role": "Legal Assistant"},
    }

    staff_key = staff_name.lower().split()[0]
    staff_info = staff_roles.get(staff_key)

    if not staff_info:
        return None

    # Build briefing data (simplified - real implementation would query cache)
    return {
        "staff_member": staff_info,
        "date": str(date.today()),
        "tasks": {"assigned": 15, "due_today": 4, "overdue": 2},
        "ar_summary": {"total_ar": 1450000, "percent_over_60": 82.2},
        "payment_plans": {"total_active": 89, "compliance_rate": 7.6},
    }


def _get_cases_for_batch_triage(phase: Optional[int], limit: int) -> list:
    """Get cases for batch triage from cache."""
    try:
        from cache import get_cache_db
        cache = get_cache_db()

        with cache._get_connection() as conn:
            cursor = conn.cursor()

            query = "SELECT * FROM cases WHERE status = 'Open'"
            params = []

            if phase:
                query += " AND current_phase = ?"
                params.append(phase)

            query += " LIMIT ?"
            params.append(limit)

            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    except Exception:
        return []


# Import re for variable extraction
import re


# ============================================================================
# Pleading Generation Commands Group
# ============================================================================

@click.group()
def pleadings_cli():
    """Missouri criminal pleading generation."""
    pass


@pleadings_cli.command("list")
def pleadings_list():
    """List available pleading types."""
    from pleadings import list_pleading_types

    types = list_pleading_types()

    table = Table(title="Available Pleading Types")
    table.add_column("Type", style="bold")
    table.add_column("Name")
    table.add_column("Charges?")
    table.add_column("Def. Signature?")
    table.add_column("Extra Params")

    for t in types:
        table.add_row(
            t["type"],
            t["name"],
            "Yes" if t["requires_charges"] else "No",
            "Yes" if t["requires_defendant_signature"] else "No",
            ", ".join(t["additional_params"]) or "-"
        )

    console.print(table)


@pleadings_cli.command("generate")
@click.argument("pleading_type")
@click.option("--case-id", type=int, help="MyCase case ID")
@click.option("--defendant", required=True, help="Defendant name")
@click.option("--case-number", required=True, help="Case number")
@click.option("--county", required=True, help="County name")
@click.option("--charges", multiple=True, help="Charges in format: 'Description|Classification|Statute'")
@click.option("--plea-type", default="not-guilty", help="Plea type for arraignment waivers")
@click.option("--current-date", help="Current setting date (for motion to continue)")
@click.option("--reason", help="Reason (for motion to continue)")
@click.option("--output", type=click.Path(), help="Output file path")
@click.option("--format", "output_format", type=click.Choice(["text", "docx"]), default="docx", help="Output format")
def pleadings_generate(
    pleading_type: str,
    case_id: Optional[int],
    defendant: str,
    case_number: str,
    county: str,
    charges: tuple,
    plea_type: str,
    current_date: Optional[str],
    reason: Optional[str],
    output: Optional[str],
    output_format: str
):
    """
    Generate a pleading document.

    Examples:
        # Request for Jury Trial
        agent.py pleadings generate request_for_jury_trial \\
            --defendant "JOHN SMITH" --case-number "22AB-CR00123" --county "Scott"

        # Waiver of Arraignment with charges
        agent.py pleadings generate waiver_of_arraignment \\
            --defendant "JANE DOE" --case-number "22AB-CR00456" --county "Scott" \\
            --charges "DWI - First Offense|Class B Misdemeanor|RSMo 577.010" \\
            --charges "Speeding|Infraction|"

        # Motion to Continue
        agent.py pleadings generate motion_to_continue \\
            --defendant "JOHN SMITH" --case-number "22AB-CR00123" --county "Scott" \\
            --current-date "February 15, 2026" \\
            --reason "Defense counsel has a scheduling conflict"
    """
    from pleadings import (
        PleadingGenerator, CaseContext, Charge, ChargeClass, FIRM_INFO
    )

    # Parse charges
    parsed_charges = []
    for i, charge_str in enumerate(charges, 1):
        parts = charge_str.split("|")
        if len(parts) >= 2:
            description = parts[0].strip()
            classification_str = parts[1].strip().lower()
            statute = parts[2].strip() if len(parts) > 2 else None

            # Map classification string to enum
            if "felony" in classification_str:
                if "class a" in classification_str:
                    charge_class = ChargeClass.FELONY_A
                elif "class b" in classification_str:
                    charge_class = ChargeClass.FELONY_B
                elif "class c" in classification_str:
                    charge_class = ChargeClass.FELONY_C
                elif "class d" in classification_str:
                    charge_class = ChargeClass.FELONY_D
                else:
                    charge_class = ChargeClass.FELONY_E
            elif "misdemeanor" in classification_str:
                if "class a" in classification_str:
                    charge_class = ChargeClass.MISDEMEANOR_A
                elif "class b" in classification_str:
                    charge_class = ChargeClass.MISDEMEANOR_B
                elif "class c" in classification_str:
                    charge_class = ChargeClass.MISDEMEANOR_C
                else:
                    charge_class = ChargeClass.MISDEMEANOR_D
            else:
                charge_class = ChargeClass.INFRACTION

            parsed_charges.append(Charge(
                count_number=i,
                description=description,
                classification=charge_class,
                statute=statute if statute else None
            ))

    # Build context
    ctx = CaseContext(
        case_number=case_number,
        county=county,
        defendant_name=defendant.upper(),
        charges=parsed_charges,
        attorneys=FIRM_INFO["default_attorneys"],
        mycase_case_id=case_id,
    )

    # Build kwargs for specific pleading types
    kwargs = {}
    if plea_type:
        kwargs["plea_type"] = plea_type
    if current_date:
        kwargs["current_date"] = current_date
    if reason:
        kwargs["reason"] = reason

    # Generate
    generator = PleadingGenerator()

    with console.status(f"Generating {pleading_type}..."):
        try:
            result = generator.generate(
                pleading_type=pleading_type,
                case_context=ctx,
                output_format=output_format,
                output_path=Path(output) if output else None,
                **kwargs
            )
        except ValueError as e:
            console.print(f"[red]Error: {e}[/red]")
            return

    # Display result
    console.print(Panel(
        f"[bold]{result['pleading_name']}[/bold]\n\n"
        f"Case: {result['context']['case_number']}\n"
        f"Defendant: {result['context']['defendant']}\n"
        f"County: {result['context']['county']}\n"
        f"Charges: {result['context']['charges_count']}",
        title="Pleading Generated"
    ))

    if output_format == "text":
        console.print("\n[bold]Content:[/bold]")
        console.print(result["content"])
    else:
        console.print(f"\n[green]Document saved to: {result['output_path']}[/green]")


@pleadings_cli.command("extract-charges")
@click.argument("text")
@click.option("--from-file", type=click.Path(exists=True), help="Read text from file")
def pleadings_extract_charges(text: str, from_file: Optional[str]):
    """
    Extract charges from case text using AI.

    Example:
        agent.py pleadings extract-charges "Defendant is charged with DWI first offense and speeding"
    """
    manager = get_skill_manager()
    if not manager:
        console.print("[red]AI features require ANTHROPIC_API_KEY[/red]")
        return

    # Register charge extraction skill
    from skills.charge_extraction import ChargeExtractionSkill
    manager.register(ChargeExtractionSkill())

    # Read from file if specified
    if from_file:
        text = Path(from_file).read_text()

    with console.status("Extracting charges..."):
        result = manager.execute("charge_extraction", text)

    charges = result.metadata.get("charges", [])

    if not charges:
        console.print("[yellow]No charges could be extracted[/yellow]")
        return

    table = Table(title="Extracted Charges")
    table.add_column("Count", style="bold")
    table.add_column("Description")
    table.add_column("Classification")
    table.add_column("Statute")
    table.add_column("Confidence")

    for c in charges:
        conf_color = {"high": "green", "medium": "yellow", "low": "red"}.get(c.get("confidence", "low"), "white")
        table.add_row(
            str(c.get("count_number", "?")),
            c.get("description", "")[:50],
            c.get("classification", ""),
            c.get("statute", "-") or "-",
            f"[{conf_color}]{c.get('confidence', 'unknown')}[/{conf_color}]"
        )

    console.print(table)

    if result.issues:
        console.print("\n[yellow]Uncertainties:[/yellow]")
        for issue in result.issues:
            console.print(f"  • {issue.get('uncertainty', '')}")

    # Show CLI format for easy copy-paste
    console.print("\n[bold]CLI format for pleading generation:[/bold]")
    for c in charges:
        statute = c.get("statute", "") or ""
        console.print(f'--charges "{c.get("description", "")}|{c.get("classification", "")}|{statute}"')


# ============================================================================
# Document Engine Commands (Multi-Tenant Template System)
# ============================================================================

@click.group()
def engine_cli():
    """
    Multi-tenant document engine.

    Template-driven document generation that works with any firm's documents.
    Import your templates once, then generate documents with variable substitution.
    """
    pass


@engine_cli.command("register-firm")
@click.argument("firm_id")
@click.argument("firm_name")
def engine_register_firm(firm_id: str, firm_name: str):
    """
    Register a new firm in the system.

    Example:
        agent.py engine register-firm jcs_law "JCS Law Firm"
    """
    from document_engine import get_engine

    engine = get_engine()
    success = engine.register_firm(firm_id, firm_name)

    if success:
        console.print(f"[green]Firm registered: {firm_name} ({firm_id})[/green]")
    else:
        console.print(f"[yellow]Firm already exists: {firm_id}[/yellow]")


@engine_cli.command("import")
@click.argument("folder", type=click.Path(exists=True))
@click.option("--firm-id", required=True, help="Firm ID to import templates for")
@click.option("--recursive/--no-recursive", default=True, help="Import subfolders")
def engine_import(folder: str, firm_id: str, recursive: bool):
    """
    Import templates from a folder.

    Scans for .docx files, auto-detects variables, and stores in database.

    Example:
        agent.py engine import "Master Document Folder" --firm-id jcs_law
    """
    from document_engine import get_engine
    from pathlib import Path

    engine = get_engine()

    # Ensure firm exists
    if not engine.get_firm(firm_id):
        console.print(f"[yellow]Firm '{firm_id}' not found. Registering...[/yellow]")
        engine.register_firm(firm_id, firm_id)

    folder_path = Path(folder)

    with console.status(f"Importing templates from {folder}..."):
        results = engine.import_folder(firm_id, folder_path, recursive=recursive)

    console.print(Panel(
        f"[bold]Import Complete[/bold]\n\n"
        f"Total files scanned: {results['total']}\n"
        f"Successfully imported: [green]{results['imported']}[/green]\n"
        f"Skipped: [yellow]{results['skipped']}[/yellow]\n"
        f"Errors: [red]{len(results['errors'])}[/red]",
        title="Template Import Results"
    ))

    if results['errors'][:5]:
        console.print("\n[red]Sample errors:[/red]")
        for err in results['errors'][:5]:
            console.print(f"  • {err}")

    if results['templates'][:5]:
        console.print("\n[green]Sample imports:[/green]")
        for t in results['templates'][:5]:
            vars_str = ", ".join(t['variables'][:3])
            if len(t['variables']) > 3:
                vars_str += f" (+{len(t['variables'])-3} more)"
            console.print(f"  • {t['name']}")
            if vars_str:
                console.print(f"    Variables: {vars_str}")


@engine_cli.command("list")
@click.option("--firm-id", required=True, help="Firm ID")
@click.option("--category", help="Filter by category")
@click.option("--limit", default=50, help="Max results")
def engine_list(firm_id: str, category: str, limit: int):
    """
    List templates for a firm.

    Example:
        agent.py engine list --firm-id jcs_law
        agent.py engine list --firm-id jcs_law --category motion
    """
    from document_engine import get_engine

    engine = get_engine()
    templates = engine.list_templates(firm_id, category=category, limit=limit)

    if not templates:
        console.print(f"[yellow]No templates found for firm '{firm_id}'[/yellow]")
        return

    table = Table(title=f"Templates for {firm_id}")
    table.add_column("ID", style="dim")
    table.add_column("Name")
    table.add_column("Category")
    table.add_column("Court/Jurisdiction")
    table.add_column("Variables")
    table.add_column("Uses", justify="right")

    for t in templates:
        jurisdiction = t.jurisdiction or ""
        if t.court_type:
            jurisdiction = f"{t.court_type}: {jurisdiction}" if jurisdiction else t.court_type

        table.add_row(
            str(t.id),
            t.name[:40] + ("..." if len(t.name) > 40 else ""),
            f"{t.category.value}/{t.subcategory}" if t.subcategory else t.category.value,
            jurisdiction[:20],
            str(len(t.variables)),
            str(t.usage_count),
        )

    console.print(table)
    console.print(f"\nTotal: {len(templates)} templates")


@engine_cli.command("search")
@click.argument("query")
@click.option("--firm-id", required=True, help="Firm ID")
@click.option("--limit", default=20, help="Max results")
def engine_search(query: str, firm_id: str, limit: int):
    """
    Search templates by name, category, or jurisdiction.

    Example:
        agent.py engine search "motion dismiss" --firm-id jcs_law
        agent.py engine search "Arnold" --firm-id jcs_law
    """
    from document_engine import get_engine

    engine = get_engine()
    templates = engine.search_templates(firm_id, query, limit=limit)

    if not templates:
        console.print(f"[yellow]No templates matching '{query}'[/yellow]")
        return

    table = Table(title=f"Search: '{query}'")
    table.add_column("ID")
    table.add_column("Name")
    table.add_column("Category")
    table.add_column("Variables")

    for t in templates:
        table.add_row(
            str(t.id),
            t.name,
            t.category.value,
            ", ".join(t.variables[:3]) + ("..." if len(t.variables) > 3 else ""),
        )

    console.print(table)


@engine_cli.command("show")
@click.argument("template_id", type=int)
def engine_show(template_id: int):
    """
    Show detailed template information including variables.

    Example:
        agent.py engine show 42
    """
    from document_engine import get_engine

    engine = get_engine()
    template = engine.get_template(template_id)

    if not template:
        console.print(f"[red]Template {template_id} not found[/red]")
        return

    console.print(Panel(
        f"[bold]{template.name}[/bold]\n"
        f"Original file: {template.original_filename}\n\n"
        f"Category: {template.category.value}\n"
        f"Subcategory: {template.subcategory or '-'}\n"
        f"Court type: {template.court_type or '-'}\n"
        f"Jurisdiction: {template.jurisdiction or '-'}\n"
        f"File size: {template.file_size:,} bytes\n"
        f"Usage count: {template.usage_count}",
        title=f"Template #{template_id}"
    ))

    if template.variables:
        console.print("\n[bold]Variables:[/bold]")
        for var in template.variables:
            mapping = template.variable_mappings.get(var, {})
            source = mapping.get('source', 'manual')
            console.print(f"  • {{{{ {var} }}}}  [dim]({source})[/dim]")

    if template.tags:
        console.print(f"\n[bold]Tags:[/bold] {', '.join(template.tags)}")


@engine_cli.command("generate")
@click.argument("template_id", type=int)
@click.option("--var", "-v", multiple=True, help="Variable in format name=value")
@click.option("--output", "-o", type=click.Path(), help="Output file path")
@click.option("--case-id", help="Case ID to pull data from (future)")
def engine_generate(template_id: int, var: tuple, output: str, case_id: str):
    """
    Generate a document from a template.

    Example:
        agent.py engine generate 42 \\
            -v "defendant_name=John Smith" \\
            -v "case_number=26JE-CR00123" \\
            -v "county=Jefferson"
    """
    from document_engine import get_engine
    from pathlib import Path

    engine = get_engine()

    # Parse variables
    variables = {}
    for v in var:
        if "=" not in v:
            console.print(f"[red]Invalid variable format: {v}[/red]")
            console.print("Use: --var 'name=value'")
            return
        name, value = v.split("=", 1)
        variables[name.strip()] = value.strip()

    # Add computed variables
    variables.setdefault('today', date.today().strftime("%B %d, %Y"))
    variables.setdefault('current_date', date.today().strftime("%B %d, %Y"))

    # Get template to show required variables
    template = engine.get_template(template_id)
    if not template:
        console.print(f"[red]Template {template_id} not found[/red]")
        return

    # Check for missing variables
    missing = [v for v in template.variables if v not in variables]
    if missing:
        console.print(f"[yellow]Warning: Missing variables: {', '.join(missing)}[/yellow]")
        console.print("These will appear as {{variable_name}} in the output.")

    # Generate
    output_path = Path(output) if output else None

    with console.status("Generating document..."):
        try:
            doc_bytes, filename = engine.generate_document(
                template_id=template_id,
                variables=variables,
                output_path=output_path,
            )
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
            return

    # Save if no output path specified
    if not output_path:
        output_dir = DATA_DIR / "generated"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / filename
        output_path.write_bytes(doc_bytes)

    console.print(Panel(
        f"[bold green]Document Generated[/bold green]\n\n"
        f"Template: {template.name}\n"
        f"Variables used: {len(variables)}\n"
        f"Output: {output_path}",
        title="Success"
    ))


@engine_cli.command("analyze")
@click.argument("file", type=click.Path(exists=True))
def engine_analyze(file: str):
    """
    Analyze a .docx file to detect variables and suggest category.

    Example:
        agent.py engine analyze "Motion to Dismiss.docx"
    """
    from document_engine import get_engine, DocumentCategory
    from pathlib import Path

    engine = get_engine()
    file_path = Path(file)

    # Read and analyze
    content = file_path.read_bytes()

    console.print(f"[bold]Analyzing: {file_path.name}[/bold]\n")

    # Detect category
    category, subcategory, court_type, jurisdiction = engine.categorize_document(file_path.name)
    console.print(f"Category: [cyan]{category.value}[/cyan]")
    if subcategory:
        console.print(f"Subcategory: [cyan]{subcategory}[/cyan]")
    if court_type:
        console.print(f"Court type: [cyan]{court_type}[/cyan]")
    if jurisdiction:
        console.print(f"Jurisdiction: [cyan]{jurisdiction}[/cyan]")

    # Detect variables
    variables = engine.detect_variables(content)

    if variables:
        console.print(f"\n[bold]Detected Variables ({len(variables)}):[/bold]")
        table = Table()
        table.add_column("Variable")
        table.add_column("Occurrences")
        table.add_column("Suggested Source")
        table.add_column("Context Sample")

        for v in sorted(variables, key=lambda x: -x.occurrences):
            context = v.sample_context[:40] + "..." if len(v.sample_context) > 40 else v.sample_context
            table.add_row(
                f"{{{{ {v.name} }}}}",
                str(v.occurrences),
                v.suggested_source.value,
                context.replace("\n", " "),
            )

        console.print(table)
    else:
        console.print("\n[yellow]No {{variable}} patterns detected.[/yellow]")
        console.print("Add variables using {{variable_name}} syntax in your document.")


@engine_cli.command("chat")
@click.option("--firm-id", required=True, help="Firm ID")
@click.option("--attorney-id", type=int, default=None, help="Attorney ID (uses primary if not specified)")
def engine_chat(firm_id: str, attorney_id: int):
    """
    Start an interactive document generation chat.

    Conversational interface where you can request documents naturally.

    Example:
        agent.py engine chat --firm-id jcs_law
        agent.py engine chat --firm-id jcs_law --attorney-id 1

    Then say things like:
        "I need a motion to dismiss for Jefferson County"
        "The defendant is John Smith, case number 26JE-CR00123"
        "Yes, export it"
    """
    from document_chat import DocumentChatEngine

    # Show attorney info if available
    attorney_info = ""
    try:
        from attorney_profiles import get_attorney, get_primary_attorney
        if attorney_id:
            att = get_attorney(attorney_id)
        else:
            att = get_primary_attorney(firm_id)
        if att:
            attorney_info = f"\n[dim]Attorney: {att.attorney_name} (#{att.bar_number})[/dim]"
        else:
            attorney_info = "\n[yellow]No attorney profile found. Documents will use placeholders.[/yellow]"
    except Exception:
        attorney_info = "\n[yellow]Attorney profiles not configured.[/yellow]"

    console.print(Panel(
        "[bold]Document Generation Assistant[/bold]\n\n"
        "I can help you generate legal documents. Just tell me what\n"
        "type of document you need and for which court/jurisdiction.\n\n"
        "[dim]Examples:[/dim]\n"
        "  • 'I need a motion to dismiss for Jefferson County'\n"
        "  • 'Generate a waiver of arraignment'\n"
        "  • 'Create a preservation letter for MSHP'\n\n"
        f"Type 'quit' to exit.{attorney_info}",
        title="Welcome"
    ))

    try:
        chat_engine = DocumentChatEngine(firm_id=firm_id, attorney_id=attorney_id)
    except Exception as e:
        console.print(f"[red]Error initializing chat: {e}[/red]")
        return

    while True:
        try:
            user_input = console.input("\n[bold cyan]You:[/bold cyan] ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if not user_input:
            continue
        if user_input.lower() in ['quit', 'exit', 'q']:
            console.print("\n[dim]Goodbye![/dim]")
            break

        with console.status("Thinking..."):
            try:
                response = chat_engine.chat(user_input)
            except Exception as e:
                console.print(f"[red]Error: {e}[/red]")
                continue

        console.print(f"\n[bold green]Assistant:[/bold green]\n{response}")


# ============================================================================
# Quick Document Generation (Shortcut)
# ============================================================================

@click.command("generate-doc")
@click.argument("request", nargs=-1)
@click.option("--firm-id", default="jcs_law", help="Firm ID")
@click.option("--attorney-id", type=int, default=None, help="Attorney ID (uses primary if not specified)")
def quick_generate_doc(request: tuple, firm_id: str, attorney_id: int):
    """
    Quick document generation from natural language.

    Example:
        agent.py generate-doc motion to dismiss for Jefferson County --firm-id jcs_law
        agent.py generate-doc motion to dismiss for Jefferson County --attorney-id 1
    """
    if not request:
        console.print("[red]Please specify what document you need[/red]")
        console.print("Example: agent.py generate-doc motion to dismiss for Jefferson County")
        return

    request_text = " ".join(request)

    from document_chat import DocumentChatEngine

    try:
        chat_engine = DocumentChatEngine(firm_id=firm_id, attorney_id=attorney_id)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        return

    console.print(f"[bold]Request:[/bold] {request_text}\n")

    with console.status("Finding template and analyzing..."):
        response = chat_engine.chat(request_text)

    console.print(response)


# ============================================================================
# Attorney Profile Management Commands
# ============================================================================

@click.group()
def attorney_cli():
    """Attorney profile management."""
    pass


@attorney_cli.command("add")
@click.option("--firm-id", required=True, help="Firm identifier")
@click.option("--name", required=True, help="Attorney full name")
@click.option("--bar", required=True, help="Bar number")
@click.option("--email", required=True, help="Email address")
@click.option("--phone", required=True, help="Phone number")
@click.option("--fax", default=None, help="Fax number (optional)")
@click.option("--firm-name", required=True, help="Law firm name")
@click.option("--address", required=True, help="Firm street address")
@click.option("--city", required=True, help="City")
@click.option("--state", default="Missouri", help="State")
@click.option("--zip", "zip_code", required=True, help="ZIP code")
@click.option("--primary", is_flag=True, help="Set as primary attorney for firm")
def attorney_add(firm_id: str, name: str, bar: str, email: str, phone: str,
                 fax: str, firm_name: str, address: str, city: str,
                 state: str, zip_code: str, primary: bool):
    """Add a new attorney profile."""
    from attorney_profiles import AttorneyProfile, save_attorney, get_attorney_db

    profile = AttorneyProfile(
        firm_id=firm_id,
        attorney_name=name,
        bar_number=bar,
        email=email,
        phone=phone,
        fax=fax,
        firm_name=firm_name,
        firm_address=address,
        firm_city=city,
        firm_state=state,
        firm_zip=zip_code,
        is_primary=primary,
    )

    attorney_id = save_attorney(profile)

    console.print(f"[green]Attorney added successfully![/green]")
    console.print(f"  ID: {attorney_id}")
    console.print(f"  Name: {name}")
    console.print(f"  Bar #: {bar}")
    console.print(f"  Firm: {firm_name}")
    if primary:
        console.print(f"  [bold]Primary attorney for {firm_id}[/bold]")


@attorney_cli.command("list")
@click.option("--firm-id", required=True, help="Firm identifier")
def attorney_list(firm_id: str):
    """List all attorneys for a firm."""
    from attorney_profiles import list_attorneys

    attorneys = list_attorneys(firm_id)

    if not attorneys:
        console.print(f"[yellow]No attorneys found for firm '{firm_id}'[/yellow]")
        console.print("\nAdd one with: agent.py attorney add --firm-id ...")
        return

    table = Table(title=f"Attorneys for {firm_id}")
    table.add_column("ID", style="cyan")
    table.add_column("Name", style="green")
    table.add_column("Bar #")
    table.add_column("Email")
    table.add_column("Primary", style="yellow")

    for att in attorneys:
        table.add_row(
            str(att.id),
            att.attorney_name,
            att.bar_number,
            att.email,
            "✓" if att.is_primary else ""
        )

    console.print(table)


@attorney_cli.command("show")
@click.argument("attorney_id", type=int)
def attorney_show(attorney_id: int):
    """Show details for an attorney."""
    from attorney_profiles import get_attorney

    att = get_attorney(attorney_id)

    if not att:
        console.print(f"[red]Attorney {attorney_id} not found[/red]")
        return

    console.print(Panel(f"""
[bold]{att.attorney_name}[/bold]
Bar Number: {att.bar_number}
Email: {att.email}
Phone: {att.phone}
{"Fax: " + att.fax if att.fax else ""}

[bold]Firm:[/bold]
{att.firm_name}
{att.firm_address}
{att.firm_city}, {att.firm_state} {att.firm_zip}

[bold]Signature Block Preview:[/bold]
{att.get_signature_block()}
""", title=f"Attorney #{att.id}"))


@attorney_cli.command("set-primary")
@click.option("--firm-id", required=True, help="Firm identifier")
@click.argument("attorney_id", type=int)
def attorney_set_primary(firm_id: str, attorney_id: int):
    """Set an attorney as the primary for their firm."""
    from attorney_profiles import get_attorney_db

    db = get_attorney_db()
    db.set_primary_attorney(firm_id, attorney_id)

    console.print(f"[green]Attorney {attorney_id} is now the primary for {firm_id}[/green]")


@attorney_cli.command("setup")
@click.option("--firm-id", required=True, help="Firm identifier")
def attorney_setup(firm_id: str):
    """Interactive setup for a new attorney profile."""
    from attorney_profiles import AttorneyProfile, save_attorney

    console.print(Panel("Attorney Profile Setup", style="bold blue"))
    console.print("Enter attorney and firm information:\n")

    # Collect info interactively
    name = click.prompt("Attorney full name")
    bar = click.prompt("Bar number")
    email = click.prompt("Email address")
    phone = click.prompt("Phone number")
    fax = click.prompt("Fax number (or press Enter to skip)", default="", show_default=False)

    console.print("\n[bold]Firm Information:[/bold]")
    firm_name = click.prompt("Firm name")
    address = click.prompt("Street address")
    city = click.prompt("City")
    state = click.prompt("State", default="Missouri")
    zip_code = click.prompt("ZIP code")

    primary = click.confirm("\nSet as primary attorney for this firm?", default=True)

    profile = AttorneyProfile(
        firm_id=firm_id,
        attorney_name=name,
        bar_number=bar,
        email=email,
        phone=phone,
        fax=fax if fax else None,
        firm_name=firm_name,
        firm_address=address,
        firm_city=city,
        firm_state=state,
        firm_zip=zip_code,
        is_primary=primary,
    )

    # Show preview
    console.print("\n[bold]Signature Block Preview:[/bold]")
    console.print(profile.get_signature_block())

    if click.confirm("\nSave this profile?", default=True):
        attorney_id = save_attorney(profile)
        console.print(f"\n[green]Attorney profile saved! ID: {attorney_id}[/green]")
    else:
        console.print("[yellow]Profile not saved.[/yellow]")
