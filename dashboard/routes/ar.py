"""
A/R and Collections routes: AR dashboard, dunning, collections
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


@router.get("/ar", response_class=HTMLResponse)
async def ar_dashboard(request: Request, year: int = None):
    """AR/Collections dashboard."""
    if not is_authenticated(request):
        return RedirectResponse(url="/login", status_code=303)

    # Default to current year if not specified
    current_year = datetime.now().year
    if year is None:
        year = current_year
    available_years = [2025, 2026]

    summary = data.get_daily_collections_summary(year=year)
    ar_aging = data.get_ar_aging_breakdown(year=year)
    trend = data.get_collections_trend(days_back=30)
    plans = data.get_payment_plans_summary()

    return templates.TemplateResponse("ar.html", {
        "request": request,
        "year": year,
        "current_year": current_year,
        "available_years": available_years,
        "summary": summary,
        "ar_aging": ar_aging,
        "trend": trend,
        "plans": plans,
        "username": request.session.get("username"),
    })


@router.get("/wonky", response_class=HTMLResponse)
async def wonky_invoices(request: Request):
    """Wonky invoices page."""
    if not is_authenticated(request):
        return RedirectResponse(url="/login", status_code=303)

    invoices = data.get_wonky_invoices()

    return templates.TemplateResponse("wonky.html", {
        "request": request,
        "invoices": invoices,
        "username": request.session.get("username"),
    })


@router.get("/dunning", response_class=HTMLResponse)
async def dunning_preview(request: Request, stage: int = None):
    """Dunning notices preview and approval dashboard."""
    if not is_authenticated(request):
        return RedirectResponse(url="/login", status_code=303)

    summary = data.get_dunning_summary()
    queue = data.get_dunning_queue(stage=stage)
    history = data.get_dunning_history(limit=20)

    return templates.TemplateResponse("dunning.html", {
        "request": request,
        "summary": summary,
        "queue": queue,
        "history": history,
        "current_stage": stage,
        "username": request.session.get("username"),
    })
