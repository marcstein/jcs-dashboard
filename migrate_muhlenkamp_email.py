#!/usr/bin/env python3
"""
Migration: Set field override for Anthony Muhlenkamp email change.

Replaces amuhlenkamp@mbstlcriminaldefense.com → tony@jcslaw.com
in cached_staff, and records a field_override so the change persists
through future cache syncs.

Safe to re-run (uses upsert logic).

Usage:
    cd /opt/jcs-mycase
    export $(grep -v '^#' .env | xargs)
    .venv/bin/python migrate_muhlenkamp_email.py
"""
import os
import sys

# Ensure DATABASE_URL is set
if not os.environ.get("DATABASE_URL"):
    print("ERROR: DATABASE_URL not set. Export .env first.")
    sys.exit(1)

from db.connection import get_connection
from db.cache import ensure_cache_tables, set_field_override


OLD_EMAIL = "amuhlenkamp@mbstlcriminaldefense.com"
NEW_EMAIL = "tony@jcslaw.com"
STAFF_NAME = "Anthony Muhlenkamp"


def main():
    ensure_cache_tables()  # Creates field_overrides table if needed

    with get_connection() as conn:
        cur = conn.cursor()

        # Find Anthony Muhlenkamp's staff record and firm_id
        cur.execute(
            "SELECT firm_id, id, email FROM cached_staff WHERE name = %s",
            (STAFF_NAME,),
        )
        row = cur.fetchone()
        if not row:
            # Try by old email
            cur.execute(
                "SELECT firm_id, id, email FROM cached_staff WHERE email = %s",
                (OLD_EMAIL,),
            )
            row = cur.fetchone()

        if not row:
            # Try by new email (already migrated)
            cur.execute(
                "SELECT firm_id, id, email FROM cached_staff WHERE email = %s",
                (NEW_EMAIL,),
            )
            row = cur.fetchone()

        if not row:
            print(f"ERROR: Could not find staff record for '{STAFF_NAME}' or '{OLD_EMAIL}'")
            sys.exit(1)

        if isinstance(row, dict):
            firm_id, staff_id, current_email = row["firm_id"], row["id"], row["email"]
        else:
            firm_id, staff_id, current_email = row

        print(f"Found: {STAFF_NAME} (ID: {staff_id}, firm: {firm_id})")
        print(f"Current email: {current_email}")

        # 1. Record the override so it persists through syncs
        set_field_override(
            firm_id=firm_id,
            entity_type="staff",
            entity_id=staff_id,
            field_name="email",
            override_value=NEW_EMAIL,
            original_value=OLD_EMAIL,
            reason="Attorney moved from MBS to JCS Law. Email changed to tony@jcslaw.com.",
            updated_by="migration_script",
        )
        print(f"✓ Override recorded: email → {NEW_EMAIL}")

        # 2. Update the cached record immediately
        cur.execute(
            "UPDATE cached_staff SET email = %s WHERE firm_id = %s AND id = %s",
            (NEW_EMAIL, firm_id, staff_id),
        )
        print(f"✓ cached_staff updated ({cur.rowcount} row)")

        # 3. Also update data_json if it contains the old email
        cur.execute(
            """UPDATE cached_staff
               SET data_json = REPLACE(data_json, %s, %s)
               WHERE firm_id = %s AND id = %s
                 AND data_json LIKE %s""",
            (OLD_EMAIL, NEW_EMAIL, firm_id, staff_id, f"%{OLD_EMAIL}%"),
        )
        if cur.rowcount:
            print(f"✓ data_json patched ({cur.rowcount} row)")

    print("\nDone. The email override will persist through future cache syncs.")


if __name__ == "__main__":
    main()
