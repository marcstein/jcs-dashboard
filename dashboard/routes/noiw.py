"""
NOIW pipeline routes

Shows all past-due invoices (30+ days) across ALL years from cached_invoices,
plus the formal NOIW tracking pipeline from noiw_tracking table.
"""
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from dashboard.auth import is_authenticated, get_data, get_current_role

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).parent.parent / "templates")


@router.get("/noiw", response_class=HTMLResponse)
async def noiw_pipeline(request: Request, status: str = None):
    """NOIW Pipeline page.

    Shows all open invoices 30+ days past due (all years) from cached_invoices,
    plus formal NOIW tracking status from noiw_tracking table.
    """
    if not is_authenticated(request):
        return RedirectResponse(url="/login", status_code=303)

    role = get_current_role(request)
    if role == 'attorney':
        return RedirectResponse(url="/attorneys", status_code=303)

    data = get_data(request)

    # Get formal NOIW pipeline (for status tracking)
    pipeline = data.get_noiw_pipeline(status_filter=status)
    summary = data.get_noiw_summary()

    # Also get ALL open invoices 30+ days past due from cached_invoices (all years)
    all_past_due = data.get_open_invoices_list(min_days_overdue=30)
    total_past_due_balance = sum(inv['balance_due'] for inv in all_past_due)

    # Build aging buckets from the live invoice data
    live_summary = {
        'total_active': len(all_past_due),
        'total_balance': total_past_due_balance,
        'bucket_30_60': len([i for i in all_past_due if 30 <= i['days_overdue'] < 60]),
        'bucket_60_90': len([i for i in all_past_due if 60 <= i['days_overdue'] < 90]),
        'bucket_90_180': len([i for i in all_past_due if 90 <= i['days_overdue'] < 180]),
        'bucket_180_plus': len([i for i in all_past_due if i['days_overdue'] >= 180]),
    }

    # Use live invoice data as the summary if it has more cases than noiw_tracking
    if live_summary['total_active'] > (summary.get('total_active', 0) or 0):
        summary.update(live_summary)

    return templates.TemplateResponse("noiw.html", {
        "request": request,
        "pipeline": pipeline,
        "all_past_due": all_past_due,
        "total_past_due_balance": total_past_due_balance,
        "summary": summary,
        "current_filter": status,
        "username": request.session.get("username"),
        "role": role,
    })
