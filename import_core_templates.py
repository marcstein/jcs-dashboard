#!/usr/bin/env python3
"""
Import all core processed templates to PostgreSQL.

Run this on the production server:
    cd /home/jcs/Legal
    source .venv/bin/activate
    python3 import_core_templates.py
"""

import os
from pathlib import Path
import psycopg2

# Read .env
env_path = Path(__file__).parent / '.env'
if env_path.exists():
    with open(env_path) as f:
        for line in f:
            if '=' in line and not line.startswith('#'):
                key, val = line.strip().split('=', 1)
                os.environ[key] = val

# Templates to import: (filename, display_name, category)
TEMPLATES = [
    ('Potential_Prosecution_Letter.docx', 'Potential Prosecution Letter', 'letter'),
    ('Preservation_Letter.docx', 'Preservation Letter', 'letter'),
    ('Entry_of_Appearance_Single.docx', 'Entry of Appearance - Single Attorney', 'pleading'),
    ('Entry_of_Appearance_Multi.docx', 'Entry of Appearance - Multiple Attorneys', 'pleading'),
    ('Entry_Arraignment_Waiver_NG_Plea.docx', 'Entry of Appearance, Waiver of Arraignment, Plea of Not Guilty', 'pleading'),
    ('Motion_for_Continuance_Municipal.docx', 'Motion for Continuance - Municipal', 'motion'),
    ('Motion_for_Continuance_Circuit.docx', 'Motion for Continuance - Circuit', 'motion'),
    ('Request_for_Discovery_Municipal.docx', 'Request for Discovery - Municipal', 'discovery'),
    ('Request_for_Discovery_Circuit.docx', 'Request for Discovery - Circuit', 'discovery'),
    ('Bond_Assignment.docx', 'Bond Assignment', 'pleading'),
]

FIRM_ID = 'jcs_law'


def main():
    # Find templates directory
    templates_dir = Path(__file__).parent / 'templates_processed'

    if not templates_dir.exists():
        print(f"ERROR: Templates directory not found: {templates_dir}")
        return

    print(f"Templates directory: {templates_dir}")
    print(f"Firm ID: {FIRM_ID}")
    print()

    # Connect to PostgreSQL
    print("Connecting to PostgreSQL...")
    conn = psycopg2.connect(
        host=os.environ.get('PG_HOST'),
        port=os.environ.get('PG_PORT', '25060'),
        database=os.environ.get('PG_DATABASE', 'defaultdb'),
        user=os.environ.get('PG_USER', 'doadmin'),
        password=os.environ.get('PG_PASSWORD', ''),
        sslmode=os.environ.get('PG_SSLMODE', 'require')
    )
    print("✓ Connected\n")

    cur = conn.cursor()

    imported = 0
    updated = 0
    errors = []

    for filename, display_name, category in TEMPLATES:
        file_path = templates_dir / filename

        if not file_path.exists():
            errors.append(f"{filename}: File not found")
            continue

        # Read file content
        with open(file_path, 'rb') as f:
            content = f.read()

        # Check if template exists
        cur.execute("""
            SELECT id FROM templates
            WHERE firm_id = %s AND name = %s
        """, (FIRM_ID, display_name))
        existing = cur.fetchone()

        if existing:
            # Update existing
            cur.execute("""
                UPDATE templates
                SET file_content = %s, category = %s, is_active = TRUE
                WHERE id = %s
            """, (psycopg2.Binary(content), category, existing[0]))
            print(f"✓ Updated: {display_name} (ID: {existing[0]})")
            updated += 1
        else:
            # Insert new
            cur.execute("""
                INSERT INTO templates (firm_id, name, category, jurisdiction, file_content, is_active)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (FIRM_ID, display_name, category, 'Missouri', psycopg2.Binary(content), True))
            new_id = cur.fetchone()[0]
            print(f"✓ Inserted: {display_name} (ID: {new_id})")
            imported += 1

    conn.commit()
    conn.close()

    print()
    print("="*50)
    print(f"Summary: {imported} imported, {updated} updated, {len(errors)} errors")

    if errors:
        print("\nErrors:")
        for err in errors:
            print(f"  - {err}")

    print("\n✓ Done! Restart the service to apply changes:")
    print("  sudo systemctl restart mycase-dashboard")


if __name__ == '__main__':
    main()
