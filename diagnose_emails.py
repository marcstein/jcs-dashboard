#!/usr/bin/env python3
"""Diagnostic script to find where client emails are stored."""
import os, json, sys
sys.path.insert(0, os.path.dirname(__file__))
from dotenv import load_dotenv
load_dotenv()
from db.connection import get_connection

firm_id = os.environ.get("FIRM_ID", "jcs_law")

with get_connection() as conn:
    cur = conn.cursor()

    # 1. Check cached_contacts
    cur.execute("SELECT COUNT(*), COUNT(NULLIF(email, '')) FROM cached_contacts WHERE firm_id = %s", (firm_id,))
    r = cur.fetchone()
    print(f"\n=== cached_contacts (firm_id={firm_id}) ===")
    print(f"  Total rows: {r[0]}")
    print(f"  Rows with non-empty email: {r[1]}")

    # 2. Check cached_clients
    cur.execute("SELECT COUNT(*), COUNT(NULLIF(email, '')) FROM cached_clients WHERE firm_id = %s", (firm_id,))
    r = cur.fetchone()
    print(f"\n=== cached_clients (firm_id={firm_id}) ===")
    print(f"  Total rows: {r[0]}")
    print(f"  Rows with non-empty email: {r[1]}")

    # 3. Check invoices with contact_id
    cur.execute("""
        SELECT COUNT(*), COUNT(contact_id), COUNT(DISTINCT contact_id)
        FROM cached_invoices WHERE firm_id = %s AND balance_due > 0
    """, (firm_id,))
    r = cur.fetchone()
    print(f"\n=== cached_invoices with balance > 0 (firm_id={firm_id}) ===")
    print(f"  Total rows: {r[0]}")
    print(f"  Rows with contact_id: {r[1]}")
    print(f"  Distinct contact_ids: {r[2]}")

    # 4. Check if contact_ids match cached_contacts
    cur.execute("""
        SELECT COUNT(*) FROM cached_invoices i
        INNER JOIN cached_contacts ct ON i.contact_id = ct.id AND i.firm_id = ct.firm_id
        WHERE i.firm_id = %s AND i.balance_due > 0
    """, (firm_id,))
    print(f"\n=== JOIN matches ===")
    print(f"  Invoices matching cached_contacts: {cur.fetchone()[0]}")

    cur.execute("""
        SELECT COUNT(*) FROM cached_invoices i
        INNER JOIN cached_clients cl ON i.contact_id = cl.id AND i.firm_id = cl.firm_id
        WHERE i.firm_id = %s AND i.balance_due > 0
    """, (firm_id,))
    print(f"  Invoices matching cached_clients: {cur.fetchone()[0]}")

    # 5. Sample contact_ids from invoices and check what tables they're in
    cur.execute("""
        SELECT DISTINCT i.contact_id FROM cached_invoices i
        WHERE i.firm_id = %s AND i.balance_due > 0 AND i.contact_id IS NOT NULL
        LIMIT 5
    """, (firm_id,))
    sample_ids = [r[0] for r in cur.fetchall()]
    print(f"\n=== Sample contact_ids from invoices: {sample_ids} ===")
    for cid in sample_ids:
        cur.execute("SELECT id, name, email FROM cached_contacts WHERE firm_id = %s AND id = %s", (firm_id, cid))
        ct_row = cur.fetchone()
        cur.execute("SELECT id, first_name, last_name, email FROM cached_clients WHERE firm_id = %s AND id = %s", (firm_id, cid))
        cl_row = cur.fetchone()
        print(f"  contact_id={cid}: contacts={ct_row}, clients={cl_row}")

    # 6. Check data_json for email in invoices
    cur.execute("""
        SELECT data_json FROM cached_invoices
        WHERE firm_id = %s AND balance_due > 0 AND contact_id IS NOT NULL
        LIMIT 1
    """, (firm_id,))
    r = cur.fetchone()
    if r and r[0]:
        inv_json = json.loads(r[0])
        print(f"\n=== Sample invoice data_json keys ===")
        print(f"  Top-level keys: {list(inv_json.keys())}")
        # Check for nested contact/client info
        for key in ['contact', 'client', 'bill_to', 'billing_contact']:
            if key in inv_json:
                val = inv_json[key]
                print(f"  '{key}': {json.dumps(val, indent=2)[:500]}")

    # 7. Check data_json in contacts for email
    cur.execute("""
        SELECT id, data_json FROM cached_contacts
        WHERE firm_id = %s AND (email IS NULL OR email = '')
        LIMIT 3
    """, (firm_id,))
    rows = cur.fetchall()
    if rows:
        print(f"\n=== Sample cached_contacts with no email (checking data_json) ===")
        for r in rows:
            if r[1]:
                d = json.loads(r[1])
                email_fields = {k: v for k, v in d.items() if 'email' in k.lower() or 'mail' in k.lower()}
                print(f"  id={r[0]}: email-related fields in data_json: {email_fields}")
                if not email_fields:
                    print(f"    All keys: {list(d.keys())}")

    # 8. Check data_json in clients for email
    cur.execute("""
        SELECT id, data_json FROM cached_clients
        WHERE firm_id = %s AND (email IS NULL OR email = '')
        LIMIT 3
    """, (firm_id,))
    rows = cur.fetchall()
    if rows:
        print(f"\n=== Sample cached_clients with no email (checking data_json) ===")
        for r in rows:
            if r[1]:
                d = json.loads(r[1])
                email_fields = {k: v for k, v in d.items() if 'email' in k.lower() or 'mail' in k.lower()}
                print(f"  id={r[0]}: email-related fields in data_json: {email_fields}")

    # 9. Check if ANY contacts/clients have emails (regardless of firm_id)
    cur.execute("SELECT COUNT(*), COUNT(NULLIF(email, '')) FROM cached_contacts")
    r = cur.fetchone()
    print(f"\n=== ALL cached_contacts (all firms) ===")
    print(f"  Total: {r[0]}, With email: {r[1]}")

    cur.execute("SELECT COUNT(*), COUNT(NULLIF(email, '')) FROM cached_clients")
    r = cur.fetchone()
    print(f"  ALL cached_clients - Total: {r[0]}, With email: {r[1]}")

print("\nDone.")
