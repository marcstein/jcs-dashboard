"""
Base skill infrastructure for LawMetrics.ai

Implements the skill pattern from Cowork's legal plugin:
- Structured system prompts with domain expertise
- GREEN/YELLOW/RED classification system
- Escalation triggers and human review flags

LLM transport: Anthropic SDK against AWS Bedrock (Opus 4.7 by default).
Shares the AWS billing account with ClientShield. Requires AWS_ACCESS_KEY_ID,
AWS_SECRET_ACCESS_KEY, and AWS_DEFAULT_REGION (us-east-1) in the environment.
The legacy ANTHROPIC_API_KEY direct path is gated by LLM_PROVIDER=claude.
"""

import json
import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

import anthropic

logger = logging.getLogger(__name__)


# ============================================================================
# Bedrock Model ID Mapping
# ============================================================================
# Mirrors ClientShield/core/llm_gateway.py BEDROCK_MODEL_MAP. Keep in sync.
# 4.7 inference profiles dropped the version suffix; 4.6 still uses -v1.

BEDROCK_MODEL_MAP = {
    "claude-opus-4-7": "us.anthropic.claude-opus-4-7",
    "claude-opus-4-6": "us.anthropic.claude-opus-4-6-v1",
    "claude-sonnet-4-5": "us.anthropic.claude-sonnet-4-5-v2-20250929",
    "claude-3-5-haiku": "us.anthropic.claude-3-5-haiku-20241022-v1:0",
}


def resolve_bedrock_model(model: str) -> str:
    """Map a short Anthropic model name to its Bedrock cross-region inference ID.

    Pass-through if the input already looks like a Bedrock ID."""
    if "us." in model or "global." in model or "anthropic." in model:
        return model
    return BEDROCK_MODEL_MAP.get(model, model)


def get_claude_client() -> anthropic.AnthropicBedrock | anthropic.Anthropic:
    """Return a Claude client for the configured provider.

    Default: AnthropicBedrock against us-east-1 using the AWS default credential
    chain (env vars, IAM role, or AWS profile). Set LLM_PROVIDER=claude to fall
    back to the direct Anthropic API (requires ANTHROPIC_API_KEY)."""
    provider = os.environ.get("LLM_PROVIDER", "bedrock").lower()
    if provider == "bedrock":
        region = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
        access_key = os.environ.get("AWS_ACCESS_KEY_ID", "")
        secret_key = os.environ.get("AWS_SECRET_ACCESS_KEY", "")
        kwargs = {"aws_region": region}
        if access_key and secret_key:
            kwargs["aws_access_key"] = access_key
            kwargs["aws_secret_key"] = secret_key
        logger.info(f"Initialized AnthropicBedrock client (region={region})")
        return anthropic.AnthropicBedrock(**kwargs)
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "LLM_PROVIDER=claude but ANTHROPIC_API_KEY is not set. "
            "Either set the API key or unset LLM_PROVIDER to use Bedrock."
        )
    return anthropic.Anthropic(api_key=api_key)


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
    # Bedrock by default — matches ClientShield. Override per-skill if needed.
    model: str = "claude-opus-4-7"
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
        # api_key kept for backwards compatibility but ignored when LLM_PROVIDER=bedrock
        # (the default). To force the direct Anthropic API, set LLM_PROVIDER=claude
        # and pass api_key here or set ANTHROPIC_API_KEY in the environment.
        if api_key and os.environ.get("LLM_PROVIDER", "bedrock").lower() != "bedrock":
            self.client = anthropic.Anthropic(api_key=api_key)
        else:
            self.client = get_claude_client()
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

        # Execute — resolve to Bedrock inference profile ID when applicable
        model_id = (
            resolve_bedrock_model(skill.model)
            if isinstance(self.client, anthropic.AnthropicBedrock)
            else skill.model
        )
        message = self.client.messages.create(
            model=model_id,
            max_tokens=skill.max_tokens,
            system=skill.build_system_prompt(context),
            messages=[{"role": "user", "content": user_content}]
        )

        response_text = message.content[0].text

        # Parse and return
        result = skill.parse_response(response_text)
        result.raw_response = response_text
        result.metadata["model"] = skill.model
        result.metadata["model_id_invoked"] = model_id
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
