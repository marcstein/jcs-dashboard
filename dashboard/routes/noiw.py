"""
NOIW pipeline routes
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


@router.get("/noiw", response_class=HTMLResponse)
async def noiw_pipeline(request: Request, status: str = None):
    """NOIW Pipeline page."""
    if not is_authenticated(request):
        return RedirectResponse(url="/login", status_code=303)

    pipeline = data.get_noiw_pipeline(status_filter=status)
    summary = data.get_noiw_summary()

    return templates.TemplateResponse("noiw.html", {
        "request": request,
        "pipeline": pipeline,
        "summary": summary,
        "current_filter": status,
        "username": request.session.get("username"),
    })
