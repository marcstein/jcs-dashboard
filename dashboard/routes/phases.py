"""
Case phases routes
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


@router.get("/phases", response_class=HTMLResponse)
async def phases_dashboard(request: Request, phase: str = None):
    """Case Phases dashboard showing phase distribution and stalled cases."""
    if not is_authenticated(request):
        return RedirectResponse(url="/login", status_code=303)

    summary = data.get_phases_summary()
    stalled = data.get_stalled_cases(threshold_days=30)
    velocity = data.get_phase_velocity()
    by_case_type = data.get_phase_by_case_type()

    # If a specific phase is selected, get cases in that phase
    phase_cases = []
    if phase:
        phase_cases = data.get_cases_in_phase(phase, limit=50)

    return templates.TemplateResponse("phases.html", {
        "request": request,
        "summary": summary,
        "stalled": stalled,
        "velocity": velocity,
        "by_case_type": by_case_type,
        "current_phase": phase,
        "phase_cases": phase_cases,
        "username": request.session.get("username"),
    })
