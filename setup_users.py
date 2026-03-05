#!/usr/bin/env python3
"""
Setup dashboard user accounts for JCS Law Firm.

Creates:
  - Attorney logins (one per lead_attorney_name with active cases)
  - Collections login for Melissa Scarlett
  - Updates admin password

Run: python setup_users.py [--firm-id jcs_law] [--dry-run]
"""
import os
import sys
import secrets
import string
import argparse

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from db.connection import get_connection
from dashboard.auth import create_user, init_users_table, update_user_password
import psycopg2.extensions


def generate_password(length=12):
    """Generate a random password."""
    chars = string.ascii_letters + string.digits + "!@#$%"
    return ''.join(secrets.choice(chars) for _ in range(length))


def username_from_name(full_name: str) -> str:
    """Convert 'John Schleiffarth' to 'john.schleiffarth'."""
    parts = full_name.strip().lower().split()
    if len(parts) >= 2:
        return f"{parts[0]}.{parts[-1]}"
    return parts[0] if parts else "unknown"


def get_active_attorneys(firm_id: str) -> list:
    """Get all attorneys with open cases."""
    with get_connection() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extensions.cursor)
        cur.execute("""
            SELECT DISTINCT lead_attorney_name, COUNT(*) as case_count
            FROM cached_cases
            WHERE firm_id = %s
              AND lead_attorney_name IS NOT NULL
              AND lead_attorney_name != ''
              AND status = 'open'
            GROUP BY lead_attorney_name
            ORDER BY lead_attorney_name
        """, (firm_id,))
        return [(row[0], row[1]) for row in cur.fetchall()]


def main():
    parser = argparse.ArgumentParser(description="Setup dashboard user accounts")
    parser.add_argument("--firm-id", default=os.environ.get("FIRM_ID", "jcs_law"),
                        help="Firm ID (default: from FIRM_ID env var or 'jcs_law')")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be created without making changes")
    parser.add_argument("--admin-password", default=None,
                        help="New admin password (generates random if not specified)")
    args = parser.parse_args()

    firm_id = args.firm_id
    print(f"\n{'='*60}")
    print(f"  LawMetrics.ai User Setup — firm_id: {firm_id}")
    print(f"{'='*60}\n")

    # Initialize table (adds attorney_name column if missing)
    if not args.dry_run:
        init_users_table()

    # 1. Get active attorneys
    attorneys = get_active_attorneys(firm_id)
    print(f"Found {len(attorneys)} attorneys with open cases:\n")

    credentials = []

    for attorney_name, case_count in attorneys:
        username = username_from_name(attorney_name)
        password = generate_password()
        credentials.append({
            'role': 'attorney',
            'name': attorney_name,
            'username': username,
            'password': password,
            'cases': case_count,
        })

        if not args.dry_run:
            create_user(
                username=username,
                password=password,
                role='attorney',
                firm_id=firm_id,
                attorney_name=attorney_name,
            )
        print(f"  [attorney] {attorney_name:30s} → username: {username:25s} ({case_count} open cases)")

    # 2. Collections login for Melissa
    melissa_password = generate_password()
    credentials.append({
        'role': 'collections',
        'name': 'Melissa Scarlett',
        'username': 'melissa.scarlett',
        'password': melissa_password,
        'cases': 'all',
    })
    if not args.dry_run:
        create_user(
            username='melissa.scarlett',
            password=melissa_password,
            role='collections',
            firm_id=firm_id,
            attorney_name=None,  # Full access
        )
    print(f"\n  [collections] Melissa Scarlett         → username: melissa.scarlett")

    # 3. Update admin password
    admin_password = args.admin_password or generate_password(16)
    if not args.dry_run:
        # Ensure admin user exists with updated password
        create_user(
            username='admin',
            password=admin_password,
            role='admin',
            firm_id=firm_id,
            attorney_name=None,
        )
    print(f"\n  [admin] Admin account                  → username: admin (password updated)")

    # Print credential table
    print(f"\n{'='*60}")
    print("  CREDENTIALS (save these — passwords are not recoverable)")
    print(f"{'='*60}\n")

    print(f"  {'Role':12s} {'Name':30s} {'Username':25s} Password")
    print(f"  {'-'*12} {'-'*30} {'-'*25} {'-'*16}")
    print(f"  {'admin':12s} {'Admin':30s} {'admin':25s} {admin_password}")
    print(f"  {'collections':12s} {'Melissa Scarlett':30s} {'melissa.scarlett':25s} {melissa_password}")
    for c in credentials:
        if c['role'] == 'attorney':
            print(f"  {'attorney':12s} {c['name']:30s} {c['username']:25s} {c['password']}")

    print(f"\n  Firm ID for login: {firm_id}")
    if args.dry_run:
        print("\n  *** DRY RUN — no changes made ***")
    else:
        print(f"\n  {len(credentials)} users created/updated successfully.")
    print()


if __name__ == "__main__":
    main()
