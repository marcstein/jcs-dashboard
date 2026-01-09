"""
FastAPI Dashboard Routes
"""
import threading
import csv
import io
import os
import json
import sqlite3
from datetime import datetime
from fastapi import APIRouter, Request, Form, Depends, BackgroundTasks
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
import anthropic

from dashboard.auth import login_user, logout_user, is_authenticated, require_auth
from dashboard.models import DashboardData

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")
data = DashboardData()

# Track sync status
_sync_status = {"running": False, "last_result": None, "error": None}


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Dashboard home page."""
    if not is_authenticated(request):
        return RedirectResponse(url="/login", status_code=303)

    stats = data.get_dashboard_stats()
    ar_aging = data.get_ar_aging_breakdown()
    recent_reports = data.get_recent_reports(limit=5)

    # SOP widget data
    melissa_sop = data.get_melissa_sop_data()
    ty_sop = data.get_ty_sop_data()
    tiffany_sop = data.get_tiffany_sop_data()
    alison_sop = data.get_legal_assistant_sop_data("Alison")
    cole_sop = data.get_legal_assistant_sop_data("Cole")

    # Additional staff with overdue tasks
    heidi_sop = data.get_legal_assistant_sop_data("Heidi")
    anthony_sop = data.get_legal_assistant_sop_data("Anthony")
    melinda_sop = data.get_legal_assistant_sop_data("Melinda")
    tiffany_personal_sop = data.get_legal_assistant_sop_data("Tiffany")

    # Attorney summary for dashboard widget
    attorney_summary = data.get_attorney_summary()

    # Staff caseload data
    tiffany_caseload = data.get_staff_caseload_data("Tiffany Willis")
    alison_caseload = data.get_staff_caseload_data("Alison Ehrhard")
    cole_caseload = data.get_staff_caseload_data("Cole Chadderdon")
    heidi_caseload = data.get_staff_caseload_data("Heidi Leopold")
    anthony_caseload = data.get_staff_caseload_data("Anthony Muhlenkamp")
    melinda_caseload = data.get_staff_caseload_data("Melinda Gorman")

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "stats": stats,
        "ar_aging": ar_aging,
        "recent_reports": recent_reports,
        "melissa_sop": melissa_sop,
        "ty_sop": ty_sop,
        "tiffany_sop": tiffany_sop,
        "alison_sop": alison_sop,
        "cole_sop": cole_sop,
        "heidi_sop": heidi_sop,
        "anthony_sop": anthony_sop,
        "melinda_sop": melinda_sop,
        "tiffany_personal_sop": tiffany_personal_sop,
        "attorney_summary": attorney_summary,
        "tiffany_caseload": tiffany_caseload,
        "alison_caseload": alison_caseload,
        "cole_caseload": cole_caseload,
        "heidi_caseload": heidi_caseload,
        "anthony_caseload": anthony_caseload,
        "melinda_caseload": melinda_caseload,
        "username": request.session.get("username"),
    })


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Login page."""
    if is_authenticated(request):
        return RedirectResponse(url="/", status_code=303)
    return templates.TemplateResponse("login.html", {
        "request": request,
        "error": None,
    })


@router.post("/login")
async def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    """Handle login form submission."""
    print(f"Login attempt: {username}")
    if login_user(request, username, password):
        print(f"Login SUCCESS - session: {dict(request.session)}")
        # 303 See Other - forces GET on redirect (proper POST-Redirect-GET pattern)
        return RedirectResponse(url="/", status_code=303)

    print(f"Login FAILED for {username}")
    return templates.TemplateResponse("login.html", {
        "request": request,
        "error": "Invalid username or password.",
    })


@router.get("/logout")
async def logout(request: Request):
    """Logout route."""
    logout_user(request)
    return RedirectResponse(url="/login", status_code=303)


@router.get("/staff/{staff_name}", response_class=HTMLResponse)
async def staff_tasks(request: Request, staff_name: str):
    """Staff task detail page."""
    if not is_authenticated(request):
        return RedirectResponse(url="/login", status_code=303)

    staff = data.get_staff_tasks(staff_name, include_completed=False)
    active_cases = data.get_staff_active_cases_list(staff_name)

    return templates.TemplateResponse("staff_tasks.html", {
        "request": request,
        "staff": staff,
        "active_cases": active_cases,
        "username": request.session.get("username"),
    })


@router.get("/ar", response_class=HTMLResponse)
async def ar_dashboard(request: Request):
    """AR/Collections dashboard."""
    if not is_authenticated(request):
        return RedirectResponse(url="/login", status_code=303)

    summary = data.get_daily_collections_summary()
    ar_aging = data.get_ar_aging_breakdown()
    trend = data.get_collections_trend(days_back=30)
    plans = data.get_payment_plans_summary()

    return templates.TemplateResponse("ar.html", {
        "request": request,
        "summary": summary,
        "ar_aging": ar_aging,
        "trend": trend,
        "plans": plans,
        "username": request.session.get("username"),
    })


@router.get("/noiw", response_class=HTMLResponse)
async def noiw_pipeline(request: Request):
    """NOIW Pipeline page."""
    if not is_authenticated(request):
        return RedirectResponse(url="/login", status_code=303)

    pipeline = data.get_noiw_pipeline()

    return templates.TemplateResponse("noiw.html", {
        "request": request,
        "pipeline": pipeline,
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


@router.get("/reports", response_class=HTMLResponse)
async def reports_list(request: Request):
    """Reports listing page."""
    if not is_authenticated(request):
        return RedirectResponse(url="/login", status_code=303)

    reports = data.get_recent_reports(limit=50)

    return templates.TemplateResponse("reports.html", {
        "request": request,
        "reports": reports,
        "username": request.session.get("username"),
    })


@router.get("/reports/{filename}", response_class=HTMLResponse)
async def view_report(request: Request, filename: str):
    """View a specific report."""
    if not is_authenticated(request):
        return RedirectResponse(url="/login", status_code=303)

    content = data.get_report_content(filename)

    return templates.TemplateResponse("report_view.html", {
        "request": request,
        "filename": filename,
        "content": content,
        "username": request.session.get("username"),
    })


# API endpoints for HTMX/JSON
@router.get("/api/stats")
async def api_stats(request: Request):
    """API endpoint for dashboard stats."""
    if not is_authenticated(request):
        return {"error": "Unauthorized"}, 401
    return data.get_dashboard_stats()


@router.get("/api/ar-aging")
async def api_ar_aging(request: Request):
    """API endpoint for AR aging data."""
    if not is_authenticated(request):
        return {"error": "Unauthorized"}, 401
    return data.get_ar_aging_breakdown()


def _run_sync():
    """Run the sync in background thread."""
    global _sync_status
    try:
        _sync_status["running"] = True
        _sync_status["error"] = None

        # Import sync manager here to avoid circular imports
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent))
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


# =========================================================================
# Attorney Productivity Routes
# =========================================================================

@router.get("/attorneys", response_class=HTMLResponse)
async def attorneys_dashboard(request: Request):
    """Attorney productivity dashboard."""
    if not is_authenticated(request):
        return RedirectResponse(url="/login", status_code=303)

    productivity = data.get_attorney_productivity_data()
    aging = data.get_attorney_invoice_aging()

    # Merge aging data into productivity
    aging_by_id = {a['attorney_id']: a for a in aging}
    for p in productivity:
        a = aging_by_id.get(p['attorney_id'], {})
        p['aging'] = a

    return templates.TemplateResponse("attorneys.html", {
        "request": request,
        "attorneys": productivity,
        "username": request.session.get("username"),
    })


@router.get("/attorney/{attorney_name}", response_class=HTMLResponse)
async def attorney_detail(request: Request, attorney_name: str):
    """Attorney detail page with call list."""
    if not is_authenticated(request):
        return RedirectResponse(url="/login", status_code=303)

    detail = data.get_attorney_detail(attorney_name)

    return templates.TemplateResponse("attorney_detail.html", {
        "request": request,
        "attorney": detail,
        "username": request.session.get("username"),
    })


@router.get("/attorneys/export")
async def attorneys_export_csv(request: Request):
    """Export attorney productivity data to CSV."""
    if not is_authenticated(request):
        return RedirectResponse(url="/login", status_code=303)

    productivity = data.get_attorney_productivity_data()
    aging = data.get_attorney_invoice_aging()

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
        'Billed 2025',
        'Collected 2025',
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
                atty.get('billed_2025', 0),
                atty.get('collected_2025', 0),
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

    # Generate filename with date
    today = datetime.now().strftime('%Y-%m-%d')
    filename = f"attorney_productivity_{today}.csv"

    # Return as downloadable CSV
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


# =========================================================================
# AI Chat API
# =========================================================================

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
- Focus on 2025 data: use strftime('%Y', date_column) = '2025'
- Collection rate = SUM(paid_amount) / SUM(total_amount) * 100
- Days Past Due (DPD) = julianday('now') - julianday(due_date)
- Key attorneys: Heidi Leopold, Anthony Muhlenkamp, Melinda Gorman
- Case types: "Felony DWI", "Misdemeanor DWI", "Felony Drug", "Misdemeanor Traffic", "Municipal Court"
- For tasks: completed=0 means pending, completed=1 means done
"""

CHAT_SYSTEM_PROMPT = f"""You are an AI assistant for LawMetrics.ai, a legal analytics dashboard.
You help users query and analyze law firm data from their MyCase practice management system.

{MYCASE_SCHEMA}

When the user asks a question:
1. Determine if it requires a database query
2. If yes, generate a SQLite query to answer their question
3. Return your response in this exact JSON format:

For database queries:
{{"type": "query", "sql": "SELECT ...", "explanation": "Brief explanation of what this query does"}}

For general questions (no query needed):
{{"type": "text", "response": "Your helpful response here"}}

Guidelines:
- Always use proper SQLite syntax
- For monetary values, format with $ and commas
- Round percentages to 1 decimal place
- Limit results to 20 rows unless user asks for more
- Order results meaningfully (by amount, date, etc.)
- When comparing attorneys, include collection rate calculations
- For time-based queries, default to 2025 unless specified otherwise
- Use aggregates (SUM, COUNT, AVG) when asking about totals or averages
- Join tables as needed to get complete information

Example queries:
- "Show billing by attorney" → Query cached_invoices joined with cached_cases, grouped by lead_attorney_name
- "Collection rate by case type" → SUM(paid_amount)/SUM(total_amount)*100 grouped by case_type_name
- "Overdue tasks" → Query cached_tasks WHERE status='Pending' AND due_date < DATE('now')
"""


def execute_chat_query(sql: str) -> tuple[list[dict], str | None]:
    """Execute a SQL query against the MyCase cache database."""
    # Use the main data cache (dashboard copy may be empty or stale)
    db_path = Path(__file__).parent.parent / "data" / "mycase_cache.db"
    if not db_path.exists():
        db_path = Path(__file__).parent / "mycase_cache.db"

    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(sql)
        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return rows, None
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
    for row in rows:
        formatted_values = []
        for h in headers:
            val = row[h]
            h_lower = h.lower()
            if val is None:
                formatted_values.append("-")
            elif isinstance(val, float):
                # Check if it's a rate/percentage
                if 'rate' in h_lower or 'percent' in h_lower or 'pct' in h_lower:
                    formatted_values.append(f"{val:.1f}%")
                # Check if it's a currency amount
                elif is_currency_column(h):
                    formatted_values.append(f"${val:,.2f}")
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
                        "response": f"**Query Error:** {error}\n\nSQL attempted: `{sql}`"
                    })

                formatted = format_query_results(rows, explanation)
                return JSONResponse({"response": formatted})

            else:
                # Text response
                return JSONResponse({"response": parsed.get("response", assistant_text)})

        except json.JSONDecodeError:
            # If not valid JSON, return as-is
            return JSONResponse({"response": assistant_text})

    except Exception as e:
        return JSONResponse({"error": f"Chat error: {str(e)}"})


# ============================================================================
# Docket Management Endpoints
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
    if not is_authenticated(request):
        return RedirectResponse(url="/login", status_code=303)

    # Get case info from cache
    import sqlite3
    from pathlib import Path
    db_path = Path(__file__).parent.parent / "data" / "mycase_cache.db"

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Get case details
    cursor.execute("SELECT * FROM cached_cases WHERE id = ?", (case_id,))
    case_row = cursor.fetchone()
    case_info = dict(case_row) if case_row else None

    # Get docket entries
    cursor.execute("""
        SELECT * FROM cached_docket_entries
        WHERE case_id = ?
        ORDER BY entry_date DESC, id DESC
    """, (case_id,))
    docket_entries = [dict(row) for row in cursor.fetchall()]

    # Get documents
    cursor.execute("""
        SELECT * FROM cached_documents
        WHERE case_id = ?
        ORDER BY created_at DESC
    """, (case_id,))
    documents = [dict(row) for row in cursor.fetchall()]

    conn.close()

    if not case_info:
        return HTMLResponse("<h1>Case not found</h1>", status_code=404)

    return templates.TemplateResponse("case_detail.html", {
        "request": request,
        "username": request.session.get("username"),
        "case": case_info,
        "docket_entries": docket_entries,
        "documents": documents,
    })
