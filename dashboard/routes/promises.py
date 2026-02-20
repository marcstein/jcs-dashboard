"""
Payment promises tracking routes
"""
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from dashboard.auth import is_authenticated
from dashboard.models import DashboardData

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).parent.parent / "templates")
data = DashboardData()


@router.get("/promises", response_class=HTMLResponse)
async def promises_dashboard(request: Request, status: str = None):
    """Payment promises tracking dashboard."""
    if not is_authenticated(request):
        return RedirectResponse(url="/login", status_code=303)

    summary = data.get_promises_summary()
    promises = data.get_promises_list(status=status)

    return templates.TemplateResponse("promises.html", {
        "request": request,
        "summary": summary,
        "promises": promises,
        "current_filter": status,
        "username": request.session.get("username"),
    })
