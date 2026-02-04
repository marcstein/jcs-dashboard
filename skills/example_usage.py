#!/usr/bin/env python3
"""
Example usage of LawMetrics.ai skills module.

Shows how to integrate AI-enhanced skills with your existing
agent.py CLI and database infrastructure.
"""

import os
import sys
from datetime import datetime, date

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from skills import (
    SkillManager,
    CaseTriageSkill,
    CollectionsRiskSkill,
    BriefingSkill,
)
from skills.briefing import format_briefing_markdown


def example_case_triage():
    """Example: Assess a case's health status."""
    print("=" * 60)
    print("Example 1: Case Triage")
    print("=" * 60)

    # Initialize skill manager
    manager = SkillManager()
    manager.register(CaseTriageSkill())

    # Example case data (would come from your cache/API)
    case_data = {
        "case_id": "12345",
        "case_name": "Smith v. State - DWI",
        "case_type": "DWI",
        "current_phase": 2,  # Discovery
        "phase_name": "Discovery & Investigation",
        "days_in_phase": 45,
        "expected_phase_duration": 56,
        "lead_attorney": "Anthony Muhlenkamp",
        "assigned_paralegal": "Alison Ehrhard",
        "client_name": "John Smith",
        "client_contact": {
            "email": "jsmith@email.com",
            "phone": "555-123-4567",
            "last_contact": "2026-01-20"
        },
        "tasks": {
            "total": 12,
            "completed": 8,
            "overdue": 2,
            "overdue_tasks": [
                {"name": "Review Discovery", "due_date": "2026-01-25"},
                {"name": "Client History Worksheet", "due_date": "2026-01-28"}
            ]
        },
        "financial": {
            "total_billed": 3500,
            "total_paid": 2000,
            "outstanding": 1500,
            "oldest_invoice_age_days": 35,
            "payment_plan": {
                "active": True,
                "compliant": False,
                "last_payment": "2026-01-01"
            }
        },
        "deadlines": {
            "dor_filed": True,
            "next_court_date": "2026-02-15",
            "discovery_deadline": "2026-02-10"
        }
    }

    # Execute triage
    result = manager.execute("case_triage", case_data)

    # Display results
    print(f"\nClassification: {result.classification.value}")
    print(f"Score: {result.score}")
    print(f"Summary: {result.summary}")

    if result.issues:
        print("\nIssues Found:")
        for issue in result.issues:
            print(f"  - [{issue.get('severity', 'medium').upper()}] {issue.get('description')}")

    if result.recommendations:
        print("\nRecommendations:")
        for rec in result.recommendations:
            print(f"  - {rec.get('action')} (Owner: {rec.get('owner')}, Priority: {rec.get('priority')})")

    if result.escalation_required:
        print(f"\n⚠️ ESCALATION REQUIRED: {result.escalation_reason}")

    return result


def example_collections_risk():
    """Example: Assess collection risk for a client."""
    print("\n" + "=" * 60)
    print("Example 2: Collections Risk Assessment")
    print("=" * 60)

    manager = SkillManager()
    manager.register(CollectionsRiskSkill())

    # Example client collection data
    collection_data = {
        "contact_id": "C-9876",
        "client_name": "Jane Doe",
        "cases": [
            {"case_id": "12345", "case_name": "Doe v. State", "status": "active"}
        ],
        "financial_summary": {
            "total_outstanding": 8500,
            "invoices": [
                {"id": "INV-001", "amount": 3500, "days_past_due": 45},
                {"id": "INV-002", "amount": 5000, "days_past_due": 15}
            ],
            "oldest_invoice_days": 45
        },
        "payment_history": {
            "total_paid_lifetime": 12000,
            "on_time_payment_rate": 0.60,
            "last_payment_date": "2025-12-15",
            "last_payment_amount": 500
        },
        "promises": {
            "total_made": 4,
            "kept": 2,
            "broken": 2,
            "pending": [
                {"amount": 1000, "date": "2026-02-01"}
            ]
        },
        "communication": {
            "last_contact_date": "2026-01-15",
            "contact_attempts_last_30_days": 3,
            "response_rate": 0.33,
            "preferred_channel": "phone"
        },
        "relationship": {
            "client_since": "2024-06-01",
            "total_cases": 2,
            "referral_source": "existing client referral"
        },
        "current_dunning_stage": 2
    }

    # Execute risk assessment
    result = manager.execute("collections_risk", collection_data)

    # Display results
    print(f"\nClassification: {result.classification.value}")
    print(f"Risk Score: {result.score}/25")
    print(f"Summary: {result.summary}")

    meta = result.metadata
    print(f"\nSeverity: {meta.get('severity', {}).get('score', '?')}/5 - {meta.get('severity', {}).get('label', '?')}")
    print(f"Likelihood: {meta.get('likelihood', {}).get('score', '?')}/5 - {meta.get('likelihood', {}).get('label', '?')}")

    print(f"\nRecommended Stage: {meta.get('recommended_stage')}")
    print(f"Communication Tone: {meta.get('communication_tone')}")
    print(f"Payment Plan Recommended: {meta.get('payment_plan_recommended')}")
    print(f"NOIW Recommended: {meta.get('noiw_recommended')}")

    if result.recommendations:
        print("\nRecommended Actions:")
        for action in result.recommendations:
            print(f"  - {action.get('action')} ({action.get('timing')}, via {action.get('channel')})")

    return result


def example_daily_briefing():
    """Example: Generate daily briefing for staff member."""
    print("\n" + "=" * 60)
    print("Example 3: Daily Briefing Generation")
    print("=" * 60)

    manager = SkillManager()
    manager.register(BriefingSkill())

    # Example staff data with their workload
    staff_briefing_data = {
        "staff_member": {
            "name": "Melissa Scarlett",
            "role": "AR Specialist",
            "email": "melissa@jcslaw.com"
        },
        "date": str(date.today()),
        "ar_summary": {
            "total_ar": 1450000,
            "current": 258000,
            "30_60_days": 290000,
            "60_120_days": 520000,
            "120_plus_days": 382000,
            "percent_over_60": 82.2
        },
        "payment_plans": {
            "total_active": 89,
            "compliant": 7,
            "non_compliant": 82,
            "compliance_rate": 7.6
        },
        "noiw_pipeline": {
            "total_cases": 163,
            "critical_60_plus": 147,
            "high_30_59": 16,
            "pending_notices": 12,
            "sent_awaiting_response": 45
        },
        "promises_due_today": [
            {"client": "John Smith", "amount": 500, "case": "Smith v. State"},
            {"client": "Mary Johnson", "amount": 750, "case": "Johnson DWI"}
        ],
        "recent_payments": [
            {"client": "Bob Wilson", "amount": 2500, "date": "2026-02-03"}
        ],
        "tasks": {
            "assigned": 15,
            "due_today": 4,
            "overdue": 2
        },
        "scheduled_calls": [
            {"time": "10:00 AM", "client": "Jane Doe", "purpose": "Payment arrangement"},
            {"time": "2:30 PM", "client": "Tom Brown", "purpose": "NOIW follow-up"}
        ]
    }

    # Execute briefing generation
    result = manager.execute("briefing", staff_briefing_data)

    # Display formatted briefing
    print("\n" + format_briefing_markdown(result))

    return result


def example_batch_processing():
    """Example: Process multiple cases for triage."""
    print("\n" + "=" * 60)
    print("Example 4: Batch Case Processing")
    print("=" * 60)

    manager = SkillManager()
    manager.register(CaseTriageSkill())

    # Simulate multiple cases (would come from your database)
    cases = [
        {
            "case_id": "001",
            "case_name": "Case A",
            "current_phase": 2,
            "days_in_phase": 30,
            "expected_phase_duration": 56,
            "tasks": {"overdue": 0},
            "financial": {"outstanding": 0}
        },
        {
            "case_id": "002",
            "case_name": "Case B",
            "current_phase": 3,
            "days_in_phase": 80,
            "expected_phase_duration": 70,
            "tasks": {"overdue": 3},
            "financial": {"outstanding": 5000, "oldest_invoice_age_days": 65}
        },
        {
            "case_id": "003",
            "case_name": "Case C",
            "current_phase": 1,
            "days_in_phase": 5,
            "expected_phase_duration": 3,
            "tasks": {"overdue": 1},
            "financial": {"outstanding": 0}
        },
    ]

    results = manager.batch_execute("case_triage", cases)

    # Summary
    print("\nBatch Processing Results:")
    print("-" * 40)

    for case, result in zip(cases, results):
        status_emoji = {
            "GREEN": "🟢",
            "YELLOW": "🟡",
            "RED": "🔴"
        }.get(result.classification.value, "⬜")

        print(f"{status_emoji} {case['case_name']}: {result.classification.value} (Score: {result.score})")

    # Aggregate stats
    classifications = [r.classification.value for r in results]
    print("\nSummary:")
    print(f"  GREEN: {classifications.count('GREEN')}")
    print(f"  YELLOW: {classifications.count('YELLOW')}")
    print(f"  RED: {classifications.count('RED')}")
    print(f"  Escalations Required: {sum(1 for r in results if r.escalation_required)}")

    return results


def integration_with_existing_cli():
    """
    Example showing how to integrate skills with your existing agent.py CLI.

    This would be added as new commands in your Click CLI.
    """
    example_cli_code = '''
# Add to agent.py

from skills import SkillManager, CaseTriageSkill, CollectionsRiskSkill, BriefingSkill
from skills.briefing import format_briefing_markdown

# Initialize skills
skill_manager = SkillManager()
skill_manager.register(CaseTriageSkill())
skill_manager.register(CollectionsRiskSkill())
skill_manager.register(BriefingSkill())

@cli.group()
def ai():
    """AI-enhanced analysis commands."""
    pass

@ai.command("triage")
@click.argument("case_id")
def ai_triage_case(case_id: str):
    """AI-assess a case's health status."""
    # Get case data from your cache
    case_data = get_case_data_from_cache(case_id)

    with console.status("Running AI assessment..."):
        result = skill_manager.execute("case_triage", case_data)

    # Display with rich formatting
    color = {"GREEN": "green", "YELLOW": "yellow", "RED": "red"}[result.classification.value]
    console.print(Panel(
        f"[{color}]{result.classification.value}[/{color}] - Score: {result.score}\\n\\n{result.summary}",
        title=f"Case {case_id} Assessment"
    ))

    if result.issues:
        table = Table(title="Issues Found")
        table.add_column("Severity")
        table.add_column("Description")
        for issue in result.issues:
            table.add_row(issue.get("severity", "medium"), issue.get("description"))
        console.print(table)

@ai.command("collections-risk")
@click.argument("contact_id")
def ai_collections_risk(contact_id: str):
    """AI-assess collection risk for a contact."""
    collection_data = get_collection_data_from_cache(contact_id)

    with console.status("Assessing collection risk..."):
        result = skill_manager.execute("collections_risk", collection_data)

    # Display risk score and recommendations
    console.print(f"Risk Score: {result.score}/25 ({result.classification.value})")
    console.print(f"Recommended Stage: {result.metadata.get('recommended_stage')}")
    console.print(f"Tone: {result.metadata.get('communication_tone')}")

@ai.command("briefing")
@click.argument("staff_name")
@click.option("--export", is_flag=True, help="Export to markdown file")
def ai_briefing(staff_name: str, export: bool):
    """Generate AI-enhanced daily briefing for a staff member."""
    staff_data = get_staff_briefing_data(staff_name)

    with console.status(f"Generating briefing for {staff_name}..."):
        result = skill_manager.execute("briefing", staff_data)

    briefing_md = format_briefing_markdown(result)

    if export:
        filename = f"briefings/{staff_name.lower().replace(' ', '_')}_{date.today()}.md"
        with open(filename, 'w') as f:
            f.write(briefing_md)
        console.print(f"Exported to {filename}")
    else:
        console.print(Markdown(briefing_md))
'''

    print("\nExample CLI Integration Code:")
    print("-" * 40)
    print(example_cli_code)


if __name__ == "__main__":
    # Check for API key
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("⚠️  ANTHROPIC_API_KEY not set. Examples will show structure only.")
        print("   Set your API key to run live examples.")
        print()

        # Show integration example without running
        integration_with_existing_cli()
    else:
        # Run all examples
        example_case_triage()
        example_collections_risk()
        example_daily_briefing()
        example_batch_processing()
        integration_with_existing_cli()
