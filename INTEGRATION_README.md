# LawMetrics.ai AI & Document Generation Integration

## Quick Start

### 1. Add Dependencies

Add to `requirements.txt`:
```
anthropic>=0.39.0
python-docx>=1.1.0
```

Install:
```bash
pip install anthropic python-docx --break-system-packages
```

### 2. Set API Key

```bash
export ANTHROPIC_API_KEY="your-key-here"
```

Or add to `.env`:
```
ANTHROPIC_API_KEY=your-key-here
```

### 3. Integrate with agent.py

Add these lines near the top of `agent.py` (after other imports):

```python
# AI and Document Generation Commands
from ai_commands import ai_cli, templates_cli, docs_cli, pleadings_cli
```

Then add these lines after the `cli` group is defined (around line 64):

```python
# Register AI command groups
cli.add_command(ai_cli, name="ai")
cli.add_command(templates_cli, name="templates")
cli.add_command(docs_cli, name="docs")
cli.add_command(pleadings_cli, name="pleadings")
```

---

## New Commands Available

### AI Analysis Commands (`agent.py ai`)

```bash
# Assess a single case's health (GREEN/YELLOW/RED)
uv run python agent.py ai triage 12345

# Assess collection risk for a contact
uv run python agent.py ai collections-risk C-9876

# Generate daily briefing for staff
uv run python agent.py ai briefing melissa
uv run python agent.py ai briefing melissa --export  # Save to file

# Batch triage all cases
uv run python agent.py ai batch-triage
uv run python agent.py ai batch-triage --phase 2 --limit 50  # Phase 2 only
uv run python agent.py ai batch-triage --export  # Export to CSV
```

### Template Management (`agent.py templates`)

```bash
# List all templates
uv run python agent.py templates list
uv run python agent.py templates list --category plea --court Municipal

# Search templates
uv run python agent.py templates search "DWI plea"

# Add a new template
uv run python agent.py templates add plea_dwi.docx \
    --name "DWI Plea - Municipal" \
    --category plea \
    --court "Municipal" \
    --jurisdiction "Hamilton County" \
    --case-types "DWI" \
    --tags "first-offense,standard"

# Show template details
uv run python agent.py templates show 1
```

### Document Generation (`agent.py docs`)

```bash
# Generate a document from template
uv run python agent.py docs generate "DWI Plea - Municipal" \
    --case-id 12345 \
    --court "Hamilton County Municipal Court" \
    --context "First offense, BAC 0.09"

# Generate with explicit variables
uv run python agent.py docs generate "NDA Standard" \
    --var "party_name=Acme Corp" \
    --var "effective_date=2026-02-15"

# Simple substitution without AI
uv run python agent.py docs generate "Letter Template" \
    --client "John Smith" \
    --no-ai

# View generation history
uv run python agent.py docs history
uv run python agent.py docs history --case-id 12345
```

### Pleading Generation (`agent.py pleadings`)

```bash
# List available pleading types
uv run python agent.py pleadings list

# Generate Request for Jury Trial
uv run python agent.py pleadings generate request_for_jury_trial \
    --defendant "JOHN SMITH" \
    --case-number "22AB-CR00123" \
    --county "Scott"

# Generate Waiver of Arraignment with charges
uv run python agent.py pleadings generate waiver_of_arraignment \
    --defendant "GLENN MANSFIELD" \
    --case-number "22SO-CR00195" \
    --county "Scott" \
    --charges "Delivery of Controlled Substance|Class C Felony|RSMo 579.020" \
    --charges "Unlawful Possession of Firearm|Class D Felony|RSMo 571.070" \
    --charges "Tampering with Physical Evidence|Class A Misdemeanor|RSMo 575.100"

# Generate Motion to Continue
uv run python agent.py pleadings generate motion_to_continue \
    --defendant "JANE DOE" \
    --case-number "22AB-CR00456" \
    --county "Scott" \
    --current-date "February 15, 2026" \
    --reason "Defense counsel has a scheduling conflict"

# Extract charges from text using AI
uv run python agent.py pleadings extract-charges \
    "Defendant charged with DWI first offense and driving while revoked"
```

---

## File Structure

```
Legal/
├── agent.py                    # Main CLI (add integration lines)
├── ai_commands.py              # NEW: AI CLI command groups
├── templates_db.py             # NEW: Template database management
├── skills/
│   ├── __init__.py             # Skills module exports
│   ├── base.py                 # Base skill classes
│   ├── case_triage.py          # Case health assessment skill
│   ├── collections_risk.py     # Collection risk assessment skill
│   ├── briefing.py             # Daily briefing generation skill
│   ├── document_generation.py  # Document generation skill
│   └── example_usage.py        # Usage examples
├── data/
│   ├── templates.db            # Template database (auto-created)
│   └── document_templates/     # Uploaded template files
├── docs/
│   └── LEGAL_PLUGIN_INTEGRATION_GUIDE.md  # Detailed patterns guide
└── INTEGRATION_README.md       # This file
```

---

## Document Generation Workflow

```
┌─────────────────────────────────────────────────────────────────┐
│                    Document Generation Flow                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. Lawyer Request                                               │
│     "Generate a DWI plea for case 12345,                        │
│      Hamilton Municipal Court, first offense"                    │
│                              │                                   │
│                              ▼                                   │
│  2. Template Lookup                                              │
│     Search templates_db for matching template                    │
│     by name, category, court, jurisdiction                       │
│                              │                                   │
│                              ▼                                   │
│  3. Context Gathering                                            │
│     Pull case data from MyCase cache:                           │
│     - Client name, contact info                                  │
│     - Case type, charges, dates                                  │
│     - Attorney, court info                                       │
│                              │                                   │
│                              ▼                                   │
│  4. AI Document Generation                                       │
│     Claude fills template with:                                  │
│     - Variable substitution                                      │
│     - Context-aware adaptations                                  │
│     - Legal language appropriate for court                       │
│                              │                                   │
│                              ▼                                   │
│  5. Quality Assessment                                           │
│     GREEN: Ready for review                                      │
│     YELLOW: Some AI inference, verify                            │
│     RED: Missing info or issues                                  │
│                              │                                   │
│                              ▼                                   │
│  6. Word Document Output                                         │
│     Generate .docx with proper formatting                        │
│     using docx-js (Node) or python-docx                         │
│                              │                                   │
│                              ▼                                   │
│  7. Audit Trail                                                  │
│     Log generation in generated_documents table                  │
│     Track template usage, variables used                         │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Template Variable Format

Templates use `{{variable_name}}` syntax:

```
IN THE {{court_name}}
{{jurisdiction}}

STATE OF {{state}}
    vs.                             Case No. {{case_number}}
{{client_name}},
    Defendant.

PLEA OF GUILTY

COMES NOW the Defendant, {{client_name}}, by and through counsel,
{{attorney_name}}, and enters a plea of guilty to the charge of
{{charge_description}}.

The Defendant understands that this plea is entered on {{plea_date}}...
```

### Variable Types

When adding templates, variables are auto-detected. You can also define them explicitly:

- **text**: Free text (default)
- **date**: Date values
- **number**: Numeric values
- **choice**: Select from predefined options
- **case_field**: Auto-mapped from MyCase data

---

## Skill Patterns Reference

The skills follow patterns from Anthropic's legal plugin:

### 1. GREEN/YELLOW/RED Classification
```python
GREEN   = Acceptable, proceed without escalation
YELLOW  = Needs review, flag specific issues
RED     = Significant issues, escalate for human review
```

### 2. Risk Matrix (Collections)
```
Risk Score = Severity (1-5) × Likelihood (1-5)
Score 1-4:   GREEN  (Low Risk)
Score 5-9:   YELLOW (Medium Risk)
Score 10-15: ORANGE (High Risk)
Score 16-25: RED    (Critical Risk)
```

### 3. Escalation Triggers
- Potential litigation or malpractice
- Client threats or complaints
- Regulatory inquiries
- Unprecedented situations
- 60+ days unresponsive with balance

---

## Example: Complete Document Generation

```python
from skills import SkillManager, DocumentGenerationSkill, DocumentGenerator
from templates_db import get_templates_db

# Initialize
skill_manager = SkillManager()
skill_manager.register(DocumentGenerationSkill())
templates_db = get_templates_db()

# Create generator
generator = DocumentGenerator(
    templates_db=templates_db,
    cache_db=my_cache_db,  # Your MyCase cache
    skill_manager=skill_manager
)

# Generate document
result = generator.generate(
    template_name="DWI Plea - Hamilton Municipal",
    case_id=12345,
    court="Hamilton County Municipal Court",
    purpose="Guilty plea for first-offense DWI",
    additional_context="Client is cooperative, employed, first offense, BAC was 0.09"
)

print(f"Document generated: {result['output_path']}")
print(f"Quality: {result['quality_assessment']['classification']}")
```

---

## Template Import System

The system can automatically import your firm's existing document library:

### Analyze Before Import

```bash
# Preview what would be imported (no changes made)
python template_importer.py "Master Document Folder" --analyze
```

Sample output:
```
Total files: 4802

By category:
  pleading/motion: 962
  letter/disposition: 412
  letter/preservation: 285
  pleading/petition: 157
  ...

By court type:
  municipal: 1466
  circuit: 810
  ...
```

### Import Templates

```bash
# Import all templates from folder
python template_importer.py "Master Document Folder"
```

### Auto-Categorization

Templates are automatically categorized based on filename patterns:

| Pattern | Category | Subcategory |
|---------|----------|-------------|
| `Motion to...` | pleading | motion |
| `Petition for...` | pleading | petition |
| `Waiver of...` | pleading | waiver |
| `Request for...` | pleading | request |
| `Dispo Ltr...` | letter | disposition |
| `Preservation Letter...` | letter | preservation |
| `Potential Prosecution...` | letter | prosecution |

### Court/Jurisdiction Detection

Courts are extracted from filenames:
- `Motion - Arnold Muni.docx` → Arnold Municipal Court
- `Plea - Jefferson County.docx` → Jefferson County Circuit Court
- `Letter - MSHP.docx` → Missouri State Highway Patrol

---

## Courts & Agencies Database

The system maintains a registry of Missouri courts and agencies:

### Courts Database

```python
from courts_db import get_courts_db, Court, CourtType

db = get_courts_db()

# Search courts
courts = db.search_courts("Arnold")

# Get court by name
court = db.get_court_by_name("Arnold Municipal", county="Jefferson")

# List all municipal courts
munis = db.list_courts(court_type="municipal")
```

### Agency Database

```python
from courts_db import Agency, AgencyType

# Get agency for preservation letter
agency = db.get_agency_by_name("MSHP")
print(agency.records_custodian)  # "Lieutenant Gerald Callahan"
print(agency.address)            # "1510 East Elm Street..."
```

### Seed Missouri Data

```python
from courts_db import (
    get_courts_db,
    seed_missouri_courts,
    seed_stl_municipal_courts,
    seed_state_agencies
)

db = get_courts_db()
seed_missouri_courts(db)       # 114 circuit courts
seed_stl_municipal_courts(db)  # 40+ municipal courts
seed_state_agencies(db)        # MSHP, DOR
```

---

## Complete File Structure

```
Legal/
├── agent.py                    # Main CLI (add integration lines)
├── ai_commands.py              # AI CLI command groups
├── templates_db.py             # Template database management
├── courts_db.py                # NEW: Courts/agencies database
├── template_importer.py        # NEW: Bulk template import
├── pleadings.py                # Pleading generator
├── skills/
│   ├── __init__.py             # Skills module exports
│   ├── base.py                 # Base skill classes
│   ├── case_triage.py          # Case health assessment
│   ├── collections_risk.py     # Collection risk assessment
│   ├── briefing.py             # Daily briefing generation
│   ├── document_generation.py  # Document generation skill
│   ├── charge_extraction.py    # AI charge extraction
│   └── example_usage.py        # Usage examples
├── data/
│   ├── templates.db            # Template database (auto-created)
│   ├── courts.db               # Courts database (auto-created)
│   └── document_templates/     # Uploaded template files
├── docs/
│   ├── LEGAL_PLUGIN_INTEGRATION_GUIDE.md  # Detailed patterns
│   ├── PLEADING_TEMPLATE_ANALYSIS.md      # Pleading analysis
│   └── DOCUMENT_SYSTEM_SPECIFICATION.md   # NEW: Full system spec
├── Master Document Folder/     # Firm document library (4,802 docs)
└── INTEGRATION_README.md       # This file
```

---

## Support

For questions about the legal plugin patterns, see:
- `docs/LEGAL_PLUGIN_INTEGRATION_GUIDE.md` - Detailed patterns and examples
- `docs/DOCUMENT_SYSTEM_SPECIFICATION.md` - Complete system specification
- `skills/example_usage.py` - Working code examples
