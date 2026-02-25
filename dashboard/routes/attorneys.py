"""
Attorney productivity routes
"""
import csv
import io
from datetime import datetime
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from dashboard.auth import is_authenticated, get_data

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).parent.parent / "templates")


@router.get("/attorneys", response_class=HTMLResponse)
async def attorneys_dashboard(request: Request, year: int = None, view: str = None):
    """Attorney productivity dashboard."""
    if not is_authenticated(request):
        return RedirectResponse(url="/login", status_code=303)

    data = get_data(request)
    current_year = datetime.now().year
    available_years = [2025, 2026]

    # View modes: None/year-based, "combined", "rolling6"
    if view == "combined":
        productivity = data.get_attorney_productivity_combined([2025, 2026])
        aging = data.get_attorney_invoice_aging_combined([2025, 2026])
        year = None
    elif view == "rolling6":
        productivity = data.get_attorney_productivity_rolling(months=6)
        aging = data.get_attorney_invoice_aging_rolling(months=6)
        year = None
    else:
        if year is None:
            year = current_year
        productivity = data.get_attorney_productivity_data(year=year)
        aging = data.get_attorney_invoice_aging(year=year)

    # Merge aging data into productivity and sanitize None→0
    empty_aging = {
        'paid_full': 0, 'dpd_1_30': 0, 'dpd_31_60': 0,
        'dpd_61_90': 0, 'dpd_91_120': 0, 'dpd_121_180': 0,
        'dpd_over_180': 0, 'needs_calls': 0,
    }
    numeric_fields = [
        'active_cases', 'closed_mtd', 'closed_ytd',
        'total_billed', 'total_collected', 'total_outstanding', 'collection_rate',
    ]
    aging_by_id = {a['attorney_id']: a for a in aging}
    for p in productivity:
        for f in numeric_fields:
            if p.get(f) is None:
                p[f] = 0

        a = aging_by_id.get(p['attorney_id'], dict(empty_aging))
        a['needs_calls'] = (
            (a.get('dpd_61_90') or 0)
            + (a.get('dpd_91_120') or 0)
            + (a.get('dpd_121_180') or 0)
        )
        for k, v in empty_aging.items():
            a.setdefault(k, v)
        p['aging'] = a

    return templates.TemplateResponse("attorneys.html", {
        "request": request,
        "year": year,
        "view": view,
        "current_year": current_year,
        "available_years": available_years,
        "attorneys": productivity,
        "username": request.session.get("username"),
    })


@router.get("/attorney/{attorney_name}", response_class=HTMLResponse)
async def attorney_detail_view(request: Request, attorney_name: str, year: int = None):
    """Attorney detail page with call list."""
    if not is_authenticated(request):
        return RedirectResponse(url="/login", status_code=303)

    # Default to current year if not specified
    current_year = datetime.now().year
    if year is None:
        year = current_year
    available_years = [2025, 2026]

    data = get_data(request)
    detail = data.get_attorney_detail(attorney_name, year=year)

    return templates.TemplateResponse("attorney_detail.html", {
        "request": request,
        "year": year,
        "current_year": current_year,
        "available_years": available_years,
        "attorney": detail,
        "username": request.session.get("username"),
    })


@router.get("/attorneys/export")
async def attorneys_export_csv(request: Request, year: int = None):
    """Export attorney productivity data to CSV."""
    if not is_authenticated(request):
        return RedirectResponse(url="/login", status_code=303)

    # Default to current year if not specified
    current_year = datetime.now().year
    if year is None:
        year = current_year

    data = get_data(request)
    productivity = data.get_attorney_productivity_data(year=year)
    aging = data.get_attorney_invoice_aging(year=year)

    # Merge aging data into productivity
    aging_by_id = {a['attorney_id']: a for a in aging}
    for p in productivity:
        a = aging_by_id.get(p['attorney_id'], {})
        a.setdefault('paid_full', 0)
        a.setdefault('dpd_1_30', 0)
        a.setdefault('dpd_31_60', 0)
        a.setdefault('dpd_61_90', 0)
        a.setdefault('dpd_91_120', 0)
        a.setdefault('dpd_121_180', 0)
        a.setdefault('dpd_over_180', 0)
        p['aging'] = a

    # Create CSV in memory
    output = io.StringIO()
    writer = csv.writer(output)

    # Header row
    writer.writerow([
        'Attorney',
        'Active Cases',
        'Closed MTD',
        'Closed YTD',
        f'Billed {year}',
        f'Collected {year}',
        'Total Outstanding',
        'Collection Rate %',
        'Paid in Full',
        '1-30 DPD',
        '31-60 DPD',
        '61-90 DPD',
        '91-120 DPD',
        '121-180 DPD',
        '180+ DPD',
        'Total Invoices 60-180 DPD (Needs Calls)',
    ])

    # Data rows - only attorneys with active cases
    for atty in productivity:
        if atty.get('active_cases', 0) > 0:
            aging = atty.get('aging', {})
            needs_calls = (
                (aging.get('dpd_61_90') or 0) +
                (aging.get('dpd_91_120') or 0) +
                (aging.get('dpd_121_180') or 0)
            )
            writer.writerow([
                atty.get('attorney_name', ''),
                atty.get('active_cases', 0),
                atty.get('closed_mtd', 0),
                atty.get('closed_ytd', 0),
                atty.get('total_billed', 0),
                atty.get('total_collected', 0),
                atty.get('total_outstanding', 0),
                round(atty.get('collection_rate', 0), 1),
                aging.get('paid_full', 0),
                aging.get('dpd_1_30', 0),
                aging.get('dpd_31_60', 0),
                aging.get('dpd_61_90', 0),
                aging.get('dpd_91_120', 0),
                aging.get('dpd_121_180', 0),
                aging.get('dpd_over_180', 0),
                needs_calls,
            ])

    # Generate filename with year and date
    today = datetime.now().strftime('%Y-%m-%d')
    filename = f"attorney_productivity_{year}_{today}.csv"

    # Return as downloadable CSV
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
