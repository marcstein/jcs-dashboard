"""
Trust-to-Operating Transfer Report route.
"""
from datetime import datetime
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
import io
import csv

from dashboard.auth import is_authenticated, get_data, get_current_role
from trust_transfer import (
    generate_trust_transfer_report,
    FEE_SCHEDULES,
    PHASE_ORDER,
    PHASE_LABELS,
)

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).parent.parent / "templates")


@router.get("/trust", response_class=HTMLResponse)
async def trust_report_page(request: Request, attorney: str = None, phase: str = None):
    """Trust-to-operating transfer report page."""
    if not is_authenticated(request):
        return RedirectResponse(url="/login", status_code=303)

    role = get_current_role(request)
    if role == 'attorney':
        return RedirectResponse(url="/attorneys", status_code=303)

    firm_id = request.session.get("firm_id")
    if not firm_id:
        return RedirectResponse(url="/login", status_code=303)

    report = generate_trust_transfer_report(firm_id)
    lines = report["lines"]
    summary = report["summary"]

    # Apply filters
    if attorney:
        lines = [l for l in lines if attorney.lower() in l.lead_attorney.lower()]
    if phase:
        lines = [l for l in lines if l.current_phase == phase]

    # Get unique attorneys and phases for filter dropdowns
    all_attorneys = sorted(set(l.lead_attorney for l in report["lines"] if l.lead_attorney))
    all_phases = []
    for pc in PHASE_ORDER:
        label = PHASE_LABELS.get(pc, pc)
        if any(l.current_phase == pc for l in report["lines"]):
            all_phases.append({"code": pc, "label": label})

    return templates.TemplateResponse("trust.html", {
        "request": request,
        "role": role,
        "lines": lines,
        "summary": summary,
        "schedules": FEE_SCHEDULES,
        "phase_order": PHASE_ORDER,
        "phase_labels": PHASE_LABELS,
        "all_attorneys": all_attorneys,
        "all_phases": all_phases,
        "selected_attorney": attorney or "",
        "selected_phase": phase or "",
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
    })


@router.get("/trust/export")
async def trust_export_csv(request: Request):
    """Export trust transfer report as CSV."""
    if not is_authenticated(request):
        return RedirectResponse(url="/login", status_code=303)

    role = get_current_role(request)
    if role == 'attorney':
        return RedirectResponse(url="/attorneys", status_code=303)

    firm_id = request.session.get("firm_id")
    if not firm_id:
        return RedirectResponse(url="/login", status_code=303)

    report = generate_trust_transfer_report(firm_id)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Case ID", "Case Name", "Client", "Lead Attorney", "Case Type",
        "Schedule", "Current Phase", "Earned %",
        "Total Fee", "Earned Amount", "In Operating", "Recommended Transfer",
        "Remaining in Trust"
    ])
    for l in report["lines"]:
        writer.writerow([
            l.case_id, l.case_name, l.client_name, l.lead_attorney,
            l.case_type, l.schedule_label, l.phase_label, f"{l.earned_pct}%",
            f"${l.total_fee:,.2f}", f"${l.earned_amount:,.2f}",
            f"${l.in_operating:,.2f}", f"${l.recommended_transfer:,.2f}",
            f"${l.remaining_in_trust:,.2f}",
        ])

    output.seek(0)
    filename = f"trust_transfer_{datetime.now().strftime('%Y%m%d')}.csv"
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode()),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
