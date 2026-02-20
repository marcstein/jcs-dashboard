"""
Re-import the Bond Assignment template with proper {{placeholder}} patterns.

Usage:
    python reimport_bond_template.py

This script:
1. Finds the existing "Bond Assignment" template in the database
2. Replaces its file_content with the properly-templated version
3. Updates the detected variables list
"""
import sys
import json
from pathlib import Path

# Ensure project root is in path
sys.path.insert(0, str(Path(__file__).parent))

from db.connection import get_connection
from db.documents import ensure_documents_tables


TEMPLATE_PATH = Path(__file__).parent / "data" / "templates" / "Bond_Assignment_Templated.docx"

EXPECTED_VARIABLES = [
    "defendant_name", "case_number", "county", "division",
    "bond_amount", "assignee_name", "assignee_address", "assignee_city_state_zip"
]


def reimport():
    """Update the Bond Assignment template in the database."""
    ensure_documents_tables()

    if not TEMPLATE_PATH.exists():
        print(f"ERROR: Template file not found: {TEMPLATE_PATH}")
        print("Run fix_bond_template.py first to create it.")
        sys.exit(1)

    new_content = TEMPLATE_PATH.read_bytes()
    print(f"Loaded template: {len(new_content):,} bytes")

    with get_connection() as conn:
        cur = conn.cursor()

        # Find the existing Bond Assignment template
        cur.execute(
            """SELECT id, name, variables, file_size
               FROM templates
               WHERE name ILIKE '%bond%assignment%'
               AND is_active = TRUE
               LIMIT 5"""
        )
        rows = cur.fetchall()

        if not rows:
            print("No existing Bond Assignment template found.")
            print("Importing as new template...")

            import hashlib
            file_hash = hashlib.sha256(new_content).hexdigest()

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
                RETURNING id
            """, (
                "jcs_law",
                "Bond Assignment",
                "Bond Assignment.docx",
                "form",
                "bond",
                json.dumps(EXPECTED_VARIABLES),
                json.dumps({
                    "defendant_name": {"source": "case", "field": "client.name"},
                    "case_number": {"source": "case", "field": "case_number"},
                    "county": {"source": "court", "field": "county"},
                    "division": {"source": "manual", "type": "text"},
                    "bond_amount": {"source": "manual", "type": "currency"},
                    "assignee_name": {"source": "firm", "field": "name"},
                    "assignee_address": {"source": "firm", "field": "address"},
                    "assignee_city_state_zip": {"source": "firm", "field": "city_state_zip"},
                }),
                json.dumps(["bond", "assignment", "cash bond"]),
                new_content,
                file_hash,
                len(new_content),
            ))
            new_id = cur.fetchone()[0]
            conn.commit()
            print(f"✓ Imported as new template ID: {new_id}")
            return

        # Show found templates
        print(f"\nFound {len(rows)} Bond Assignment template(s):")
        for row in rows:
            tid = row[0] if isinstance(row, tuple) else row['id']
            name = row[1] if isinstance(row, tuple) else row['name']
            size = row[3] if isinstance(row, tuple) else row['file_size']
            print(f"  ID {tid}: {name} ({size:,} bytes)")

        # Update each matching template
        import hashlib
        file_hash = hashlib.sha256(new_content).hexdigest()

        for row in rows:
            tid = row[0] if isinstance(row, tuple) else row['id']
            name = row[1] if isinstance(row, tuple) else row['name']

            cur.execute("""
                UPDATE templates SET
                    file_content = %s,
                    file_hash = %s,
                    file_size = %s,
                    variables = %s,
                    variable_mappings = %s
                WHERE id = %s
            """, (
                new_content,
                file_hash,
                len(new_content),
                json.dumps(EXPECTED_VARIABLES),
                json.dumps({
                    "defendant_name": {"source": "case", "field": "client.name"},
                    "case_number": {"source": "case", "field": "case_number"},
                    "county": {"source": "court", "field": "county"},
                    "division": {"source": "manual", "type": "text"},
                    "bond_amount": {"source": "manual", "type": "currency"},
                    "assignee_name": {"source": "firm", "field": "name"},
                    "assignee_address": {"source": "firm", "field": "address"},
                    "assignee_city_state_zip": {"source": "firm", "field": "city_state_zip"},
                }),
                tid,
            ))
            print(f"  ✓ Updated template ID {tid}: {name}")

        conn.commit()
        print("\n✓ All Bond Assignment templates updated successfully!")
        print(f"  Variables: {', '.join(EXPECTED_VARIABLES)}")


if __name__ == "__main__":
    reimport()
