#!/usr/bin/env python3
"""Diagnostic script - phase 2: find how invoices link to clients."""
import os, json, sys
sys.path.insert(0, os.path.dirname(__file__))
from dotenv import load_dotenv
load_dotenv()
from db.connection import get_connection

firm_id = os.environ.get("FIRM_ID", "jcs_law")

def v(row, key):
    if row is None:
        return None
    if isinstance(row, dict):
        return row.get(key)
    return None

with get_connection() as conn:
    cur = conn.cursor()

    # 1. Check invoice data_json for contact/client references
    cur.execute("""
        SELECT data_json FROM cached_invoices
        WHERE firm_id = %s AND balance_due > 0
        LIMIT 1
    """, (firm_id,))
    r = cur.fetchone()
    dj = v(r, 'data_json')
    if dj:
        inv = json.loads(dj)
        print("=== Sample invoice data_json ===")
        print(f"  Top-level keys: {list(inv.keys())}")
        for key in ['contact', 'client', 'bill_to', 'billing_contact', 'case', 'contact_id', 'client_id']:
            if key in inv:
                val = inv[key]
                if isinstance(val, dict):
                    print(f"  '{key}': {json.dumps(val, indent=2)[:300]}")
                else:
                    print(f"  '{key}': {val}")

    # 2. Check cached_cases for client references
    cur.execute("""
        SELECT data_json FROM cached_cases
        WHERE firm_id = %s
        LIMIT 1
    """, (firm_id,))
    r = cur.fetchone()
    dj = v(r, 'data_json')
    if dj:
        case = json.loads(dj)
        print(f"\n=== Sample case data_json ===")
        print(f"  Top-level keys: {list(case.keys())}")
        for key in ['contact', 'client', 'contacts', 'clients', 'contact_id', 'client_id', 'billing_contact']:
            if key in case:
                val = case[key]
                if isinstance(val, (dict, list)):
                    print(f"  '{key}': {json.dumps(val, indent=2)[:500]}")
                else:
                    print(f"  '{key}': {val}")

    # 3. Check cached_cases schema - does it have a client_id column?
    cur.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'cached_cases'
        ORDER BY ordinal_position
    """)
    cols = [v(r, 'column_name') for r in cur.fetchall()]
    print(f"\n=== cached_cases columns ===")
    print(f"  {cols}")

    # 4. Check if cases have contact_id populated
    cur.execute("""
        SELECT COUNT(*) as cnt, COUNT(contact_id) as has_cid
        FROM cached_cases WHERE firm_id = %s
    """, (firm_id,))
    r = cur.fetchone()
    print(f"\n=== cached_cases contact_id ===")
    print(f"  Total cases: {v(r, 'cnt')}, With contact_id: {v(r, 'has_cid')}")

    # 5. Try joining invoice -> case -> client via case contact_id
    cur.execute("""
        SELECT COUNT(*) as cnt FROM cached_invoices i
        JOIN cached_cases c ON i.case_id = c.id AND i.firm_id = c.firm_id
        JOIN cached_clients cl ON c.contact_id = cl.id AND c.firm_id = cl.firm_id
        WHERE i.firm_id = %s AND i.balance_due > 0
    """, (firm_id,))
    r = cur.fetchone()
    print(f"  Invoices -> case -> client match: {v(r, 'cnt')}")

    # 6. Sample the full chain
    cur.execute("""
        SELECT i.invoice_number, c.name as case_name, cl.first_name, cl.last_name, cl.email
        FROM cached_invoices i
        JOIN cached_cases c ON i.case_id = c.id AND i.firm_id = c.firm_id
        JOIN cached_clients cl ON c.contact_id = cl.id AND c.firm_id = cl.firm_id
        WHERE i.firm_id = %s AND i.balance_due > 0 AND cl.email IS NOT NULL AND cl.email != ''
        LIMIT 5
    """, (firm_id,))
    rows = cur.fetchall()
    print(f"\n=== Sample invoice -> case -> client with email ===")
    for r in rows:
        print(f"  Invoice {v(r, 'invoice_number')}: {v(r, 'case_name')} -> {v(r, 'first_name')} {v(r, 'last_name')} <{v(r, 'email')}>")

    if not rows:
        # Maybe contact_id on cases is also null - try via case data_json
        cur.execute("""
            SELECT c.data_json FROM cached_invoices i
            JOIN cached_cases c ON i.case_id = c.id AND i.firm_id = c.firm_id
            WHERE i.firm_id = %s AND i.balance_due > 0
            LIMIT 3
        """, (firm_id,))
        for r in cur.fetchall():
            dj = v(r, 'data_json')
            if dj:
                case = json.loads(dj)
                for key in ['contact', 'client', 'contacts', 'clients', 'contact_id', 'client_id']:
                    if key in case:
                        print(f"  Case has '{key}': {json.dumps(case[key])[:200]}")

print("\nDone.")
