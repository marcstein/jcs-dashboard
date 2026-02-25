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

    # All open invoices with balance due — across ALL years, no year filter
    open_invoices = data.get_open_invoices_list(min_days_overdue=0)
    total_open_balance = sum(inv['balance_due'] for inv in open_invoices)
    past_due_invoices = [inv for inv in open_invoices if inv['days_overdue'] > 0]

    return templates.TemplateResponse("ar.html", {
        "request": request,
        "year": year,
        "current_year": current_year,
        "available_years": available_years,
        "summary": summary,
        "ar_aging": ar_aging,
        "trend": trend,
        "plans": plans,
        "open_invoices": open_invoices,
        "past_due_invoices": past_due_invoices,
        "total_open_balance": total_open_balance,
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

    raw = data.get_dunning_summary()
    raw_queue = data.get_dunning_queue(stage=stage)
    history = data.get_dunning_history(limit=20)

    # Reshape summary keys to match template expectations
    stage_names = {1: 'Friendly Reminder', 2: 'Past Due Notice',
                   3: 'Final Warning', 4: 'Collections Referral'}
    stage_days = {1: '5-14', 2: '15-29', 3: '30-44', 4: '45+'}
    stages = {}
    for s_num in [1, 2, 3, 4]:
        s_data = raw.get('by_stage', {}).get(s_num, {})
        stages[s_num] = {
            'name': stage_names.get(s_num, f'Stage {s_num}'),
            'days': stage_days.get(s_num, ''),
            'count': s_data.get('count', 0) or 0,
            'balance': s_data.get('total', 0) or 0,
        }

    summary = {
        'total_count': raw.get('total_count', 0) or 0,
        'total_balance': raw.get('total_amount', 0) or 0,
        'stages': stages,
    }

    # Reshape queue items to match template field names
    queue = []
    for inv in raw_queue:
        s = inv.get('stage', 1) or 1
        queue.append({
            'invoice_number': inv.get('invoice_id', ''),
            'case_name': inv.get('case_name', ''),
            'attorney': inv.get('attorney', inv.get('contact_name', '')),
            'balance_due': inv.get('balance_due', 0) or 0,
            'days_overdue': inv.get('days_delinquent', 0) or 0,
            'dunning_stage': s,
            'stage_name': stage_names.get(s, f'Stage {s}'),
            'due_date': inv.get('last_notice_date', ''),
        })

    return templates.TemplateResponse("dunning.html", {
        "request": request,
        "summary": summary,
        "queue": queue,
        "history": history,
        "current_stage": stage,
        "username": request.session.get("username"),
    })
