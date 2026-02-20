"""
JSON API endpoints: Chat, docket management, document generation, sync, etc.
"""
import threading
import json
import os
import io
from datetime import datetime
from pathlib import Path

import anthropic
from fastapi import APIRouter, Request, BackgroundTasks
from fastapi.responses import JSONResponse, HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

from dashboard.auth import is_authenticated
from dashboard.models import DashboardData
from db.connection import get_connection

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).parent.parent / "templates")
data = DashboardData()

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
    current_year = datetime.now().year
    if year is None:
        year = current_year
    return data.get_dashboard_stats(year=year)


@router.get("/api/ar-aging")
async def api_ar_aging(request: Request, year: int = None):
    """API endpoint for AR aging data."""
    if not is_authenticated(request):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
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
- Use proper PostgreSQL syntax
- Limit results to 20 rows unless user asks for more
- Order results meaningfully (by amount, date, etc.)
- When comparing attorneys, include collection rate calculations
- For time-based queries, default to current year unless specified
- Use aggregates (SUM, COUNT, AVG) when asking about totals or averages
- Join tables as needed to get complete information
- For monetary columns use aliases like "total_billed" or "balance_due" (system auto-formats as currency)
- For percentages use aliases containing "rate" or "pct" (system auto-formats with %)

Example - user asks "Show billing by attorney":
{{"type": "query", "sql": "SELECT lead_attorney_name, COUNT(*) as invoice_count, SUM(total_amount) as total_billed, SUM(paid_amount) as collected FROM cached_invoices i JOIN cached_cases c ON i.case_id = c.id WHERE EXTRACT(YEAR FROM invoice_date) = 2025 GROUP BY lead_attorney_name ORDER BY total_billed DESC LIMIT 20", "explanation": "Billing by attorney for 2025"}}
"""


def execute_chat_query(sql: str) -> tuple[list[dict], str | None]:
    """Execute a SQL query against the PostgreSQL MyCase cache database."""
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql)

            # Get column names
            column_names = [desc[0] for desc in cursor.description]

            # Fetch all rows
            rows = []
            for row in cursor.fetchall():
                rows.append(dict(zip(column_names, row)))

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
            # Create new session
            firm_id = "jcs_law"  # Default firm for now
            chat_engine = DocumentChatEngine(firm_id=firm_id)
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
