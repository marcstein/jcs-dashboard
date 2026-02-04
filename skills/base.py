"""
Base skill infrastructure for LawMetrics.ai

Implements the skill pattern from Cowork's legal plugin:
- Structured system prompts with domain expertise
- GREEN/YELLOW/RED classification system
- Escalation triggers and human review flags
"""

import json
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

import anthropic


class Classification(Enum):
    """Standard tri-level classification system from legal plugin."""
    GREEN = "GREEN"      # Acceptable / Standard - proceed without escalation
    YELLOW = "YELLOW"    # Needs Review - flag issues, suggest modifications
    RED = "RED"          # Significant Issues - full review required, escalate


@dataclass
class SkillResult:
    """Structured output from skill execution."""
    classification: Classification
    score: Optional[float] = None
    summary: str = ""
    issues: list[dict] = field(default_factory=list)
    recommendations: list[dict] = field(default_factory=list)
    escalation_required: bool = False
    escalation_reason: Optional[str] = None
    raw_response: str = ""
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "classification": self.classification.value,
            "score": self.score,
            "summary": self.summary,
            "issues": self.issues,
            "recommendations": self.recommendations,
            "escalation_required": self.escalation_required,
            "escalation_reason": self.escalation_reason,
            "metadata": self.metadata
        }


@dataclass
class LegalSkill(ABC):
    """
    Base class for legal skills.

    Following the legal plugin pattern:
    1. Role definition with disclaimer
    2. Classification criteria (GREEN/YELLOW/RED)
    3. Evaluation methodology
    4. Escalation triggers
    5. Output format specification
    """
    name: str
    description: str
    model: str = "claude-sonnet-4-20250514"
    max_tokens: int = 2048

    # Standard disclaimer - should appear in all legal-adjacent skills
    DISCLAIMER = """
**Important**: You assist with law firm operational workflows but do not provide
legal advice. All assessments should be reviewed by qualified professionals
before being relied upon for legal decisions.
"""

    @property
    @abstractmethod
    def system_prompt(self) -> str:
        """Return the full system prompt for this skill."""
        pass

    @property
    def escalation_triggers(self) -> list[str]:
        """Universal escalation triggers that apply to all skills."""
        return [
            "Matter involves potential litigation or malpractice claim",
            "Client threatens bar complaint or lawsuit",
            "Regulatory or ethics inquiry involved",
            "Media attention is involved or likely",
            "Situation is unprecedented (no prior handling by the firm)",
            "Matter involves firm leadership or partners",
            "Client is unresponsive for 60+ days with significant balance",
        ]

    def build_system_prompt(self, additional_context: Optional[str] = None) -> str:
        """Construct the full system prompt with optional context."""
        prompt = self.system_prompt

        if additional_context:
            prompt += f"\n\n## Additional Context\n{additional_context}"

        return prompt

    @abstractmethod
    def parse_response(self, response: str) -> SkillResult:
        """Parse Claude's response into a structured SkillResult."""
        pass


class SkillManager:
    """
    Manages skill registration and execution.

    Usage:
        manager = SkillManager()
        manager.register(CaseTriageSkill())
        result = manager.execute("case_triage", case_data)
    """

    def __init__(self, api_key: Optional[str] = None):
        self.client = anthropic.Anthropic(
            api_key=api_key or os.getenv("ANTHROPIC_API_KEY")
        )
        self.skills: dict[str, LegalSkill] = {}

    def register(self, skill: LegalSkill) -> None:
        """Register a skill for use."""
        self.skills[skill.name] = skill

    def list_skills(self) -> list[dict]:
        """List all registered skills."""
        return [
            {"name": s.name, "description": s.description}
            for s in self.skills.values()
        ]

    def execute(
        self,
        skill_name: str,
        input_data: Any,
        context: Optional[str] = None
    ) -> SkillResult:
        """
        Execute a skill with the given input data.

        Args:
            skill_name: Name of the registered skill
            input_data: Data to process (will be JSON-serialized if dict)
            context: Optional additional context for the system prompt

        Returns:
            SkillResult with classification, issues, and recommendations
        """
        if skill_name not in self.skills:
            raise ValueError(f"Unknown skill: {skill_name}")

        skill = self.skills[skill_name]

        # Prepare input
        if isinstance(input_data, dict):
            user_content = json.dumps(input_data, indent=2, default=str)
        else:
            user_content = str(input_data)

        # Execute
        message = self.client.messages.create(
            model=skill.model,
            max_tokens=skill.max_tokens,
            system=skill.build_system_prompt(context),
            messages=[{"role": "user", "content": user_content}]
        )

        response_text = message.content[0].text

        # Parse and return
        result = skill.parse_response(response_text)
        result.raw_response = response_text
        result.metadata["model"] = skill.model
        result.metadata["skill"] = skill_name

        return result

    def batch_execute(
        self,
        skill_name: str,
        items: list[Any],
        context: Optional[str] = None
    ) -> list[SkillResult]:
        """Execute a skill on multiple items."""
        return [
            self.execute(skill_name, item, context)
            for item in items
        ]
