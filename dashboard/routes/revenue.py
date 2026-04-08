"""
Revenue dashboard route — admin only.

Shows new monthly revenue (sum of invoice total_amount for cases created in
the month) and new cases by month, with month-over-month performance and a
12-month rolling chart.
"""
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from dashboard.auth import is_authenticated, get_data, get_current_role

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).parent.parent / "templates")


@router.get("/revenue", response_class=HTMLResponse)
async def revenue_dashboard(request: Request):
    """Admin-only revenue dashboard with new cases + new case value KPIs."""
    if not is_authenticated(request):
        return RedirectResponse(url="/login", status_code=303)

    role = get_current_role(request)
    if role != 'admin':
        # Send non-admins to their home page
        if role == 'collections':
            return RedirectResponse(url="/ar", status_code=303)
        if role == 'attorney':
            return RedirectResponse(url="/attorneys", status_code=303)
        return RedirectResponse(url="/", status_code=303)

    data = get_data(request)
    summary = data.get_revenue_summary(months=12)
    by_practice = data.get_revenue_by_practice_area(months=12)

    return templates.TemplateResponse("revenue.html", {
        "request": request,
        "summary": summary,
        "series": summary["series"],
        "by_practice_area": by_practice,
        "username": request.session.get("username"),
        "role": role,
    })
