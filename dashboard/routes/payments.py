"""
Payment analytics routes
"""
from datetime import datetime
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from dashboard.auth import is_authenticated
from dashboard.models import DashboardData

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).parent.parent / "templates")
data = DashboardData()


@router.get("/payments", response_class=HTMLResponse)
async def payments_analytics(request: Request, year: int = None):
    """Payment analytics dashboard - time to payment by attorney and case type."""
    if not is_authenticated(request):
        return RedirectResponse(url="/login", status_code=303)

    # Default to current year if not specified
    current_year = datetime.now().year
    if year is None:
        year = current_year
    available_years = [2025, 2026]

    summary = data.get_payment_analytics_summary(year=year)
    by_attorney = data.get_time_to_payment_by_attorney(year=year)
    by_case_type = data.get_time_to_payment_by_case_type(year=year)
    velocity_trend = data.get_payment_velocity_trend(year=year)

    return templates.TemplateResponse("payments.html", {
        "request": request,
        "year": year,
        "current_year": current_year,
        "available_years": available_years,
        "summary": summary,
        "by_attorney": by_attorney,
        "by_case_type": by_case_type,
        "velocity_trend": velocity_trend,
        "username": request.session.get("username"),
    })
