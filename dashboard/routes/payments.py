"""
Payment analytics routes
"""
from datetime import datetime
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from dashboard.auth import is_authenticated, get_data, get_current_role

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).parent.parent / "templates")


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

    data = get_data(request)
    raw = data.get_payment_analytics_summary(year=year)
    raw_by_attorney = data.get_time_to_payment_by_attorney(year=year)
    raw_by_case_type = data.get_time_to_payment_by_case_type(year=year)
    raw_velocity = data.get_payment_velocity_trend(year=year)

    # Reshape velocity trend: model returns 'billed'/'collected', template expects 'total_billed'/'total_collected'
    velocity_trend = []
    for v in raw_velocity:
        billed = v.get('billed', 0) or v.get('total_billed', 0) or 0
        collected = v.get('collected', 0) or v.get('total_collected', 0) or 0
        velocity_trend.append({
            'month': v.get('month', ''),
            'total_billed': billed,
            'total_collected': collected,
            'collection_rate': round(collected / billed * 100, 1) if billed > 0 else 0,
            'avg_days_to_payment': v.get('avg_days_to_payment', None),
        })

    # Ensure all template-expected keys exist with safe defaults
    total_billed = raw.get('total_billed', 0) or 0
    total_collected = raw.get('total_collected', 0) or 0
    summary = {
        'total_billed': total_billed,
        'total_collected': total_collected,
        'collection_rate': raw.get('collection_rate', 0) or 0,
        'avg_days_to_payment': raw.get('avg_days_to_payment', 0) or 0,
        'total_invoices': raw.get('total_invoices', 0) or 0,
        'paid_in_full_count': raw.get('paid_in_full_count', 0) or 0,
        'total_outstanding': total_billed - total_collected,
        'avg_dpd_outstanding': raw.get('avg_dpd_outstanding', 0) or 0,
    }

    # Enrich attorney rows with computed fields the template expects
    by_attorney = []
    for a in raw_by_attorney:
        billed = a.get('total_billed', 0) or 0
        collected = a.get('total_collected', 0) or 0
        a['collection_rate'] = round(collected / billed * 100, 1) if billed > 0 else 0
        a['avg_days_to_payment'] = a.get('avg_days', 0) or 0
        a.setdefault('min_days', None)
        a.setdefault('max_days', None)
        by_attorney.append(a)

    # Enrich case type rows
    by_case_type = []
    for c in raw_by_case_type:
        billed = c.get('total_billed', 0) or 0
        collected = c.get('total_collected', 0) or 0
        c['collection_rate'] = round(collected / billed * 100, 1) if billed > 0 else 0
        c['avg_days_to_payment'] = c.get('avg_days', 0) or 0
        c.setdefault('min_days', None)
        c.setdefault('max_days', None)
        by_case_type.append(c)

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
        "role": get_current_role(request),
    })
