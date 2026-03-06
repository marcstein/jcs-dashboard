"""
JSON API endpoints: Chat, docket management, document generation, sync, etc.
"""
import threading
import json
import os
import io
import csv as csv_mod
import re
import uuid
from datetime import datetime
from pathlib import Path

import anthropic
from fastapi import APIRouter, Request, BackgroundTasks, UploadFile, File
from fastapi.responses import JSONResponse, HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

from dashboard.auth import is_authenticated, get_data, get_current_role, get_current_attorney_name
from db.connection import get_connection

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).parent.parent / "templates")

# Track sync status
_sync_status = {"running": False, "last_result": None, "error": None}

# Store active document chat sessions
_doc_sessions = {}


# ============================================================================
# Dashboard Stats API
# ============================================================================

@router.get("/api/stats")
async def api_stats(request: Request, year: int = None):
    """API endpoint for dashboard stats."""
    if not is_authenticated(request):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    data = get_data(request)
    current_year = datetime.now().year
    if year is None:
        year = current_year
    return data.get_dashboard_stats(year=year)


@router.get("/api/ar-aging")
async def api_ar_aging(request: Request, year: int = None):
    """API endpoint for AR aging data."""
    if not is_authenticated(request):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    data = get_data(request)
    current_year = datetime.now().year
    if year is None:
        year = current_year
    return data.get_ar_aging_breakdown(year=year)


# ============================================================================
# Sync Management API
# ============================================================================

def _run_sync():
    """Run the sync in background thread."""
    global _sync_status
    try:
        _sync_status["running"] = True
        _sync_status["error"] = None

        # Import sync manager here to avoid circular imports
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent.parent))
        from sync import get_sync_manager

        manager = get_sync_manager()
        results = manager.sync_all()

        # Summarize results
        total_changes = sum(r.changes for r in results.values())
        total_errors = sum(1 for r in results.values() if r.error)

        _sync_status["last_result"] = {
            "total_changes": total_changes,
            "total_errors": total_errors,
            "entities": {k: {"inserted": v.inserted, "updated": v.updated, "error": v.error}
                        for k, v in results.items()}
        }
    except Exception as e:
        _sync_status["error"] = str(e)
    finally:
        _sync_status["running"] = False


@router.post("/api/sync")
async def api_start_sync(request: Request, background_tasks: BackgroundTasks):
    """Start a background sync of all data from MyCase."""
    if not is_authenticated(request):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    if _sync_status["running"]:
        return JSONResponse({"status": "already_running"})

    # Start sync in background thread
    thread = threading.Thread(target=_run_sync, daemon=True)
    thread.start()

    return JSONResponse({"status": "started"})


@router.get("/api/sync/status")
async def api_sync_status(request: Request):
    """Get current sync status."""
    if not is_authenticated(request):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    return JSONResponse({
        "running": _sync_status["running"],
        "last_result": _sync_status["last_result"],
        "error": _sync_status["error"],
    })


# ============================================================================
# Dunning Actions API
# ============================================================================

@router.post("/api/dunning/run")
async def api_dunning_run(request: Request):
    """Run dunning cycle — dry-run previews what would be sent, execute sends via SendGrid.

    Sends from billing@jcsattorney.com. Only sends notices that haven't already
    been sent at the current stage (dedup via dunning_notices table).
    Optional 'stage' parameter to limit to a specific stage (1-4).
    """
    if not is_authenticated(request):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    try:
        body = await request.json()
        mode = body.get("mode", "dry-run")
        stage_filter = body.get("stage")  # optional: limit to one stage

        firm_id = request.session.get("firm_id", "")
        if not firm_id:
            return JSONResponse({"error": "No firm_id in session"}, status_code=400)

        data = get_data(request)
        # Get only unsent notices
        queue = data.get_dunning_preview(stage=stage_filter, include_sent=False)

        # Filter to only invoices with a client email
        sendable = [inv for inv in queue if inv.get('contact_email')]

        if mode != "execute":
            return JSONResponse({
                "mode": "dry-run",
                "would_send": len(sendable),
                "no_email": len(queue) - len(sendable),
                "by_stage": _count_by_stage(sendable),
            })

        # --- Execute mode: send via SendGrid ---
        sendgrid_key = os.getenv("SENDGRID_API_KEY", "")
        if not sendgrid_key:
            return JSONResponse({
                "error": "SENDGRID_API_KEY not configured. Set it in .env to enable batch sending."
            }, status_code=500)

        import httpx

        from_email = os.getenv("DUNNING_FROM_EMAIL", "billing@jcsattorney.com")
        from_name = os.getenv("DUNNING_FROM_NAME", "JCS Law Firm - Billing")
        firm_name = "JCS Law Firm"
        firm_phone = "(314) 561-9690"
        firm_email = "info@jcslaw.com"

        sent = 0
        failed = 0
        errors = []

        for inv in sendable:
            inv_num = inv.get('invoice_id', '')
            stage = inv.get('stage', 1)
            contact_email = inv['contact_email']
            contact_name = inv.get('contact_name', 'Client')
            case_name = inv.get('case_name', '')
            days = inv.get('days_delinquent', 0)
            balance = inv.get('balance_due', 0)
            amount_now = inv.get('amount_now_due') or balance
            total_bal = inv.get('total_remaining_balance', balance)
            due_date = inv.get('last_notice_date', '')
            invoice_db_id = inv.get('invoice_db_id', 0)

            # Build amount section
            if abs(amount_now - total_bal) < 0.01:
                amount_section = f"Amount Due: ${amount_now:,.2f}"
            else:
                amount_section = f"Amount Now Due: ${amount_now:,.2f}\nTotal Remaining Balance: ${total_bal:,.2f}"

            # Generate stage-appropriate email
            subject, body_text = _generate_dunning_email(
                stage, inv_num, contact_name, case_name, days,
                amount_section, due_date, firm_name, firm_phone, firm_email)

            # Send via SendGrid
            payload = {
                "personalizations": [{"to": [{"email": contact_email}], "subject": subject}],
                "from": {"email": from_email, "name": from_name},
                "content": [{"type": "text/plain", "value": body_text}],
            }

            try:
                response = httpx.post(
                    "https://api.sendgrid.com/v3/mail/send",
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {sendgrid_key}",
                        "Content-Type": "application/json",
                    },
                    timeout=30,
                )

                if response.status_code in (200, 202):
                    sent += 1
                    # Record in dunning_notices for dedup
                    with get_connection() as conn:
                        cur = conn.cursor()
                        cur.execute("""
                            INSERT INTO dunning_notices
                                (firm_id, invoice_id, contact_id, invoice_number,
                                 days_overdue, notice_level, amount_due, template_used,
                                 delivery_method, delivery_status, sent_at)
                            VALUES (%s, %s, 0, %s, %s, %s, %s, %s, 'email', 'sent', CURRENT_TIMESTAMP)
                            ON CONFLICT (firm_id, invoice_id, notice_level) DO UPDATE SET
                                amount_due = EXCLUDED.amount_due,
                                template_used = EXCLUDED.template_used,
                                sent_at = CURRENT_TIMESTAMP,
                                delivery_status = 'sent'
                        """, (firm_id, invoice_db_id, inv_num, days, stage, amount_now,
                              f"stage_{stage}_sendgrid_batch"))
                else:
                    failed += 1
                    errors.append(f"Invoice {inv_num}: HTTP {response.status_code}")
            except Exception as e:
                failed += 1
                errors.append(f"Invoice {inv_num}: {str(e)}")

        return JSONResponse({
            "mode": "execute",
            "sent": sent,
            "failed": failed,
            "no_email": len(queue) - len(sendable),
            "errors": errors[:10],  # limit error list
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse({"error": str(e)}, status_code=500)


def _count_by_stage(queue: list) -> dict:
    """Count sendable invoices by stage."""
    counts = {}
    for inv in queue:
        s = inv.get('stage', 0)
        counts[s] = counts.get(s, 0) + 1
    return counts


def _generate_dunning_email(stage, inv_num, contact_name, case_name, days,
                            amount_section, due_date, firm_name, firm_phone, firm_email):
    """Generate subject and body text for a dunning notice by stage."""
    if stage == 1:
        subject = f"Friendly Reminder - Invoice #{inv_num} Past Due"
        body = (
            f"Dear {contact_name},\n\n"
            f"This is a friendly reminder that Invoice #{inv_num} "
            f"is now {days} days past due.\n\n"
            f"Case: {case_name}\n"
            f"Original Due Date: {due_date}\n"
            f"{amount_section}\n\n"
            f"Please remit payment at your earliest convenience. If you have already "
            f"sent payment, please disregard this notice.\n\n"
            f"If you have any questions about this invoice, please don't hesitate "
            f"to contact our office.\n\n"
            f"Sincerely,\n{firm_name}\n{firm_phone}"
        )
    elif stage == 2:
        subject = f"Past Due Notice - Invoice #{inv_num}"
        body = (
            f"Dear {contact_name},\n\n"
            f"Our records indicate that Invoice #{inv_num} "
            f"is now {days} days past due.\n\n"
            f"Case: {case_name}\n"
            f"Original Due Date: {due_date}\n"
            f"{amount_section}\n\n"
            f"We kindly request that you submit payment within the next 7 days "
            f"to avoid any further collection activity.\n\n"
            f"If you are experiencing financial difficulties, please contact our "
            f"office to discuss payment arrangements.\n\n"
            f"Sincerely,\n{firm_name}\n{firm_phone}"
        )
    elif stage == 3:
        subject = f"URGENT: Payment Required - Invoice #{inv_num}"
        body = (
            f"URGENT: Payment Required\n\n"
            f"Dear {contact_name},\n\n"
            f"This is a formal notice that Invoice #{inv_num} remains unpaid "
            f"and is now {days} days past due.\n\n"
            f"Case: {case_name}\n"
            f"{amount_section}\n\n"
            f"Immediate payment is required to avoid further collection action. "
            f"Please remit payment within 10 days of this notice.\n\n"
            f"If you wish to discuss payment options, please contact our office "
            f"immediately.\n\n"
            f"{firm_name}\n{firm_phone}\n{firm_email}"
        )
    else:  # stage 4 — NOIW
        subject = f"NOTICE OF INTENT TO WITHDRAW - Invoice #{inv_num}"
        body = (
            f"NOTICE OF INTENT TO WITHDRAW\n\n"
            f"Dear {contact_name},\n\n"
            f"Despite our previous communications, Invoice #{inv_num} remains "
            f"unpaid and is now {days} days past due with no payment received "
            f"in over 60 days.\n\n"
            f"Case: {case_name}\n"
            f"{amount_section}\n\n"
            f"Please be advised that {firm_name} intends to file a Motion to Withdraw "
            f"from representation in this matter if full payment or an acceptable payment "
            f"arrangement is not received within 10 business days of this notice.\n\n"
            f"We strongly encourage you to contact our office immediately to discuss "
            f"your options and avoid any interruption in your legal representation.\n\n"
            f"{firm_name}\n{firm_phone}\n{firm_email}"
        )
    return subject, body


@router.post("/api/dunning/draft-email")
async def api_dunning_draft_email(request: Request):
    """Generate dunning email content for a specific invoice."""
    if not is_authenticated(request):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    try:
        body = await request.json()
        contact_name = body.get("contact_name", "Client")
        contact_email = body.get("contact_email", "")
        invoice_number = body.get("invoice_number", "")
        case_name = body.get("case_name", "")
        balance_due = body.get("balance_due", 0)
        amount_now_due = body.get("amount_now_due", balance_due)
        total_balance = body.get("total_balance", balance_due)
        days_overdue = body.get("days_overdue", 0)
        stage = body.get("stage", 1)
        due_date = body.get("due_date", "")

        # Determine subject and body based on dunning stage
        firm_name = "JCS Law Firm"
        firm_phone = "(314) 561-9690"
        firm_email = "info@jcslaw.com"

        # Build amount section — show both if they differ
        if abs(amount_now_due - total_balance) < 0.01:
            amount_section = f"Amount Due: ${amount_now_due:,.2f}"
        else:
            amount_section = (
                f"Amount Now Due: ${amount_now_due:,.2f}\n"
                f"Total Remaining Balance: ${total_balance:,.2f}"
            )

        if stage == 1:
            subject = f"Friendly Reminder - Invoice #{invoice_number} Past Due"
            email_body = (
                f"Dear {contact_name},\n\n"
                f"This is a friendly reminder that Invoice #{invoice_number} "
                f"is now {days_overdue} days past due.\n\n"
                f"Case: {case_name}\n"
                f"Original Due Date: {due_date}\n"
                f"{amount_section}\n\n"
                f"Please remit payment at your earliest convenience. If you have already "
                f"sent payment, please disregard this notice.\n\n"
                f"If you have any questions about this invoice, please don't hesitate "
                f"to contact our office.\n\n"
                f"Sincerely,\n{firm_name}\n{firm_phone}"
            )
        elif stage == 2:
            subject = f"Past Due Notice - Invoice #{invoice_number}"
            email_body = (
                f"Dear {contact_name},\n\n"
                f"Our records indicate that Invoice #{invoice_number} "
                f"is now {days_overdue} days past due.\n\n"
                f"Case: {case_name}\n"
                f"Original Due Date: {due_date}\n"
                f"{amount_section}\n\n"
                f"We kindly request that you submit payment within the next 7 days "
                f"to avoid any further collection activity.\n\n"
                f"If you are experiencing financial difficulties, please contact our "
                f"office to discuss payment arrangements.\n\n"
                f"Sincerely,\n{firm_name}\n{firm_phone}"
            )
        elif stage == 3:
            subject = f"URGENT: Payment Required - Invoice #{invoice_number}"
            email_body = (
                f"URGENT: Payment Required\n\n"
                f"Dear {contact_name},\n\n"
                f"This is a formal notice that Invoice #{invoice_number} remains unpaid "
                f"and is now {days_overdue} days past due.\n\n"
                f"Case: {case_name}\n"
                f"{amount_section}\n\n"
                f"Immediate payment is required to avoid further collection action. "
                f"Please remit payment within 10 days of this notice.\n\n"
                f"If you wish to discuss payment options, please contact our office "
                f"immediately.\n\n"
                f"{firm_name}\n{firm_phone}\n{firm_email}"
            )
        else:  # stage 4 — Notice of Intent to Withdraw
            subject = f"NOTICE OF INTENT TO WITHDRAW - Invoice #{invoice_number}"
            email_body = (
                f"NOTICE OF INTENT TO WITHDRAW\n\n"
                f"Dear {contact_name},\n\n"
                f"Despite our previous communications, Invoice #{invoice_number} remains "
                f"unpaid and is now {days_overdue} days past due with no payment received "
                f"in over 60 days.\n\n"
                f"Case: {case_name}\n"
                f"{amount_section}\n\n"
                f"Please be advised that {firm_name} intends to file a Motion to Withdraw "
                f"from representation in this matter if full payment or an acceptable payment "
                f"arrangement is not received within 10 business days of this notice.\n\n"
                f"We strongly encourage you to contact our office immediately to discuss "
                f"your options and avoid any interruption in your legal representation.\n\n"
                f"{firm_name}\n{firm_phone}\n{firm_email}"
            )

        return JSONResponse({
            "subject": subject,
            "body": email_body,
            "to": contact_email,
            "contact_name": contact_name,
        })

    except Exception as e:
        return JSONResponse({"error": str(e)})


@router.post("/api/dunning/mark-sent")
async def api_dunning_mark_sent(request: Request):
    """Record that a dunning notice was sent for an invoice at a given stage.

    This prevents the same notice from being sent twice for the same invoice+stage.
    """
    if not is_authenticated(request):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    try:
        body = await request.json()
        invoice_db_id = body.get("invoice_db_id")
        invoice_number = body.get("invoice_number", "")
        stage = body.get("stage", 1)
        amount_due = body.get("amount_due", 0)
        contact_name = body.get("contact_name", "")
        case_name = body.get("case_name", "")

        if not invoice_db_id:
            return JSONResponse({"error": "invoice_db_id is required"}, status_code=400)

        # Get firm_id from session
        firm_id = request.session.get("firm_id", "")
        if not firm_id:
            return JSONResponse({"error": "No firm_id in session"}, status_code=400)

        with get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO dunning_notices
                    (firm_id, invoice_id, contact_id, invoice_number,
                     days_overdue, notice_level, amount_due, template_used,
                     delivery_method, delivery_status, sent_at)
                VALUES (%s, %s, 0, %s, 0, %s, %s, %s, 'email', 'sent', CURRENT_TIMESTAMP)
                ON CONFLICT (firm_id, invoice_id, notice_level) DO UPDATE SET
                    amount_due = EXCLUDED.amount_due,
                    template_used = EXCLUDED.template_used,
                    sent_at = CURRENT_TIMESTAMP,
                    delivery_status = 'sent'
                RETURNING id
            """, (firm_id, invoice_db_id, invoice_number, stage, amount_due,
                  f"stage_{stage}_outlook"))
            row = cur.fetchone()
            notice_id = row[0] if row else 0

        return JSONResponse({
            "ok": True,
            "notice_id": notice_id,
            "message": f"Recorded: Stage {stage} notice for invoice {invoice_number}",
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/api/dunning/export")
async def api_dunning_export(request: Request, stage: int = None):
    """Export dunning queue to CSV."""
    if not is_authenticated(request):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    import csv as csv_mod

    data = get_data(request)
    queue = data.get_dunning_queue(stage=stage)

    output = io.StringIO()
    writer = csv_mod.writer(output)
    writer.writerow(['Invoice', 'Case', 'Client Name', 'Client Email', 'Attorney', 'Balance Due', 'Days Overdue', 'Stage', 'Due Date'])

    for inv in queue:
        writer.writerow([
            inv.get('invoice_id', ''),
            inv.get('case_name', ''),
            inv.get('contact_name', ''),
            inv.get('contact_email', ''),
            inv.get('attorney', inv.get('contact_name', '')),
            inv.get('balance_due', 0),
            inv.get('days_delinquent', 0),
            inv.get('stage', ''),
            inv.get('last_notice_date', ''),
        ])

    output.seek(0)
    today = datetime.now().strftime('%Y-%m-%d')
    filename = f"dunning_queue_{today}.csv"

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


# ============================================================================
# Aging Invoice Upload API
# ============================================================================

def _parse_currency(val):
    """Parse currency string like '$1,234.56' to float."""
    if val is None:
        return None
    s = str(val).strip()
    if not s:
        return None
    # Remove $, commas, spaces
    s = re.sub(r'[$,\s]', '', s)
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


def _parse_date(val):
    """Parse date string in various formats to YYYY-MM-DD."""
    if val is None:
        return None
    s = str(val).strip()
    if not s:
        return None
    for fmt in ('%m/%d/%Y', '%Y-%m-%d', '%m-%d-%Y', '%m/%d/%y', '%Y/%m/%d'):
        try:
            return datetime.strptime(s, fmt).strftime('%Y-%m-%d')
        except ValueError:
            continue
    return None


def _normalize_header(h):
    """Normalize CSV header to a standard key."""
    h = h.strip().lower().replace(' ', '_')
    mapping = {
        'invoice_number': 'invoice_number',
        'invoice': 'invoice_number',
        'inv_number': 'invoice_number',
        'inv_#': 'invoice_number',
        'inv': 'invoice_number',
        'client': 'client_name',
        'client_name': 'client_name',
        'case': 'case_name',
        'case_name': 'case_name',
        'matter': 'case_name',
        'amount_overdue': 'amount_overdue',
        'amount_due': 'amount_overdue',
        'overdue': 'amount_overdue',
        'balance': 'amount_overdue',
        'balance_due': 'amount_overdue',
        'invoice_total': 'invoice_total',
        'total': 'invoice_total',
        'total_amount': 'invoice_total',
        'amount_paid': 'amount_paid',
        'paid': 'amount_paid',
        'paid_amount': 'amount_paid',
        'due_date': 'due_date',
        'due': 'due_date',
        'status': 'status',
        'days_aging': 'days_aging',
        'days': 'days_aging',
        'dpd': 'days_aging',
        'days_overdue': 'days_aging',
        'aging': 'days_aging',
    }
    return mapping.get(h, h)


@router.post("/api/aging-upload")
async def api_aging_upload(request: Request, file: UploadFile = File(...)):
    """Upload an aging invoice report CSV."""
    if not is_authenticated(request):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    firm_id = request.session.get("firm_id")
    if not firm_id:
        return JSONResponse({"error": "No firm_id in session"}, status_code=400)

    try:
        content = await file.read()
        text = content.decode('utf-8-sig')  # Handle BOM
        reader = csv_mod.DictReader(io.StringIO(text))

        # Normalize headers
        if not reader.fieldnames:
            return JSONResponse({"error": "CSV file has no headers"}, status_code=400)

        header_map = {}
        for h in reader.fieldnames:
            header_map[h] = _normalize_header(h)

        batch_id = str(uuid.uuid4())
        rows_imported = 0

        with get_connection() as conn:
            cursor = conn.cursor()

            for row in reader:
                # Map to normalized keys
                mapped = {}
                for orig_key, val in row.items():
                    norm_key = header_map.get(orig_key, orig_key)
                    mapped[norm_key] = val

                invoice_number = (mapped.get('invoice_number') or '').strip()
                if not invoice_number:
                    continue

                cursor.execute("""
                    INSERT INTO aging_invoice_uploads
                        (firm_id, invoice_number, client_name, case_name,
                         amount_overdue, invoice_total, amount_paid,
                         due_date, status, days_aging, upload_batch_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    firm_id,
                    invoice_number,
                    (mapped.get('client_name') or '').strip(),
                    (mapped.get('case_name') or '').strip(),
                    _parse_currency(mapped.get('amount_overdue')),
                    _parse_currency(mapped.get('invoice_total')),
                    _parse_currency(mapped.get('amount_paid')),
                    _parse_date(mapped.get('due_date')),
                    (mapped.get('status') or '').strip(),
                    int(mapped['days_aging']) if mapped.get('days_aging') and str(mapped['days_aging']).strip().isdigit() else None,
                    batch_id,
                ))
                rows_imported += 1

            conn.commit()

        return JSONResponse({
            "success": True,
            "rows_imported": rows_imported,
            "batch_id": batch_id,
            "filename": file.filename,
        })

    except UnicodeDecodeError:
        return JSONResponse({"error": "File is not a valid CSV (encoding error)"}, status_code=400)
    except Exception as e:
        return JSONResponse({"error": f"Upload failed: {str(e)}"}, status_code=500)


@router.get("/api/aging-upload/history")
async def api_aging_upload_history(request: Request):
    """Get recent aging upload history."""
    if not is_authenticated(request):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    firm_id = request.session.get("firm_id")
    if not firm_id:
        return JSONResponse({"error": "No firm_id in session"}, status_code=400)

    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT upload_batch_id, COUNT(*) as row_count,
                       MIN(uploaded_at) as uploaded_at
                FROM aging_invoice_uploads
                WHERE firm_id = %s
                GROUP BY upload_batch_id
                ORDER BY MIN(uploaded_at) DESC
                LIMIT 10
            """, (firm_id,))
            history = []
            for r in cursor.fetchall():
                history.append({
                    'batch_id': r[0],
                    'row_count': r[1],
                    'uploaded_at': r[2].isoformat() if r[2] else '',
                })
            return JSONResponse({"history": history})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ============================================================================
# Chat API
# ============================================================================

# Database schema context for Claude
MYCASE_SCHEMA = """
You have access to a MyCase law firm management database with these tables:

## cached_cases
- id (INTEGER PRIMARY KEY)
- case_number (TEXT) - e.g., "2025-CR-001234"
- name (TEXT) - Client name and case description
- case_type (TEXT) - often empty, use practice_area instead
- practice_area (TEXT) - e.g., "Criminal - Felony", "Criminal - Misdemeanor", "Criminal - Muni", "Criminal Defense", "DWI"
- status (TEXT) - "open" or "closed" (lowercase)
- date_opened (DATE) - Date case was opened
- date_closed (DATE) - Date case was closed (NULL if open)
- lead_attorney_id (INTEGER)
- lead_attorney_name (TEXT) - e.g., "Heidi Leopold", "Anthony Muhlenkamp"
- stage (TEXT) - Current case stage

## cached_contacts
- id (INTEGER PRIMARY KEY)
- first_name, last_name (TEXT)
- company (TEXT)
- email (TEXT)

## cached_invoices
- id (INTEGER PRIMARY KEY)
- invoice_number (TEXT)
- case_id (INTEGER) - Links to cached_cases.id
- contact_id (INTEGER)
- total_amount (REAL) - Total billed
- paid_amount (REAL) - Amount collected
- balance_due (REAL) - Outstanding balance
- status (TEXT) - "Sent", "Paid", "Partial", "Draft"
- invoice_date (DATE)
- due_date (DATE)

## cached_tasks
- id (INTEGER PRIMARY KEY)
- name (TEXT) - e.g., "Review Discovery", "Client History Worksheet"
- description (TEXT)
- case_id (INTEGER) - Links to cached_cases.id
- due_date (DATE)
- completed (BOOLEAN) - 0=pending, 1=completed
- completed_at (TIMESTAMP)
- assignee_id (INTEGER)
- assignee_name (TEXT) - Staff member assigned

## cached_staff
- id (INTEGER PRIMARY KEY)
- name (TEXT) - Full name
- first_name, last_name (TEXT)
- email (TEXT)
- title (TEXT)
- staff_type (TEXT) - "Attorney", "Paralegal", etc.
- active (BOOLEAN)

## Key Relationships:
- cached_invoices.case_id → cached_cases.id
- cached_tasks.case_id → cached_cases.id
- cached_cases.lead_attorney_id → cached_staff.id

## Important Notes:
- This is a criminal defense law firm in Kansas City
- Focus on 2025 data: use EXTRACT(YEAR FROM date_column) = 2025
- Collection rate = SUM(paid_amount) / SUM(total_amount) * 100
- Days Past Due (DPD) = CURRENT_DATE - due_date::date
- Key attorneys: Heidi Leopold, Anthony Muhlenkamp, Melinda Gorman
- Case types: "Felony DWI", "Misdemeanor DWI", "Felony Drug", "Misdemeanor Traffic", "Municipal Court"
- Case status values are LOWERCASE: 'open', 'closed' (NOT 'Open' or 'Closed')
- For tasks: completed is BOOLEAN (use completed = false for pending, completed = true for done)
"""

CHAT_SYSTEM_PROMPT = f"""You are an AI assistant for LawMetrics.ai, a legal analytics dashboard.
You help users query and analyze law firm data from their MyCase practice management system.

{MYCASE_SCHEMA}

CRITICAL: You MUST respond with ONLY valid JSON - no other text before or after.
The system will execute your SQL query and show the results to the user.
NEVER show SQL queries to users - they cannot run them. The system handles execution automatically.

When the user asks a question:
1. Determine if it requires a database query
2. If yes, generate a PostgreSQL query - the system will run it and show results
3. Return ONLY this JSON format (no markdown, no extra text):

For database queries:
{{"type": "query", "sql": "SELECT ...", "explanation": "Brief explanation"}}

For general questions (no query needed):
{{"type": "text", "response": "Your helpful response here"}}

Guidelines:
- ALWAYS return valid JSON only - nothing else
- Use proper PostgreSQL syntax (IMPORTANT: ROUND() requires numeric type — always cast with ::numeric before rounding, e.g. ROUND(SUM(amount)::numeric, 2) not ROUND(SUM(amount), 2))
- Limit results to 20 rows unless user asks for more
- Order results meaningfully (by amount, date, etc.)
- When comparing attorneys, include collection rate calculations
- For time-based queries, default to current year unless specified
- Use aggregates (SUM, COUNT, AVG) when asking about totals or averages
- Join tables as needed to get complete information
- For monetary columns use aliases like "total_billed" or "balance_due" (system auto-formats as currency)
- For percentages use aliases containing "rate" or "pct" (system auto-formats with %)

Example - user asks "Show billing by attorney":
{{"type": "query", "sql": "SELECT lead_attorney_name, COUNT(*) as invoice_count, SUM(total_amount) as total_billed, SUM(paid_amount) as collected, ROUND((SUM(paid_amount) / NULLIF(SUM(total_amount), 0) * 100)::numeric, 1) as collection_rate FROM cached_invoices i JOIN cached_cases c ON i.case_id = c.id WHERE EXTRACT(YEAR FROM invoice_date) = 2025 GROUP BY lead_attorney_name ORDER BY total_billed DESC LIMIT 20", "explanation": "Billing by attorney for 2025"}}
"""


def execute_chat_query(sql: str) -> tuple[list[dict], str | None]:
    """Execute a SQL query against the PostgreSQL MyCase cache database."""
    try:
        # Bypass connection pool to get a plain tuple cursor
        # (pool sets RealDictCursor which causes dict iteration issues)
        import psycopg2
        import os
        raw_conn = psycopg2.connect(os.environ.get("DATABASE_URL", ""))
        try:
            cursor = raw_conn.cursor()
            cursor.execute(sql)

            # Get column names from cursor description
            column_names = [desc[0] for desc in cursor.description]

            # Fetch all rows as plain tuples, zip with column names
            rows = []
            for row in cursor.fetchall():
                rows.append(dict(zip(column_names, row)))

            return rows, None
        finally:
            raw_conn.close()
    except Exception as e:
        return [], str(e)


def format_query_results(rows: list[dict], explanation: str) -> str:
    """Format query results as a markdown response."""
    if not rows:
        return "No results found."

    # Get column headers
    headers = list(rows[0].keys())

    # Format as markdown table (no explanation text, just the data)
    result = ""

    # Header row
    result += "| " + " | ".join(headers) + " |\n"
    result += "| " + " | ".join(["---"] * len(headers)) + " |\n"

    # Column names that indicate currency (amounts, not counts)
    currency_keywords = ['amount', 'billed', 'collected', 'balance', 'paid', 'due', 'revenue', 'fee', 'cost', 'price']
    # Column names that indicate counts (should NOT be currency)
    count_keywords = ['count', 'invoice_count', 'case_count', 'task_count', 'total_invoices', 'total_cases', 'total_tasks', 'open_cases', 'closed', 'overdue']

    def is_currency_column(col_name):
        col_lower = col_name.lower()
        # Exclude count columns first
        if any(kw in col_lower for kw in count_keywords):
            return False
        # Include currency columns
        return any(kw in col_lower for kw in currency_keywords)

    # Data rows
    from decimal import Decimal
    for row in rows:
        formatted_values = []
        for h in headers:
            val = row[h]
            h_lower = h.lower()
            # Convert Decimal to float for formatting (PostgreSQL ROUND returns Decimal)
            if isinstance(val, Decimal):
                val = float(val)
            if val is None:
                formatted_values.append("-")
            elif isinstance(val, float):
                # Check if it's a year (e.g. EXTRACT(YEAR FROM ...)) — show as integer
                if ('year' in h_lower or 'month' in h_lower) and 1900 <= val <= 2100:
                    formatted_values.append(str(int(val)))
                # Check if it's a rate/percentage
                elif 'rate' in h_lower or 'percent' in h_lower or 'pct' in h_lower:
                    formatted_values.append(f"{val:.1f}%")
                # Check if it's a currency amount
                elif is_currency_column(h):
                    if val < 0:
                        formatted_values.append(f"-${abs(val):,.2f}")
                    else:
                        formatted_values.append(f"${val:,.2f}")
                # Check if it looks like a whole number (e.g. count returned as float)
                elif val == int(val) and abs(val) < 1_000_000:
                    formatted_values.append(f"{int(val):,}")
                else:
                    formatted_values.append(f"{val:,.1f}")
            elif isinstance(val, int):
                if is_currency_column(h):
                    formatted_values.append(f"${val:,}")
                else:
                    formatted_values.append(f"{val:,}")
            else:
                formatted_values.append(str(val))
        result += "| " + " | ".join(formatted_values) + " |\n"

    if len(rows) == 20:
        result += "\n*Results limited to 20 rows*"

    return result


@router.post("/api/chat")
async def api_chat(request: Request):
    """AI chat endpoint for natural language queries."""
    if not is_authenticated(request):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    try:
        body = await request.json()
        user_message = body.get("message", "").strip()

        if not user_message:
            return JSONResponse({"error": "No message provided"})

        # Initialize Anthropic client
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            return JSONResponse({"error": "AI service not configured. Set ANTHROPIC_API_KEY environment variable."})

        client = anthropic.Anthropic(api_key=api_key)

        # Call Claude to interpret the query
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            system=CHAT_SYSTEM_PROMPT,
            messages=[
                {"role": "user", "content": user_message}
            ]
        )

        # Parse Claude's response
        assistant_text = response.content[0].text

        # Try to parse as JSON
        try:
            # Find JSON in response (it might have markdown code blocks)
            json_str = assistant_text
            if "```json" in json_str:
                json_str = json_str.split("```json")[1].split("```")[0]
            elif "```" in json_str:
                json_str = json_str.split("```")[1].split("```")[0]

            parsed = json.loads(json_str.strip())

            if parsed.get("type") == "query":
                # Execute the SQL query
                sql = parsed.get("sql", "")
                explanation = parsed.get("explanation", "")

                rows, error = execute_chat_query(sql)

                if error:
                    return JSONResponse({
                        "response": f"**Query Error:** {error}\n\nPlease try rephrasing your question."
                    })

                formatted = format_query_results(rows, explanation)
                return JSONResponse({"response": formatted})

            else:
                # Text response
                return JSONResponse({"response": parsed.get("response", assistant_text)})

        except json.JSONDecodeError:
            # JSON parsing failed - try to extract and execute SQL if present
            sql_match = None

            # Look for SQL in various formats
            import re

            # Try to find SELECT statement in the response
            sql_patterns = [
                r'```sql\s*(SELECT[^`]+)```',  # ```sql SELECT ... ```
                r'`(SELECT[^`]+)`',             # `SELECT ...`
                r'"sql":\s*"(SELECT[^"]+)"',    # "sql": "SELECT ..."
                r"'sql':\s*'(SELECT[^']+)'",    # 'sql': 'SELECT ...'
                r'(SELECT\s+.+?(?:LIMIT\s+\d+|;|\Z))',  # Raw SELECT statement
            ]

            for pattern in sql_patterns:
                match = re.search(pattern, assistant_text, re.IGNORECASE | re.DOTALL)
                if match:
                    sql_match = match.group(1).strip().rstrip(';')
                    break

            if sql_match:
                # Found SQL - execute it
                rows, error = execute_chat_query(sql_match)

                if error:
                    return JSONResponse({
                        "response": f"**Query Error:** {error}\n\nPlease try rephrasing your question."
                    })

                formatted = format_query_results(rows, "")
                return JSONResponse({"response": formatted})

            # No SQL found - return the text response but clean it up
            # Remove any JSON-like formatting that might confuse users
            clean_response = assistant_text
            clean_response = re.sub(r'\{["\']type["\'].*?\}', '', clean_response, flags=re.DOTALL)
            clean_response = clean_response.strip()

            if clean_response:
                return JSONResponse({"response": clean_response})
            else:
                return JSONResponse({"response": "I couldn't process that request. Please try rephrasing your question."})

    except Exception as e:
        return JSONResponse({"error": f"Chat error: {str(e)}"})


# ============================================================================
# Docket Management API
# ============================================================================

@router.post("/api/docket/import")
async def import_docket(request: Request):
    """Import docket text from Missouri CaseNet."""
    if not is_authenticated(request):
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    try:
        body = await request.json()
        docket_text = body.get("docket_text", "")
        case_id = body.get("case_id")

        if not docket_text:
            return JSONResponse({"error": "No docket text provided"})

        from docket import DocketManager
        manager = DocketManager()
        result = manager.import_docket(docket_text, case_id=case_id)

        return JSONResponse(result)

    except Exception as e:
        return JSONResponse({"error": f"Import error: {str(e)}"})


@router.get("/api/docket/{case_number}")
async def get_docket(request: Request, case_number: str):
    """Get docket entries for a case."""
    if not is_authenticated(request):
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    try:
        from docket import DocketManager
        manager = DocketManager()
        entries = manager.get_case_docket(case_number=case_number)

        return JSONResponse({"case_number": case_number, "entries": entries})

    except Exception as e:
        return JSONResponse({"error": f"Error: {str(e)}"})


@router.get("/api/docket/upcoming/{days}")
async def get_upcoming_actions(request: Request, days: int = 14):
    """Get upcoming court actions requiring attention."""
    if not is_authenticated(request):
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    try:
        from docket import DocketManager
        manager = DocketManager()
        upcoming = manager.get_upcoming_actions(days_ahead=days)

        return JSONResponse({"days_ahead": days, "actions": upcoming})

    except Exception as e:
        return JSONResponse({"error": f"Error: {str(e)}"})


@router.post("/api/docket/notify")
async def send_docket_notifications(request: Request):
    """Send email notifications for upcoming court actions."""
    if not is_authenticated(request):
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    try:
        body = await request.json()
        email_to = body.get("email", "marc.stein@gmail.com")
        days_ahead = body.get("days", 14)

        from docket import DocketManager
        manager = DocketManager()
        result = manager.send_upcoming_notifications(email_to=email_to, days_ahead=days_ahead)

        return JSONResponse(result)

    except Exception as e:
        return JSONResponse({"error": f"Error: {str(e)}"})


@router.get("/case/{case_id}", response_class=HTMLResponse)
async def case_detail(request: Request, case_id: int):
    """Case detail page with docket timeline."""
    from dashboard.auth import is_authenticated, require_auth
    if not is_authenticated(request):
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="/login", status_code=303)

    try:
        # Get case info from cache using db functions
        with get_connection() as conn:
            cursor = conn.cursor()

            # Get case details
            cursor.execute(
                "SELECT * FROM cached_cases WHERE id = %s",
                (case_id,)
            )
            case_row = cursor.fetchone()

            if not case_row:
                return HTMLResponse("<h1>Case not found</h1>", status_code=404)

            # Convert to dict
            case_info = {}
            if case_row:
                column_names = [desc[0] for desc in cursor.description]
                case_info = dict(zip(column_names, case_row))

            # Get docket entries
            cursor.execute(
                """SELECT * FROM cached_docket_entries
                   WHERE case_id = %s
                   ORDER BY entry_date DESC, id DESC""",
                (case_id,)
            )
            docket_rows = cursor.fetchall()
            docket_column_names = [desc[0] for desc in cursor.description]
            docket_entries = [dict(zip(docket_column_names, row)) for row in docket_rows]

            # Get documents
            cursor.execute(
                """SELECT * FROM cached_documents
                   WHERE case_id = %s
                   ORDER BY created_at DESC""",
                (case_id,)
            )
            doc_rows = cursor.fetchall()
            doc_column_names = [desc[0] for desc in cursor.description]
            documents = [dict(zip(doc_column_names, row)) for row in doc_rows]

        if not case_info:
            return HTMLResponse("<h1>Case not found</h1>", status_code=404)

        return templates.TemplateResponse("case_detail.html", {
            "request": request,
            "username": request.session.get("username"),
            "case": case_info,
            "docket_entries": docket_entries,
            "documents": documents,
        })
    except Exception as e:
        return HTMLResponse(f"<h1>Error loading case</h1><p>{str(e)}</p>", status_code=500)


# ============================================================================
# Document Generation API
# ============================================================================

@router.get("/documents", response_class=HTMLResponse)
async def documents_page(request: Request):
    """Document generation page."""
    if not is_authenticated(request):
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="/login", status_code=303)

    return templates.TemplateResponse("documents.html", {
        "request": request,
        "username": request.session.get("username"),
        "role": get_current_role(request),
    })


@router.post("/api/documents/chat")
async def api_documents_chat(request: Request):
    """Document generation chat API endpoint."""
    if not is_authenticated(request):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    try:
        body = await request.json()
        user_message = body.get("message", "").strip()
        session_id = body.get("session_id")

        if not user_message:
            return JSONResponse({"error": "No message provided"})

        # Import document chat engine
        try:
            from document_chat import DocumentChatEngine
        except ImportError as e:
            return JSONResponse({"error": f"Document system not available: {e}"})

        # Get or create session
        if session_id and session_id in _doc_sessions:
            chat_engine = _doc_sessions[session_id]
        else:
            # Create new session — use session firm_id and attorney profile
            firm_id = request.session.get("firm_id", "jcs_law")
            attorney_id = None
            attorney_name_override = None

            # If logged-in user is an attorney, auto-set them as signing attorney
            attorney_name = request.session.get("attorney_name")
            if attorney_name:
                try:
                    from attorney_profiles import get_attorney_by_name
                    atty = get_attorney_by_name(firm_id, attorney_name)
                    if atty and atty.id:
                        attorney_id = atty.id
                    else:
                        # Attorney has no profile — use primary for firm details
                        # but override the name for signing
                        attorney_name_override = attorney_name
                except Exception:
                    attorney_name_override = attorney_name

            chat_engine = DocumentChatEngine(
                firm_id=firm_id,
                attorney_id=attorney_id,
                attorney_name_override=attorney_name_override,
            )
            session_id = f"doc_{datetime.now().strftime('%Y%m%d%H%M%S')}_{id(chat_engine)}"
            _doc_sessions[session_id] = chat_engine

        # Get response from document chat
        response_text = chat_engine.chat(user_message)

        # Check if a document was generated
        download_url = None
        session = chat_engine.get_session()
        if session.output_path and session.output_path.exists():
            # Create download URL using the filename
            filename = session.output_path.name
            download_url = f"/api/documents/download-file/{filename}"

        return JSONResponse({
            "response": response_text,
            "session_id": session_id,
            "download_url": download_url
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse({"error": str(e)})


@router.get("/api/documents/download/{session_id}")
async def api_documents_download(request: Request, session_id: str):
    """Download generated document by session ID."""
    if not is_authenticated(request):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    if session_id not in _doc_sessions:
        return JSONResponse({"error": "Session not found"}, status_code=404)

    chat_engine = _doc_sessions[session_id]
    session = chat_engine.get_session()

    if not session.output_path or not session.output_path.exists():
        return JSONResponse({"error": "No document generated"}, status_code=404)

    # Read file and return as download
    content = session.output_path.read_bytes()
    filename = session.output_path.name

    return StreamingResponse(
        io.BytesIO(content),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.get("/api/documents/download-file/{filename:path}")
async def api_documents_download_file(request: Request, filename: str):
    """Download generated document by filename."""
    if not is_authenticated(request):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    # Security: only allow files from the generated directory
    generated_dir = Path(__file__).parent.parent.parent / "data" / "generated"
    file_path = generated_dir / filename

    # Prevent directory traversal attacks
    try:
        file_path = file_path.resolve()
        if not str(file_path).startswith(str(generated_dir.resolve())):
            return JSONResponse({"error": "Access denied"}, status_code=403)
    except Exception:
        return JSONResponse({"error": "Invalid path"}, status_code=400)

    if not file_path.exists():
        return JSONResponse({"error": "Document not found"}, status_code=404)

    # Read file and return as download
    content = file_path.read_bytes()

    return StreamingResponse(
        io.BytesIO(content),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename={file_path.name}"}
    )
