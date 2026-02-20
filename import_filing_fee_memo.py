"""
Import the unified Filing Fee Memo template into the database.

Usage:
    python import_filing_fee_memo.py

This script:
1. Deactivates any existing Filing Fee Memo templates in the database
2. Imports the new unified template with proper {{placeholder}} variables
3. Sets up variable mappings for attorney profile auto-fill
"""
import sys
import json
import hashlib
from pathlib import Path

# Ensure project root is in path
sys.path.insert(0, str(Path(__file__).parent))

from db.connection import get_connection
from db.documents import ensure_documents_tables


TEMPLATE_PATH = Path(__file__).parent / "data" / "templates" / "Filing_Fee_Memo_Unified.docx"

# Variables the user must provide per document
CASE_VARIABLES = [
    "county", "petitioner_name", "case_number", "respondent_name",
    "filing_fee", "signing_attorney", "signing_attorney_bar",
    "signing_attorney_email", "party_role", "service_signatory",
]

# Variables auto-filled from attorney profile
PROFILE_VARIABLES = [
    "firm_name", "attorney_name", "attorney_bar",
    "firm_address", "firm_city_state_zip",
    "firm_phone", "firm_fax", "attorney_email",
]

ALL_VARIABLES = CASE_VARIABLES + PROFILE_VARIABLES


def import_template():
    """Import the unified Filing Fee Memo template."""
    ensure_documents_tables()

    if not TEMPLATE_PATH.exists():
        print(f"ERROR: Template file not found: {TEMPLATE_PATH}")
        sys.exit(1)

    new_content = TEMPLATE_PATH.read_bytes()
    file_hash = hashlib.sha256(new_content).hexdigest()
    print(f"Loaded template: {len(new_content):,} bytes")

    with get_connection() as conn:
        cur = conn.cursor()

        # Deactivate any existing Filing Fee Memo templates
        cur.execute(
            """UPDATE templates
               SET is_active = FALSE
               WHERE name ILIKE '%filing fee memo%'
               AND is_active = TRUE
               RETURNING id, name"""
        )
        deactivated = cur.fetchall()
        if deactivated:
            print(f"\nDeactivated {len(deactivated)} old template(s):")
            for row in deactivated:
                tid = row[0] if isinstance(row, tuple) else row['id']
                name = row[1] if isinstance(row, tuple) else row['name']
                print(f"  - ID {tid}: {name}")
        else:
            print("\nNo existing Filing Fee Memo templates found.")

        # Insert the unified template
        variable_mappings = {
            # Case-specific (user provides)
            "county": {"source": "court", "field": "county"},
            "petitioner_name": {"source": "case", "field": "client.name"},
            "case_number": {"source": "case", "field": "case_number"},
            "respondent_name": {"source": "manual", "type": "text",
                                "description": "Opposing party (e.g., Department of Revenue, Director of Revenue)"},
            "filing_fee": {"source": "manual", "type": "currency",
                           "description": "Filing fee amount (e.g., $50.00)"},
            "signing_attorney": {"source": "manual", "type": "text",
                                 "description": "Attorney signing the memo"},
            "signing_attorney_bar": {"source": "manual", "type": "text",
                                     "description": "Signing attorney bar number"},
            "signing_attorney_email": {"source": "manual", "type": "text",
                                       "description": "Signing attorney email"},
            "party_role": {"source": "manual", "type": "text",
                           "description": "Party role (e.g., Petitioner, Defendant)"},
            "service_signatory": {"source": "manual", "type": "text",
                                  "description": "Person signing certificate of service"},
            # Auto-filled from attorney profile
            "firm_name": {"source": "firm", "field": "name"},
            "attorney_name": {"source": "attorney", "field": "name"},
            "attorney_bar": {"source": "attorney", "field": "bar_number"},
            "firm_address": {"source": "firm", "field": "address"},
            "firm_city_state_zip": {"source": "firm", "field": "city_state_zip"},
            "firm_phone": {"source": "firm", "field": "phone"},
            "firm_fax": {"source": "firm", "field": "fax"},
            "attorney_email": {"source": "attorney", "field": "email"},
        }

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
            "Filing Fee Memo",
            "Filing_Fee_Memo_Unified.docx",
            "pleading",
            "filing_fee",
            json.dumps(ALL_VARIABLES),
            json.dumps(variable_mappings),
            json.dumps(["filing fee", "memo", "fee", "filing"]),
            new_content,
            file_hash,
            len(new_content),
        ))
        new_id = cur.fetchone()[0]
        conn.commit()

        print(f"\n✓ Imported unified Filing Fee Memo as template ID: {new_id}")
        print(f"  Case variables (user provides): {', '.join(CASE_VARIABLES)}")
        print(f"  Profile variables (auto-fill):  {', '.join(PROFILE_VARIABLES)}")


if __name__ == "__main__":
    import_template()
