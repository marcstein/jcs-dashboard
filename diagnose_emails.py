#!/usr/bin/env python3
"""Diagnostic script to find where client emails are stored.
Works with both tuple cursors and RealDictCursor."""
import os, json, sys
sys.path.insert(0, os.path.dirname(__file__))
from dotenv import load_dotenv
load_dotenv()
from db.connection import get_connection

firm_id = os.environ.get("FIRM_ID", "jcs_law")

def val(row, key_or_idx):
    """Get value from row whether it's a dict or tuple."""
    if isinstance(row, dict):
        return row.get(key_or_idx)
    return row[key_or_idx] if row else None

with get_connection() as conn:
    cur = conn.cursor()

    # 1. Check cached_contacts
    cur.execute("SELECT COUNT(*) as cnt, COUNT(NULLIF(email, '')) as has_email FROM cached_contacts WHERE firm_id = %s", (firm_id,))
    r = cur.fetchone()
    print(f"\n=== cached_contacts (firm_id={firm_id}) ===")
    print(f"  Total rows: {val(r, 'cnt') or val(r, 0)}")
    print(f"  Rows with non-empty email: {val(r, 'has_email') or val(r, 1)}")

    # 2. Check cached_clients
    cur.execute("SELECT COUNT(*) as cnt, COUNT(NULLIF(email, '')) as has_email FROM cached_clients WHERE firm_id = %s", (firm_id,))
    r = cur.fetchone()
    print(f"\n=== cached_clients (firm_id={firm_id}) ===")
    print(f"  Total rows: {val(r, 'cnt') or val(r, 0)}")
    print(f"  Rows with non-empty email: {val(r, 'has_email') or val(r, 1)}")

    # 3. Check invoices with contact_id
    cur.execute("""
        SELECT COUNT(*) as cnt, COUNT(contact_id) as has_cid, COUNT(DISTINCT contact_id) as distinct_cid
        FROM cached_invoices WHERE firm_id = %s AND balance_due > 0
    """, (firm_id,))
    r = cur.fetchone()
    print(f"\n=== cached_invoices with balance > 0 (firm_id={firm_id}) ===")
    print(f"  Total rows: {val(r, 'cnt') or val(r, 0)}")
    print(f"  Rows with contact_id: {val(r, 'has_cid') or val(r, 1)}")
    print(f"  Distinct contact_ids: {val(r, 'distinct_cid') or val(r, 2)}")

    # 4. Check if contact_ids match cached_contacts
    cur.execute("""
        SELECT COUNT(*) as cnt FROM cached_invoices i
        INNER JOIN cached_contacts ct ON i.contact_id = ct.id AND i.firm_id = ct.firm_id
        WHERE i.firm_id = %s AND i.balance_due > 0
    """, (firm_id,))
    r = cur.fetchone()
    print(f"\n=== JOIN matches ===")
    print(f"  Invoices matching cached_contacts: {val(r, 'cnt') or val(r, 0)}")

    cur.execute("""
        SELECT COUNT(*) as cnt FROM cached_invoices i
        INNER JOIN cached_clients cl ON i.contact_id = cl.id AND i.firm_id = cl.firm_id
        WHERE i.firm_id = %s AND i.balance_due > 0
    """, (firm_id,))
    r = cur.fetchone()
    print(f"  Invoices matching cached_clients: {val(r, 'cnt') or val(r, 0)}")

    # 5. Sample contact_ids from invoices and check what tables they're in
    cur.execute("""
        SELECT DISTINCT contact_id as cid FROM cached_invoices
        WHERE firm_id = %s AND balance_due > 0 AND contact_id IS NOT NULL
        LIMIT 5
    """, (firm_id,))
    sample_ids = [val(r, 'cid') or val(r, 0) for r in cur.fetchall()]
    print(f"\n=== Sample contact_ids from invoices: {sample_ids} ===")
    for cid in sample_ids:
        cur.execute("SELECT id, name, email FROM cached_contacts WHERE firm_id = %s AND id = %s", (firm_id, cid))
        ct_row = cur.fetchone()
        cur.execute("SELECT id, first_name, last_name, email FROM cached_clients WHERE firm_id = %s AND id = %s", (firm_id, cid))
        cl_row = cur.fetchone()
        print(f"  contact_id={cid}: contacts={dict(ct_row) if ct_row else None}, clients={dict(cl_row) if cl_row else None}")

    # 6. Check data_json for email in invoices
    cur.execute("""
        SELECT data_json FROM cached_invoices
        WHERE firm_id = %s AND balance_due > 0 AND contact_id IS NOT NULL
        LIMIT 1
    """, (firm_id,))
    r = cur.fetchone()
    dj = val(r, 'data_json') or val(r, 0) if r else None
    if dj:
        inv_json = json.loads(dj)
        print(f"\n=== Sample invoice data_json keys ===")
        print(f"  Top-level keys: {list(inv_json.keys())}")
        for key in ['contact', 'client', 'bill_to', 'billing_contact']:
            if key in inv_json:
                v = inv_json[key]
                print(f"  '{key}': {json.dumps(v, indent=2)[:500]}")

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
            dj = val(r, 'data_json') or val(r, 1)
            rid = val(r, 'id') or val(r, 0)
            if dj:
                d = json.loads(dj)
                email_fields = {k: v for k, v in d.items() if 'email' in k.lower() or 'mail' in k.lower()}
                print(f"  id={rid}: email-related fields in data_json: {email_fields}")
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
            dj = val(r, 'data_json') or val(r, 1)
            rid = val(r, 'id') or val(r, 0)
            if dj:
                d = json.loads(dj)
                email_fields = {k: v for k, v in d.items() if 'email' in k.lower() or 'mail' in k.lower()}
                print(f"  id={rid}: email-related fields in data_json: {email_fields}")

    # 9. Check if ANY contacts/clients have emails (regardless of firm_id)
    cur.execute("SELECT COUNT(*) as cnt, COUNT(NULLIF(email, '')) as has_email FROM cached_contacts")
    r = cur.fetchone()
    print(f"\n=== ALL cached_contacts (all firms) ===")
    print(f"  Total: {val(r, 'cnt') or val(r, 0)}, With email: {val(r, 'has_email') or val(r, 1)}")

    cur.execute("SELECT COUNT(*) as cnt, COUNT(NULLIF(email, '')) as has_email FROM cached_clients")
    r = cur.fetchone()
    print(f"  ALL cached_clients - Total: {val(r, 'cnt') or val(r, 0)}, With email: {val(r, 'has_email') or val(r, 1)}")

print("\nDone.")
