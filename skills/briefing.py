"""
Briefing Generation Skill

AI-enhanced daily briefing generation following the legal plugin's
meeting-briefing pattern.

Integrates with LawMetrics.ai's SOP reports and staff huddles.
"""

import json
import re
from dataclasses import dataclass

from .base import LegalSkill, SkillResult, Classification


@dataclass
class BriefingSkill(LegalSkill):
    """
    Generate structured daily briefings for staff.

    Follows the meeting-briefing pattern from the legal plugin:
    - Prioritized alerts (RED items)
    - Focus areas (YELLOW items)
    - Metrics snapshot
    - Action items with owners
    """

    name: str = "briefing"
    description: str = "Generate daily ops briefings for staff members"
    max_tokens: int = 4096  # Briefings need more tokens

    @property
    def system_prompt(self) -> str:
        return f"""You are an operations briefing assistant for a law firm.
You synthesize case management and collections data into actionable daily briefings.

{self.DISCLAIMER}

## Staff Roles and Briefing Focus

| Role | Focus Areas | Key Metrics |
|------|-------------|-------------|
| AR Specialist | Collections, payment plans, aging, NOIW | AR total, 60+ day %, compliance rate |
| Intake Lead | New cases, leads, case setup | Cases/week, conversion, assignment rate |
| Senior Paralegal | Tasks, team ops, daily huddle | Open tasks, done this week, overdue |
| Legal Assistant | Case tasks, discovery, filings | Assigned tasks, deadlines, completions |

## Briefing Structure

### 1. Priority Alerts (RED)
Critical items requiring immediate attention:
- Overdue statutory deadlines (DOR/PFR filings)
- Severely delinquent accounts (60+ days)
- Cases stalled >50% over expected duration
- Critical tasks overdue
- NOIW cases requiring action

### 2. Today's Focus (YELLOW)
Items needing attention today:
- Cases approaching phase limits
- Follow-up calls scheduled/needed
- Documents awaiting review
- Deadlines within 7 days
- Payment promises due today

### 3. Metrics Snapshot
Key numbers for the day:
- Open cases by phase
- AR aging summary
- Task completion rate
- Collection activity

### 4. Wins & Progress (GREEN)
Brief acknowledgment of positive items:
- Cases closed this week
- Payments received
- Tasks completed
- Payment plans established

### 5. Action Items
Specific, assignable tasks:
- Clear description of what needs to be done
- Owner (specific person)
- Priority (HIGH/MEDIUM/LOW)
- Deadline (specific date)

## Briefing Tone Guidelines

- **Concise**: Scannable, no fluff
- **Actionable**: Every item has a next step
- **Prioritized**: Most important first
- **Specific**: Names, numbers, dates
- **Balanced**: Acknowledge wins briefly

## Output Format

Respond with a JSON object:
```json
{{
  "briefing_date": "YYYY-MM-DD",
  "staff_role": "string",
  "staff_name": "string",
  "priority_alerts": [
    {{
      "type": "deadline|collections|case_stalled|task_overdue|noiw",
      "description": "string",
      "case_id": "string or null",
      "action_required": "string",
      "deadline": "string"
    }}
  ],
  "todays_focus": [
    {{
      "category": "string",
      "description": "string",
      "related_items": ["string"]
    }}
  ],
  "metrics_snapshot": {{
    "primary_metrics": [
      {{"name": "string", "value": "string", "trend": "up|down|stable", "status": "good|warning|critical"}}
    ]
  }},
  "wins": [
    {{"description": "string"}}
  ],
  "action_items": [
    {{
      "action": "string",
      "owner": "string",
      "priority": "HIGH|MEDIUM|LOW",
      "deadline": "string",
      "context": "string"
    }}
  ],
  "summary": "1-2 sentence overall assessment",
  "overall_status": "GREEN|YELLOW|RED"
}}
```
"""

    def parse_response(self, response: str) -> SkillResult:
        """Parse the JSON response from Claude."""
        json_match = re.search(r'\{[\s\S]*\}', response)
        if not json_match:
            return SkillResult(
                classification=Classification.YELLOW,
                summary="Failed to parse briefing response",
                escalation_required=True,
                escalation_reason="AI response parsing failed - manual review needed"
            )

        try:
            data = json.loads(json_match.group())
        except json.JSONDecodeError:
            return SkillResult(
                classification=Classification.YELLOW,
                summary="Invalid JSON in briefing response",
                escalation_required=True,
                escalation_reason="AI response parsing failed - manual review needed"
            )

        # Determine classification from overall status
        overall_status = data.get("overall_status", "YELLOW")
        classification = Classification[overall_status]

        # Count priority alerts for scoring
        alert_count = len(data.get("priority_alerts", []))
        score = max(0, 100 - (alert_count * 10))

        return SkillResult(
            classification=classification,
            score=score,
            summary=data.get("summary", ""),
            issues=data.get("priority_alerts", []),
            recommendations=data.get("action_items", []),
            escalation_required=alert_count >= 5,
            escalation_reason="High number of priority alerts" if alert_count >= 5 else None,
            metadata={
                "briefing_date": data.get("briefing_date"),
                "staff_role": data.get("staff_role"),
                "staff_name": data.get("staff_name"),
                "todays_focus": data.get("todays_focus", []),
                "metrics_snapshot": data.get("metrics_snapshot", {}),
                "wins": data.get("wins", [])
            }
        )


def format_briefing_markdown(result: SkillResult) -> str:
    """Format a briefing result as readable markdown."""
    meta = result.metadata
    lines = [
        f"# Daily Briefing - {meta.get('staff_name', 'Staff')}",
        f"**Date**: {meta.get('briefing_date', 'Today')}",
        f"**Role**: {meta.get('staff_role', 'Unknown')}",
        f"**Status**: {result.classification.value}",
        "",
        f"## Summary",
        result.summary,
        "",
    ]

    # Priority Alerts
    if result.issues:
        lines.append("## 🔴 Priority Alerts")
        for alert in result.issues:
            lines.append(f"- **{alert.get('type', 'Alert')}**: {alert.get('description')}")
            if alert.get('action_required'):
                lines.append(f"  - Action: {alert.get('action_required')}")
        lines.append("")

    # Today's Focus
    if meta.get('todays_focus'):
        lines.append("## 🟡 Today's Focus")
        for item in meta['todays_focus']:
            lines.append(f"- **{item.get('category')}**: {item.get('description')}")
        lines.append("")

    # Metrics
    if meta.get('metrics_snapshot', {}).get('primary_metrics'):
        lines.append("## 📊 Metrics Snapshot")
        for metric in meta['metrics_snapshot']['primary_metrics']:
            status_emoji = {"good": "✅", "warning": "⚠️", "critical": "🔴"}.get(
                metric.get('status', 'good'), "📊"
            )
            lines.append(f"- {status_emoji} **{metric.get('name')}**: {metric.get('value')}")
        lines.append("")

    # Wins
    if meta.get('wins'):
        lines.append("## 🟢 Wins & Progress")
        for win in meta['wins']:
            lines.append(f"- {win.get('description')}")
        lines.append("")

    # Action Items
    if result.recommendations:
        lines.append("## ✅ Action Items")
        for item in result.recommendations:
            priority_emoji = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🟢"}.get(
                item.get('priority', 'MEDIUM'), "⬜"
            )
            lines.append(f"- {priority_emoji} **{item.get('action')}**")
            lines.append(f"  - Owner: {item.get('owner')} | Due: {item.get('deadline')}")
        lines.append("")

    return "\n".join(lines)
