#!/usr/bin/env python3
"""
Import a generic template into PostgreSQL.

Usage:
    python import_generic_template.py Waiver_of_Arraignment_Generic.docx "Waiver of Arraignment"
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

def main():
    if len(sys.argv) < 3:
        print("Usage: python import_generic_template.py <file.docx> <template_name>")
        print("Example: python import_generic_template.py Waiver_of_Arraignment_Generic.docx 'Waiver of Arraignment'")
        sys.exit(1)

    file_path = Path(sys.argv[1])
    template_name = sys.argv[2]
    firm_id = sys.argv[3] if len(sys.argv) > 3 else "jcs_law"

    if not file_path.exists():
        print(f"Error: File not found: {file_path}")
        sys.exit(1)

    # Read template file
    with open(file_path, 'rb') as f:
        content = f.read()

    print(f"Template: {template_name}")
    print(f"File: {file_path} ({len(content)} bytes)")
    print(f"Firm: {firm_id}")

    # Connect to PostgreSQL
    import psycopg2

    conn = psycopg2.connect(
        host=os.getenv('PG_HOST'),
        port=os.getenv('PG_PORT', '25060'),
        database=os.getenv('PG_DATABASE', 'defaultdb'),
        user=os.getenv('PG_USER', 'doadmin'),
        password=os.getenv('PG_PASSWORD', ''),
        sslmode=os.getenv('PG_SSLMODE', 'require')
    )
    print("✓ Connected to PostgreSQL")

    cur = conn.cursor()

    # Check if template already exists
    cur.execute("SELECT id FROM templates WHERE name = %s AND firm_id = %s",
                (template_name, firm_id))
    existing = cur.fetchone()

    if existing:
        # Update existing
        cur.execute("""
            UPDATE templates
            SET file_content = %s
            WHERE id = %s
        """, (psycopg2.Binary(content), existing[0]))
        print(f"✓ Updated existing template (id={existing[0]})")
    else:
        # Insert new
        cur.execute("""
            INSERT INTO templates (firm_id, name, category, jurisdiction, file_content, is_active)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (firm_id, template_name, 'criminal', 'Missouri', psycopg2.Binary(content), True))
        new_id = cur.fetchone()[0]
        print(f"✓ Inserted new template (id={new_id})")

    conn.commit()
    conn.close()
    print("✓ Done!")


if __name__ == "__main__":
    main()
