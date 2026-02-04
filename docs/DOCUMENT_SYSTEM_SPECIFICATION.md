# LawMetrics.ai Document Generation System Specification

## Executive Summary

This specification defines a generalized document generation system for law firms based on analysis of JCS Law Firm's Master Document Folder containing **4,802 documents** across **290 folders**. The system enables lawyers to request documents by specifying purpose, court, and client details, with AI-powered template selection and variable substitution.

---

## Document Library Analysis

### Volume Summary

| Category | Document Count | Variation Type |
|----------|---------------|----------------|
| Pleadings | 130+ | Court type, case type |
| Motion for Continuance | 120 | Court-specific |
| Preservation/Discovery Letters | 130+ | Police agency-specific |
| Potential Prosecution Letters | 60+ | Court-specific |
| Disposition Letters to Clients | 50+ | Court-specific |
| Plea Forms | 30+ | County-specific |
| DWI Documents | 40+ | Refusal vs. Blow, county |
| Client Letters | 35+ | Purpose-specific |
| Subpoenas | 10+ | County-specific |
| Driver's License | 20+ | Petition type |
| SATOP Documents | 10+ | Provider-specific |
| Intake Forms | 6 | Standard |

### Key Variation Dimensions

1. **Jurisdiction** (100+ variations)
   - Circuit Courts by county (Franklin, Jefferson, St. Louis, etc.)
   - Municipal Courts by city (Arnold, Ballwin, Bridgeton, etc.)
   - State agencies (DOR, MSHP)

2. **Case Type**
   - DWI (Refusal vs. Blow)
   - Traffic Violations
   - Felony Criminal
   - Misdemeanor
   - Driver's License matters

3. **Attorney Assignment** (firm-specific)
   - ATM = Attorney initials
   - DCL = Attorney initials
   - DCC = Attorney initials

4. **Document Purpose**
   - Pre-charge (potential prosecution, preservation)
   - Pre-trial (motions, discovery)
   - Plea/Resolution (plea forms, waivers)
   - Post-disposition (closing, disposition letters)

---

## Document Categories

### 1. Pleadings
Formal court filings requiring case caption and court-specific formatting.

**Subcategories:**
- **Motions**: Bond reduction, continuance, dismiss, compel, suppress, withdraw
- **Petitions**: TDN, LDP, license after denial, IID waiver
- **Waivers**: Arraignment, preliminary hearing, jury trial
- **Requests**: Jury trial, supplemental discovery, preliminary hearing
- **Notices**: Hearing, change of address, deposition

**Template Variables:**
```
{{court_name}}          - Full court name with division
{{county}}              - County name
{{case_number}}         - Case number format varies by court
{{defendant_name}}      - Client/defendant full name
{{charges}}             - List of charges with classifications
{{attorney_name}}       - Filing attorney
{{attorney_bar_number}} - MO bar number
{{filing_date}}         - Date of filing
{{hearing_date}}        - Scheduled hearing date
```

### 2. Client Letters
Communications to clients about case status and outcomes.

**Subcategories:**
- **Disposition Letters**: Post-resolution with payment instructions (court-specific)
- **Status Updates**: Case progress notifications
- **Closing Letters**: Case completion with review request
- **Requirement Letters**: Instructions for specific courts

**Template Variables:**
```
{{client_name}}         - Client full name
{{client_address}}      - Full mailing address
{{case_outcome}}        - Result description (amended to X, dismissed, etc.)
{{fine_amount}}         - Total fines and costs
{{payment_deadline}}    - Due date for payment
{{court_address}}       - Court payment address
{{court_hours}}         - Court business hours
{{payment_methods}}     - Accepted payment methods
{{next_court_date}}     - If applicable
```

### 3. Prosecution Letters
Communications with prosecuting attorneys before/during proceedings.

**Subcategories:**
- **Potential Prosecution**: Pre-charge notification of representation
- **Discovery Requests**: Formal discovery communications

**Template Variables:**
```
{{prosecutor_name}}     - Prosecuting attorney name
{{prosecutor_address}}  - Office address
{{prosecutor_title}}    - Title (Prosecuting Attorney, City Attorney, etc.)
{{client_name}}         - Client name
```

### 4. Discovery/Preservation Letters
Evidence preservation and supplemental discovery requests to agencies.

**Subcategories:**
- **Preservation Letters**: Evidence preservation requests (agency-specific)
- **Supplemental Discovery**: Post-initial discovery requests

**Template Variables:**
```
{{agency_name}}         - Police department or agency
{{agency_address}}      - Agency mailing address
{{records_custodian}}   - Name of records custodian (if known)
{{defendant_name}}      - Client name
{{defendant_dob}}       - Date of birth
{{arrest_date}}         - Date of arrest
{{ticket_number}}       - Citation/ticket number
{{arresting_officer}}   - Officer name (if known)
{{charges}}             - Charges at arrest
```

### 5. Plea Forms
Court-specific plea documentation with varying format requirements.

**Subcategories:**
- **Circuit Court Pleas**: By county (Jefferson, Franklin, St. Charles, etc.)
- **Municipal Court Pleas**: Simplified format
- **Acknowledgment Forms**: Rights acknowledgment
- **Sentencing Forms**: Sentencing documentation

**Template Variables:**
```
{{court_name}}          - Court name
{{case_number}}         - Case number
{{defendant_name}}      - Defendant name
{{charges_with_class}}  - Charges with classification
{{sentence_terms}}      - Sentence details (probation, SIS, etc.)
{{fine_amount}}         - Fine amount
{{probation_term}}      - Probation length
{{special_conditions}}  - Community service, treatment, etc.
```

### 6. DWI-Specific Documents
Specialized documents for DWI defense (Refusal vs. Blow procedures).

**Subcategories:**
- **Petition for Review (PFR)**: DOR administrative hearing (county-specific)
- **Stay Orders**: License suspension stays
- **Confession Orders**: St. Louis County specific
- **DOR Motions**: Motions to dismiss DOR actions

**Template Variables:**
```
{{petitioner_name}}     - Client name
{{dob}}                 - Date of birth
{{drivers_license}}     - DL number
{{arrest_date}}         - Arrest date
{{test_result}}         - BAC or REFUSAL
{{arresting_agency}}    - Agency that made arrest
{{county}}              - County for filing
```

### 7. Driver's License Documents
License reinstatement and limited driving privileges.

**Subcategories:**
- **LDP Applications**: Limited Driving Privilege requests
- **Reinstatement Petitions**: Post-denial petitions
- **5/10 Year Denial Petitions**: Long-term denial matters

### 8. Subpoenas
Court subpoenas for records and witnesses (county-specific forms).

---

## System Architecture

### Database Schema

```sql
-- Courts/Jurisdictions Registry
CREATE TABLE courts (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,                    -- "Arnold Municipal Court"
    court_type TEXT NOT NULL,              -- "municipal", "circuit", "dor"
    county TEXT,                           -- "Jefferson"
    city TEXT,                             -- "Arnold"
    address TEXT,
    phone TEXT,
    hours TEXT,
    payment_methods TEXT,                  -- JSON array
    clerk_name TEXT,
    prosecutor_name TEXT,
    prosecutor_address TEXT,
    case_number_format TEXT,               -- Regex pattern
    metadata JSON                          -- Additional court-specific data
);

-- Police/Agency Registry
CREATE TABLE agencies (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,                    -- "Missouri State Highway Patrol"
    short_name TEXT,                       -- "MSHP"
    agency_type TEXT,                      -- "state_police", "county_sheriff", "municipal_pd"
    address TEXT,
    records_custodian TEXT,
    records_phone TEXT,
    preservation_email TEXT,
    metadata JSON
);

-- Document Templates
CREATE TABLE templates (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT NOT NULL,                -- "pleading", "letter", "form"
    subcategory TEXT,                      -- "motion", "disposition", "preservation"
    document_type TEXT,                    -- Specific type identifier
    court_id INTEGER,                      -- NULL for universal templates
    agency_id INTEGER,                     -- NULL for non-agency templates
    case_types TEXT,                       -- JSON array: ["dwi", "traffic", "felony"]
    file_path TEXT NOT NULL,
    variables JSON,                        -- Required template variables
    version INTEGER DEFAULT 1,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    FOREIGN KEY (court_id) REFERENCES courts(id),
    FOREIGN KEY (agency_id) REFERENCES agencies(id)
);

-- Template Variables Definition
CREATE TABLE template_variables (
    id INTEGER PRIMARY KEY,
    template_id INTEGER,
    variable_name TEXT NOT NULL,           -- "client_name"
    display_name TEXT,                     -- "Client Name"
    variable_type TEXT,                    -- "text", "date", "currency", "choice", "case_field"
    source TEXT,                           -- "mycase", "court", "manual", "ai_inferred"
    mycase_field TEXT,                     -- Mapping to MyCase field
    required BOOLEAN DEFAULT TRUE,
    default_value TEXT,
    validation_regex TEXT,
    choices JSON,                          -- For choice type
    FOREIGN KEY (template_id) REFERENCES templates(id)
);

-- Generated Documents Audit Log
CREATE TABLE generated_documents (
    id INTEGER PRIMARY KEY,
    template_id INTEGER,
    case_id TEXT,                          -- MyCase case ID
    client_id TEXT,                        -- MyCase contact ID
    court_id INTEGER,
    generated_by TEXT,                     -- User who requested
    variables_used JSON,                   -- Actual values used
    ai_inferences JSON,                    -- What AI filled in
    quality_score TEXT,                    -- GREEN, YELLOW, RED
    output_path TEXT,
    generated_at TIMESTAMP,
    FOREIGN KEY (template_id) REFERENCES templates(id),
    FOREIGN KEY (court_id) REFERENCES courts(id)
);
```

### Template Selection Logic

```python
def select_template(
    document_type: str,
    court: Optional[str] = None,
    agency: Optional[str] = None,
    case_type: Optional[str] = None
) -> Template:
    """
    Select the most specific matching template.

    Priority order:
    1. Exact match (document_type + court + case_type)
    2. Court-specific (document_type + court)
    3. Case-type specific (document_type + case_type)
    4. Universal (document_type only)
    """
    # Query templates with specificity scoring
    candidates = db.query("""
        SELECT t.*,
            (CASE WHEN t.court_id = ? THEN 10 ELSE 0 END) +
            (CASE WHEN t.agency_id = ? THEN 10 ELSE 0 END) +
            (CASE WHEN ? IN (SELECT value FROM json_each(t.case_types)) THEN 5 ELSE 0 END)
            AS specificity_score
        FROM templates t
        WHERE t.document_type = ?
          AND t.is_active = TRUE
        ORDER BY specificity_score DESC
        LIMIT 1
    """, [court_id, agency_id, case_type, document_type])

    return candidates[0] if candidates else None
```

### Variable Resolution Pipeline

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Variable Resolution Pipeline                       │
├─────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  1. User Request                                                      │
│     "Generate disposition letter for case 12345, Arnold Municipal"   │
│                              │                                        │
│                              ▼                                        │
│  2. Template Selection                                                │
│     → Find: "Dispo Ltr to Client - Arnold Muni.docx"                │
│     → Extract required variables from template                       │
│                              │                                        │
│                              ▼                                        │
│  3. MyCase Data Pull                                                  │
│     → client_name: from case.client.name                             │
│     → client_address: from case.client.address                       │
│     → case_number: from case.case_number                             │
│     → charges: from case.charges                                      │
│                              │                                        │
│                              ▼                                        │
│  4. Court Data Pull                                                   │
│     → court_address: from courts table                               │
│     → court_hours: from courts table                                  │
│     → payment_methods: from courts table                             │
│                              │                                        │
│                              ▼                                        │
│  5. AI Inference (Claude)                                             │
│     → case_outcome: Infer from charges and disposition               │
│     → fine_amount: Calculate from court schedule                      │
│     → next_court_date: From case events                              │
│                              │                                        │
│                              ▼                                        │
│  6. User Override                                                     │
│     → Allow manual override of any variable                          │
│     → Flag AI-inferred values for review                             │
│                              │                                        │
│                              ▼                                        │
│  7. Document Generation                                               │
│     → Substitute variables                                            │
│     → Format document (python-docx)                                  │
│     → Quality assessment (GREEN/YELLOW/RED)                          │
│                              │                                        │
│                              ▼                                        │
│  8. Output                                                            │
│     → Save .docx to output folder                                    │
│     → Log generation in audit table                                  │
│                                                                       │
└─────────────────────────────────────────────────────────────────────┘
```

---

## AI Integration Points

### 1. Template Selection Assistant

```python
TEMPLATE_SELECTOR_PROMPT = """
You are a legal document assistant for a Missouri law firm.
Given a document request, identify the best template match.

Available document types:
{document_types_list}

Courts in database:
{courts_list}

User request: {user_request}

Respond with JSON:
{{
    "document_type": "identified type",
    "court": "identified court or null",
    "case_type": "dwi|traffic|felony|misdemeanor|other",
    "confidence": "high|medium|low",
    "clarifications_needed": ["list of questions if confidence is low"]
}}
"""
```

### 2. Variable Inference

```python
VARIABLE_INFERENCE_PROMPT = """
You are a legal document assistant. Given case data, infer missing template variables.

Template requires: {required_variables}
Case data available: {case_data}
Court data available: {court_data}

For each missing variable, either:
1. Infer from available data with explanation
2. Mark as "REQUIRES_INPUT" if cannot be inferred

Respond with JSON:
{{
    "inferred_variables": {{
        "variable_name": {{
            "value": "inferred value",
            "source": "explanation of how inferred",
            "confidence": "high|medium|low"
        }}
    }},
    "requires_input": ["list of variables that cannot be inferred"]
}}
"""
```

### 3. Quality Assessment

```python
QUALITY_ASSESSMENT_PROMPT = """
Review this generated legal document for quality and completeness.

Document type: {document_type}
Court: {court}
Generated content: {document_content}
Variables used: {variables}
AI-inferred values: {ai_inferences}

Classification:
- GREEN: All required fields populated accurately, ready for attorney review
- YELLOW: Some AI inference used, verify flagged items before sending
- RED: Missing critical information or potential errors

Respond with JSON:
{{
    "classification": "GREEN|YELLOW|RED",
    "issues": ["list of specific issues"],
    "suggestions": ["list of improvements"],
    "verification_required": ["items attorney should verify"]
}}
"""
```

---

## CLI Commands

### Document Generation Commands

```bash
# Generate by document type (AI selects template)
uv run python agent.py docs generate "disposition letter" \
    --case-id 12345 \
    --court "Arnold Municipal"

# Generate specific template
uv run python agent.py docs generate-template "Dispo Ltr to Client - Arnold Muni" \
    --case-id 12345

# Generate with explicit variables
uv run python agent.py docs generate "preservation letter" \
    --agency "MSHP" \
    --var "defendant_name=John Smith" \
    --var "arrest_date=2026-01-15"

# Batch generate for multiple cases
uv run python agent.py docs batch-generate "disposition letter" \
    --case-ids 12345,12346,12347 \
    --court "St. Louis County Circuit"
```

### Template Management Commands

```bash
# Import templates from folder
uv run python agent.py templates import "/path/to/Master Document Folder" \
    --recursive \
    --auto-categorize

# List templates by category
uv run python agent.py templates list --category pleading --court "Jefferson County"

# Show template variables
uv run python agent.py templates variables "Motion for Bond Reduction"

# Update court data
uv run python agent.py courts update "Arnold Municipal" \
    --address "2101 Jeffco Boulevard, Arnold, MO 63010" \
    --hours "8:00am-4:30pm M-F"
```

### Court/Agency Management

```bash
# List all courts
uv run python agent.py courts list --county "St. Louis"

# Add new court
uv run python agent.py courts add "New City Municipal Court" \
    --type municipal \
    --county "St. Louis" \
    --city "New City"

# List agencies
uv run python agent.py agencies list --type state_police

# Update agency records custodian
uv run python agent.py agencies update "MSHP" \
    --records-custodian "Lieutenant Gerald Callahan"
```

---

## Template Import Process

### Auto-Categorization Rules

```python
CATEGORIZATION_RULES = {
    # Filename patterns → Category assignment
    r"Motion to|Motion for": ("pleading", "motion"),
    r"Petition for": ("pleading", "petition"),
    r"Waiver of": ("pleading", "waiver"),
    r"Request for": ("pleading", "request"),
    r"Notice of": ("pleading", "notice"),

    r"Dispo Ltr|Disposition Letter": ("letter", "disposition"),
    r"Status Update": ("letter", "status"),
    r"Closing [Ll]etter": ("letter", "closing"),

    r"Potential Prosecution": ("prosecution", "potential"),
    r"Preservation Letter": ("discovery", "preservation"),
    r"Supplemental Disc": ("discovery", "supplemental"),

    r"Plea of Guilty|Plea Form": ("plea", "guilty"),
    r"Sentencing": ("plea", "sentencing"),

    r"PFR|Petition for Review": ("dwi", "pfr"),
    r"Stay Order": ("dwi", "stay"),

    r"Subpoena": ("subpoena", None),
}

COURT_EXTRACTION_PATTERNS = [
    r" - ([A-Za-z\s]+) Muni\.?(?:cipal)?",  # "- Arnold Muni"
    r" - ([A-Za-z\s]+) County",              # "- Jefferson County"
    r" - ([A-Za-z\s]+) Circuit",             # "- Franklin County Circuit"
]

AGENCY_EXTRACTION_PATTERNS = [
    r" - MSHP",
    r" - ([A-Za-z\s]+) Police Dept\.?",
    r" - ([A-Za-z\s]+) Sheriff",
]
```

### Variable Detection

```python
def extract_template_variables(docx_path: str) -> List[str]:
    """
    Scan document for {{variable}} patterns.
    Returns list of variable names found.
    """
    doc = Document(docx_path)
    variables = set()

    pattern = re.compile(r'\{\{([a-z_]+)\}\}')

    for para in doc.paragraphs:
        matches = pattern.findall(para.text)
        variables.update(matches)

    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                matches = pattern.findall(cell.text)
                variables.update(matches)

    return list(variables)
```

---

## Implementation Phases

### Phase 1: Foundation (Week 1-2)
- [ ] Create courts/agencies database with Missouri data
- [ ] Import Master Document Folder templates
- [ ] Auto-categorize templates by filename patterns
- [ ] Extract variables from template files
- [ ] Basic CLI for template listing and search

### Phase 2: Generation Engine (Week 3-4)
- [ ] Variable resolution from MyCase cache
- [ ] Variable resolution from courts/agencies database
- [ ] Basic document generation (variable substitution)
- [ ] Word document output with formatting preservation
- [ ] Generation audit logging

### Phase 3: AI Integration (Week 5-6)
- [ ] AI-powered template selection
- [ ] AI variable inference for missing data
- [ ] Quality assessment scoring
- [ ] Natural language document requests

### Phase 4: Advanced Features (Week 7-8)
- [ ] Batch document generation
- [ ] Template versioning and history
- [ ] Document comparison (diff)
- [ ] Web interface for non-CLI users
- [ ] Integration with MyCase document upload

---

## Appendix: Missouri Courts Reference

### Circuit Courts (114 counties)
Major counties with high case volume:
- St. Louis County Circuit Court
- St. Louis City Circuit Court
- Jefferson County Circuit Court
- Franklin County Circuit Court
- St. Charles County Circuit Court

### Municipal Courts (300+)
Sampling of municipalities in database:
- Arnold, Ballwin, Berkeley, Bridgeton, Byrnes Mill
- Chesterfield, Clayton, Cool Valley, Cottleville
- Crestwood, Creve Coeur, Dellwood, DeSoto
- Ellisville, Eureka, Fenton, Festus, Florissant
- Frontenac, Hazelwood, Kirkwood, Ladue
- Lake St. Louis, Manchester, Maplewood
- Maryland Heights, Normandy, O'Fallon, Olivette
- Overland, Richmond Heights, Rock Hill
- St. Charles, St. John, St. Peters
- Town & Country, University City, Valley Park
- Webster Groves, Wentzville, Wildwood

### State Agencies
- Missouri Department of Revenue (DOR)
- Missouri State Highway Patrol (MSHP)
- County Sheriff Departments (114)

---

## File Naming Convention

For imported templates, maintain consistent naming:

```
{Category}/{Subcategory}/{DocumentType} - {Jurisdiction}.docx

Examples:
Pleadings/Motions/Motion for Bond Reduction - Jefferson County.docx
Letters/Disposition/Dispo Ltr to Client - Arnold Muni.docx
Discovery/Preservation/Preservation Letter - MSHP.docx
Pleas/Circuit/Plea of Guilty - Franklin County.docx
```
