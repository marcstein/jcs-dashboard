#!/usr/bin/env python3
"""
Migration 001: Consolidate firms table

Adds all multi-tenant columns to the existing firms table and populates
the JCS Law firm record from current environment variables.

Safe to run multiple times (idempotent).

Usage:
    cd /opt/jcs-mycase
    export $(grep -v '^#' .env | xargs)
    python -m db.migrations.001_consolidate_firms
"""
import os
import sys
import json
import logging
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def run_migration():
    """Run the firms table consolidation migration."""
    from db.connection import get_connection
    from db.firms import ensure_firms_tables

    # Step 1: Ensure schema is up to date (adds missing columns)
    logger.info("Step 1: Ensuring unified firms schema...")
    ensure_firms_tables()
    logger.info("  Schema updated successfully")

    # Step 2: Populate JCS Law firm record from environment variables
    firm_id = os.getenv("FIRM_ID", "jcs_law")
    logger.info(f"Step 2: Populating firm record for '{firm_id}'...")

    # Build notification config from current env vars
    notification_config = {
        "sendgrid_api_key": os.getenv("SENDGRID_API_KEY", ""),
        "sendgrid_from_email": os.getenv("DUNNING_FROM_EMAIL", "billing@jcsattorney.com"),
        "sendgrid_from_name": os.getenv("DUNNING_FROM_NAME", "JCS Law Firm - Billing"),
        "slack_webhook_url": os.getenv("SLACK_WEBHOOK_URL", ""),
        "twilio_account_sid": os.getenv("TWILIO_ACCOUNT_SID", ""),
        "twilio_auth_token": os.getenv("TWILIO_AUTH_TOKEN", ""),
        "twilio_from_number": os.getenv("TWILIO_FROM_NUMBER", ""),
        "smtp_server": os.getenv("SMTP_SERVER", "smtp.gmail.com"),
        "smtp_port": int(os.getenv("SMTP_PORT", "587")),
        "smtp_username": os.getenv("SMTP_USERNAME", ""),
        "smtp_password": os.getenv("SMTP_PASSWORD", ""),
        "smtp_from_email": os.getenv("SMTP_FROM_EMAIL", ""),
        "dunning_from_email": os.getenv("DUNNING_FROM_EMAIL", "billing@jcsattorney.com"),
        "dunning_from_name": os.getenv("DUNNING_FROM_NAME", "JCS Law Firm - Billing"),
    }

    # Settings (schedule preferences, feature flags)
    settings = {
        "schedule": {
            "sync_time": "06:00",
            "dunning_time": "07:30",
            "reports_time": "08:00",
            "timezone": "America/Chicago",
        },
    }

    with get_connection() as conn:
        cur = conn.cursor()

        # Check if firm already exists
        cur.execute("SELECT id, name FROM firms WHERE id = %s", (firm_id,))
        existing = cur.fetchone()

        if existing:
            logger.info(f"  Firm '{firm_id}' exists, updating config columns...")
            cur.execute("""
                UPDATE firms SET
                    notification_config = %s::jsonb,
                    firm_phone = COALESCE(firm_phone, %s),
                    firm_email = COALESCE(firm_email, %s),
                    firm_website = COALESCE(firm_website, %s),
                    settings = COALESCE(settings, '{}'::jsonb) || %s::jsonb,
                    mycase_client_id = COALESCE(mycase_client_id, %s),
                    mycase_client_secret = COALESCE(mycase_client_secret, %s),
                    subscription_status = COALESCE(subscription_status, 'active'),
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
            """, (
                json.dumps(notification_config),
                "(314) 561-9690",
                "info@jcslaw.com",
                "https://jcsattorney.com",
                json.dumps(settings),
                os.getenv("MYCASE_CLIENT_ID", ""),
                os.getenv("MYCASE_CLIENT_SECRET", ""),
                firm_id,
            ))
        else:
            logger.info(f"  Creating firm '{firm_id}'...")
            cur.execute("""
                INSERT INTO firms (
                    id, name, subscription_status, subscription_tier,
                    notification_config, firm_phone, firm_email, firm_website,
                    settings, mycase_client_id, mycase_client_secret,
                    mycase_connected, sync_frequency_minutes
                ) VALUES (
                    %s, %s, 'active', 'standard',
                    %s::jsonb, %s, %s, %s,
                    %s::jsonb, %s, %s,
                    TRUE, 240
                )
            """, (
                firm_id, "JCS Law Firm",
                json.dumps(notification_config),
                "(314) 561-9690",
                "info@jcslaw.com",
                "https://jcsattorney.com",
                json.dumps(settings),
                os.getenv("MYCASE_CLIENT_ID", ""),
                os.getenv("MYCASE_CLIENT_SECRET", ""),
            ))

        conn.commit()
        logger.info(f"  Firm '{firm_id}' config populated")

    # Step 3: Migrate OAuth tokens from tokens.json if present
    tokens_file = Path(__file__).parent.parent.parent / "data" / "tokens.json"
    if tokens_file.exists():
        logger.info("Step 3: Migrating OAuth tokens from tokens.json...")
        try:
            with open(tokens_file) as f:
                tokens = json.load(f)

            with get_connection() as conn:
                cur = conn.cursor()
                cur.execute("""
                    UPDATE firms SET
                        mycase_oauth_token = %s,
                        mycase_oauth_refresh = %s,
                        mycase_connected = TRUE,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                """, (
                    tokens.get("access_token", ""),
                    tokens.get("refresh_token", ""),
                    firm_id,
                ))
                conn.commit()
            logger.info("  OAuth tokens migrated to firms table")
        except Exception as e:
            logger.warning(f"  Could not migrate tokens: {e}")
    else:
        logger.info("Step 3: No tokens.json found, skipping OAuth migration")

    # Step 4: Verify
    logger.info("Step 4: Verifying migration...")
    from db.firms import get_firm
    firm = get_firm(firm_id)
    if firm:
        nc = firm.get("notification_config", {})
        has_sendgrid = bool(nc.get("sendgrid_api_key"))
        has_slack = bool(nc.get("slack_webhook_url"))
        has_oauth = bool(firm.get("mycase_oauth_token"))

        logger.info(f"  Firm: {firm['name']} ({firm['id']})")
        logger.info(f"  Subscription: {firm.get('subscription_status')}")
        logger.info(f"  SendGrid configured: {has_sendgrid}")
        logger.info(f"  Slack configured: {has_slack}")
        logger.info(f"  OAuth tokens present: {has_oauth}")
        logger.info(f"  Phone: {firm.get('firm_phone')}")
        logger.info(f"  Dunning from: {nc.get('dunning_from_email')}")
    else:
        logger.error(f"  FAILED: Firm '{firm_id}' not found after migration!")
        return False

    logger.info("\nMigration complete!")
    return True


if __name__ == "__main__":
    success = run_migration()
    sys.exit(0 if success else 1)
