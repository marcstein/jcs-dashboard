"""
Celery Tasks for LawMetrics.ai

Task categories:
1. Sync orchestration  - dispatch_pending_syncs, sync_firm_task
2. Token management    - refresh_firm_tokens, refresh_expiring_tokens
3. Report generation   - dispatch_daily_reports, generate_firm_reports
4. Maintenance         - detect_stale_syncs, cleanup_sync_history
"""
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded

logger = logging.getLogger(__name__)


# =============================================================================
# 1. SYNC ORCHESTRATION
# =============================================================================

@shared_task(name="tasks.dispatch_pending_syncs", bind=True)
def dispatch_pending_syncs(self):
    """
    Check which firms are due for sync and queue individual sync tasks.
    Runs every 5 minutes via Celery Beat.
    """
    from platform_db import get_platform_db

    db = get_platform_db()
    max_dispatch = 10

    try:
        firms = db.get_firms_due_for_sync(limit=max_dispatch)

        if not firms:
            logger.debug("No firms due for sync")
            return {"dispatched": 0}

        dispatched = 0
        for firm in firms:
            firm_id = firm["id"]
            firm_name = firm.get("name", firm_id)

            # Don't queue if already running
            sync_status = db.get_sync_status(firm_id)
            if sync_status.get("status") == "running":
                started = sync_status.get("started_at")
                if started:
                    if isinstance(started, str):
                        started = datetime.fromisoformat(started)
                    if datetime.utcnow() - started < timedelta(minutes=45):
                        logger.info(f"Skipping {firm_name}: sync already running")
                        continue

            sync_firm_task.apply_async(
                args=[firm_id],
                kwargs={"triggered_by": "scheduler"},
                countdown=dispatched * 5,
            )
            dispatched += 1
            logger.info(f"Queued sync for {firm_name} (#{dispatched})")

        return {"dispatched": dispatched, "pending": len(firms)}

    except Exception as e:
        logger.error(f"dispatch_pending_syncs failed: {e}", exc_info=True)
        raise


@shared_task(
    name="tasks.sync_firm_task",
    bind=True,
    max_retries=3,
    default_retry_delay=300,
    acks_late=True,
    reject_on_worker_lost=True,
)
def sync_firm_task(self, firm_id: str, triggered_by: str = "scheduler",
                   entities: List[str] = None, force_full: bool = False):
    """
    Sync all data for a single firm from MyCase API to cache.

    1. Validates the firm exists and has active credentials
    2. Refreshes the OAuth token if needed
    3. Runs the sync via SyncManager
    4. Records the result in sync_history
    5. Schedules the next sync based on firm's sync_frequency
    """
    from platform_db import get_platform_db
    from tenant import TenantContextManager

    db = get_platform_db()
    started_at = datetime.utcnow()
    total_records = 0

    try:
        # Validate firm
        firm = db.get_firm(firm_id)
        if not firm:
            logger.error(f"Firm {firm_id} not found")
            return {"status": "error", "message": "Firm not found"}

        if not firm.mycase_connected:
            logger.warning(f"Firm {firm.name} not connected to MyCase")
            return {"status": "skipped", "message": "MyCase not connected"}

        if firm.subscription_status not in ("trial", "active"):
            logger.info(f"Firm {firm.name} subscription is {firm.subscription_status}, skipping")
            return {"status": "skipped", "message": f"Subscription {firm.subscription_status}"}

        logger.info(f"Starting sync for {firm.name} (triggered by {triggered_by})")

        # Mark sync as running
        db.update_sync_status(firm_id, "running")
        history_id = db.record_sync_start(firm_id, triggered_by=triggered_by,
                                           celery_task_id=self.request.id)

        # Refresh token if needed
        creds = db.get_mycase_credentials(firm_id)
        if creds and creds.token_expires_at:
            if datetime.utcnow() >= creds.token_expires_at - timedelta(minutes=10):
                logger.info(f"Refreshing token for {firm.name}")
                _refresh_token(firm_id, db)

        # Run sync within tenant context
        with TenantContextManager(firm_id=firm_id):
            from sync_mt import SyncManager as MTSyncManager

            manager = MTSyncManager(firm_id=firm_id)
            results = manager.sync_all(
                force_full=force_full,
                entities=entities,
                update_platform_status=False,  # tasks.py manages status/history
            )

            for entity_type, result in results.items():
                total_records += result.inserted + result.updated
                if result.error:
                    logger.warning(f"  {entity_type} error for {firm.name}: {result.error}")

        # Record success
        completed_at = datetime.utcnow()
        duration = (completed_at - started_at).total_seconds()

        db.update_sync_status(firm_id, "completed", records_synced=total_records)
        db.record_sync_complete(
            firm_id,
            records_synced=total_records,
            duration_seconds=duration,
            entity_results={k: {
                "inserted": v.inserted,
                "updated": v.updated,
                "unchanged": v.unchanged,
                "error": v.error,
            } for k, v in results.items()},
        )

        # Schedule next sync
        db.schedule_next_sync(firm_id)

        logger.info(
            f"Sync complete for {firm.name}: {total_records} records "
            f"in {duration:.1f}s"
        )

        return {
            "status": "completed",
            "firm_id": firm_id,
            "records": total_records,
            "duration_seconds": round(duration, 1),
        }

    except SoftTimeLimitExceeded:
        logger.error(f"Sync timed out for firm {firm_id}")
        db.update_sync_status(firm_id, "failed", error_message="Sync timed out (30 min limit)")
        db.record_sync_failure(firm_id, error="Sync timed out")
        db.schedule_next_sync(firm_id, delay_minutes=30)
        return {"status": "timeout", "firm_id": firm_id}

    except Exception as e:
        logger.error(f"Sync failed for firm {firm_id}: {e}", exc_info=True)
        db.update_sync_status(firm_id, "failed", error_message=str(e)[:500])
        db.record_sync_failure(firm_id, error=str(e)[:500])

        retry_delay = 300 * (2 ** self.request.retries)
        db.schedule_next_sync(firm_id, delay_minutes=retry_delay // 60)

        raise self.retry(exc=e, countdown=retry_delay, max_retries=3)


@shared_task(name="tasks.initial_sync_task", bind=True, max_retries=2)
def initial_sync_task(self, firm_id: str):
    """Run first-time sync for a newly connected firm."""
    from platform_db import get_platform_db

    db = get_platform_db()
    logger.info(f"Starting initial sync for firm {firm_id}")

    try:
        result = sync_firm_task.apply(
            args=[firm_id],
            kwargs={"triggered_by": "initial", "force_full": True},
        )

        firm = db.get_firm(firm_id)
        if firm:
            _notify_sync_complete(firm_id, firm.name, result.get("records", 0))

        return result

    except Exception as e:
        logger.error(f"Initial sync failed for {firm_id}: {e}", exc_info=True)
        raise self.retry(exc=e, countdown=60)


# =============================================================================
# 2. TOKEN MANAGEMENT
# =============================================================================

@shared_task(name="tasks.refresh_expiring_tokens", bind=True)
def refresh_expiring_tokens(self):
    """Proactively refresh OAuth tokens expiring within the next hour."""
    from platform_db import get_platform_db

    db = get_platform_db()

    try:
        firms = db.get_firms_with_expiring_tokens(within_minutes=60)

        if not firms:
            return {"refreshed": 0}

        refreshed = 0
        failed = 0

        for firm in firms:
            try:
                _refresh_token(firm["id"], db)
                refreshed += 1
                logger.info(f"Refreshed token for firm {firm.get('name', firm['id'])}")
            except Exception as e:
                failed += 1
                logger.error(f"Token refresh failed for firm {firm['id']}: {e}")

        return {"refreshed": refreshed, "failed": failed}

    except Exception as e:
        logger.error(f"refresh_expiring_tokens failed: {e}", exc_info=True)
        raise


@shared_task(name="tasks.refresh_firm_tokens", bind=True, max_retries=3)
def refresh_firm_tokens(self, firm_id: str):
    """Refresh OAuth tokens for a specific firm."""
    from platform_db import get_platform_db

    db = get_platform_db()

    try:
        _refresh_token(firm_id, db)
        return {"status": "refreshed", "firm_id": firm_id}
    except Exception as e:
        logger.error(f"Token refresh failed for {firm_id}: {e}")
        raise self.retry(exc=e, countdown=60)


def _refresh_token(firm_id: str, db):
    """Internal: refresh a firm's MyCase OAuth token.

    Updates both the platform DB and data/tokens.json so the existing
    dashboard app stays in sync during the migration period.
    """
    import json
    import httpx
    from pathlib import Path
    from config import MYCASE_AUTH_URL, CLIENT_ID, CLIENT_SECRET

    creds = db.get_mycase_credentials(firm_id)
    if not creds:
        raise ValueError(f"No credentials found for firm {firm_id}")

    response = httpx.post(
        f"{MYCASE_AUTH_URL}/oauth/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": creds.refresh_token,
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
        },
        timeout=30,
    )

    if response.status_code != 200:
        raise RuntimeError(
            f"Token refresh failed ({response.status_code}): {response.text}"
        )

    data = response.json()
    new_access = data["access_token"]
    new_refresh = data.get("refresh_token", creds.refresh_token)
    expires_in = data.get("expires_in", 7200)

    # Update platform DB
    db.update_mycase_tokens(
        firm_id=firm_id,
        access_token=new_access,
        refresh_token=new_refresh,
        expires_in=expires_in,
    )

    # Also update tokens.json for the existing dashboard app
    try:
        now = datetime.utcnow()
        tokens_file = Path(__file__).parent / "data" / "tokens.json"
        token_data = {
            "access_token": new_access,
            "token_type": "Bearer",
            "scope": data.get("scope", ""),
            "refresh_token": new_refresh,
            "expires_in": expires_in,
            "saved_at": now.isoformat(),
            "expires_at": (now + timedelta(seconds=expires_in)).isoformat(),
        }
        tokens_file.write_text(json.dumps(token_data, indent=2))
        logger.info(f"Updated tokens.json for firm {firm_id}")
    except Exception as e:
        logger.warning(f"Failed to update tokens.json: {e}")


# =============================================================================
# 3. REPORT GENERATION
# =============================================================================

@shared_task(name="tasks.dispatch_daily_reports", bind=True)
def dispatch_daily_reports(self):
    """Dispatch daily report generation for all active firms."""
    from platform_db import get_platform_db

    db = get_platform_db()

    try:
        firms = db.get_active_firms_list()
        dispatched = 0

        for firm in firms:
            generate_firm_reports.apply_async(
                args=[firm["id"]],
                countdown=dispatched * 10,
            )
            dispatched += 1

        logger.info(f"Dispatched daily reports for {dispatched} firms")
        return {"dispatched": dispatched}

    except Exception as e:
        logger.error(f"dispatch_daily_reports failed: {e}", exc_info=True)
        raise


@shared_task(name="tasks.generate_firm_reports", bind=True, max_retries=2)
def generate_firm_reports(self, firm_id: str):
    """Generate all daily reports for a single firm."""
    from platform_db import get_platform_db
    from tenant import TenantContextManager

    db = get_platform_db()

    try:
        firm = db.get_firm(firm_id)
        if not firm:
            return {"status": "error", "message": "Firm not found"}

        logger.info(f"Generating daily reports for {firm.name}")

        with TenantContextManager(firm_id=firm_id):
            results = {}

            try:
                events_result = _generate_events_reports(firm_id)
                results["events"] = events_result
            except Exception as e:
                logger.error(f"Events report failed for {firm.name}: {e}")
                results["events"] = {"status": "error", "message": str(e)}

        logger.info(f"Reports complete for {firm.name}: {results}")
        return {"status": "completed", "firm_id": firm_id, "results": results}

    except Exception as e:
        logger.error(f"Reports failed for {firm_id}: {e}", exc_info=True)
        raise self.retry(exc=e, countdown=120)


@shared_task(name="tasks.send_events_reports_task", bind=True, max_retries=2)
def send_events_reports_task(self, firm_id: str, days: int = 7):
    """Generate and send individual events reports for a firm."""
    from tenant import TenantContextManager

    try:
        with TenantContextManager(firm_id=firm_id):
            result = _generate_events_reports(firm_id, days=days)
        return result
    except Exception as e:
        logger.error(f"Events reports failed for {firm_id}: {e}")
        raise self.retry(exc=e, countdown=60)


def _generate_events_reports(firm_id: str, days: int = 7) -> Dict[str, Any]:
    """Internal: generate and send individual events reports."""
    try:
        from events_report import send_individual_events_reports
        results = send_individual_events_reports(days=days, dry_run=False)
        sent = sum(1 for v in results.values() if v)
        total = len(results)
        return {"status": "completed", "sent": sent, "total": total}
    except ImportError:
        logger.warning("events_report module not available")
        return {"status": "skipped", "message": "events_report not available"}


def _notify_sync_complete(firm_id: str, firm_name: str, records: int):
    """Notify firm admin that initial sync is complete."""
    from platform_db import get_platform_db

    db = get_platform_db()
    users = db.get_firm_users(firm_id)
    admins = [u for u in users if u.role == "admin"]

    for admin in admins:
        logger.info(
            f"Initial sync complete for {firm_name}: "
            f"{records} records synced. Notify {admin.email}"
        )


# =============================================================================
# 4. MAINTENANCE
# =============================================================================

@shared_task(name="tasks.detect_stale_syncs")
def detect_stale_syncs():
    """Find syncs stuck in 'running' for over 45 minutes and mark them failed."""
    from platform_db import get_platform_db

    db = get_platform_db()

    try:
        stale = db.detect_and_fail_stale_syncs(stale_minutes=45)
        if stale:
            logger.warning(f"Marked {len(stale)} stale syncs as failed: {stale}")
        return {"stale_count": len(stale)}
    except Exception as e:
        logger.error(f"detect_stale_syncs failed: {e}", exc_info=True)
        raise


@shared_task(name="tasks.cleanup_sync_history")
def cleanup_sync_history():
    """Remove sync_history records older than 90 days."""
    from platform_db import get_platform_db

    db = get_platform_db()

    try:
        deleted = db.cleanup_old_sync_history(days=90)
        logger.info(f"Cleaned up {deleted} old sync history records")
        return {"deleted": deleted}
    except Exception as e:
        logger.error(f"cleanup_sync_history failed: {e}", exc_info=True)
        raise


# =============================================================================
# 5. MANUAL / API-TRIGGERED TASKS
# =============================================================================

@shared_task(name="tasks.manual_sync")
def manual_sync(firm_id: str, user_id: str = None, entities: List[str] = None):
    """Manually triggered sync from dashboard or API."""
    from platform_db import get_platform_db

    db = get_platform_db()

    if user_id:
        db.log_audit(firm_id, user_id, "manual_sync", {"entities": entities})

    return sync_firm_task.apply(
        args=[firm_id],
        kwargs={"triggered_by": "manual", "entities": entities},
    )
