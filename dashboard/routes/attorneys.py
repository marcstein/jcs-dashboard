"""
Attorney productivity routes
"""
import csv
import io
import math
from datetime import datetime, timedelta
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from dashboard.auth import is_authenticated, get_data, get_current_role, get_current_attorney_name

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).parent.parent / "templates")

# Month abbreviations for sparkline labels
_MONTH_ABBRS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


@router.get("/attorneys", response_class=HTMLResponse)
async def attorneys_dashboard(request: Request, year: int = None, view: str = None):
    """Attorney productivity dashboard.
    Attorney role gets redirected to their own performance page."""
    if not is_authenticated(request):
        return RedirectResponse(url="/login", status_code=303)

    role = get_current_role(request)
    if role == 'collections':
        return RedirectResponse(url="/ar", status_code=303)

    # Attorney role: redirect to their personal performance page
    if role == 'attorney':
        attorney_name = get_current_attorney_name(request)
        if attorney_name:
            return RedirectResponse(url=f"/attorney/{attorney_name}", status_code=303)

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
        "role": get_current_role(request),
    })


@router.get("/attorney/{attorney_name}", response_class=HTMLResponse)
async def attorney_detail_view(request: Request, attorney_name: str, year: int = None):
    """Attorney detail page — gamified performance view for attorney role,
    full billing detail for admin."""
    if not is_authenticated(request):
        return RedirectResponse(url="/login", status_code=303)

    role = get_current_role(request)
    if role == 'collections':
        return RedirectResponse(url="/ar", status_code=303)
    if role == 'attorney':
        current_attorney = get_current_attorney_name(request)
        if current_attorney and current_attorney != attorney_name:
            return RedirectResponse(url=f"/attorney/{current_attorney}", status_code=303)

    data = get_data(request)

    # For attorney role: show gamified performance view (no billing numbers)
    if role == 'attorney':
        perf = data.get_single_attorney_performance(attorney_name)
        if perf:
            return _render_performance_page(request, role, perf, data, attorney_name)

    # For admin role (or no target data): show full billing detail
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
        "role": role,
    })


def _render_performance_page(request, role, perf, data, attorney_name):
    """Render the gamified performance template with gauge calculations."""
    # SVG gauge math: circumference of circle r=96
    circumference = 2 * math.pi * 96  # ~603.19
    # Cap the fill at 120% for visual (don't wrap around)
    fill_pct = min(perf["pct_of_target"] / 100, 1.2)
    dasharray = circumference
    dashoffset = circumference * (1 - fill_pct)

    # Monthly sparkline: generate month labels for last 12 months
    today = datetime.now()
    months = []
    for i in range(12):
        dt = today - timedelta(days=30 * (11 - i))
        months.append(_MONTH_ABBRS[dt.month - 1])

    # Max value for sparkline scaling (at least 120 so target line at 100 looks right)
    max_spark_pct = max(max(perf["monthly_pcts"], default=0), 120)

    # Get active cases list for the attorney
    try:
        from db.connection import get_connection
        import psycopg2.extensions
        firm_id = request.session.get("firm_id", "jcs_law")
        with get_connection() as conn:
            cur = conn.cursor(cursor_factory=psycopg2.extensions.cursor)
            cur.execute("""
                SELECT id, name, practice_area, case_number, status, created_at
                FROM cached_cases
                WHERE firm_id = %s AND lead_attorney_name = %s AND status = 'open'
                ORDER BY created_at DESC
            """, (firm_id, attorney_name))
            active_cases = [{
                'id': r[0], 'name': r[1], 'practice_area': r[2],
                'case_number': r[3], 'status': r[4], 'date_opened': r[5],
            } for r in cur.fetchall()]
    except Exception:
        active_cases = []

    return templates.TemplateResponse("attorney_performance.html", {
        "request": request,
        "role": role,
        "perf": perf,
        "gauge_dasharray": f"{circumference:.1f}",
        "gauge_dashoffset": f"{dashoffset:.1f}",
        "months": months,
        "max_spark_pct": max_spark_pct,
        "active_cases": active_cases,
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
