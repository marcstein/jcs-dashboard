#!/usr/bin/env python3
"""
LawMetrics.ai Auto-Sync Deployment Tool

Run this locally to:
  1. Verify configuration
  2. Run database migration
  3. Test local Celery setup
  4. Generate server deployment commands

Usage:
    uv run python deploy_sync.py check       # Verify config & connectivity
    uv run python deploy_sync.py migrate      # Run DB migration (dry-run first)
    uv run python deploy_sync.py migrate-apply  # Apply DB migration
    uv run python deploy_sync.py test-local   # Test Celery locally
    uv run python deploy_sync.py server-setup # Print server setup commands
    uv run python deploy_sync.py all          # Run full deployment sequence
"""
import os
import sys
from pathlib import Path
from datetime import datetime

# Ensure we're in the project directory
PROJECT_DIR = Path(__file__).parent
os.chdir(PROJECT_DIR)

# Load .env
try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_DIR / ".env")
except ImportError:
    pass


# =============================================================================
# Colors for terminal output
# =============================================================================
class C:
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    BOLD = "\033[1m"
    END = "\033[0m"

def ok(msg): print(f"  {C.GREEN}✓{C.END} {msg}")
def fail(msg): print(f"  {C.RED}✗{C.END} {msg}")
def warn(msg): print(f"  {C.YELLOW}!{C.END} {msg}")
def info(msg): print(f"  {C.BLUE}→{C.END} {msg}")
def header(msg): print(f"\n{C.BOLD}{msg}{C.END}")


# =============================================================================
# 1. CHECK - Verify configuration and connectivity
# =============================================================================
def cmd_check():
    """Verify all configuration and connectivity."""
    header("=" * 60)
    header("LawMetrics Auto-Sync - Configuration Check")
    header("=" * 60)

    all_good = True

    # --- Check required files ---
    header("\n[1/6] Required Files")
    required_files = [
        "celery_app.py", "tasks.py", "sync_mt.py", "platform_db.py",
        "sync_routes.py", "migrate_sync_tables.py", "tenant.py",
        "api_client_mt.py", "cache_mt.py",
        "deployment/celery-worker.service", "deployment/celery-beat.service",
        "deployment/setup_celery.sh",
    ]
    for f in required_files:
        if (PROJECT_DIR / f).exists():
            ok(f)
        else:
            fail(f"{f} - MISSING")
            all_good = False

    # --- Check .env variables ---
    header("\n[2/6] Environment Variables")
    env_checks = {
        "PG_HOST": os.environ.get("PG_HOST"),
        "PG_PORT": os.environ.get("PG_PORT"),
        "PG_DATABASE": os.environ.get("PG_DATABASE"),
        "PG_USER": os.environ.get("PG_USER"),
        "PG_PASSWORD": os.environ.get("PG_PASSWORD"),
        "REDIS_URL": os.environ.get("REDIS_URL"),
        "CELERY_CONCURRENCY": os.environ.get("CELERY_CONCURRENCY"),
        "MYCASE_CLIENT_ID": os.environ.get("MYCASE_CLIENT_ID"),
        "MYCASE_CLIENT_SECRET": os.environ.get("MYCASE_CLIENT_SECRET"),
    }
    for key, val in env_checks.items():
        if val:
            display = val[:20] + "..." if len(val) > 20 else val
            ok(f"{key} = {display}")
        else:
            if key == "REDIS_URL":
                warn(f"{key} - not set (will default to redis://localhost:6379/0)")
            else:
                fail(f"{key} - NOT SET")
                all_good = False

    encryption_key = os.environ.get("ENCRYPTION_KEY")
    if encryption_key:
        ok(f"ENCRYPTION_KEY = {encryption_key[:10]}...")
    else:
        warn("ENCRYPTION_KEY - not set (tokens stored with base64, not encrypted)")
        info("Generate with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\"")

    # --- Check PostgreSQL connectivity ---
    header("\n[3/6] PostgreSQL Connection")
    try:
        import psycopg2
        from psycopg2.extras import RealDictCursor

        conn = psycopg2.connect(
            host=os.environ.get("PG_HOST"),
            port=int(os.environ.get("PG_PORT", 25060)),
            database=os.environ.get("PG_DATABASE"),
            user=os.environ.get("PG_USER"),
            password=os.environ.get("PG_PASSWORD"),
            sslmode=os.environ.get("PG_SSLMODE", "require"),
            connect_timeout=10,
        )
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        cursor.execute("SELECT version()")
        version = cursor.fetchone()["version"]
        ok(f"Connected: {version[:60]}")

        # Check tables
        cursor.execute("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public' ORDER BY table_name
        """)
        tables = [row["table_name"] for row in cursor.fetchall()]
        ok(f"Tables found: {', '.join(tables) if tables else '(none)'}")

        # Check if firms table has sync columns
        if "firms" in tables:
            cursor.execute("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'firms' AND column_name = 'sync_frequency_minutes'
            """)
            if cursor.fetchone():
                ok("Sync columns already exist in firms table")
            else:
                warn("Sync columns NOT yet added to firms table (run: deploy_sync.py migrate-apply)")

        # Check sync_history
        if "sync_history" in tables:
            cursor.execute("SELECT COUNT(*) as cnt FROM sync_history")
            cnt = cursor.fetchone()["cnt"]
            ok(f"sync_history table exists ({cnt} rows)")
        else:
            warn("sync_history table does not exist yet (run: deploy_sync.py migrate-apply)")

        # Check firm count
        if "firms" in tables:
            cursor.execute("SELECT COUNT(*) as cnt FROM firms")
            cnt = cursor.fetchone()["cnt"]
            cursor.execute("""
                SELECT COUNT(*) as cnt FROM firms
                WHERE subscription_status IN ('trial', 'active')
                AND mycase_connected = TRUE
            """)
            active = cursor.fetchone()["cnt"]
            ok(f"Firms: {cnt} total, {active} active with MyCase")

        conn.close()

    except ImportError:
        fail("psycopg2 not installed (pip install psycopg2-binary)")
        all_good = False
    except Exception as e:
        fail(f"PostgreSQL connection failed: {e}")
        all_good = False

    # --- Check Redis (local) ---
    header("\n[4/6] Redis (Local)")
    try:
        import redis
        redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        r = redis.from_url(redis_url, socket_timeout=3)
        r.ping()
        ok(f"Redis connected at {redis_url}")
        info_dict = r.info("server")
        ok(f"Redis version: {info_dict.get('redis_version', 'unknown')}")
    except ImportError:
        warn("redis package not installed (pip install redis)")
    except Exception as e:
        warn(f"Redis not available locally: {e}")
        info("Install with: brew install redis && brew services start redis")
        info("Or skip - only needed for local Celery testing")

    # --- Check Celery import ---
    header("\n[5/6] Celery Configuration")
    try:
        from celery_app import app
        ok(f"Celery app loaded: {app.main}")
        ok(f"Broker: {app.conf.broker_url}")
        beat_tasks = list(app.conf.beat_schedule.keys())
        ok(f"Beat schedule: {len(beat_tasks)} tasks ({', '.join(beat_tasks)})")
    except ImportError as e:
        fail(f"Celery import failed: {e}")
        all_good = False
    except Exception as e:
        warn(f"Celery config issue: {e}")

    # --- Check tasks import ---
    header("\n[6/6] Task Definitions")
    try:
        import tasks
        task_names = [
            "dispatch_pending_syncs", "sync_firm_task", "initial_sync_task",
            "refresh_expiring_tokens", "refresh_firm_tokens",
            "dispatch_daily_reports", "generate_firm_reports",
            "detect_stale_syncs", "cleanup_sync_history", "manual_sync",
        ]
        for name in task_names:
            if hasattr(tasks, name):
                ok(f"tasks.{name}")
            else:
                fail(f"tasks.{name} - NOT FOUND")
                all_good = False
    except Exception as e:
        fail(f"Tasks import failed: {e}")
        all_good = False

    # --- Summary ---
    header("\n" + "=" * 60)
    if all_good:
        print(f"{C.GREEN}{C.BOLD}All checks passed! Ready for deployment.{C.END}")
    else:
        print(f"{C.YELLOW}{C.BOLD}Some issues found. Fix them before deploying.{C.END}")

    return all_good


# =============================================================================
# 2. MIGRATE - Run database migration
# =============================================================================
def cmd_migrate(apply: bool = False):
    """Run database migration."""
    header("=" * 60)
    header(f"Database Migration {'(APPLY)' if apply else '(DRY RUN)'}")
    header("=" * 60)

    from migrate_sync_tables import run_migration
    run_migration(check_only=not apply)

    if not apply:
        print(f"\n{C.YELLOW}This was a dry run. To apply, run:{C.END}")
        print(f"  uv run python deploy_sync.py migrate-apply")


# =============================================================================
# 3. TEST LOCAL - Start Celery locally for testing
# =============================================================================
def cmd_test_local():
    """Print instructions for local Celery testing."""
    header("=" * 60)
    header("Local Celery Testing")
    header("=" * 60)

    print(f"""
{C.BOLD}Terminal 1 - Start Redis{C.END}
  brew install redis  # if not installed
  redis-server

{C.BOLD}Terminal 2 - Start Celery Worker{C.END}
  cd {PROJECT_DIR}
  uv run celery -A celery_app worker --loglevel=info --concurrency=2 --queues=default,sync,reports

{C.BOLD}Terminal 3 - Test Tasks{C.END}
  cd {PROJECT_DIR}

  # Test dispatch (checks which firms are due):
  uv run python -c "from tasks import dispatch_pending_syncs; print(dispatch_pending_syncs())"

  # Test sync for a specific firm:
  uv run python -c "from tasks import sync_firm_task; print(sync_firm_task.delay('YOUR_FIRM_ID'))"

  # Check sync health:
  uv run python -c "from platform_db import get_platform_db; print(get_platform_db().get_sync_health_summary())"

{C.BOLD}Terminal 4 (optional) - Start Beat Scheduler{C.END}
  cd {PROJECT_DIR}
  uv run celery -A celery_app beat --loglevel=info

{C.BOLD}Or run worker + beat together (dev only):{C.END}
  uv run celery -A celery_app worker --beat --loglevel=info --concurrency=2 --queues=default,sync,reports
""")


# =============================================================================
# 4. SERVER SETUP - Generate server deployment commands
# =============================================================================
def cmd_server_setup():
    """Print complete server deployment commands."""
    header("=" * 60)
    header("Server Deployment Guide")
    header("=" * 60)

    print(f"""
{C.BOLD}Prerequisites:{C.END}
  - Digital Ocean droplet with Ubuntu 22.04+
  - Base setup.sh already run (app at /opt/jcs-mycase)
  - PostgreSQL managed database (already configured)

{C.BOLD}Step 1: Copy files to server{C.END}
  scp celery_app.py tasks.py platform_db.py sync_mt.py sync_routes.py \\
      migrate_sync_tables.py platform_db_sync_extensions.py tenant.py \\
      api_client_mt.py cache_mt.py config.py requirements.txt .env \\
      root@YOUR_SERVER:/opt/jcs-mycase/

  scp deployment/celery-worker.service deployment/celery-beat.service \\
      deployment/setup_celery.sh \\
      root@YOUR_SERVER:/opt/jcs-mycase/deployment/

{C.BOLD}Step 2: SSH into server and run setup{C.END}
  ssh root@YOUR_SERVER
  cd /opt/jcs-mycase
  chmod +x deployment/setup_celery.sh
  ./deployment/setup_celery.sh

{C.BOLD}Step 3: Verify services{C.END}
  systemctl status celery-worker
  systemctl status celery-beat
  systemctl status redis-server

  # Watch logs
  journalctl -u celery-worker -f
  journalctl -u celery-beat -f

{C.BOLD}Step 4: Verify sync is working{C.END}
  sudo -u mycase /opt/jcs-mycase/.venv/bin/python -c \\
    "from platform_db import get_platform_db; \\
     db = get_platform_db(); \\
     print('Health:', db.get_sync_health_summary()); \\
     print('Due:', db.get_firms_due_for_sync())"

  # Trigger a manual sync
  sudo -u mycase /opt/jcs-mycase/.venv/bin/python -c \\
    "from tasks import dispatch_pending_syncs; \\
     print(dispatch_pending_syncs())"

{C.BOLD}Step 5: Restart dashboard to pick up sync routes{C.END}
  systemctl restart mycase-dashboard

  # Test the API
  curl http://localhost:3000/api/sync/admin/health

{C.BOLD}Useful monitoring commands:{C.END}
  redis-cli ping                          # Test Redis
  redis-cli info stats | grep ops         # Redis throughput
  redis-cli llen sync                     # Pending sync tasks
  journalctl -u celery-worker --since "1 hour ago"  # Recent logs

{C.BOLD}Service management:{C.END}
  systemctl restart celery-worker         # Restart worker
  systemctl restart celery-beat           # Restart scheduler
  systemctl stop celery-worker celery-beat   # Stop everything
""")


# =============================================================================
# 5. ALL - Full deployment sequence
# =============================================================================
def cmd_all():
    """Run full deployment sequence."""
    header("=" * 60)
    header("LawMetrics Auto-Sync - Full Deployment")
    header("=" * 60)

    # Step 1: Check
    print(f"\n{C.BOLD}Phase 1: Configuration Check{C.END}")
    checks_ok = cmd_check()

    if not checks_ok:
        print(f"\n{C.RED}Fix the issues above before continuing.{C.END}")
        return

    # Step 2: Migration dry run
    print(f"\n{C.BOLD}Phase 2: Database Migration (dry run){C.END}")
    cmd_migrate(apply=False)

    # Step 3: Ask to apply
    print(f"\n{C.YELLOW}Ready to apply migration?{C.END}")
    response = input("  Apply database migration? [y/N]: ").strip().lower()
    if response == "y":
        cmd_migrate(apply=True)
    else:
        print("  Skipped. Run 'deploy_sync.py migrate-apply' when ready.")

    # Step 4: Show next steps
    print(f"\n{C.BOLD}Phase 3: Next Steps{C.END}")
    cmd_test_local()
    cmd_server_setup()


# =============================================================================
# CLI Router
# =============================================================================
def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)

    command = sys.argv[1]

    commands = {
        "check": cmd_check,
        "migrate": lambda: cmd_migrate(apply=False),
        "migrate-apply": lambda: cmd_migrate(apply=True),
        "test-local": cmd_test_local,
        "server-setup": cmd_server_setup,
        "all": cmd_all,
    }

    if command not in commands:
        print(f"Unknown command: {command}")
        print(f"Available: {', '.join(commands.keys())}")
        sys.exit(1)

    commands[command]()


if __name__ == "__main__":
    main()
