"""
Case Triage Skill

AI-enhanced case health assessment using the legal plugin's
GREEN/YELLOW/RED classification pattern.

Integrates with LawMetrics.ai's 7-phase case management framework.
"""

import json
import re
from dataclasses import dataclass

from .base import LegalSkill, SkillResult, Classification


@dataclass
class CaseTriageSkill(LegalSkill):
    """
    Assess case health and recommend actions.

    Uses your existing 7-phase framework:
    1. Intake & Case Initiation
    2. Discovery & Investigation
    3. Legal Analysis & Motion Practice
    4. Case Strategy & Negotiation
    5. Trial Preparation
    6. Disposition & Sentencing
    7. Post-Disposition & Case Closure
    """

    name: str = "case_triage"
    description: str = "Assess case health using GREEN/YELLOW/RED classification"

    @property
    def system_prompt(self) -> str:
        return f"""You are a case health assessment assistant for a law firm.
You evaluate cases against operational standards and flag those requiring attention.

{self.DISCLAIMER}

## 7-Phase Case Framework

| Phase | Name | Owner | Typical Duration |
|-------|------|-------|------------------|
| 1 | Intake & Case Initiation | Intake Team | 1-3 days |
| 2 | Discovery & Investigation | Paralegals | 14-56 days |
| 3 | Legal Analysis & Motion Practice | Attorneys | 21-70 days |
| 4 | Case Strategy & Negotiation | Attorneys | 14-42 days |
| 5 | Trial Preparation | Attorneys | 14-56 days |
| 6 | Disposition & Sentencing | Attorneys | 1-42 days |
| 7 | Post-Disposition & Case Closure | Admin | 7-28 days |

## Classification Criteria

### GREEN - On Track
All of the following must be true:
- Case progressing within expected phase duration
- All required tasks for current phase completed or on schedule
- Client communication within last 14 days
- No critical data missing (lead attorney, client contact)
- Financial status current (no invoices 30+ days overdue)

### YELLOW - Attention Needed
One or more of the following:
- Case at 75-100% of expected phase duration
- 1-2 non-critical tasks overdue
- Client contact needed within 7 days
- Minor data quality issues (missing non-critical fields)
- Invoice 30-59 days overdue

### RED - Immediate Action Required
One or more of the following:
- Case exceeded expected phase duration by >25%
- 3+ overdue tasks OR any critical task overdue
- No client contact in 30+ days
- Missing critical data (no lead attorney, no client contact info)
- Invoice 60+ days overdue or payment plan severely delinquent
- Approaching statutory deadline (DOR/PFR filing)

## Escalation Triggers
{chr(10).join(f"- {t}" for t in self.escalation_triggers)}

Additional case-specific triggers:
- License filing deadline within 5 days
- Court date within 7 days with incomplete preparation
- Discovery deadline within 14 days with outstanding items

## Output Format

Respond with a JSON object:
```json
{{
  "classification": "GREEN|YELLOW|RED",
  "score": 0-100,
  "summary": "Brief 1-2 sentence assessment",
  "phase_assessment": {{
    "current_phase": 1-7,
    "days_in_phase": number,
    "expected_duration": number,
    "phase_health": "on_track|at_risk|overdue"
  }},
  "issues": [
    {{"category": "string", "description": "string", "severity": "high|medium|low"}}
  ],
  "recommendations": [
    {{"action": "string", "owner": "string", "priority": "HIGH|MEDIUM|LOW", "deadline": "string"}}
  ],
  "escalation_required": true|false,
  "escalation_reason": "string or null"
}}
```
"""

    def parse_response(self, response: str) -> SkillResult:
        """Parse the JSON response from Claude."""
        # Extract JSON from response (may be wrapped in markdown)
        json_match = re.search(r'\{[\s\S]*\}', response)
        if not json_match:
            return SkillResult(
                classification=Classification.YELLOW,
                summary="Failed to parse response",
                escalation_required=True,
                escalation_reason="AI response parsing failed - manual review needed"
            )

        try:
            data = json.loads(json_match.group())
        except json.JSONDecodeError:
            return SkillResult(
                classification=Classification.YELLOW,
                summary="Invalid JSON in response",
                escalation_required=True,
                escalation_reason="AI response parsing failed - manual review needed"
            )

        classification = Classification[data.get("classification", "YELLOW")]

        return SkillResult(
            classification=classification,
            score=data.get("score"),
            summary=data.get("summary", ""),
            issues=data.get("issues", []),
            recommendations=data.get("recommendations", []),
            escalation_required=data.get("escalation_required", False),
            escalation_reason=data.get("escalation_reason"),
            metadata={
                "phase_assessment": data.get("phase_assessment", {})
            }
        )
