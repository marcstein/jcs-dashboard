"""
Legal Pleading Generation System

Handles generation of Missouri criminal court pleadings with:
- Reusable caption/signature components
- Smart charge list formatting
- Court-specific formatting
- MyCase data integration

Supported Pleadings:
- Request for Jury Trial
- Waiver of Arraignment
- Entry of Appearance
- Motion to Continue
- Motion to Suppress
- Plea Agreement
"""

import re
from dataclasses import dataclass, field
from datetime import datetime, date
from enum import Enum
from pathlib import Path
from typing import List, Dict, Optional, Any

from config import DATA_DIR


# ============================================================================
# Data Models
# ============================================================================

class ChargeClass(Enum):
    """Missouri charge classifications."""
    FELONY_A = "Class A Felony"
    FELONY_B = "Class B Felony"
    FELONY_C = "Class C Felony"
    FELONY_D = "Class D Felony"
    FELONY_E = "Class E Felony"
    MISDEMEANOR_A = "Class A Misdemeanor"
    MISDEMEANOR_B = "Class B Misdemeanor"
    MISDEMEANOR_C = "Class C Misdemeanor"
    MISDEMEANOR_D = "Class D Misdemeanor"
    INFRACTION = "Infraction"


@dataclass
class Charge:
    """Represents a criminal charge/count."""
    count_number: int
    description: str
    classification: ChargeClass
    statute: Optional[str] = None  # e.g., "RSMo 195.211"

    def format_roman(self) -> str:
        """Convert count number to Roman numeral."""
        roman_map = [
            (1000, 'M'), (900, 'CM'), (500, 'D'), (400, 'CD'),
            (100, 'C'), (90, 'XC'), (50, 'L'), (40, 'XL'),
            (10, 'X'), (9, 'IX'), (5, 'V'), (4, 'IV'), (1, 'I')
        ]
        result = ''
        num = self.count_number
        for value, numeral in roman_map:
            while num >= value:
                result += numeral
                num -= value
        return result

    def to_text(self) -> str:
        """Format charge as text for pleading."""
        statute_ref = f" ({self.statute})" if self.statute else ""
        return f"Count {self.format_roman()}: {self.description}{statute_ref}, a {self.classification.value}"


@dataclass
class Attorney:
    """Attorney information."""
    name: str
    bar_number: str
    email: str
    is_lead: bool = False


@dataclass
class CaseContext:
    """All context needed for pleading generation."""
    # Required fields (no defaults) - must come first
    case_number: str
    county: str
    defendant_name: str

    # Optional fields with defaults
    court_type: str = "Circuit"  # Circuit, Municipal, Federal
    defendant_name_formal: Optional[str] = None  # For "I, John Smith, ..."

    # Charges
    charges: List[Charge] = field(default_factory=list)

    # Attorneys
    attorneys: List[Attorney] = field(default_factory=list)
    lead_attorney: Optional[Attorney] = None

    # Dates
    filing_date: Optional[date] = None
    service_date: Optional[date] = None

    # Staff
    service_signer: str = "Tiffany Willis"

    # Additional
    mycase_case_id: Optional[int] = None
    custom_fields: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.defendant_name_formal:
            self.defendant_name_formal = self.defendant_name.title()
        if not self.filing_date:
            self.filing_date = date.today()
        if not self.service_date:
            self.service_date = date.today()
        if self.attorneys and not self.lead_attorney:
            self.lead_attorney = next((a for a in self.attorneys if a.is_lead), self.attorneys[0])


# ============================================================================
# Firm Constants
# ============================================================================

FIRM_INFO = {
    "name": "John C. Schleiffarth, P.C.",
    "address_line1": "75 West Lockwood Avenue, Suite 250",
    "address_line2": "Webster Groves, Missouri 63119",
    "phone": "314-561-9690",
    "fax": "314-596-0658",
    "default_attorneys": [
        Attorney("John C. Schleiffarth", "63222", "john@jcsattorney.com", is_lead=True),
        Attorney("Andrew Morris", "67504", "andy@jcsattorney.com"),
    ]
}


# ============================================================================
# Pleading Components
# ============================================================================

def format_case_caption(ctx: CaseContext) -> str:
    """Generate the standard case caption header."""
    # Determine court line
    court_line = f"IN THE {ctx.court_type.upper()} COURT OF {ctx.county.upper()} COUNTY"

    # Format defendant name in caps for caption
    defendant_caps = ctx.defendant_name.upper()

    caption = f"""{court_line}
STATE OF MISSOURI

STATE OF MISSOURI,                )
                                  )
         Plaintiff,               )    Case No.: {ctx.case_number}
                                  )
vs.                               )
                                  )
{defendant_caps},                 )
                                  )
         Defendant.               )
"""
    return caption


def format_attorney_signature_block(ctx: CaseContext, include_all: bool = True) -> str:
    """Generate the attorney signature block."""
    lead = ctx.lead_attorney or (ctx.attorneys[0] if ctx.attorneys else FIRM_INFO["default_attorneys"][0])

    lines = [
        "",
        "                                        Respectfully Submitted,",
        "",
        f"                                        {FIRM_INFO['name']}",
        "",
        f"                                        /s/{lead.name}_________________",
        f"                                        {lead.name} #{lead.bar_number}",
    ]

    # Add additional attorneys
    if include_all:
        for atty in ctx.attorneys:
            if atty.name != lead.name:
                lines.append(f"                                        {atty.name} #{atty.bar_number}")

    # Add firm info
    lines.extend([
        f"                                        {FIRM_INFO['address_line1']}",
        f"                                        {FIRM_INFO['address_line2']}",
        f"                                        Telephone: {FIRM_INFO['phone']}",
        f"                                        Facsimile: {FIRM_INFO['fax']}",
        f"                                        Email: {lead.email}",
        "                                        Attorney for Defendant",
    ])

    return "\n".join(lines)


def format_certificate_of_service(ctx: CaseContext) -> str:
    """Generate the certificate of service."""
    # Format date as "January 15, 2026"
    date_formatted = ctx.service_date.strftime("%B %d, %Y") if ctx.service_date else date.today().strftime("%B %d, %Y")

    return f"""
                    CERTIFICATE OF SERVICE

The below signature certifies a true and accurate copy of the foregoing
was filed via the Court's electronic filing system, this {date_formatted},
to all counsel of record.

                                        /s/{ctx.service_signer}_________________
"""


def format_defendant_signature_block() -> str:
    """Generate defendant signature lines."""
    return """
__________________________________    ________________________
Defendant's Signature                 Date

__________________________________    ________________________
Attorney for Defendant                Date
"""


def format_charges_list(charges: List[Charge]) -> str:
    """Format a list of charges for pleadings."""
    if not charges:
        return "[CHARGES TO BE LISTED]"

    lines = []
    for charge in sorted(charges, key=lambda c: c.count_number):
        lines.append(charge.to_text())
        lines.append("")  # Blank line between charges

    return "\n".join(lines).strip()


# ============================================================================
# Pleading Generators
# ============================================================================

def generate_request_for_jury_trial(ctx: CaseContext) -> str:
    """Generate a Request for Jury Trial pleading."""
    parts = [
        format_case_caption(ctx),
        "",
        "                    REQUEST FOR JURY TRIAL",
        "",
        "Comes now Defendant, by and through counsel, and pursuant to RSMo",
        "Section 543.200, requests a trial by jury in the above-captioned case.",
        "",
        format_attorney_signature_block(ctx),
        "",
        format_certificate_of_service(ctx),
    ]

    return "\n".join(parts)


def generate_waiver_of_arraignment(
    ctx: CaseContext,
    plea_type: str = "not-guilty"
) -> str:
    """Generate a Waiver of Arraignment pleading."""
    lead = ctx.lead_attorney or FIRM_INFO["default_attorneys"][0]

    parts = [
        format_case_caption(ctx),
        "",
        "                    WAIVER OF ARRAIGNMENT",
        "",
        f"I, {ctx.defendant_name_formal}, understand that I am charged with the following",
        "offenses:",
        "",
        format_charges_list(ctx.charges),
        "",
        f"I am represented by my attorney, {lead.name} of the Law Office",
        f"of {FIRM_INFO['name']} I understand I have a right to have the",
        "Judge of this Court read the charges to me word for word, and I",
        "understand that I can give up that right if I wish to do so. By signing",
        "my name below, I am notifying the Court that I am revoking my right to",
        "have the charges read aloud and that I understand the offenses with",
        "which I have been charged.",
        "",
        f"I hereby enter a plea of {plea_type} and request this case be placed on",
        "the docket for setting or disposition on a future date.",
        "",
        format_defendant_signature_block(),
    ]

    return "\n".join(parts)


def generate_entry_of_appearance(ctx: CaseContext) -> str:
    """Generate an Entry of Appearance pleading."""
    lead = ctx.lead_attorney or FIRM_INFO["default_attorneys"][0]

    parts = [
        format_case_caption(ctx),
        "",
        "                    ENTRY OF APPEARANCE",
        "",
        f"Comes now the undersigned attorney and enters an appearance on behalf of",
        f"Defendant, {ctx.defendant_name_formal}, in the above-captioned case.",
        "",
        "All future pleadings, notices, and communications should be directed to",
        "the undersigned at the address below.",
        "",
        format_attorney_signature_block(ctx, include_all=False),
        "",
        format_certificate_of_service(ctx),
    ]

    return "\n".join(parts)


def generate_motion_to_continue(
    ctx: CaseContext,
    current_date: str,
    reason: str
) -> str:
    """Generate a Motion to Continue pleading."""
    parts = [
        format_case_caption(ctx),
        "",
        "                    MOTION TO CONTINUE",
        "",
        f"Comes now Defendant, {ctx.defendant_name_formal}, by and through counsel,",
        "and moves this Court for an Order continuing the matter currently set for",
        f"{current_date}, and in support thereof states:",
        "",
        f"1. {reason}",
        "",
        "2. This continuance will not prejudice any party.",
        "",
        "3. Defendant waives any speedy trial issues that may arise from this",
        "   continuance.",
        "",
        "WHEREFORE, Defendant respectfully requests this Court grant the Motion",
        "to Continue and reset this matter for a future date.",
        "",
        format_attorney_signature_block(ctx),
        "",
        format_certificate_of_service(ctx),
    ]

    return "\n".join(parts)


# ============================================================================
# Pleading Type Registry
# ============================================================================

PLEADING_TYPES = {
    "request_for_jury_trial": {
        "name": "Request for Jury Trial",
        "generator": generate_request_for_jury_trial,
        "requires_charges": False,
        "requires_defendant_signature": False,
        "additional_params": [],
    },
    "waiver_of_arraignment": {
        "name": "Waiver of Arraignment",
        "generator": generate_waiver_of_arraignment,
        "requires_charges": True,
        "requires_defendant_signature": True,
        "additional_params": ["plea_type"],
    },
    "entry_of_appearance": {
        "name": "Entry of Appearance",
        "generator": generate_entry_of_appearance,
        "requires_charges": False,
        "requires_defendant_signature": False,
        "additional_params": [],
    },
    "motion_to_continue": {
        "name": "Motion to Continue",
        "generator": generate_motion_to_continue,
        "requires_charges": False,
        "requires_defendant_signature": False,
        "additional_params": ["current_date", "reason"],
    },
}


# ============================================================================
# High-Level API
# ============================================================================

class PleadingGenerator:
    """
    High-level pleading generation with MyCase integration.

    Usage:
        generator = PleadingGenerator(cache_db)
        result = generator.generate(
            pleading_type="waiver_of_arraignment",
            case_id=12345,
            plea_type="not-guilty"
        )
    """

    def __init__(self, cache_db=None, skill_manager=None):
        self.cache_db = cache_db
        self.skill_manager = skill_manager

    def generate(
        self,
        pleading_type: str,
        case_id: Optional[int] = None,
        case_context: Optional[CaseContext] = None,
        output_format: str = "text",  # "text", "docx"
        output_path: Optional[Path] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Generate a pleading document.

        Args:
            pleading_type: Type of pleading (see PLEADING_TYPES)
            case_id: MyCase case ID (will load context from cache)
            case_context: Pre-built CaseContext (alternative to case_id)
            output_format: "text" or "docx"
            output_path: Where to save the document
            **kwargs: Additional parameters for the pleading type

        Returns:
            Dict with generated content and metadata
        """
        if pleading_type not in PLEADING_TYPES:
            raise ValueError(f"Unknown pleading type: {pleading_type}. Options: {list(PLEADING_TYPES.keys())}")

        pleading_info = PLEADING_TYPES[pleading_type]

        # Build context
        if case_context:
            ctx = case_context
        elif case_id and self.cache_db:
            ctx = self._build_context_from_cache(case_id)
        else:
            raise ValueError("Must provide either case_id (with cache_db) or case_context")

        # Check requirements
        if pleading_info["requires_charges"] and not ctx.charges:
            # Try to extract charges with AI if available
            if self.skill_manager:
                ctx.charges = self._extract_charges_with_ai(ctx)

            if not ctx.charges:
                raise ValueError(f"{pleading_info['name']} requires charges but none provided")

        # Generate the pleading
        generator_func = pleading_info["generator"]
        if pleading_info["additional_params"]:
            content = generator_func(ctx, **kwargs)
        else:
            content = generator_func(ctx)

        # Generate output file if requested
        file_path = None
        if output_format == "docx":
            file_path = self._generate_docx(content, pleading_type, ctx, output_path)

        return {
            "pleading_type": pleading_type,
            "pleading_name": pleading_info["name"],
            "content": content,
            "output_path": str(file_path) if file_path else None,
            "context": {
                "case_number": ctx.case_number,
                "defendant": ctx.defendant_name,
                "county": ctx.county,
                "charges_count": len(ctx.charges),
            }
        }

    def _build_context_from_cache(self, case_id: int) -> CaseContext:
        """Build CaseContext from MyCase cache data."""
        with self.cache_db._get_connection() as conn:
            cursor = conn.cursor()

            # Get case
            cursor.execute("SELECT * FROM cases WHERE id = ?", (case_id,))
            case_row = cursor.fetchone()
            if not case_row:
                raise ValueError(f"Case {case_id} not found in cache")

            case_data = dict(case_row)

            # Get client/defendant
            defendant_name = case_data.get("name", "UNKNOWN DEFENDANT")

            # Parse county from court name (e.g., "Scott County Circuit Court" -> "Scott")
            court_name = case_data.get("court", "")
            county_match = re.search(r"(\w+)\s+County", court_name, re.IGNORECASE)
            county = county_match.group(1) if county_match else "Unknown"

            # Get case number
            case_number = case_data.get("number", case_data.get("case_number", "UNKNOWN"))

            # Try to parse charges from description or custom fields
            charges = self._parse_charges(case_data)

            return CaseContext(
                case_number=case_number,
                county=county,
                defendant_name=defendant_name.upper(),
                charges=charges,
                attorneys=FIRM_INFO["default_attorneys"],
                mycase_case_id=case_id,
            )

    def _parse_charges(self, case_data: dict) -> List[Charge]:
        """Parse charges from case data."""
        # This is a simplified version - real implementation would
        # look at custom fields or case description
        charges = []

        # Check for charges in custom fields
        custom_charges = case_data.get("charges", [])
        if isinstance(custom_charges, list):
            for i, charge_text in enumerate(custom_charges, 1):
                charges.append(Charge(
                    count_number=i,
                    description=charge_text,
                    classification=ChargeClass.MISDEMEANOR_A  # Default, should be parsed
                ))

        return charges

    def _extract_charges_with_ai(self, ctx: CaseContext) -> List[Charge]:
        """Use AI to extract charges from case description."""
        # This would use the skill manager to analyze case data
        # and extract structured charges
        return []

    def _generate_docx(
        self,
        content: str,
        pleading_type: str,
        ctx: CaseContext,
        output_path: Optional[Path]
    ) -> Path:
        """Generate a Word document from the pleading content."""
        try:
            from docx import Document
            from docx.shared import Inches, Pt
            from docx.enum.text import WD_ALIGN_PARAGRAPH
        except ImportError:
            raise ImportError("python-docx required: pip install python-docx")

        doc = Document()

        # Set up page margins (1 inch)
        for section in doc.sections:
            section.top_margin = Inches(1)
            section.bottom_margin = Inches(1)
            section.left_margin = Inches(1)
            section.right_margin = Inches(1)

        # Set default font
        style = doc.styles['Normal']
        style.font.name = 'Courier New'  # Common for legal documents
        style.font.size = Pt(12)

        # Add content line by line
        for line in content.split('\n'):
            p = doc.add_paragraph(line)

            # Center titles
            if line.strip().startswith("IN THE") or "COUNTY" in line.upper():
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            elif line.strip().isupper() and len(line.strip()) > 10:
                # Likely a document title
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER

        # Determine output path
        if not output_path:
            output_dir = DATA_DIR / "pleadings"
            output_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_name = re.sub(r'[^\w\-]', '_', pleading_type)
            filename = f"{safe_name}_{ctx.case_number}_{timestamp}.docx"
            output_path = output_dir / filename

        doc.save(str(output_path))
        return output_path


def list_pleading_types() -> List[dict]:
    """List all available pleading types."""
    return [
        {
            "type": key,
            "name": info["name"],
            "requires_charges": info["requires_charges"],
            "requires_defendant_signature": info["requires_defendant_signature"],
            "additional_params": info["additional_params"],
        }
        for key, info in PLEADING_TYPES.items()
    ]
