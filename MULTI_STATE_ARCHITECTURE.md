# LawMetrics.ai Multi-State Document Engine — Architecture Specification

**Version:** 1.0 (Draft)
**Date:** February 21, 2026
**Author:** JCS Development Team
**Status:** Implementation Roadmap

---

## 1. Executive Summary

LawMetrics.ai currently powers document generation for JCS Law Firm in Missouri — a free-form state with no mandatory court forms and a fragmented 46-circuit court system. Over six development cycles, we consolidated ~4,800 per-county template variants into 56 universal templates with `{{placeholder}}` substitution, attorney profile auto-fill, and a conversational generation interface. This document defines the architecture for expanding that system to serve law firms in any US state, starting with six Phase 1 states.

### Why These Six States First

California, Iowa, Illinois, Minnesota, Kentucky, and Oklahoma were selected because they share two characteristics that dramatically reduce implementation complexity: unified court systems (a single trial court level statewide) and mandatory standardized forms published by their judiciaries. Where Missouri required us to author every template from scratch, these states provide 60-70% of the document infrastructure through official fillable PDFs and standardized formats.

| State | Court System | Population | Attorneys | Key Advantage |
|-------|-------------|-----------|-----------|---------------|
| California | 58 Superior Courts | 39.0M | 170K | Largest market. 700+ Judicial Council forms. |
| Illinois | Circuit Court (unified) | 12.6M | 65K | Adjacent to Missouri. Statewide standardized forms. |
| Iowa | District Court (unified) | 3.2M | 8K | Cleanest unified system. Ideal proof-of-concept. |
| Minnesota | District Court (unified) | 5.7M | 25K | Forms in Word + PDF. Easiest to automate. |
| Kentucky | Court of Justice (unified) | 4.5M | 14K | Unified since 1975. Searchable fillable PDFs. |
| Oklahoma | District Court + CCA | 4.0M | 12K | 12+ mandatory forms via Rule 13. |

### What We're Building

A new multi-state document generation engine that runs alongside the existing Missouri engine. The new engine adds three capabilities the Missouri engine does not have: a jurisdiction layer that selects the correct templates, formatting rules, and party terminology per state and court; a PDF form filling engine for mandatory court forms (using pypdf); and a court registry that stores addresses, local rules, and local form requirements down to the individual court level.

### Architecture Principles

1. **Separate templates per state.** Missouri templates stay as-is. Each new state gets its own template set authored to that state's rules and formatting requirements. A universal document type taxonomy maps equivalent documents across jurisdictions.

2. **Jurisdiction resolution by court.** The system resolves jurisdiction at the court level, not just the state level. California's 58 Superior Courts may have different local forms. Illinois circuit courts may have local rules. The court registry captures this granularity.

3. **Multi-state firms from day one.** A single firm can be licensed in multiple states. An attorney can hold bar admissions in multiple states. The system provisions the correct templates and forms for each jurisdiction the firm practices in.

4. **Two document output formats.** Free-form filings output as .docx (same as Missouri). Mandatory court forms output as filled PDFs. The generation pipeline determines which format based on the document type and jurisdiction.

5. **Hybrid onboarding.** Firms self-service through state selection and attorney profile setup. JCS reviews and customizes before go-live — validating template selection, court registry accuracy, and attorney profile completeness.

## 2. Current Architecture (Missouri Engine)

The Missouri engine is fully operational and will continue running unchanged. Understanding its structure is important because the multi-state engine reuses its core patterns while adding jurisdiction awareness.

### How It Works Today

The Missouri engine has four layers:

**Template Storage** — 56 consolidated .docx templates stored in PostgreSQL (`templates` table) with full-text search via `tsvector`/`tsquery`. Each template uses `{{placeholder}}` syntax for variable substitution. Templates are scoped by `firm_id` for multi-tenant isolation.

**Document Type Registry** — The `DOCUMENT_TYPES` dictionary in `document_chat.py` defines each document type's required variables, optional variables, and which fields auto-fill from the attorney profile. Template detection maps user requests (natural language or button clicks) to the correct document type and template.

**Generation Engine** — Three-pass variable substitution: (1) run-level replacement via python-docx preserving formatting, (2) cross-run replacement for placeholders split across XML runs, (3) XML-level post-processing for hyperlink-enclosed placeholders. Includes uppercase context detection for court captions and signature line normalization.

**Attorney Profiles** — Stored in the `attorneys` table with firm name, address, bar number, email, phone, fax. A primary attorney flag determines which profile auto-fills by default. Profile fields map to template placeholders like `{{attorney_name}}`, `{{firm_address}}`, `{{attorney_bar}}`.

### What the Multi-State Engine Inherits

The placeholder substitution engine, attorney profile auto-fill pattern, uppercase context detection, signature normalization, and conversational chat interface all carry forward. The multi-state engine wraps these in a jurisdiction-aware layer that determines which template to use, what formatting to apply, and whether to output .docx or filled PDF.

### What Changes

The multi-state engine does NOT modify `document_chat.py` or the Missouri template set. Instead, it introduces a new entry point (`multi_state_engine.py` or similar) that handles jurisdiction resolution, then delegates to either the .docx generation pipeline (similar to Missouri's) or a new PDF form filling pipeline.

## 3. Multi-State Data Model

All new tables follow the existing convention: PostgreSQL with multi-tenant isolation via `firm_id` where applicable, `%s` parameter placeholders, and bulk operations via `execute_values()`.

### New Tables

#### `jurisdictions`

State-level configuration. One row per state the platform supports.

```sql
CREATE TABLE jurisdictions (
    id              TEXT PRIMARY KEY,          -- 'MO', 'CA', 'IL', etc.
    state_name      TEXT NOT NULL,             -- 'Missouri', 'California'
    court_system    TEXT NOT NULL,             -- 'circuit', 'superior', 'district'
    is_unified      BOOLEAN DEFAULT false,     -- Unified trial court system?
    criminal_party_prosecution TEXT NOT NULL,   -- 'State of Missouri', 'People of the State of California'
    criminal_party_defense     TEXT DEFAULT 'Defendant',
    admin_agency    TEXT,                       -- 'DOR', 'DMV', 'SOS' (license agency)
    admin_hearing_deadline_days INTEGER,        -- 15 (MO), 10 (CA), etc.
    pleading_format JSONB,                     -- {"line_numbered": true, "lines_per_page": 28, ...}
    caption_template TEXT NOT NULL,            -- 'IN THE {{court_type}} OF {{COUNTY}} COUNTY, {{state_name}}'
    efiling_system  TEXT,                       -- 'Show-Me Courts', 'eFileTexas', etc.
    efiling_url     TEXT,
    forms_url       TEXT,                       -- Official forms portal URL
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
```

#### `courts`

Individual courts within each state. Jurisdiction resolution happens at this level.

```sql
CREATE TABLE courts (
    id              SERIAL PRIMARY KEY,
    jurisdiction_id TEXT NOT NULL REFERENCES jurisdictions(id),
    court_name      TEXT NOT NULL,              -- 'Superior Court of California, County of Los Angeles'
    court_type      TEXT NOT NULL,              -- 'superior', 'circuit', 'district', 'municipal'
    county          TEXT,                        -- 'Los Angeles', 'Jefferson'
    city            TEXT,
    division        TEXT,                        -- 'Criminal', 'Traffic', 'Family'
    address_line1   TEXT,
    address_line2   TEXT,
    city_state_zip  TEXT,
    phone           TEXT,
    local_rules_url TEXT,                        -- URL to court's local rules
    has_local_forms BOOLEAN DEFAULT false,       -- Does this court have its own forms?
    efiling_required BOOLEAN DEFAULT false,
    notes           TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(jurisdiction_id, county, court_type, division)
);
```

#### `document_type_taxonomy`

Universal document types that span jurisdictions. A "Motion for Continuance" is the same concept everywhere even if the template, rule citation, and terminology differ.

```sql
CREATE TABLE document_type_taxonomy (
    id              SERIAL PRIMARY KEY,
    type_key        TEXT NOT NULL UNIQUE,       -- 'motion_for_continuance', 'entry_of_appearance'
    display_name    TEXT NOT NULL,              -- 'Motion for Continuance'
    category        TEXT NOT NULL,              -- 'motions', 'pleadings', 'discovery', 'letters', 'notices', 'bond_fees'
    description     TEXT,
    is_court_filing BOOLEAN DEFAULT true,       -- false for letters, internal docs
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
```

#### `jurisdiction_templates`

Links a universal document type to a state-specific template. This is the core mapping table — it answers "what template do I use for a Motion for Continuance in California?"

```sql
CREATE TABLE jurisdiction_templates (
    id              SERIAL PRIMARY KEY,
    jurisdiction_id TEXT NOT NULL REFERENCES jurisdictions(id),
    document_type_id INTEGER NOT NULL REFERENCES document_type_taxonomy(id),
    template_name   TEXT NOT NULL,              -- 'Motion for Continuance (CA)'
    template_format TEXT NOT NULL DEFAULT 'docx', -- 'docx' or 'pdf'
    file_content    BYTEA,                      -- .docx template or PDF form
    required_vars   JSONB NOT NULL DEFAULT '[]', -- ["defendant_name", "case_number", "county"]
    optional_vars   JSONB DEFAULT '[]',
    auto_fill_from_profile JSONB DEFAULT '[]',  -- ["attorney_name", "firm_address", ...]
    rule_citation   TEXT,                        -- 'Penal Code §1050' (CA), 'Rule 65.03' (MO)
    party_terminology TEXT,                      -- 'defendant', 'petitioner', 'respondent'
    filing_notes    TEXT,                        -- 'Requires 2-day written notice + affidavit'
    is_active       BOOLEAN DEFAULT true,
    firm_id         TEXT,                        -- NULL = platform-wide, or firm-specific override
    search_vector   TSVECTOR,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(jurisdiction_id, document_type_id, firm_id)
);

CREATE INDEX idx_jt_jurisdiction ON jurisdiction_templates(jurisdiction_id);
CREATE INDEX idx_jt_document_type ON jurisdiction_templates(document_type_id);
CREATE INDEX idx_jt_search ON jurisdiction_templates USING GIN(search_vector);
```

#### `court_forms`

Official fillable PDF court forms published by state judiciaries. These are NOT authored by us — they are downloaded from official sources and stored for programmatic filling.

```sql
CREATE TABLE court_forms (
    id              SERIAL PRIMARY KEY,
    jurisdiction_id TEXT NOT NULL REFERENCES jurisdictions(id),
    court_id        INTEGER REFERENCES courts(id), -- NULL = statewide, non-NULL = local court form
    form_number     TEXT NOT NULL,              -- 'CR-101', 'FW-001', 'JDF-724'
    form_title      TEXT NOT NULL,              -- 'Plea Form With Explanations and Waiver of Rights'
    category        TEXT,                        -- 'plea', 'expungement', 'fee_waiver', 'restitution'
    document_type_id INTEGER REFERENCES document_type_taxonomy(id),
    source_url      TEXT NOT NULL,              -- URL where form was downloaded
    file_content    BYTEA NOT NULL,             -- The PDF form file
    is_mandatory    BOOLEAN DEFAULT true,        -- Must use this form (vs. optional/suggested)
    is_fillable     BOOLEAN DEFAULT true,
    last_checked    TIMESTAMPTZ,                -- When we last verified the form is current
    version_date    TEXT,                        -- Form revision date from the PDF
    notes           TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
```

#### `court_form_field_mappings`

Maps PDF form field names (as embedded in the PDF) to our universal placeholder names. This is how we know that PDF field `"defendant_name_1"` should receive the value of `{{defendant_name}}`.

```sql
CREATE TABLE court_form_field_mappings (
    id              SERIAL PRIMARY KEY,
    court_form_id   INTEGER NOT NULL REFERENCES court_forms(id),
    pdf_field_name  TEXT NOT NULL,              -- Field name in the PDF: 'defendant_name_1'
    placeholder_key TEXT NOT NULL,              -- Our universal key: 'defendant_name'
    field_type      TEXT DEFAULT 'text',        -- 'text', 'checkbox', 'radio', 'date'
    transform       TEXT,                        -- Optional: 'uppercase', 'date_format:MM/DD/YYYY'
    notes           TEXT,
    UNIQUE(court_form_id, pdf_field_name)
);
```

#### `attorney_bar_admissions`

An attorney can be barred in multiple states. Separates bar admissions from the base `attorneys` table.

```sql
CREATE TABLE attorney_bar_admissions (
    id              SERIAL PRIMARY KEY,
    attorney_id     INTEGER NOT NULL REFERENCES attorneys(id),
    jurisdiction_id TEXT NOT NULL REFERENCES jurisdictions(id),
    bar_number      TEXT NOT NULL,
    status          TEXT DEFAULT 'active',      -- 'active', 'inactive', 'suspended'
    admission_date  DATE,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(attorney_id, jurisdiction_id)
);
```

#### `firm_jurisdictions`

Which states a firm is licensed to practice in. Controls template provisioning.

```sql
CREATE TABLE firm_jurisdictions (
    id              SERIAL PRIMARY KEY,
    firm_id         TEXT NOT NULL,              -- References firms table
    jurisdiction_id TEXT NOT NULL REFERENCES jurisdictions(id),
    is_primary      BOOLEAN DEFAULT false,      -- Firm's home state
    onboarding_status TEXT DEFAULT 'pending',   -- 'pending', 'active', 'suspended'
    activated_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(firm_id, jurisdiction_id)
);
```

### Modified Existing Tables

#### `templates` (Missouri engine — minimal change)

Add a `jurisdiction_id` column defaulting to `'MO'` for all existing rows. This allows the Missouri engine to continue working unchanged while the multi-state engine can query templates by jurisdiction.

```sql
ALTER TABLE templates ADD COLUMN jurisdiction_id TEXT DEFAULT 'MO' REFERENCES jurisdictions(id);
```

#### `attorneys` (keep existing columns, add relationship)

The existing `bar_number` field on `attorneys` becomes the Missouri bar number. Multi-state bar numbers live in `attorney_bar_admissions`. Existing queries continue to work — the new table is additive.

### Entity Relationship Summary

```
jurisdictions (1) ──── (*) courts
jurisdictions (1) ──── (*) jurisdiction_templates
jurisdictions (1) ──── (*) court_forms
jurisdictions (1) ──── (*) attorney_bar_admissions
jurisdictions (1) ──── (*) firm_jurisdictions

document_type_taxonomy (1) ──── (*) jurisdiction_templates
document_type_taxonomy (1) ──── (*) court_forms

court_forms (1) ──── (*) court_form_field_mappings

attorneys (1) ──── (*) attorney_bar_admissions
firms (1) ──── (*) firm_jurisdictions
```

## 4. Template Strategy by State

Each state gets its own template set. Templates are authored to that state's procedural rules, court caption format, party terminology, and formatting requirements. The universal document type taxonomy maps equivalent documents across states so the system knows that California's "Demurrer" and Missouri's "Motion to Dismiss" serve the same function.

### California (Largest Market — 39M pop, 170K attorneys)

**Court system:** 58 Superior Courts (one per county), unified statewide rules. Criminal Division handles DUI/misdemeanor/felony. Traffic Division handles infractions.

**Caption format:** `SUPERIOR COURT OF THE STATE OF CALIFORNIA / COUNTY OF {{COUNTY}}`

**Party terminology:** `The People of the State of California v. {{defendant_name}}`

**Formatting requirement:** Free-form filings must use 28-line numbered pleading paper with specific margins (1" top, 0.5" bottom, 1" left, 0.5" right). This requires a California-specific .docx base template with line numbering enabled.

**Mandatory PDF forms (fill, don't author):**
- CR-101 — Plea Form with Explanations and Waiver of Rights (felony)
- CR-102 — Domestic Violence Plea Form (misdemeanor)
- CR-110 — Order for Victim Restitution
- CR-180 — Petition for Dismissal (expungement)
- CR-181 — Order for Dismissal
- FW-001 — Request for Fee Waiver
- TR-510 — Waiver of Rights (traffic/remote arraignment)

**Free-form templates to author (~25-30):** Entry of Appearance (Notice of Appearance in CA), Motion for Continuance (cite Penal Code §1050), Motion to Dismiss (Penal Code §995 for criminal), Demurrer (civil — new document type), Discovery Request (cite Penal Code §1054), Preservation Letter, Motion to Compel, Motion to Withdraw (cite CRC Rule 3.1362), Notice of Hearing, Disposition Letter, Closing Letter, DL Reinstatement Letter (to DMV), Motion for Bail Reduction (PC §1275), Waiver of Arraignment (PC §977, misdemeanor only), and others.

**Key differences from Missouri:** No bond assignment (CA uses bail, not bond). DUI admin hearings go to DMV (not DOR) with a 10-day deadline (not 15). No Petition for Review equivalent — separate criminal court process. Motion to Dismiss in civil cases uses "Demurrer" procedure.

**Estimated effort:** ~30 custom .docx templates + ~7 PDF form integrations + 58 court registry entries.

---

### Illinois (Adjacent to Missouri — 12.6M pop, 65K attorneys)

**Court system:** Circuit Courts (unified). 24 judicial circuits. No separate municipal courts.

**Caption format:** `IN THE CIRCUIT COURT OF THE {{ordinal}} JUDICIAL CIRCUIT / {{COUNTY}} COUNTY, ILLINOIS`

**Party terminology:** `People of the State of Illinois v. {{defendant_name}}`

**Mandatory forms:** Illinois Supreme Court publishes statewide standardized forms that all circuit courts must accept. Includes appearance form, limited scope appearance, and various criminal forms.

**Free-form templates to author (~20):** Entry of Appearance (statewide standard form as base), Motion for Continuance, Motion to Dismiss (725 ILCS 5/114-1), Discovery (Supreme Court Rule 412), Plea of Guilty, Waiver of Arraignment, Preservation Letter, Motion to Compel (Rule 415), Disposition Letter, Closing Letter, and others.

**Key differences from Missouri:** Uses judicial circuit numbering (not county name) in captions. DUI admin process through Secretary of State (SOS), not DOR. Statutory Summary Suspension petition (not PFR). Unified e-filing through Odyssey statewide.

**Estimated effort:** ~20 custom .docx templates + statewide standard form PDFs + 24 circuit court registry entries.

---

### Iowa (Proof-of-Concept — 3.2M pop, 8K attorneys)

**Court system:** District Courts (unified). 8 judicial districts. Cleanest unified system in the country.

**Caption format:** `IN THE IOWA DISTRICT COURT FOR {{COUNTY}} COUNTY`

**Party terminology:** `State of Iowa v. {{defendant_name}}`

**Mandatory forms:** Waiver of Rights and Written Guilty Plea (serious/aggravated misdemeanor), Written Arraignment and Plea of Not Guilty, Application for Postconviction Relief, Waiver of Initial Appearance and Preliminary Hearing. All available as fillable PDFs.

**Free-form templates to author (~15):** Entry of Appearance, Motion for Continuance, Motion to Dismiss, Discovery requests, Preservation Letter, Disposition Letter, Closing Letter, and others.

**Key differences from Missouri:** Smallest template set needed. Very clean, predictable system. 8 judicial districts (vs Missouri's 46 circuits). DUI admin handled through Iowa DOT.

**Estimated effort:** ~15 custom .docx templates + ~4 PDF form integrations + 8 district court registry entries. **Recommended as first implementation target** due to low complexity and clean system.

---

### Minnesota (Easiest to Automate — 5.7M pop, 25K attorneys)

**Court system:** District Courts (unified). 10 judicial districts.

**Caption format:** `STATE OF MINNESOTA / DISTRICT COURT / {{ordinal}} JUDICIAL DISTRICT / COUNTY OF {{COUNTY}}`

**Party terminology:** `State of Minnesota v. {{defendant_name}}`

**Mandatory forms:** Felony Petition to Enter Plea of Guilty, Misdemeanor/Gross Misdemeanor Petition to Enter Plea of Guilty, Plea Agreement forms. Available in both Word and PDF formats — the Word versions are particularly useful as they can be directly adapted into our template format.

**Free-form templates to author (~20):** Similar set to Iowa with Minnesota-specific rule citations.

**Key differences from Missouri:** Forms available in Word format (huge advantage — we can use them as template starting points). DUI admin through Minnesota Department of Public Safety. Implied consent hearing process.

**Estimated effort:** ~20 custom .docx templates (some adaptable from state Word forms) + ~5 PDF form integrations + 10 district court entries.

---

### Kentucky (Unified Since 1975 — 4.5M pop, 14K attorneys)

**Court system:** Court of Justice (unified). Circuit Courts (120 counties) and District Courts. Unified by 1975 constitutional amendment.

**Caption format:** `COMMONWEALTH OF KENTUCKY / {{COUNTY}} CIRCUIT COURT / {{division}} DIVISION`

**Party terminology:** `Commonwealth of Kentucky v. {{defendant_name}}` (Kentucky is a Commonwealth)

**Mandatory forms:** Expungement petition, mediation agreement, HIV testing order, and others. Available as searchable fillable PDFs through the Kentucky Court of Justice portal.

**Free-form templates to author (~20):** Entry of Appearance, Motion for Continuance, Motion to Dismiss, Discovery requests, and standard criminal defense documents with Kentucky rule citations.

**Key differences from Missouri:** Uses "Commonwealth" (not "State"). Court of Justice umbrella. DUI admin through Kentucky Transportation Cabinet. ADE (Alcohol/Drug Education) program requirements.

**Estimated effort:** ~20 custom .docx templates + PDF form integrations + 120 county court entries (though Kentucky's unified system means less county-level variation).

---

### Oklahoma (Mandatory Appellate Forms — 4.0M pop, 12K attorneys)

**Court system:** District Courts (77 counties) and Court of Criminal Appeals (CCA). Trial courts partially unified.

**Caption format:** `IN THE DISTRICT COURT OF {{COUNTY}} COUNTY / STATE OF OKLAHOMA`

**Party terminology:** `State of Oklahoma v. {{defendant_name}}`

**Mandatory forms:** Rule 13 mandates 12+ forms including Uniform Plea of Guilty – Summary of Facts (Form 13.10), Application for Post Conviction Relief (Form 13.11), Uniform Judgment and Sentence (Form 13.8), and Affidavit in Forma Pauperis (Form 13.2). CCA forms are the most standardized; trial court forms vary more.

**Free-form templates to author (~25):** Entry of Appearance, Motion for Continuance, Motion to Dismiss, Discovery, and standard criminal defense documents. Trial-level filings are less standardized than appellate.

**Key differences from Missouri:** Strong appellate form standardization but more trial-court variation. DUI admin through Oklahoma DPS. Board of Tests for Alcohol and Drug Influence handles testing standards.

**Estimated effort:** ~25 custom .docx templates + ~12 PDF form integrations (Rule 13 forms) + 77 county court entries.

---

### Phase 1 Summary

| State | Custom .docx | PDF Forms | Court Entries | Unique Challenges |
|-------|-------------|-----------|---------------|-------------------|
| California | ~30 | ~7 | 58 | 28-line pleading paper; bail (not bond); DMV admin |
| Illinois | ~20 | TBD | 24 | Judicial circuit numbering; SOS admin |
| Iowa | ~15 | ~4 | 8 | Minimal — cleanest system |
| Minnesota | ~20 | ~5 | 10 | Word-format forms (advantage) |
| Kentucky | ~20 | TBD | 120 | "Commonwealth" terminology |
| Oklahoma | ~25 | ~12 | 77 | Strong appellate, weaker trial standardization |
| **Total** | **~130** | **~28+** | **~297** | |

## 5. Document Generation Pipeline

The multi-state pipeline adds jurisdiction resolution before template selection. Once the correct template is identified, generation follows the same patterns as the Missouri engine (for .docx) or routes through the new PDF form engine (for mandatory court forms).

### Request Flow

```
User Request
  "I need a motion for continuance in Los Angeles County"
    │
    ▼
┌─────────────────────────────────────┐
│  1. JURISDICTION RESOLUTION         │
│                                     │
│  Input: county, state (or court)    │
│  Lookup: courts table → jurisdiction│
│  Output: jurisdiction_id = 'CA'     │
│          court_id = 47 (LA Superior)│
│          formatting = {28-line...}  │
│          caption_template = '...'   │
│          party_term = 'People...'   │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│  2. DOCUMENT TYPE MAPPING           │
│                                     │
│  Input: "motion for continuance"    │
│  Lookup: document_type_taxonomy     │
│  Output: type_key =                 │
│    'motion_for_continuance'         │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│  3. TEMPLATE SELECTION              │
│                                     │
│  Query: jurisdiction_templates      │
│    WHERE jurisdiction_id = 'CA'     │
│    AND document_type_id = (match)   │
│                                     │
│  Also check: court_forms            │
│    WHERE jurisdiction_id = 'CA'     │
│    AND document_type_id = (match)   │
│                                     │
│  Decision: .docx template found     │
│    → route to DOCX pipeline         │
│  OR: mandatory PDF form found       │
│    → route to PDF pipeline          │
│  OR: both exist                     │
│    → prefer mandatory PDF if        │
│      is_mandatory = true            │
└──────────┬────────────┬─────────────┘
           │            │
     ┌─────┘            └─────┐
     ▼                        ▼
┌──────────────┐    ┌──────────────────┐
│ 4a. DOCX     │    │ 4b. PDF FORM     │
│ PIPELINE     │    │ PIPELINE         │
│              │    │                  │
│ Load .docx   │    │ Load PDF form    │
│ Apply format │    │ Map fields       │
│ Fill {{vars}}│    │ Fill fields      │
│ Normalize    │    │ Flatten          │
│ Output .docx │    │ Output .pdf      │
└──────┬───────┘    └────────┬─────────┘
       │                     │
       └──────────┬──────────┘
                  ▼
┌─────────────────────────────────────┐
│  5. ATTORNEY PROFILE AUTO-FILL      │
│                                     │
│  Lookup: attorney_bar_admissions    │
│    WHERE jurisdiction_id = 'CA'     │
│  Fill: bar_number, firm_address,    │
│    signature block per state        │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│  6. OUTPUT & STORAGE                │
│                                     │
│  Save to generated_documents table  │
│  Return file to user                │
│  Log generation in audit trail      │
└─────────────────────────────────────┘
```

### Jurisdiction Resolution Logic

The system determines jurisdiction from the information available, in priority order:

1. **Explicit court selection** — User picks from a dropdown (dashboard) or specifies in chat ("Los Angeles Superior Court"). Direct lookup in `courts` table.
2. **County + state** — User provides county and state. Lookup `courts` WHERE `county` = X AND `jurisdiction_id` = Y. If multiple courts exist (e.g., criminal vs. family division), prompt for division.
3. **State only** — User provides state but no county. System uses the firm's primary office location in that state as default, or prompts for county.
4. **Inferred from case data** — If generating from a case record (MyCase integration), the case's county and state are already known.

### Formatting Rule Application

Before filling placeholders, the .docx pipeline applies jurisdiction-specific formatting:

- **California:** Apply 28-line numbered pleading paper base template. Set margins (1" top, 0.5" bottom, 1" left, 0.5" right). Enable line numbering.
- **Missouri:** Standard formatting (no line numbering). Existing templates already have correct formatting baked in.
- **Other states:** Standard formatting unless the jurisdiction's `pleading_format` JSONB field specifies otherwise.

The formatting rules are stored in `jurisdictions.pleading_format` as JSONB, allowing per-state customization without code changes:

```json
{
  "line_numbered": true,
  "lines_per_page": 28,
  "margin_top": "1in",
  "margin_bottom": "0.5in",
  "margin_left": "1in",
  "margin_right": "0.5in",
  "font": "Times New Roman",
  "font_size": 12
}
```

### Caption Generation

Each jurisdiction has a `caption_template` string that uses the same `{{placeholder}}` syntax as document templates:

```
-- Missouri
IN THE {{court_type}} OF {{COUNTY}} COUNTY, MISSOURI

-- California
SUPERIOR COURT OF THE STATE OF CALIFORNIA
COUNTY OF {{COUNTY}}

-- Illinois
IN THE CIRCUIT COURT OF THE {{ordinal}} JUDICIAL CIRCUIT
{{COUNTY}} COUNTY, ILLINOIS

-- Iowa
IN THE IOWA DISTRICT COURT FOR {{COUNTY}} COUNTY

-- Minnesota
STATE OF MINNESOTA          DISTRICT COURT
{{ordinal}} JUDICIAL DISTRICT    COUNTY OF {{COUNTY}}

-- Kentucky
COMMONWEALTH OF KENTUCKY
{{COUNTY}} CIRCUIT COURT
{{division}} DIVISION

-- Oklahoma
IN THE DISTRICT COURT OF {{COUNTY}} COUNTY
STATE OF OKLAHOMA
```

The caption is generated from the template before being inserted into the document, ensuring consistent formatting per jurisdiction.

## 6. PDF Form Engine

This is a new capability. The Missouri engine only produces .docx files. The multi-state engine adds the ability to fill official court PDF forms programmatically.

### Technology

**Library:** `pypdf` (pure Python, no external binaries). Supports reading form fields, setting values, and flattening output. Already compatible with our Python environment — install via `pip install pypdf`.

**Why pypdf over alternatives:**
- Pure Python — no pdftk binary dependency, simpler deployment
- Handles standard AcroForm fields used in Judicial Council PDFs
- Active maintenance, good documentation
- Supports text fields, checkboxes, radio buttons, and date fields

### Form Lifecycle

```
1. ACQUISITION
   Download official PDF from state judiciary website
   Store in court_forms table with source_url and version_date

2. FIELD MAPPING
   Extract all fillable field names from the PDF
   Map each field to our universal placeholder keys
   Store mappings in court_form_field_mappings table

3. FILLING
   Load PDF from court_forms.file_content
   Build value dict from case data + attorney profile
   Apply field mappings to translate our keys → PDF field names
   Apply transforms (uppercase, date formatting)
   Fill all mapped fields

4. FLATTENING
   Flatten the filled PDF (make fields non-editable)
   Required by most e-filing systems
   Prevents accidental modification after generation

5. OUTPUT
   Return filled, flattened PDF to user
   Store in generated_documents table
```

### Field Extraction Tool

A CLI tool to extract and inspect fillable fields from a PDF form, used during the mapping setup process:

```bash
# Extract all field names from a Judicial Council form
python multi_state_engine.py pdf-fields CR-101.pdf

# Output:
# Field: "defendant_name_1"    Type: text     Page: 1
# Field: "case_number"         Type: text     Page: 1
# Field: "county"              Type: text     Page: 1
# Field: "plea_guilty"         Type: checkbox Page: 2
# Field: "plea_no_contest"     Type: checkbox Page: 2
# ...
```

### Field Mapping Example (CR-101 Plea Form)

```json
{
  "court_form_id": 1,
  "form_number": "CR-101",
  "mappings": [
    {"pdf_field_name": "defendant_name_1", "placeholder_key": "defendant_name", "field_type": "text"},
    {"pdf_field_name": "case_number",      "placeholder_key": "case_number",    "field_type": "text"},
    {"pdf_field_name": "county",           "placeholder_key": "county",         "field_type": "text", "transform": "uppercase"},
    {"pdf_field_name": "attorney_name",    "placeholder_key": "attorney_name",  "field_type": "text"},
    {"pdf_field_name": "bar_number",       "placeholder_key": "attorney_bar",   "field_type": "text"},
    {"pdf_field_name": "date_signed",      "placeholder_key": "date",           "field_type": "date", "transform": "date_format:MM/DD/YYYY"}
  ]
}
```

### Form Version Management

Court forms change periodically. The system needs to detect and handle updates:

- `court_forms.last_checked` tracks when we last verified the form is current
- `court_forms.source_url` stores the download URL for re-acquisition
- A scheduled task (`scheduler.py`) can periodically check source URLs for updated forms
- When a form is updated, the old version is deactivated and the new version is imported with fresh field mappings
- A `version_date` field stores the form's revision date (usually printed on the form itself)

## 7. Attorney Profile Expansion

The existing `attorneys` table stores one bar number per attorney. Multi-state practice requires bar admissions in multiple jurisdictions, potentially with different firm addresses per state.

### Current State

```
attorneys table:
  attorney_name, bar_number, email, phone, fax
  firm_name, firm_address, firm_city, firm_state, firm_zip
  is_primary
```

This works for single-state firms. For multi-state, we need:

### Multi-State Attorney Profile

**Bar admissions** move to `attorney_bar_admissions` (defined in Section 3). The existing `bar_number` field on `attorneys` is preserved for backward compatibility — it remains the attorney's primary bar number (Missouri for existing JCS attorneys).

**Firm addresses per jurisdiction** — A firm may have a Missouri office and a California office. When generating a California document, the signature block should use the California office address. New table:

```sql
CREATE TABLE firm_office_locations (
    id              SERIAL PRIMARY KEY,
    firm_id         TEXT NOT NULL,
    jurisdiction_id TEXT NOT NULL REFERENCES jurisdictions(id),
    office_name     TEXT,                      -- 'Main Office', 'California Office'
    address_line1   TEXT NOT NULL,
    address_line2   TEXT,
    city            TEXT NOT NULL,
    state           TEXT NOT NULL,
    zip             TEXT NOT NULL,
    phone           TEXT,
    fax             TEXT,
    is_primary      BOOLEAN DEFAULT false,     -- Primary office in this state
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(firm_id, jurisdiction_id, is_primary)
);
```

### Auto-Fill Logic Change

When generating a document, the attorney profile auto-fill resolves per jurisdiction:

1. Look up `attorney_bar_admissions` WHERE `attorney_id` = X AND `jurisdiction_id` = Y → get state-specific bar number
2. Look up `firm_office_locations` WHERE `firm_id` = X AND `jurisdiction_id` = Y → get state-specific office address
3. Fall back to the base `attorneys` record if no jurisdiction-specific data exists

This means a single attorney can have:
- Missouri bar #12345, office at 123 Main St, St. Louis, MO
- Illinois bar #67890, office at 456 State St, Chicago, IL
- Signature blocks auto-fill with the correct bar number and address for each state

## 8. Court Registry

The court registry is the system's knowledge of every court the platform can generate documents for. It stores addresses (for service of process and certificate of service), local rules, and local form requirements.

### Data Sources for Initial Population

| State | Source | Courts | Method |
|-------|--------|--------|--------|
| California | courts.ca.gov/find-a-court | 58 Superior Courts | Scrape court directory |
| Illinois | illinoiscourts.gov/circuit-court | 24 circuits | Scrape court directory |
| Iowa | iowacourts.gov/iowa-courts/district-court | 8 districts, 99 counties | Scrape court directory |
| Minnesota | mncourts.gov/Find-Courts | 10 districts, 87 counties | Scrape court directory |
| Kentucky | kycourts.gov/courts | 57 circuits, 120 counties | Scrape court directory |
| Oklahoma | oscn.net/applications/oscn/courts | 77 counties | Scrape OSCN directory |

### Court Registry Maintenance

Court addresses, judges, and divisions change. The registry needs periodic updates:

- **Scheduled check** — Monthly task (via `scheduler.py`) to flag courts whose data hasn't been verified in 90+ days
- **Community corrections** — When a firm reports an incorrect address or division, the update propagates to all firms in that jurisdiction
- **Version tracking** — `courts` table includes `last_verified` timestamp; admin dashboard shows stale entries

### Local Forms Detection

Some courts have their own mandatory forms beyond the statewide set. The `courts.has_local_forms` flag triggers additional form lookup when generating documents for that court:

- **California examples:** San Diego (CRM-133 DUI Addendum), Los Angeles (local criminal forms), San Francisco (SFACC series)
- **Other states:** Less common in unified systems, but the architecture supports it

Local forms are stored in `court_forms` with a non-NULL `court_id` to scope them to the specific court.

## 9. Migration Path

The Missouri engine continues running unchanged. Migration is additive — new tables and new code alongside the existing system, not replacing it.

### Phase 0: Foundation (No Impact on Missouri)

1. **Create new tables** — Run DDL for all tables defined in Section 3. No existing tables are modified yet.
2. **Seed `jurisdictions`** — Insert rows for MO, CA, IL, IA, MN, KY, OK with caption templates, party terminology, and formatting rules.
3. **Seed `document_type_taxonomy`** — Insert universal document types based on the 56 Missouri template types. These become the canonical reference.
4. **Create `multi_state_engine.py`** — New entry point, imports shared utilities from `document_chat.py` but does not modify it.

### Phase 1: Wire Missouri Into the New Model (Backward Compatible)

5. **Add `jurisdiction_id` to `templates`** — `ALTER TABLE templates ADD COLUMN jurisdiction_id TEXT DEFAULT 'MO'`. All existing rows get `'MO'`. The Missouri engine's queries don't include `jurisdiction_id` in their WHERE clauses, so they continue working as before.
6. **Populate `jurisdiction_templates`** — For each of the 56 active Missouri templates, insert a corresponding row in `jurisdiction_templates` with `jurisdiction_id = 'MO'`. This is a read-only mirror — the Missouri engine still reads from `templates` directly.
7. **Migrate attorney bar numbers** — For each attorney in `attorneys`, insert a row in `attorney_bar_admissions` with `jurisdiction_id = 'MO'` and the existing `bar_number`.
8. **Create firm jurisdictions** — For JCS Law, insert `firm_jurisdictions` with `jurisdiction_id = 'MO'` and `is_primary = true`.

After Phase 1, both the old and new engines can see Missouri data. The Missouri engine is unaware of the new tables. The multi-state engine can query Missouri templates through `jurisdiction_templates`.

### Phase 2: Add First New State (Iowa Recommended)

9. **Author Iowa templates** — Create ~15 .docx templates with Iowa caption format, rule citations, and party terminology.
10. **Download Iowa court forms** — Acquire fillable PDFs from iowacourts.gov, store in `court_forms`, map fields.
11. **Populate court registry** — Insert Iowa's 8 district courts and 99 county courts into `courts` table.
12. **End-to-end test** — Generate every Iowa document type, verify formatting, captions, and auto-fill.

### Phase 3: Scale to Remaining Phase 1 States

Repeat Phase 2 for California, Illinois, Minnesota, Kentucky, and Oklahoma. Each state is independent — they can be built in parallel by different team members.

### Rollback Plan

Because the migration is additive:
- Dropping the new tables reverts to the pre-migration state
- The Missouri engine never reads from new tables, so it's unaffected by any multi-state issues
- The `jurisdiction_id` column on `templates` defaults to `'MO'`, so removing it is a single `ALTER TABLE DROP COLUMN`

## 10. Implementation Roadmap

### Work Package 1: Data Model & Foundation (Weeks 1-3)

**Deliverables:**
- All new database tables created (Section 3 DDL)
- `jurisdictions` table seeded with 7 states (MO + 6 Phase 1)
- `document_type_taxonomy` seeded with universal document types
- Missouri data wired into new model (Phase 1 migration steps 5-8)
- `multi_state_engine.py` scaffold with jurisdiction resolution logic

**Dependencies:** None (greenfield)

**Validation:** Missouri engine continues to work unchanged. New tables queryable.

---

### Work Package 2: PDF Form Engine (Weeks 2-4)

**Deliverables:**
- `pypdf` integration for reading, filling, and flattening PDF forms
- CLI tool for extracting field names from PDF forms (`pdf-fields` command)
- `court_forms` and `court_form_field_mappings` tables populated for Iowa (proof-of-concept)
- End-to-end: fill an Iowa plea form from case data + attorney profile

**Dependencies:** WP1 (tables must exist)

**Validation:** Generate a filled, flattened Iowa plea form PDF. Open in Adobe Reader and verify all fields populated correctly.

---

### Work Package 3: Iowa — First State (Weeks 3-6)

**Deliverables:**
- ~15 Iowa .docx templates authored with correct captions, rules, terminology
- Iowa court forms downloaded and field-mapped
- Iowa court registry populated (8 districts, 99 counties)
- Iowa attorney profile support (bar admissions, office locations)
- Full test harness (equivalent to Missouri's 55-template test)

**Dependencies:** WP1, WP2

**Validation:** Generate every Iowa document type. All templates pass test harness. Documents open correctly in Word. PDFs open correctly in Adobe Reader.

**Why Iowa first:** Smallest template set (~15), cleanest unified system (8 districts), fastest path to proving the multi-state architecture works end-to-end.

---

### Work Package 4: California (Weeks 5-10)

**Deliverables:**
- ~30 California .docx templates with 28-line pleading paper format
- Judicial Council PDF forms (CR-101, CR-180, FW-001, etc.) downloaded and field-mapped
- 58 Superior Court registry entries
- California-specific attorney profile fields
- Full test harness

**Dependencies:** WP1, WP2, WP3 (patterns established in Iowa)

**Validation:** Generate every California document type including both .docx and PDF outputs. Verify 28-line pleading paper formatting. Verify Judicial Council forms fill correctly.

---

### Work Package 5: Illinois (Weeks 7-10)

**Deliverables:**
- ~20 Illinois .docx templates with judicial circuit numbering
- Illinois Supreme Court standardized forms integrated
- 24 circuit court registry entries
- Full test harness

**Dependencies:** WP1, WP2

**Validation:** Standard test harness pass. Verify circuit numbering in captions.

---

### Work Package 6: Minnesota, Kentucky, Oklahoma (Weeks 8-12)

**Deliverables:**
- ~20 Minnesota templates (leverage Word-format state forms as starting points)
- ~20 Kentucky templates (Commonwealth terminology)
- ~25 Oklahoma templates + Rule 13 mandatory forms
- Court registries for all three states
- Full test harnesses

**Dependencies:** WP1, WP2

**Validation:** Standard test harness pass for each state. All mandatory PDF forms fill correctly.

---

### Work Package 7: Dashboard & Onboarding (Weeks 10-14)

**Deliverables:**
- Multi-state jurisdiction selector in dashboard
- Per-state template browsing and Quick Generate panels
- Attorney profile management with multi-state bar admissions
- Firm onboarding flow: state selection → attorney setup → template provisioning
- Admin review interface for hybrid onboarding

**Dependencies:** WP3-WP6 (templates must exist to display)

**Validation:** End-to-end onboarding: create a new firm, select Iowa + California, set up attorneys with bar numbers in both states, generate documents in both jurisdictions.

---

### Work Package 8: Testing & QA (Weeks 12-16)

**Deliverables:**
- Cross-state test suite: same attorney generates equivalent documents in all 7 jurisdictions
- PDF form regression tests (detect when official forms are updated)
- Court registry accuracy audit
- Performance testing (template retrieval, PDF filling, concurrent generation)
- Documentation: updated CLAUDE.md, API docs, onboarding guide

**Dependencies:** All prior WPs

**Validation:** Full regression pass. No degradation to Missouri engine. All 7 states operational.

---

### Timeline Summary

```
Week:  1   2   3   4   5   6   7   8   9  10  11  12  13  14  15  16
WP1:  [████████████]
WP2:      [████████████]
WP3:          [████████████████]
WP4:                  [████████████████████████]
WP5:                          [████████████████]
WP6:                              [████████████████████]
WP7:                                          [████████████████████]
WP8:                                                      [████████████████████]
```

**Total estimated timeline: 16 weeks (4 months) from start to all 7 states operational.**

Iowa operational by week 6. California by week 10. All Phase 1 states by week 12. Dashboard and QA complete by week 16.
