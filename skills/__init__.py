"""
LawMetrics.ai Skills Module

Implements legal plugin patterns for Claude API integration.
Provides AI-enhanced triage, risk assessment, briefing generation,
and document generation from templates.
"""

from .base import LegalSkill, SkillManager, SkillResult, Classification
from .case_triage import CaseTriageSkill
from .collections_risk import CollectionsRiskSkill
from .briefing import BriefingSkill
from .document_generation import DocumentGenerationSkill, DocumentGenerator
from .charge_extraction import ChargeExtractionSkill, charges_from_skill_result

__all__ = [
    'LegalSkill',
    'SkillManager',
    'SkillResult',
    'Classification',
    'CaseTriageSkill',
    'CollectionsRiskSkill',
    'BriefingSkill',
    'DocumentGenerationSkill',
    'DocumentGenerator',
    'ChargeExtractionSkill',
    'charges_from_skill_result',
]
