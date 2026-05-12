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
    if role != 'admin':
        return RedirectResponse(url="/ar" if role == 'collections' else "/attorneys" if role == 'attorney' else "/", status_code=303)

    firm_id = request.session.get("firm_id")
    if not firm_id:
        return RedirectResponse(url="/login", status_code=303)

    report = generate_trust_transfer_report(firm_id)
    lines = report["lines"]
    summary = report["summary"]
    schedules = report["schedules"]

    # Load trust balances from latest upload
    try:
        from db.trust import get_latest_trust_balances, get_latest_upload_batch_id
        trust_balances = get_latest_trust_balances(firm_id)
        upload_batch_id = get_latest_upload_batch_id(firm_id)
    except Exception:
        trust_balances = {}
        upload_batch_id = None

    has_trust_data = len(trust_balances) > 0

    # Attach trust balance to each line and compute transferable amount
    for l in lines:
        tb = trust_balances.get(l.case_id)
        if tb:
            l._trust_balance = tb["trust_balance"]
            # Transferable = min(trust balance, earned) — can't transfer more than what's in trust
            l._transferable = min(tb["trust_balance"], l.paid_to_date)
        else:
            l._trust_balance = None
            l._transferable = None

    # Recalculate summary with trust data
    if has_trust_data:
        summary["total_trust_balance"] = sum(
            l._trust_balance for l in lines if l._trust_balance is not None
        )
        summary["total_transferable"] = sum(
            l._transferable for l in lines if l._transferable is not None
        )
        summary["cases_with_trust"] = sum(
            1 for l in lines if l._trust_balance is not None
        )

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
        "schedules": schedules,
        "phase_order": PHASE_ORDER,
        "phase_labels": PHASE_LABELS,
        "all_attorneys": all_attorneys,
        "all_phases": all_phases,
        "selected_attorney": attorney or "",
        "selected_phase": phase or "",
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "has_trust_data": has_trust_data,
        "upload_batch_id": upload_batch_id,
    })


@router.get("/trust/export")
async def trust_export_csv(request: Request):
    """Export trust transfer report as CSV."""
    if not is_authenticated(request):
        return RedirectResponse(url="/login", status_code=303)

    role = get_current_role(request)
    if role != 'admin':
        return RedirectResponse(url="/ar" if role == 'collections' else "/attorneys" if role == 'attorney' else "/", status_code=303)

    firm_id = request.session.get("firm_id")
    if not firm_id:
        return RedirectResponse(url="/login", status_code=303)

    report = generate_trust_transfer_report(firm_id)

    # Load trust balances
    try:
        from db.trust import get_latest_trust_balances
        trust_balances = get_latest_trust_balances(firm_id)
    except Exception:
        trust_balances = {}

    output = io.StringIO()
    writer = csv.writer(output)
    headers = [
        "Case ID", "Case Name", "Client", "Lead Attorney", "Case Type",
        "Schedule", "Current Phase",
        "Total Fee", "Earned (Received)", "% Earned", "Pace Target %",
        "Behind Pace", "Outstanding",
    ]
    if trust_balances:
        headers.extend(["Trust Balance", "Transferable"])
    writer.writerow(headers)

    for l in report["lines"]:
        row = [
            l.case_id, l.case_name, l.client_name, l.lead_attorney,
            l.case_type, l.schedule_label, l.phase_label,
            f"${l.total_fee:,.2f}", f"${l.paid_to_date:,.2f}",
            f"{l.pct_paid:.1f}%", f"{l.phase_target_pct}%",
            f"${l.billing_gap:,.2f}", f"${l.outstanding_balance:,.2f}",
        ]
        if trust_balances:
            tb = trust_balances.get(l.case_id)
            if tb:
                row.append(f"${tb['trust_balance']:,.2f}")
                row.append(f"${min(tb['trust_balance'], l.paid_to_date):,.2f}")
            else:
                row.extend(["", ""])
        writer.writerow(row)

    output.seek(0)
    filename = f"trust_transfer_{datetime.now().strftime('%Y%m%d')}.csv"
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode()),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
