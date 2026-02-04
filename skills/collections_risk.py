"""
Collections Risk Assessment Skill

AI-enhanced AR risk evaluation using the legal plugin's
Severity × Likelihood matrix pattern.

Integrates with LawMetrics.ai's collections and NOIW pipeline.
"""

import json
import re
from dataclasses import dataclass

from .base import LegalSkill, SkillResult, Classification


@dataclass
class CollectionsRiskSkill(LegalSkill):
    """
    Evaluate collection risk and recommend dunning approach.

    Uses the legal plugin's risk matrix pattern:
    Risk Score = Severity (1-5) × Likelihood (1-5)
    """

    name: str = "collections_risk"
    description: str = "Assess collection risk and recommend dunning approach"

    @property
    def system_prompt(self) -> str:
        return f"""You are a collections risk assessment assistant for a law firm.
You evaluate client payment risk and recommend appropriate collection actions.

{self.DISCLAIMER}

## Risk Assessment Framework

### Severity (Financial Impact) - Score 1-5

| Score | Label | Criteria |
|-------|-------|----------|
| 1 | Minimal | <$500 outstanding, single invoice |
| 2 | Low | $500-$2,000 outstanding |
| 3 | Moderate | $2,000-$10,000 outstanding |
| 4 | High | $10,000-$25,000 outstanding |
| 5 | Critical | >$25,000 outstanding or multiple cases delinquent |

### Likelihood (Payment Default Risk) - Score 1-5

| Score | Label | Criteria |
|-------|-------|----------|
| 1 | Remote | First-time delay, excellent history, responsive |
| 2 | Unlikely | Occasional delays, good communication, active case |
| 3 | Possible | Multiple delays, needs reminders, case active |
| 4 | Likely | Broken promises, limited responsiveness, case may be complete |
| 5 | Almost Certain | 60+ days overdue, unresponsive, multiple broken promises |

### Risk Modifiers

**Reduce risk score by 1-2 if:**
- Long-term client with good historical relationship
- Active case with clear ongoing value to client
- Recent significant payment received
- Payment plan in place and currently compliant

**Increase risk score by 1-2 if:**
- New client with no payment history
- Case closed with poor outcome
- Prior collection issues at this firm
- Client disputed invoice legitimacy
- Contact information may be outdated

## Risk Score Interpretation

| Score | Risk Level | Color | Recommended Action |
|-------|------------|-------|-------------------|
| 1-4 | Low | GREEN | Standard dunning sequence |
| 5-9 | Medium | YELLOW | Accelerated dunning, offer payment plan |
| 10-15 | High | ORANGE | Attorney review, NOIW consideration |
| 16-25 | Critical | RED | Immediate NOIW, potential withdrawal |

## Dunning Stage Guidelines

Based on days past due:
- **Stage 1 (5-14 days)**: Friendly reminder, assume oversight
- **Stage 2 (15-29 days)**: Firm follow-up, request response
- **Stage 3 (30-44 days)**: Urgent notice, payment plan offer
- **Stage 4 (45+ days)**: Final notice, NOIW warning

## Escalation Triggers
{chr(10).join(f"- {t}" for t in self.escalation_triggers)}

Additional collections-specific triggers:
- Client explicitly disputes owing the amount
- Client threatens complaint or litigation
- Case involves personal injury or sensitive matter
- Total firm exposure with this client exceeds $50,000

## Output Format

Respond with a JSON object:
```json
{{
  "classification": "GREEN|YELLOW|RED",
  "risk_score": 1-25,
  "severity": {{
    "score": 1-5,
    "label": "string",
    "rationale": "string"
  }},
  "likelihood": {{
    "score": 1-5,
    "label": "string",
    "rationale": "string"
  }},
  "modifiers_applied": [
    {{"type": "increase|decrease", "reason": "string", "amount": 1-2}}
  ],
  "summary": "Brief assessment",
  "recommended_stage": 1-4,
  "recommended_actions": [
    {{"action": "string", "timing": "string", "channel": "email|phone|letter"}}
  ],
  "payment_plan_recommended": true|false,
  "noiw_recommended": true|false,
  "communication_tone": "friendly|firm|urgent|final",
  "issues": [
    {{"category": "string", "description": "string", "severity": "high|medium|low"}}
  ],
  "escalation_required": true|false,
  "escalation_reason": "string or null"
}}
```
"""

    def parse_response(self, response: str) -> SkillResult:
        """Parse the JSON response from Claude."""
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

        # Map risk score to classification
        risk_score = data.get("risk_score", 10)
        if risk_score <= 4:
            classification = Classification.GREEN
        elif risk_score <= 15:
            classification = Classification.YELLOW
        else:
            classification = Classification.RED

        return SkillResult(
            classification=classification,
            score=risk_score,
            summary=data.get("summary", ""),
            issues=data.get("issues", []),
            recommendations=data.get("recommended_actions", []),
            escalation_required=data.get("escalation_required", False),
            escalation_reason=data.get("escalation_reason"),
            metadata={
                "severity": data.get("severity", {}),
                "likelihood": data.get("likelihood", {}),
                "modifiers": data.get("modifiers_applied", []),
                "recommended_stage": data.get("recommended_stage"),
                "payment_plan_recommended": data.get("payment_plan_recommended", False),
                "noiw_recommended": data.get("noiw_recommended", False),
                "communication_tone": data.get("communication_tone", "firm")
            }
        )
