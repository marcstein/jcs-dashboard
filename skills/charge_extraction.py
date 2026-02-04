"""
Charge Extraction Skill

AI-powered extraction of criminal charges from case descriptions,
police reports, or charging documents.

Outputs structured charge data suitable for pleading generation.
"""

import json
import re
from dataclasses import dataclass

from .base import LegalSkill, SkillResult, Classification


@dataclass
class ChargeExtractionSkill(LegalSkill):
    """
    Extract structured charge information from text.

    Identifies:
    - Charge descriptions
    - Statutory references
    - Classification levels (Felony A-E, Misdemeanor A-D, Infraction)
    """

    name: str = "charge_extraction"
    description: str = "Extract criminal charges from case text"
    max_tokens: int = 2048

    @property
    def system_prompt(self) -> str:
        return f"""You are a legal document analyst specializing in Missouri criminal law.
You extract structured charge information from case descriptions, police reports,
and other legal documents.

{self.DISCLAIMER}

## Missouri Charge Classification Reference

**Felonies (most to least serious):**
- Class A Felony: Murder, severe violent crimes
- Class B Felony: Serious violent crimes, major drug distribution
- Class C Felony: Significant crimes (assault, drug delivery)
- Class D Felony: Mid-level crimes (theft over threshold, some drug offenses)
- Class E Felony: Lower-level felonies (some property crimes)

**Misdemeanors:**
- Class A Misdemeanor: Most serious (DWI, assault 4th degree)
- Class B Misdemeanor: Mid-level (minor theft, trespass)
- Class C Misdemeanor: Minor offenses
- Class D Misdemeanor: Least serious

**Infractions:** Traffic violations, minor ordinance violations

## Common Missouri Charges

| Charge | Classification | Statute |
|--------|---------------|---------|
| DWI (1st offense) | Class B Misdemeanor | RSMo 577.010 |
| DWI (2nd offense) | Class A Misdemeanor | RSMo 577.010 |
| DWI (Chronic offender) | Class E Felony | RSMo 577.010 |
| Driving While Revoked | Class D Felony | RSMo 302.321 |
| Possession of Controlled Substance | Class D Felony | RSMo 579.015 |
| Delivery of Controlled Substance | Class C Felony | RSMo 579.020 |
| Unlawful Possession of Firearm | Class D Felony | RSMo 571.070 |
| Tampering with Physical Evidence | Class A Misdemeanor | RSMo 575.100 |
| Assault 4th Degree | Class A Misdemeanor | RSMo 565.056 |
| Stealing | Class A/B/C/D (by value) | RSMo 570.030 |

## Extraction Process

1. **Identify all charges** mentioned in the text
2. **Determine classification** based on statute reference or charge description
3. **Extract statutory reference** if provided (RSMo section)
4. **Number the counts** in order of appearance or severity
5. **Flag uncertainties** when classification is unclear

## Output Format

Respond with a JSON object:
```json
{{
  "charges": [
    {{
      "count_number": 1,
      "description": "Full charge description as it should appear in pleading",
      "short_description": "Brief name for the charge",
      "classification": "Class X Felony|Class X Misdemeanor|Infraction",
      "statute": "RSMo XXX.XXX or null if unknown",
      "confidence": "high|medium|low",
      "notes": "Any special notes about this charge"
    }}
  ],
  "extraction_notes": "Any overall notes about the extraction",
  "uncertainties": ["List of anything that needs human verification"],
  "classification": "GREEN|YELLOW|RED"
}}
```

## Classification Rules

**GREEN**: All charges clearly identified with high confidence
**YELLOW**: Some charges have medium confidence or missing statute references
**RED**: Unable to determine charges or significant uncertainty
"""

    def parse_response(self, response: str) -> SkillResult:
        """Parse the JSON response from Claude."""
        json_match = re.search(r'\{[\s\S]*\}', response)
        if not json_match:
            return SkillResult(
                classification=Classification.RED,
                summary="Failed to parse charge extraction response",
                escalation_required=True,
                escalation_reason="AI response parsing failed"
            )

        try:
            data = json.loads(json_match.group())
        except json.JSONDecodeError:
            return SkillResult(
                classification=Classification.RED,
                summary="Invalid JSON in response",
                escalation_required=True,
                escalation_reason="AI response parsing failed"
            )

        classification = Classification[data.get("classification", "YELLOW")]

        return SkillResult(
            classification=classification,
            summary=data.get("extraction_notes", ""),
            issues=[{"uncertainty": u} for u in data.get("uncertainties", [])],
            recommendations=[],
            escalation_required=classification == Classification.RED,
            escalation_reason="Charge extraction uncertain" if classification == Classification.RED else None,
            metadata={
                "charges": data.get("charges", []),
            }
        )


def charges_from_skill_result(result: SkillResult) -> list:
    """
    Convert skill result to Charge objects for pleading generation.

    Usage:
        result = skill_manager.execute("charge_extraction", case_text)
        charges = charges_from_skill_result(result)
        ctx.charges = charges
    """
    from pleadings import Charge, ChargeClass

    charges = []
    for c in result.metadata.get("charges", []):
        # Map classification string to enum
        class_str = c.get("classification", "").lower()
        if "felony" in class_str:
            if "class a" in class_str:
                charge_class = ChargeClass.FELONY_A
            elif "class b" in class_str:
                charge_class = ChargeClass.FELONY_B
            elif "class c" in class_str:
                charge_class = ChargeClass.FELONY_C
            elif "class d" in class_str:
                charge_class = ChargeClass.FELONY_D
            else:
                charge_class = ChargeClass.FELONY_E
        elif "misdemeanor" in class_str:
            if "class a" in class_str:
                charge_class = ChargeClass.MISDEMEANOR_A
            elif "class b" in class_str:
                charge_class = ChargeClass.MISDEMEANOR_B
            elif "class c" in class_str:
                charge_class = ChargeClass.MISDEMEANOR_C
            else:
                charge_class = ChargeClass.MISDEMEANOR_D
        else:
            charge_class = ChargeClass.INFRACTION

        charges.append(Charge(
            count_number=c.get("count_number", len(charges) + 1),
            description=c.get("description", "Unknown charge"),
            classification=charge_class,
            statute=c.get("statute"),
        ))

    return charges
