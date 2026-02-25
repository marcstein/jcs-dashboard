"""
Payment promises tracking routes
"""
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from dashboard.auth import is_authenticated, get_data

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).parent.parent / "templates")


@router.get("/promises", response_class=HTMLResponse)
async def promises_dashboard(request: Request, status: str = None):
    """Payment promises tracking dashboard."""
    if not is_authenticated(request):
        return RedirectResponse(url="/login", status_code=303)

    data = get_data(request)
    raw = data.get_promises_summary()
    promises = data.get_promises_list(status=status)

    # Reshape model keys to match template expectations
    summary = {
        'total_pending': raw.get('pending_count', 0) or 0,
        'due_today': raw.get('due_today', 0) or 0,
        'overdue': raw.get('overdue_count', 0) or 0,
        'upcoming_7_days': raw.get('upcoming_7_days', 0) or 0,
        'kept_rate': raw.get('keep_rate', 0) or 0,
        'kept_count': raw.get('kept_count', 0) or 0,
        'broken_count': raw.get('broken_count', 0) or 0,
        'total_promised': raw.get('pending_total', 0) or 0,
        'total_collected': raw.get('kept_total', 0) or 0,
    }

    return templates.TemplateResponse("promises.html", {
        "request": request,
        "summary": summary,
        "promises": promises,
        "current_filter": status,
        "username": request.session.get("username"),
    })
