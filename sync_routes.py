"""
Sync Management API Routes

REST endpoints for:
- Customer: Sync status, manual refresh, frequency settings
- Admin: Sync health dashboard, manual sync triggers, history

Mount in your FastAPI app:
    from sync_routes import router as sync_router
    app.include_router(sync_router, prefix="/api/sync")
"""
from datetime import datetime, timedelta
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel

router = APIRouter(tags=["sync"])


# ---------------------------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------------------------

class SyncStatusResponse(BaseModel):
    last_sync_at: Optional[str] = None
    last_sync_status: Optional[str] = None
    last_sync_records: Optional[int] = None
    last_sync_duration_seconds: Optional[float] = None
    last_sync_error: Optional[str] = None
    next_sync_at: Optional[str] = None
    sync_frequency_minutes: Optional[int] = None
    recent_history: list = []


class SyncHealthResponse(BaseModel):
    healthy: int = 0
    failed: int = 0
    running: int = 0
    never_synced: int = 0
    overdue: int = 0
    total: int = 0


class ManualSyncRequest(BaseModel):
    entities: Optional[List[str]] = None
    force_full: bool = False


class UpdateFrequencyRequest(BaseModel):
    sync_frequency_minutes: int


class SyncHistoryItem(BaseModel):
    id: int
    status: str
    triggered_by: str
    started_at: str
    completed_at: Optional[str] = None
    duration_seconds: Optional[float] = None
    records_synced: int = 0
    error_message: Optional[str] = None


# ---------------------------------------------------------------------------
# Auth Dependencies - Uses dashboard session auth
# ---------------------------------------------------------------------------

async def get_current_firm_id(request: "Request"):
    """
    Extract firm_id from the authenticated request.

    In multi-tenant mode, reads from tenant context (JWT/session).
    In single-tenant mode (JCS dashboard), returns the default firm.
    """
    from fastapi import Request as _Request
    from dashboard.auth import is_authenticated

    if not is_authenticated(request):
        raise HTTPException(status_code=401, detail="Not authenticated")

    # Try multi-tenant context first
    try:
        from tenant import get_current_firm_id as _get_firm_id
        return _get_firm_id()
    except (ValueError, ImportError):
        pass

    # Single-tenant fallback: get the first active firm, or use default
    try:
        from platform_db import get_platform_db
        db = get_platform_db()
        firms = db.get_active_firms_list()
        if firms:
            return firms[0]["id"]
    except Exception:
        pass

    raise HTTPException(status_code=404, detail="No firm configured")


async def require_admin_auth(request: "Request"):
    """Require admin role for platform-wide operations."""
    from fastapi import Request as _Request
    from dashboard.auth import is_authenticated, is_admin

    if not is_authenticated(request):
        raise HTTPException(status_code=401, detail="Not authenticated")
    if not is_admin(request):
        raise HTTPException(status_code=403, detail="Admin access required")
    return request.session.get("username")


async def _require_admin_legacy():
    """Legacy: Require admin via tenant context (multi-tenant mode)."""
    from tenant import get_current_context
    try:
        ctx = get_current_context()
        if ctx.user_role != "admin":
            raise HTTPException(status_code=403, detail="Admin access required")
        return ctx
    except ValueError:
        raise HTTPException(status_code=401, detail="Not authenticated")


# ---------------------------------------------------------------------------
# Customer-Facing Endpoints
# ---------------------------------------------------------------------------

@router.get("/status", response_model=SyncStatusResponse)
async def get_sync_status(firm_id: str = Depends(get_current_firm_id)):
    """Get sync status for the current firm."""
    from platform_db import get_platform_db

    db = get_platform_db()
    result = db.get_firm_sync_dashboard(firm_id)

    if not result:
        raise HTTPException(status_code=404, detail="Firm not found")

    return result


@router.post("/trigger")
async def trigger_manual_sync(
    request: ManualSyncRequest,
    firm_id: str = Depends(get_current_firm_id),
):
    """
    Manually trigger a sync for the current firm.
    Rate limited to 1 manual sync per 5 minutes per firm.
    """
    from platform_db import get_platform_db
    from tasks import sync_firm_task

    db = get_platform_db()

    # Check if already running
    status = db.get_sync_status(firm_id)
    if status.get("status") == "running":
        raise HTTPException(
            status_code=429,
            detail="A sync is already in progress. Please wait for it to complete."
        )

    # Check cooldown
    last_sync = status.get("completed_at")
    if last_sync:
        if isinstance(last_sync, str):
            last_sync = datetime.fromisoformat(last_sync)
        if datetime.utcnow() - last_sync < timedelta(minutes=5):
            raise HTTPException(
                status_code=429,
                detail="Please wait at least 5 minutes between manual syncs."
            )

    task = sync_firm_task.apply_async(
        args=[firm_id],
        kwargs={
            "triggered_by": "manual",
            "entities": request.entities,
            "force_full": request.force_full,
        },
    )

    return {
        "message": "Sync queued successfully",
        "task_id": task.id,
        "estimated_duration": "2-5 minutes",
    }


@router.get("/history", response_model=List[SyncHistoryItem])
async def get_sync_history(
    firm_id: str = Depends(get_current_firm_id),
    limit: int = Query(default=20, le=100),
):
    """Get sync history for the current firm."""
    from platform_db import get_platform_db

    db = get_platform_db()
    return db.get_sync_history(firm_id, limit=limit)


@router.put("/frequency")
async def update_sync_frequency(
    request: UpdateFrequencyRequest,
    firm_id: str = Depends(get_current_firm_id),
):
    """
    Update sync frequency for the current firm.
    Allowed values: 60, 120, 240, 480 minutes.
    Hourly sync (60 min) requires Professional tier.
    """
    allowed = [60, 120, 240, 480]
    if request.sync_frequency_minutes not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Frequency must be one of: {allowed} minutes"
        )

    from platform_db import get_platform_db

    db = get_platform_db()

    if request.sync_frequency_minutes == 60:
        firm = db.get_firm(firm_id)
        if firm and firm.subscription_tier != "professional":
            raise HTTPException(
                status_code=403,
                detail="Hourly sync requires Professional tier"
            )

    with db._get_connection() as conn:
        cursor = conn.cursor()
        if db.use_postgres:
            cursor.execute(
                "UPDATE firms SET sync_frequency_minutes = %s WHERE id = %s",
                (request.sync_frequency_minutes, firm_id),
            )
        else:
            cursor.execute(
                "UPDATE firms SET sync_frequency_minutes = ? WHERE id = ?",
                (request.sync_frequency_minutes, firm_id),
            )

    db.schedule_next_sync(firm_id)

    return {
        "message": f"Sync frequency updated to every {request.sync_frequency_minutes} minutes",
        "sync_frequency_minutes": request.sync_frequency_minutes,
    }


# ---------------------------------------------------------------------------
# Admin Endpoints
# ---------------------------------------------------------------------------

@router.get("/admin/health", response_model=SyncHealthResponse)
async def admin_sync_health(admin=Depends(require_admin_auth)):
    """Get sync health summary across all firms (admin only)."""
    from platform_db import get_platform_db

    db = get_platform_db()
    return db.get_sync_health_summary()


@router.get("/admin/firms")
async def admin_list_firm_sync_status(
    admin=Depends(require_admin_auth),
    status_filter: Optional[str] = Query(default=None),
):
    """List all firms with their sync status (admin only)."""
    from platform_db import get_platform_db

    db = get_platform_db()

    with db._get_connection() as conn:
        cursor = conn.cursor()

        if db.use_postgres:
            cursor.execute("""
                SELECT id, name, subscription_status, subscription_tier,
                       last_sync_at, last_sync_status, last_sync_records,
                       last_sync_error, next_sync_at, sync_frequency_minutes
                FROM firms
                WHERE subscription_status IN ('trial', 'active')
                AND mycase_connected = TRUE
                ORDER BY last_sync_at DESC NULLS LAST
            """)
        else:
            cursor.execute("""
                SELECT id, name, subscription_status, subscription_tier,
                       last_sync_at, last_sync_status, last_sync_records,
                       last_sync_error, next_sync_at, sync_frequency_minutes
                FROM firms
                WHERE subscription_status IN ('trial', 'active')
                AND mycase_connected = 1
                ORDER BY last_sync_at DESC
            """)

        firms = [dict(row) for row in cursor.fetchall()]

    if status_filter == "failed":
        firms = [f for f in firms if f.get("last_sync_status") == "failed"]
    elif status_filter == "overdue":
        now = datetime.utcnow()
        firms = [f for f in firms if f.get("next_sync_at") and
                 datetime.fromisoformat(str(f["next_sync_at"])) < now]
    elif status_filter == "healthy":
        firms = [f for f in firms if f.get("last_sync_status") == "completed"]

    return {"firms": firms, "count": len(firms)}


@router.post("/admin/sync/{firm_id}")
async def admin_trigger_sync(
    firm_id: str,
    request: ManualSyncRequest = ManualSyncRequest(),
    admin=Depends(require_admin_auth),
):
    """Trigger sync for any firm (admin only). No rate limiting."""
    from tasks import sync_firm_task

    task = sync_firm_task.apply_async(
        args=[firm_id],
        kwargs={
            "triggered_by": "manual",
            "entities": request.entities,
            "force_full": request.force_full,
        },
    )

    return {"message": f"Sync queued for firm {firm_id}", "task_id": task.id}


@router.post("/admin/sync-all")
async def admin_trigger_all_syncs(admin=Depends(require_admin_auth)):
    """Force sync for all active firms (admin only)."""
    from tasks import dispatch_pending_syncs

    result = dispatch_pending_syncs.apply_async()
    return {"message": "Sync dispatch queued", "task_id": result.id}
