"""
Main dashboard routes: Home page, staff pages, login/logout
"""
from datetime import datetime
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from dashboard.auth import login_user, logout_user, is_authenticated
from dashboard.models import DashboardData

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).parent.parent / "templates")
data = DashboardData()


@router.get("/", response_class=HTMLResponse)
async def index(request: Request, year: int = None):
    """Dashboard home page."""
    if not is_authenticated(request):
        return RedirectResponse(url="/login", status_code=303)

    # Default to current year if not specified
    current_year = datetime.now().year
    if year is None:
        year = current_year
    available_years = [2025, 2026]

    stats = data.get_dashboard_stats(year=year)
    ar_aging = data.get_ar_aging_breakdown(year=year)
    recent_reports = data.get_recent_reports(limit=5)

    # SOP widget data
    melissa_sop = data.get_melissa_sop_data(year=year)
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
    attorney_summary = data.get_attorney_summary(year=year)

    # Staff caseload data
    tiffany_caseload = data.get_staff_caseload_data("Tiffany Willis")
    alison_caseload = data.get_staff_caseload_data("Alison Ehrhard")
    cole_caseload = data.get_staff_caseload_data("Cole Chadderdon")
    heidi_caseload = data.get_staff_caseload_data("Heidi Leopold")
    anthony_caseload = data.get_staff_caseload_data("Anthony Muhlenkamp")
    melinda_caseload = data.get_staff_caseload_data("Melinda Gorman")

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "year": year,
        "current_year": current_year,
        "available_years": available_years,
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
    username: str = ...,
    password: str = ...,
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
