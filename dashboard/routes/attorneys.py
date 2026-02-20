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

from dashboard.auth import is_authenticated
from dashboard.models import DashboardData

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).parent.parent / "templates")
data = DashboardData()


@router.get("/attorneys", response_class=HTMLResponse)
async def attorneys_dashboard(request: Request, year: int = None):
    """Attorney productivity dashboard."""
    if not is_authenticated(request):
        return RedirectResponse(url="/login", status_code=303)

    # Default to current year if not specified
    current_year = datetime.now().year
    if year is None:
        year = current_year
    available_years = [2025, 2026]

    productivity = data.get_attorney_productivity_data(year=year)
    aging = data.get_attorney_invoice_aging(year=year)

    # Merge aging data into productivity
    aging_by_id = {a['attorney_id']: a for a in aging}
    for p in productivity:
        a = aging_by_id.get(p['attorney_id'], {})
        p['aging'] = a

    return templates.TemplateResponse("attorneys.html", {
        "request": request,
        "year": year,
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

    productivity = data.get_attorney_productivity_data(year=year)
    aging = data.get_attorney_invoice_aging(year=year)

    # Merge aging data into productivity
    aging_by_id = {a['attorney_id']: a for a in aging}
    for p in productivity:
        a = aging_by_id.get(p['attorney_id'], {})
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
