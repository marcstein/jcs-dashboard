#!/usr/bin/env python3
"""
Onboard JCS Law Firm to LawMetrics.ai Platform

This script:
1. Creates the JCS firm record in the platform database
2. Creates an admin user (Marc)
3. Stores MyCase OAuth credentials from local tokens.json
4. Runs initial data sync (all entities from MyCase → Postgres cache)
5. Schedules the first automated sync

Prerequisites:
- DATABASE_URL set (Digital Ocean PostgreSQL)
- Valid tokens in data/tokens.json (run `python agent.py auth` first if expired)
- All _mt modules available (cache_mt, sync_mt, api_client_mt, platform_db, tenant)

Usage:
    python onboard_jcs.py              # Full onboard: create firm + sync
    python onboard_jcs.py --skip-sync  # Create firm only, no data sync
    python onboard_jcs.py --sync-only  # Re-sync existing firm (no creation)
    python onboard_jcs.py --status     # Check current status
"""
import sys
import os
import json
import time
from pathlib import Path
from datetime import datetime, timedelta

# Ensure .env is loaded
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass

from config import DATA_DIR, TOKEN_FILE


# ─── Constants ────────────────────────────────────────────────────────────────
JCS_FIRM_NAME = "JCS Law Firm"
JCS_ADMIN_EMAIL = "marc.stein@gmail.com"
JCS_ADMIN_NAME = "Marc Stein"


def load_local_tokens() -> dict:
    """Load OAuth tokens from local tokens.json."""
    if not TOKEN_FILE.exists():
        print(f"ERROR: Token file not found: {TOKEN_FILE}")
        print("Run: python agent.py auth login")
        sys.exit(1)

    with open(TOKEN_FILE) as f:
        tokens = json.load(f)

    # Check if refresh token is still valid (2-week window)
    saved_at = datetime.fromisoformat(tokens.get("saved_at", "2000-01-01"))
    if datetime.now() > saved_at + timedelta(weeks=2):
        print("WARNING: Refresh token may be expired (saved >2 weeks ago).")
        print(f"  Saved at: {saved_at.isoformat()}")
        print(f"  Now:      {datetime.now().isoformat()}")
        print("Run: python agent.py auth login   to re-authorize first.")
        resp = input("Continue anyway? [y/N] ").strip().lower()
        if resp != "y":
            sys.exit(1)

    return tokens


def get_or_create_firm(db, tokens: dict):
    """Get existing JCS firm or create a new one."""
    # Check by name
    with db._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM firms WHERE name = %s", (JCS_FIRM_NAME,))
        row = cursor.fetchone()
        if row:
            firm_id = dict(row)["id"]
            firm = db.get_firm(firm_id)
            print(f"Found existing firm: {firm.name} (ID: {firm.id})")
            return firm, False  # False = not newly created

    # Create new firm
    print(f"Creating firm: {JCS_FIRM_NAME}")
    firm = db.create_firm(JCS_FIRM_NAME, trial_days=365)
    print(f"  Firm ID: {firm.id}")

    # Upgrade to active immediately (internal use)
    db.update_firm_subscription(firm.id, status="active", tier="enterprise")
    print(f"  Subscription: active / enterprise")

    return firm, True


def store_credentials(db, firm_id: str, tokens: dict):
    """Store MyCase OAuth credentials in platform DB."""
    access_token = tokens["access_token"]
    refresh_token = tokens["refresh_token"]
    expires_in = tokens.get("expires_in", 86400)
    firm_uuid = tokens.get("firm_uuid", "")

    # Deterministic int from UUID for mycase_firm_id column
    mycase_firm_id = abs(hash(firm_uuid)) % (10 ** 9)

    db.store_mycase_credentials(
        firm_id=firm_id,
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=expires_in,
        mycase_firm_id=mycase_firm_id,
    )
    print(f"  OAuth credentials stored (MyCase UUID: {firm_uuid})")

    # Set sync schedule
    with db._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE firms SET 
                sync_frequency_minutes = 240,
                next_sync_at = NOW()
            WHERE id = %s
        """, (firm_id,))
    print(f"  Sync frequency: every 4 hours")


def create_admin_user(db, firm_id: str):
    """Create admin user for the firm."""
    existing = db.get_user_by_email(JCS_ADMIN_EMAIL)
    if existing:
        print(f"  Admin user already exists: {existing.email}")
        return existing

    user = db.create_user(
        firm_id=firm_id,
        email=JCS_ADMIN_EMAIL,
        name=JCS_ADMIN_NAME,
        role="admin",
    )
    print(f"  Admin user created: {user.email} (ID: {user.id})")
    return user


def run_initial_sync(firm_id: str):
    """Run full data sync from MyCase API to Postgres cache."""
    from tenant import TenantContextManager
    from sync_mt import SyncManager
    from cache_mt import initialize_firm_cache

    print(f"\n{'='*60}")
    print(f"Starting initial data sync for {JCS_FIRM_NAME}")
    print(f"{'='*60}")

    # Initialize cache tables
    print("\nInitializing cache tables...")
    initialize_firm_cache(firm_id)

    # Run sync within tenant context
    start_time = time.time()
    with TenantContextManager(firm_id=firm_id):
        manager = SyncManager(firm_id=firm_id)
        results = manager.sync_all(force_full=True)

    duration = time.time() - start_time

    # Print results
    total_records = 0
    print(f"\n{'='*60}")
    print(f"Sync Results ({duration:.1f}s)")
    print(f"{'='*60}")
    for entity_type, result in results.items():
        records = result.inserted + result.updated
        total_records += records
        status = "OK" if not result.error else "ERR"
        print(f"  [{status}] {entity_type:15} | {result.total_in_cache:6} cached | "
              f"{result.inserted} new, {result.updated} updated "
              f"({result.duration_seconds:.1f}s)")
        if result.error:
            print(f"        ERROR: {result.error}")

    print(f"\nTotal: {total_records} records synced in {duration:.1f}s")
    return results


def check_status():
    """Check current platform status."""
    from platform_db import get_platform_db
    db = get_platform_db()

    print(f"\n{'='*60}")
    print(f"LawMetrics.ai Platform Status")
    print(f"{'='*60}")

    # Check firms
    with db._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, name, subscription_status, mycase_connected, 
                   last_sync_at, last_sync_status, last_sync_records,
                   last_sync_duration_seconds, mycase_token_expires_at
            FROM firms
        """)
        firms = [dict(r) for r in cursor.fetchall()]

    if not firms:
        print("\n  No firms registered. Run: python onboard_jcs.py")
        return

    for firm in firms:
        print(f"\n  Firm: {firm['name']}")
        print(f"  ID: {firm['id']}")
        print(f"  Status: {firm['subscription_status']}")
        print(f"  MyCase: {'Connected' if firm['mycase_connected'] else 'NOT Connected'}")
        print(f"  Last Sync: {firm['last_sync_at'] or 'Never'}")
        print(f"  Sync Status: {firm['last_sync_status'] or 'N/A'}")
        if firm['last_sync_records']:
            print(f"  Last Sync Records: {firm['last_sync_records']}")
        if firm['last_sync_duration_seconds']:
            print(f"  Last Sync Duration: {firm['last_sync_duration_seconds']:.1f}s")

        # Token status
        token_exp = firm.get('mycase_token_expires_at')
        if token_exp:
            from datetime import timezone
            now = datetime.now(timezone.utc) if token_exp.tzinfo else datetime.now()
            if now > token_exp:
                print(f"  Token: EXPIRED ({token_exp})")
            else:
                remaining = token_exp - now
                print(f"  Token: Valid (expires in {remaining})")
        else:
            print(f"  Token: N/A")

        # Check cache tables
        cache_tables = ['cached_cases', 'cached_events', 'cached_invoices',
                        'cached_clients', 'cached_contacts', 'cached_staff',
                        'cached_tasks', 'cached_payments', 'cached_time_entries']
        with db._get_connection() as conn:
            cursor = conn.cursor()
            print(f"\n  Cache Records:")
            for table in cache_tables:
                try:
                    cursor.execute(f"SELECT COUNT(*) as cnt FROM {table} WHERE firm_id = %s",
                                   (firm['id'],))
                    cnt = cursor.fetchone()
                    if cnt:
                        print(f"    {table:25} {dict(cnt)['cnt']:>6}")
                except Exception:
                    print(f"    {table:25} (table not found)")

        # Check users
        users = db.get_firm_users(firm['id'])
        print(f"\n  Users: {len(users)}")
        for u in users:
            print(f"    {u.name} ({u.email}) - {u.role}")

    # Sync history
    if firms:
        with db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT started_at, status, records_synced, duration_seconds, error_message
                FROM sync_history WHERE firm_id = %s
                ORDER BY started_at DESC LIMIT 5
            """, (firms[0]['id'],))
            history = [dict(r) for r in cursor.fetchall()]
            if history:
                print(f"\n  Recent Sync History:")
                for h in history:
                    err = f" - {h['error_message'][:40]}" if h.get('error_message') else ""
                    print(f"    {h['started_at']} | {h['status']:10} | "
                          f"{h.get('records_synced', 0)} records | "
                          f"{h.get('duration_seconds', 0):.1f}s{err}")


def main():
    args = sys.argv[1:]

    if "--status" in args:
        check_status()
        return

    from platform_db import get_platform_db
    db = get_platform_db()

    skip_sync = "--skip-sync" in args
    sync_only = "--sync-only" in args

    if sync_only:
        # Find existing firm
        with db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM firms WHERE name = %s", (JCS_FIRM_NAME,))
            row = cursor.fetchone()
            if not row:
                print(f"ERROR: Firm '{JCS_FIRM_NAME}' not found. Run without --sync-only first.")
                sys.exit(1)
            firm_id = dict(row)["id"]

        # Refresh credentials from local tokens
        tokens = load_local_tokens()
        store_credentials(db, firm_id, tokens)

        # Run sync
        run_initial_sync(firm_id)
        return

    # Full onboard flow
    print(f"\n{'='*60}")
    print(f"LawMetrics.ai - Onboarding {JCS_FIRM_NAME}")
    print(f"{'='*60}\n")

    # Step 1: Load local tokens
    print("[1/4] Loading MyCase OAuth tokens...")
    tokens = load_local_tokens()
    print(f"  Token saved at: {tokens.get('saved_at')}")
    print(f"  Firm UUID: {tokens.get('firm_uuid')}")

    # Step 2: Create or get firm
    print(f"\n[2/4] Setting up firm in platform database...")
    firm, is_new = get_or_create_firm(db, tokens)

    # Step 3: Store credentials & create user
    print(f"\n[3/4] Configuring firm...")
    store_credentials(db, firm.id, tokens)
    create_admin_user(db, firm.id)

    # Step 4: Initial sync
    if skip_sync:
        print(f"\n[4/4] Skipping initial sync (--skip-sync)")
        print(f"\nTo sync later, run:")
        print(f"  python onboard_jcs.py --sync-only")
    else:
        print(f"\n[4/4] Running initial data sync...")
        run_initial_sync(firm.id)

    # Schedule next sync
    db.schedule_next_sync(firm.id, delay_minutes=240)

    print(f"\n{'='*60}")
    print(f"Onboarding Complete!")
    print(f"{'='*60}")
    print(f"  Firm ID: {firm.id}")
    print(f"  Status: active")
    print(f"  MyCase: connected")
    print(f"\nNext steps:")
    print(f"  1. Restart Celery: systemctl restart celery-worker celery-beat")
    print(f"  2. Check status:   python onboard_jcs.py --status")


if __name__ == "__main__":
    main()
