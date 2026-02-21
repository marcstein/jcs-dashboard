"""
Import consolidated templates into the database.

Usage:
    python import_consolidated_templates.py

Templates imported (Batch 1 - ~197 variants replaced):
  1. Entry of Appearance (State) - replaces ~30 county variants
  2. Entry of Appearance (Muni) - replaces ~76 municipal variants
  3. Motion for Continuance - replaces ~34 county/muni variants
  4. Request for Discovery - replaces ~36 county/muni variants
  5. Potential Prosecution Letter - replaces ~21 county/muni variants

Templates imported (Batch 2 - ~792 variants replaced):
  6. Preservation/Supplemental Discovery Letter - replaces ~164 variants
  7. Preservation Letter - replaces ~105 variants
  8. Motion to Recall Warrant - replaces ~70 variants
  9. Proposed Stay Order - replaces ~54 variants
  10. Disposition Letter to Client - replaces ~399 variants
"""
import sys
import json
import hashlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from db.connection import get_connection
from db.documents import ensure_documents_tables


TEMPLATE_DIR = Path(__file__).parent / "data" / "templates"

# ── Template definitions ──────────────────────────────────────────────

TEMPLATES = [
    {
        "name": "Entry of Appearance (State)",
        "filename": "Entry_of_Appearance_State.docx",
        "category": "pleading",
        "subcategory": "entry_of_appearance",
        "tags": ["entry", "appearance", "state", "circuit court"],
        "deactivate_pattern": None,  # Don't deactivate old ones yet
        "case_variables": [
            "county", "plaintiff_name", "defendant_name", "case_number",
            "attorney_names", "signing_attorney",
            "second_attorney_name", "second_attorney_bar", "second_attorney_email",
            "service_date", "service_signatory",
        ],
        "profile_variables": [
            "firm_name", "attorney_name", "attorney_bar", "attorney_email",
            "firm_address", "firm_city_state_zip", "firm_phone", "firm_fax",
        ],
    },
    {
        "name": "Entry of Appearance (Muni)",
        "filename": "Entry_of_Appearance_Muni.docx",
        "category": "pleading",
        "subcategory": "entry_of_appearance",
        "tags": ["entry", "appearance", "municipal", "muni"],
        "deactivate_pattern": None,
        "case_variables": [
            "city", "defendant_name", "case_number",
            "attorney_names", "signing_attorney",
            "second_attorney_name", "second_attorney_bar", "second_attorney_email",
            "prosecutor_name", "prosecutor_address", "prosecutor_city_state_zip",
            "service_date", "service_signatory",
        ],
        "profile_variables": [
            "firm_name", "attorney_name", "attorney_bar", "attorney_email",
            "firm_address", "firm_city_state_zip", "firm_phone", "firm_fax",
        ],
    },
    {
        "name": "Motion for Continuance",
        "filename": "Motion_for_Continuance.docx",
        "category": "motion",
        "subcategory": "continuance",
        "tags": ["motion", "continuance", "continue", "mtc"],
        "deactivate_pattern": None,
        "case_variables": [
            "county", "defendant_name", "case_number",
            "hearing_date", "continuance_reason",
            "attorney_names", "signing_attorney",
            "second_attorney_name", "second_attorney_bar", "second_attorney_email",
            "service_date", "service_signatory",
        ],
        "profile_variables": [
            "firm_name", "attorney_name", "attorney_bar", "attorney_email",
            "firm_address", "firm_city_state_zip", "firm_phone", "firm_fax",
        ],
    },
    {
        "name": "Request for Discovery",
        "filename": "Request_for_Discovery.docx",
        "category": "discovery",
        "subcategory": "request",
        "tags": ["discovery", "request", "rog", "interrogatories"],
        "deactivate_pattern": None,
        "case_variables": [
            "county", "defendant_name", "case_number",
            "signing_attorney",
            "second_attorney_name", "second_attorney_bar", "second_attorney_email",
            "service_date", "service_signatory",
        ],
        "profile_variables": [
            "firm_name", "attorney_email",
            "firm_address", "firm_city_state_zip", "firm_phone", "firm_fax",
        ],
    },
    {
        "name": "Potential Prosecution Letter",
        "filename": "Potential_Prosecution_Letter.docx",
        "category": "letter",
        "subcategory": "prosecution",
        "tags": ["letter", "prosecution", "potential", "representation"],
        "deactivate_pattern": None,
        "case_variables": [
            "letter_date", "client_name",
            "prosecutor_name", "prosecutor_title", "court_name",
            "prosecutor_address_line1", "prosecutor_address_line2",
            "prosecutor_city_state_zip", "prosecutor_salutation",
            "initials",
        ],
        "profile_variables": [
            "attorney_name", "attorney_bar", "attorney_email",
            "firm_address_line1", "firm_address_line2",
            "firm_city_state_zip", "firm_phone", "firm_fax",
        ],
    },
    # ── Batch 2 templates ────────────────────────────────────────────
    {
        "name": "Preservation/Supplemental Discovery Letter",
        "filename": "Preservation_Supplemental_Discovery_Letter.docx",
        "category": "letter",
        "subcategory": "preservation",
        "tags": ["preservation", "supplemental", "discovery", "evidence", "video"],
        "deactivate_pattern": None,
        "case_variables": [
            "letter_date", "agency_name", "agency_attention",
            "agency_address", "agency_city_state_zip",
            "defendant_name", "defendant_dob", "charges",
            "arrest_date", "ticket_number", "arresting_officer",
            "defendant_honorific", "defendant_last_name", "defendant_pronoun",
            "initials",
        ],
        "profile_variables": [
            "attorney_name", "attorney_bar", "attorney_email",
            "second_attorney_name", "second_attorney_bar", "second_attorney_email",
            "firm_address", "firm_city_state_zip", "firm_phone",
        ],
    },
    {
        "name": "Preservation Letter",
        "filename": "Preservation_Letter.docx",
        "category": "letter",
        "subcategory": "preservation",
        "tags": ["preservation", "evidence", "video", "booking"],
        "deactivate_pattern": None,
        "case_variables": [
            "letter_date", "agency_name", "agency_attention",
            "agency_address", "agency_city_state_zip",
            "defendant_name", "defendant_dob", "charges",
            "arrest_date", "ticket_number", "arresting_officer",
            "initials",
        ],
        "profile_variables": [
            "attorney_name", "attorney_bar", "attorney_email",
            "second_attorney_name", "second_attorney_bar", "second_attorney_email",
            "firm_address", "firm_city_state_zip", "firm_phone",
        ],
    },
    {
        "name": "Motion to Recall Warrant",
        "filename": "Motion_to_Recall_Warrant.docx",
        "category": "motion",
        "subcategory": "recall_warrant",
        "tags": ["motion", "recall", "warrant", "muni"],
        "deactivate_pattern": None,
        "case_variables": [
            "county", "defendant_name", "case_number",
            "signing_attorney",
            "second_attorney_name", "second_attorney_bar", "second_attorney_email",
            "service_date", "service_signatory",
        ],
        "profile_variables": [
            "firm_name", "attorney_name", "attorney_bar", "attorney_email",
            "firm_address", "firm_city_state_zip", "firm_phone", "firm_fax",
        ],
    },
    {
        "name": "Proposed Stay Order",
        "filename": "Proposed_Stay_Order.docx",
        "category": "motion",
        "subcategory": "stay_order",
        "tags": ["stay", "order", "dor", "pfr", "refusal", "driving"],
        "deactivate_pattern": None,
        "case_variables": [
            "county", "petitioner_name", "dln", "dob", "case_number",
            "arrest_date",
            "respondent_attorney_name", "respondent_attorney_bar",
            "judge_name", "judge_title", "division",
            "order_month", "order_year",
        ],
        "profile_variables": [
            "attorney_name", "attorney_full_name", "attorney_bar",
        ],
    },
    {
        "name": "Disposition Letter to Client",
        "filename": "Disposition_Letter_to_Client.docx",
        "category": "letter",
        "subcategory": "disposition",
        "tags": ["disposition", "dispo", "letter", "client", "result", "plea"],
        "deactivate_pattern": None,
        "case_variables": [
            "letter_date", "client_name", "client_first_name",
            "client_address", "client_city_state_zip",
            "disposition_paragraph", "court_name",
            "court_address", "court_city_state_zip",
            "payment_instructions", "payment_deadline",
            "initials",
        ],
        "profile_variables": [
            "attorney_name", "attorney_email",
            "firm_address", "firm_city_state_zip", "firm_phone",
        ],
    },
]


def import_template(tmpl_def):
    """Import a single consolidated template."""
    filepath = TEMPLATE_DIR / tmpl_def["filename"]
    if not filepath.exists():
        print(f"  ERROR: {filepath} not found, skipping")
        return None

    content = filepath.read_bytes()
    file_hash = hashlib.sha256(content).hexdigest()
    all_vars = tmpl_def["case_variables"] + tmpl_def["profile_variables"]

    # Build variable_mappings
    variable_mappings = {}
    for v in tmpl_def["case_variables"]:
        variable_mappings[v] = {"source": "manual", "type": "text"}
    for v in tmpl_def["profile_variables"]:
        if v.startswith("firm_"):
            variable_mappings[v] = {"source": "firm", "field": v}
        elif v.startswith("attorney_"):
            variable_mappings[v] = {"source": "attorney", "field": v}

    with get_connection() as conn:
        cur = conn.cursor()

        # Optionally deactivate old variants
        if tmpl_def.get("deactivate_pattern"):
            cur.execute(
                """UPDATE templates SET is_active = FALSE
                   WHERE name ILIKE %s AND is_active = TRUE
                   RETURNING id, name""",
                (tmpl_def["deactivate_pattern"],)
            )
            deactivated = cur.fetchall()
            if deactivated:
                print(f"  Deactivated {len(deactivated)} old template(s)")

        cur.execute("""
            INSERT INTO templates (
                firm_id, name, original_filename, category, subcategory,
                variables, variable_mappings, tags,
                file_content, file_hash, file_size, is_active
            ) VALUES (
                %s, %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s, TRUE
            )
            ON CONFLICT (firm_id, name) DO UPDATE SET
                original_filename = EXCLUDED.original_filename,
                category = EXCLUDED.category,
                subcategory = EXCLUDED.subcategory,
                variables = EXCLUDED.variables,
                variable_mappings = EXCLUDED.variable_mappings,
                tags = EXCLUDED.tags,
                file_content = EXCLUDED.file_content,
                file_hash = EXCLUDED.file_hash,
                file_size = EXCLUDED.file_size,
                is_active = TRUE
            RETURNING id
        """, (
            "jcs_law",
            tmpl_def["name"],
            tmpl_def["filename"],
            tmpl_def["category"],
            tmpl_def["subcategory"],
            json.dumps(all_vars),
            json.dumps(variable_mappings),
            json.dumps(tmpl_def["tags"]),
            content,
            file_hash,
            len(content),
        ))
        row = cur.fetchone()
        new_id = row['id'] if isinstance(row, dict) else row[0]
        conn.commit()

    return new_id


def main():
    ensure_documents_tables()
    print("Importing consolidated templates...\n")

    for tmpl_def in TEMPLATES:
        filepath = TEMPLATE_DIR / tmpl_def["filename"]
        size = filepath.stat().st_size if filepath.exists() else 0
        print(f"[{tmpl_def['name']}] ({size:,} bytes)")
        tid = import_template(tmpl_def)
        if tid:
            print(f"  -> Template ID: {tid}")
            print(f"     Case vars: {len(tmpl_def['case_variables'])}, "
                  f"Profile vars: {len(tmpl_def['profile_variables'])}")
        print()

    print("Done! All templates imported.")


if __name__ == "__main__":
    main()
