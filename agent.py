#!/usr/bin/env python3
"""
MyCase Automation Agent — CLI Entry Point

Thin wrapper that registers command groups from commands/ package.
All command logic lives in commands/*.py files.
"""
import click

from commands.auth import auth
from commands.collections import collections
from commands.deadlines import deadlines
from commands.analytics import analytics
from commands.templates_cmd import templates
from commands.sync import sync_data, run_all
from commands.kpi import kpi
from commands.plans import plans
from commands.intake import intake
from commands.tasks import tasks
from commands.quality import quality
from commands.sop import sop
from commands.scheduler import scheduler
from commands.promises import promises
from commands.notifications import notify
from commands.trends import trends
from commands.reports import reports
from commands.users import users
from commands.phases import phases
from commands.dashboard import dashboard_cmd

# AI and Document Generation Commands
from ai_commands import (
    ai_cli, templates_cli, docs_cli, pleadings_cli,
    engine_cli, quick_generate_doc, attorney_cli,
)


@click.group()
@click.version_option(version="2.0.0")
def cli():
    """
    MyCase Automation Agent

    Automate client notices, collections, deadline tracking, and analytics
    for your law firm using the MyCase API.
    """
    pass


# ── Register command groups from commands/ package ──────────────────────

cli.add_command(auth)
cli.add_command(collections)
cli.add_command(deadlines)
cli.add_command(analytics)
cli.add_command(templates, name="templates")
cli.add_command(sync_data, name="sync")
cli.add_command(run_all, name="run")
cli.add_command(kpi)
cli.add_command(plans)
cli.add_command(intake)
cli.add_command(tasks)
cli.add_command(quality)
cli.add_command(sop)
cli.add_command(scheduler)
cli.add_command(promises)
cli.add_command(notify)
cli.add_command(trends)
cli.add_command(reports)
cli.add_command(users)
cli.add_command(phases)
cli.add_command(dashboard_cmd, name="dashboard")

# ── Register AI / Document Generation groups ────────────────────────────

cli.add_command(ai_cli, name="ai")
cli.add_command(templates_cli, name="ai-templates")
cli.add_command(docs_cli, name="docs")
cli.add_command(pleadings_cli, name="pleadings")
cli.add_command(engine_cli, name="engine")
cli.add_command(quick_generate_doc, name="generate-doc")
cli.add_command(attorney_cli, name="attorney")


def main():
    """Main entry point."""
    cli()


if __name__ == "__main__":
    main()
