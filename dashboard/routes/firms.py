"""
Firm management routes: Admin-only firm configuration UI.

Routes:
    GET  /firms          — List all firms (admin only)
    GET  /firms/{id}     — View/edit firm settings
    POST /firms/create   — Create a new firm
    POST /firms/{id}/update — Update firm settings
    GET  /api/firms       — JSON list of firms
    GET  /api/firms/{id}  — JSON firm details
"""
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from dashboard.auth import is_authenticated, get_current_role

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).parent.parent / "templates")


def _require_admin(request: Request):
    """Check authentication and admin role. Returns error response or None."""
    if not is_authenticated(request):
        return RedirectResponse(url="/login", status_code=303)
    if get_current_role(request) != "admin":
        return HTMLResponse("Forbidden: Admin access required", status_code=403)
    return None


# ── HTML Routes ──────────────────────────────────────────────────────

@router.get("/firms", response_class=HTMLResponse)
async def firms_list(request: Request):
    """List all firms (admin only)."""
    err = _require_admin(request)
    if err:
        return err

    from db.firms import list_firms
    all_firms = list_firms(active_only=False)

    return templates.TemplateResponse("firms.html", {
        "request": request,
        "firms": all_firms,
        "role": get_current_role(request),
        "username": request.session.get("username"),
    })


@router.get("/firms/{firm_id}", response_class=HTMLResponse)
async def firm_detail(request: Request, firm_id: str):
    """View/edit a firm's settings."""
    err = _require_admin(request)
    if err:
        return err

    from firm_settings import FirmSettings
    try:
        fs = FirmSettings(firm_id)
    except ValueError:
        return HTMLResponse(f"Firm '{firm_id}' not found", status_code=404)

    return templates.TemplateResponse("firm_detail.html", {
        "request": request,
        "firm": fs.firm,
        "firm_info": fs.get_firm_info(),
        "dunning_config": fs.get_dunning_config(),
        "sync_config": fs.get_sync_config(),
        "schedule_config": fs.get_schedule_config(),
        "has_sendgrid": bool(fs.get_sendgrid_key()),
        "has_slack": bool(fs.get_slack_webhook()),
        "has_twilio": fs.has_twilio(),
        "is_mycase_connected": fs.is_mycase_connected(),
        "subscription_status": fs.get_subscription_status(),
        "subscription_tier": fs.get_subscription_tier(),
        "role": get_current_role(request),
        "username": request.session.get("username"),
    })


@router.post("/firms/create")
async def create_firm(request: Request, name: str = Form(...), firm_id: str = Form(...)):
    """Create a new firm."""
    err = _require_admin(request)
    if err:
        return err

    from db.firms import upsert_firm
    upsert_firm(firm_id=firm_id, name=name, subscription_status="trial")
    return RedirectResponse(url=f"/firms/{firm_id}", status_code=303)


@router.post("/firms/{firm_id}/update")
async def update_firm(request: Request, firm_id: str):
    """Update firm settings from form submission."""
    err = _require_admin(request)
    if err:
        return err

    form = await request.form()
    from db.connection import get_connection
    from db.firms import update_firm_notification_config
    from firm_settings import clear_settings_cache
    import json

    # Update branding columns
    branding = {}
    for key in ("firm_phone", "firm_email", "firm_website"):
        val = form.get(key, "").strip()
        if val:
            branding[key] = val

    firm_name = form.get("name", "").strip()

    if branding or firm_name:
        with get_connection() as conn:
            cur = conn.cursor()
            sets = []
            vals = []
            if firm_name:
                sets.append("name = %s")
                vals.append(firm_name)
            for k, v in branding.items():
                sets.append(f"{k} = %s")
                vals.append(v)
            sets.append("updated_at = CURRENT_TIMESTAMP")
            vals.append(firm_id)
            cur.execute(f"UPDATE firms SET {', '.join(sets)} WHERE id = %s", vals)
            conn.commit()

    # Update notification config JSONB keys
    nc_updates = {}
    nc_keys = [
        "sendgrid_api_key", "dunning_from_email", "dunning_from_name",
        "slack_webhook_url", "twilio_account_sid", "twilio_auth_token",
        "twilio_from_number",
    ]
    for key in nc_keys:
        val = form.get(key, "").strip()
        if val:
            nc_updates[key] = val

    if nc_updates:
        update_firm_notification_config(firm_id, **nc_updates)

    clear_settings_cache(firm_id)
    return RedirectResponse(url=f"/firms/{firm_id}?saved=1", status_code=303)


# ── JSON API Routes ──────────────────────────────────────────────────

@router.get("/api/firms")
async def api_firms_list(request: Request):
    """JSON list of firms."""
    if not is_authenticated(request):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    if get_current_role(request) != "admin":
        return JSONResponse({"error": "Forbidden"}, status_code=403)

    from db.firms import list_firms
    return JSONResponse(list_firms(active_only=False))


@router.get("/api/firms/{firm_id}")
async def api_firm_detail(request: Request, firm_id: str):
    """JSON firm details."""
    if not is_authenticated(request):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    if get_current_role(request) != "admin":
        return JSONResponse({"error": "Forbidden"}, status_code=403)

    from firm_settings import FirmSettings
    try:
        fs = FirmSettings(firm_id)
    except ValueError:
        return JSONResponse({"error": f"Firm '{firm_id}' not found"}, status_code=404)

    return JSONResponse({
        "firm_info": fs.get_firm_info(),
        "dunning_config": fs.get_dunning_config(),
        "sync_config": fs.get_sync_config(),
        "has_sendgrid": bool(fs.get_sendgrid_key()),
        "has_slack": bool(fs.get_slack_webhook()),
        "has_twilio": fs.has_twilio(),
        "is_mycase_connected": fs.is_mycase_connected(),
        "subscription_status": fs.get_subscription_status(),
    })
