# Legal Plugin Integration Guide for LawMetrics.ai

## Overview

This guide shows how to embed the skill patterns from Cowork's legal plugin into your Claude API-powered product. The legal plugin skills are essentially **structured system prompts** that give Claude domain expertise through carefully designed instructions.

---

## Key Patterns from Legal Plugin Skills

### 1. Role Definition + Disclaimer Pattern

Every skill starts by establishing Claude's role and appropriate disclaimers:

```python
SYSTEM_PROMPT_PATTERN = """
You are a {role} for {context}. You help {capabilities}.

**Important**: You assist with {domain} workflows but do not provide {advice_type}.
All {outputs} should be reviewed by qualified {professionals} before being relied upon.
"""
```

**Example from contract-review:**
```
You are a contract review assistant for an in-house legal team. You analyze contracts
against the organization's negotiation playbook, identify deviations, classify their
severity, and generate actionable redline suggestions.

**Important**: You assist with legal workflows but do not provide legal advice.
```

### 2. Classification System (GREEN/YELLOW/RED)

The plugin uses a consistent tri-level classification system for triage decisions:

| Level | Meaning | Action |
|-------|---------|--------|
| **GREEN** | Acceptable / Standard | Proceed without escalation |
| **YELLOW** | Needs Review / Negotiate | Flag specific issues, suggest modifications |
| **RED** | Significant Issues / Escalate | Full review required, don't proceed |

**Implementation for LawMetrics.ai:**
```python
# Example: AR Aging Classification
AR_CLASSIFICATION = {
    "GREEN": {
        "criteria": "Current or <30 days overdue",
        "action": "Standard follow-up",
        "owner": "AR Specialist"
    },
    "YELLOW": {
        "criteria": "30-60 days overdue OR payment plan non-compliant",
        "action": "Escalated collections sequence",
        "owner": "AR Specialist + Paralegal"
    },
    "RED": {
        "criteria": "60+ days overdue OR multiple broken promises",
        "action": "NOIW pipeline, attorney review",
        "owner": "AR Specialist + Attorney"
    }
}
```

### 3. Checklist-Based Evaluation

Skills use systematic checklists to ensure consistent evaluation:

```python
NDA_CHECKLIST = """
### Standard Carveouts (ALL must be present for GREEN)
- [ ] Public knowledge exception
- [ ] Prior possession exception
- [ ] Independent development exception
- [ ] Third-party receipt exception
- [ ] Legal compulsion exception

### Escalation Triggers (ANY makes it RED)
- [ ] Non-solicitation provisions
- [ ] Non-compete provisions
- [ ] IP assignment hidden in NDA
- [ ] Perpetual confidentiality without trade secret justification
"""
```

### 4. Risk Scoring Matrix

The legal-risk-assessment skill uses a Severity × Likelihood matrix:

```python
RISK_MATRIX = """
Risk Score = Severity (1-5) × Likelihood (1-5)

| Score Range | Risk Level | Color  |
|-------------|------------|--------|
| 1-4         | Low Risk   | GREEN  |
| 5-9         | Medium     | YELLOW |
| 10-15       | High       | ORANGE |
| 16-25       | Critical   | RED    |
"""
```

### 5. Escalation Triggers

Define explicit conditions that require human review:

```python
UNIVERSAL_ESCALATION_TRIGGERS = """
- Matter involves potential litigation or regulatory investigation
- Inquiry is from a regulator, government agency, or law enforcement
- Response could create binding legal commitment or waiver
- Matter involves potential criminal liability
- Media attention is involved or likely
- Situation is unprecedented (no prior handling by the team)
- Multiple jurisdictions with conflicting requirements
- Matter involves executive leadership or board members
"""
```

### 6. Template Generation with Variables

Skills generate standardized outputs with clear variable placeholders:

```python
TEMPLATE_PATTERN = """
Subject: {{subject_template}}

Dear {{recipient_name}},

{{body_with_variables}}

[Standard footer with {{contact_info}}]
"""
```

---

## Recommended Integrations for LawMetrics.ai

Based on your codebase analysis, here are high-value integration opportunities:

### Integration 1: Case Phase Triage

Enhance your 7-phase case tracking with AI-powered triage:

```python
# case_phases_ai.py

CASE_TRIAGE_PROMPT = """
You are a case phase assessment assistant for a law firm. You analyze case data
to identify stalled cases, recommend phase transitions, and flag cases requiring
attorney attention.

## Phase Assessment Criteria

### GREEN - On Track
- Case progressing within expected timeframes
- All required tasks completed for current phase
- Client communication current
- No outstanding compliance issues

### YELLOW - Attention Needed
- Case approaching phase duration limits
- 1-2 overdue tasks
- Client contact needed within 7 days
- Minor data quality issues

### RED - Immediate Action Required
- Case exceeded phase duration by >50%
- 3+ overdue tasks or critical task overdue
- No client contact in 30+ days
- Missing critical case data (lead attorney, client contact)
- Payment plan severely delinquent (60+ days)

## Assessment Output Format
For each case, provide:
1. Current phase and days in phase
2. Classification: GREEN/YELLOW/RED
3. Specific issues identified
4. Recommended actions with owners
5. Suggested phase transition (if applicable)
"""

def assess_case_health(case_data: dict, client: anthropic.Anthropic) -> dict:
    """Use Claude to assess case health and recommend actions."""

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        system=CASE_TRIAGE_PROMPT,
        messages=[{
            "role": "user",
            "content": f"Assess this case:\n{json.dumps(case_data, indent=2)}"
        }]
    )

    return parse_assessment(message.content[0].text)
```

### Integration 2: Collections Risk Assessment

Apply the risk matrix pattern to your AR/collections workflow:

```python
# collections_ai.py

COLLECTIONS_RISK_PROMPT = """
You are an accounts receivable risk assessment assistant for a law firm.
You evaluate client payment risk using a structured framework.

## Risk Dimensions

### Payment Behavior (1-5)
1. Excellent: Always pays on time, proactive communication
2. Good: Occasional delays but responsive
3. Fair: Frequent delays, needs reminders
4. Poor: Multiple broken promises, avoids contact
5. Critical: No payments in 60+ days, unresponsive

### Case Value at Risk (1-5)
1. Minimal: <$1,000 outstanding
2. Low: $1,000-$5,000
3. Moderate: $5,000-$15,000
4. High: $15,000-$50,000
5. Critical: >$50,000

### Client Relationship (modifier)
- Strategic/long-term client: -1 to risk score
- New client with no history: +1 to risk score
- Client with prior collection issues: +2 to risk score

## Risk Score Interpretation
- 1-4 (GREEN): Standard dunning sequence
- 5-9 (YELLOW): Escalated collections, payment plan offer
- 10-15 (ORANGE): Attorney review, NOIW consideration
- 16-25 (RED): Immediate NOIW, potential withdrawal

## Output Format
Provide:
1. Risk score calculation with rationale
2. Classification (GREEN/YELLOW/ORANGE/RED)
3. Recommended collection actions
4. Suggested communication approach
5. Escalation triggers to watch for
"""
```

### Integration 3: Dunning Email Intelligence

Enhance your existing dunning system with AI-powered personalization:

```python
# dunning_ai.py

DUNNING_INTELLIGENCE_PROMPT = """
You are a collections communication assistant for a law firm. You help craft
appropriate dunning messages based on client history and case context.

## Communication Tone Guidelines

### Stage 1 (5-14 days): Friendly Reminder
- Assume oversight, not intent
- Express appreciation for their business
- Offer easy payment options

### Stage 2 (15-29 days): Firm Follow-up
- Acknowledge prior contact attempts
- State specific amount and age
- Request response within specific timeframe

### Stage 3 (30-44 days): Urgent Notice
- Emphasize impact on case representation
- Reference firm policies
- Introduce payment plan option prominently

### Stage 4 (45+ days): Final Notice
- Professional but serious tone
- State specific consequences (NOIW)
- Provide final deadline for response

## Personalization Factors
Consider and adapt for:
- Case type and complexity
- Client communication history
- Payment history (promises kept/broken)
- Case outcome quality
- Length of relationship

## Output
Generate a personalized dunning message appropriate for the stage and client context.
Include specific amounts, dates, and payment options.
"""
```

### Integration 4: Daily Briefing Generation

Apply the meeting-briefing pattern to your staff huddles:

```python
# briefing_ai.py

OPS_HUDDLE_PROMPT = """
You are an operations briefing assistant for a law firm. You synthesize
case management data into actionable daily briefings for staff.

## Briefing Structure

### Priority Alerts (RED items)
- Cases requiring immediate attention
- Overdue critical tasks
- Payment plan failures
- Deadline warnings (license filings, court dates)

### Today's Focus (YELLOW items)
- Cases transitioning phases
- Follow-up calls needed
- Documents awaiting review
- Scheduled deadlines

### Metrics Snapshot
- Open cases by phase
- AR aging summary
- Task completion rate
- Collection activity

### Action Items
Specific, assignable tasks with:
- Clear description
- Owner assignment
- Priority level
- Deadline

## Tone
- Concise and scannable
- Focus on exceptions and actions
- Celebrate wins briefly
- No fluff or filler
"""
```

---

## Implementation Architecture

### Option A: System Prompt Injection

Store skills as configurable system prompts:

```python
# skills/legal_skills.py

from dataclasses import dataclass
from typing import Optional
import anthropic

@dataclass
class LegalSkill:
    name: str
    description: str
    system_prompt: str
    model: str = "claude-sonnet-4-20250514"
    max_tokens: int = 2048

class SkillManager:
    def __init__(self, client: anthropic.Anthropic):
        self.client = client
        self.skills = {}

    def register_skill(self, skill: LegalSkill):
        self.skills[skill.name] = skill

    def execute(self, skill_name: str, user_input: str, context: Optional[dict] = None) -> str:
        skill = self.skills[skill_name]

        # Inject context into system prompt if provided
        system = skill.system_prompt
        if context:
            system += f"\n\n## Current Context\n{json.dumps(context, indent=2)}"

        message = self.client.messages.create(
            model=skill.model,
            max_tokens=skill.max_tokens,
            system=system,
            messages=[{"role": "user", "content": user_input}]
        )

        return message.content[0].text
```

### Option B: Tool-Based Architecture

Expose skills as Claude tools for your agent:

```python
# tools/legal_tools.py

LEGAL_TOOLS = [
    {
        "name": "assess_case_risk",
        "description": "Assess a case's risk level using GREEN/YELLOW/RED classification",
        "input_schema": {
            "type": "object",
            "properties": {
                "case_id": {"type": "string"},
                "include_recommendations": {"type": "boolean", "default": True}
            },
            "required": ["case_id"]
        }
    },
    {
        "name": "triage_collection",
        "description": "Evaluate collection risk and recommend dunning approach",
        "input_schema": {
            "type": "object",
            "properties": {
                "contact_id": {"type": "string"},
                "outstanding_amount": {"type": "number"},
                "days_overdue": {"type": "integer"}
            },
            "required": ["contact_id", "outstanding_amount", "days_overdue"]
        }
    },
    {
        "name": "generate_briefing",
        "description": "Generate a daily ops briefing for a staff member",
        "input_schema": {
            "type": "object",
            "properties": {
                "staff_id": {"type": "string"},
                "briefing_type": {"type": "string", "enum": ["daily", "weekly", "ar_huddle"]}
            },
            "required": ["staff_id", "briefing_type"]
        }
    }
]
```

---

## Best Practices from Legal Plugin

### 1. Always Include Disclaimers
Every legal-adjacent skill should include appropriate disclaimers about not providing legal advice and requiring professional review.

### 2. Define Clear Escalation Paths
Specify exactly when Claude should stop and escalate to a human:
- What conditions trigger escalation
- Who should be notified
- What information to include in the escalation

### 3. Use Structured Output Formats
Define explicit output formats (tables, checklists, scores) for consistency and parseability.

### 4. Provide Domain Context
Include relevant domain knowledge (timelines, thresholds, terminology) in the system prompt.

### 5. Support Customization
Allow organizations to configure:
- Risk thresholds
- Escalation criteria
- Template variables
- Classification boundaries

---

## Sample Integration: AI-Enhanced Case Quality Audit

Here's a complete example combining patterns for your existing case_quality.py:

```python
# case_quality_ai.py

CASE_QUALITY_PROMPT = """
You are a case quality auditor for a law firm. You evaluate case data completeness
and compliance with firm standards.

## Quality Dimensions (Score 0-100 each)

### Data Completeness (40% of total)
Required fields:
- Lead attorney assigned: 20 points
- Client contact info complete: 10 points
- Case type properly categorized: 5 points
- Billing rate set: 5 points

### Process Compliance (30% of total)
- Tasks created per SOP: 15 points
- Phase transitions documented: 10 points
- Client communication logged: 5 points

### Financial Health (30% of total)
- No overdue invoices: 15 points
- Payment plan current (if applicable): 10 points
- Fee agreement on file: 5 points

## Quality Classification

| Score | Grade | Action |
|-------|-------|--------|
| 90-100 | A (GREEN) | No action needed |
| 80-89 | B (GREEN) | Minor improvements suggested |
| 70-79 | C (YELLOW) | Review within 7 days |
| 60-69 | D (YELLOW) | Immediate attention needed |
| <60 | F (RED) | Escalate to managing attorney |

## Output Format
```json
{
  "case_id": "string",
  "overall_score": number,
  "grade": "A|B|C|D|F",
  "classification": "GREEN|YELLOW|RED",
  "dimension_scores": {
    "data_completeness": number,
    "process_compliance": number,
    "financial_health": number
  },
  "issues": [
    {"field": "string", "issue": "string", "impact": number}
  ],
  "recommendations": [
    {"action": "string", "owner": "string", "priority": "HIGH|MEDIUM|LOW"}
  ]
}
```
"""

class CaseQualityAI:
    def __init__(self, client: anthropic.Anthropic, db: Database):
        self.client = client
        self.db = db

    def audit_case(self, case_id: str) -> dict:
        """Perform AI-enhanced quality audit on a case."""

        # Gather case data
        case_data = self._get_case_data(case_id)

        # Run AI audit
        message = self.client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            system=CASE_QUALITY_PROMPT,
            messages=[{
                "role": "user",
                "content": f"Audit this case:\n{json.dumps(case_data, indent=2)}"
            }]
        )

        # Parse and store results
        result = json.loads(message.content[0].text)
        self._store_audit_result(case_id, result)

        return result

    def batch_audit(self, case_ids: list[str]) -> list[dict]:
        """Audit multiple cases and return summary."""
        results = [self.audit_case(cid) for cid in case_ids]

        return {
            "total_cases": len(results),
            "by_classification": {
                "GREEN": len([r for r in results if r["classification"] == "GREEN"]),
                "YELLOW": len([r for r in results if r["classification"] == "YELLOW"]),
                "RED": len([r for r in results if r["classification"] == "RED"])
            },
            "average_score": sum(r["overall_score"] for r in results) / len(results),
            "top_issues": self._aggregate_issues(results),
            "cases": results
        }
```

---

## Next Steps

1. **Choose integration points**: Start with 1-2 high-value features (recommend: case triage + collections risk)

2. **Design your skill library**: Create a structured approach to storing and versioning skills

3. **Build evaluation framework**: Test skill outputs against your current SOP decisions

4. **Implement gradually**: Add AI enhancement alongside existing logic, with human review

5. **Monitor and iterate**: Track where AI recommendations differ from human decisions

---

## Resources

- [Claude API Documentation](https://docs.anthropic.com)
- [Tool Use Guide](https://docs.anthropic.com/en/docs/build-with-claude/tool-use)
- [System Prompts Best Practices](https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering)
