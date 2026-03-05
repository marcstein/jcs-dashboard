"""
Main dashboard routes: Home page, staff pages, login/logout
"""
from datetime import datetime
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from dashboard.auth import (
    login_user, logout_user, is_authenticated, get_data, get_current_role,
    get_user, get_current_firm_id, validate_password, update_user_password,
)
from werkzeug.security import check_password_hash

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).parent.parent / "templates")


@router.get("/", response_class=HTMLResponse)
async def index(request: Request, year: int = None, view: str = None):
    """Dashboard home page."""
    if not is_authenticated(request):
        return RedirectResponse(url="/login", status_code=303)

    role = get_current_role(request)
    if role == 'attorney':
        return RedirectResponse(url="/attorneys", status_code=303)

    # Default to current year if not specified
    current_year = datetime.now().year
    available_years = [2025, 2026]

    data = get_data(request)

    # View modes: None/year-based, "combined", "rolling6"
    if view == "combined":
        stats = data.get_dashboard_stats(years=[2025, 2026])
        ar_aging = data.get_ar_aging_breakdown(years=[2025, 2026])
        melissa_sop = data.get_melissa_sop_data(years=[2025, 2026])
        attorney_summary = data.get_attorney_summary(years=[2025, 2026])
        year = None  # signal combined mode
    elif view == "rolling6":
        stats = data.get_dashboard_stats(rolling_months=6)
        ar_aging = data.get_ar_aging_breakdown(rolling_months=6)
        melissa_sop = data.get_melissa_sop_data(rolling_months=6)
        attorney_summary = data.get_attorney_summary(rolling_months=6)
        year = None
    else:
        if year is None:
            year = current_year
        stats = data.get_dashboard_stats(year=year)
        ar_aging = data.get_ar_aging_breakdown(year=year)
        melissa_sop = data.get_melissa_sop_data(year=year)
        attorney_summary = data.get_attorney_summary(year=year)

    recent_reports = data.get_recent_reports(limit=5)

    # SOP widget data (not year-dependent)
    ty_sop = data.get_ty_sop_data()
    tiffany_sop = data.get_tiffany_sop_data()
    alison_sop = data.get_legal_assistant_sop_data("Alison")
    cole_sop = data.get_legal_assistant_sop_data("Cole")

    # Additional staff with overdue tasks
    heidi_sop = data.get_legal_assistant_sop_data("Heidi")
    anthony_sop = data.get_legal_assistant_sop_data("Anthony")
    melinda_sop = data.get_legal_assistant_sop_data("Melinda")
    tiffany_personal_sop = data.get_legal_assistant_sop_data("Tiffany")
    john_sop = data.get_legal_assistant_sop_data("John")
    leigh_sop = data.get_legal_assistant_sop_data("Leigh")
    jen_sop = data.get_legal_assistant_sop_data("Jen")
    ethan_sop = data.get_legal_assistant_sop_data("Ethan")

    # Staff caseload data
    tiffany_caseload = data.get_staff_caseload_data("Tiffany Willis")
    alison_caseload = data.get_staff_caseload_data("Alison Ehrhard")
    cole_caseload = data.get_staff_caseload_data("Cole Chadderdon")
    heidi_caseload = data.get_staff_caseload_data("Heidi Leopold")
    anthony_caseload = data.get_staff_caseload_data("Anthony Muhlenkamp")
    melinda_caseload = data.get_staff_caseload_data("Melinda Gorman")
    john_caseload = data.get_staff_caseload_data("John Schleiffarth")
    leigh_caseload = data.get_staff_caseload_data("Leigh Hawk")
    jen_caseload = data.get_staff_caseload_data("Jen Kusmer")
    ethan_caseload = data.get_staff_caseload_data("Ethan Dwyer")

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "year": year,
        "view": view,
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
        "john_sop": john_sop,
        "leigh_sop": leigh_sop,
        "jen_sop": jen_sop,
        "ethan_sop": ethan_sop,
        "attorney_summary": attorney_summary,
        "tiffany_caseload": tiffany_caseload,
        "alison_caseload": alison_caseload,
        "cole_caseload": cole_caseload,
        "heidi_caseload": heidi_caseload,
        "anthony_caseload": anthony_caseload,
        "melinda_caseload": melinda_caseload,
        "john_caseload": john_caseload,
        "leigh_caseload": leigh_caseload,
        "jen_caseload": jen_caseload,
        "ethan_caseload": ethan_caseload,
        "username": request.session.get("username"),
        "role": role,
    })


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Login page."""
    if is_authenticated(request):
        return RedirectResponse(url="/", status_code=303)
    return templates.TemplateResponse("login.html", {
        "request": request,
        "error": None,
        "firm_id": None,
        "username": None,
    })


@router.post("/login")
async def login_submit(
    request: Request,
    firm_id: str = Form(...),
    username: str = Form(...),
    password: str = Form(...),
):
    """Handle login form submission."""
    firm_id = firm_id.strip()
    username = username.strip()
    print(f"Login attempt: {username} @ firm_id={firm_id}")
    if login_user(request, username, password, firm_id=firm_id):
        print(f"Login SUCCESS - session: {dict(request.session)}")
        # 303 See Other - forces GET on redirect (proper POST-Redirect-GET pattern)
        # Attorneys go directly to their attorney dashboard
        if request.session.get("role") == "attorney":
            return RedirectResponse(url="/attorneys", status_code=303)
        return RedirectResponse(url="/", status_code=303)

    print(f"Login FAILED for {username} @ firm_id={firm_id}")
    return templates.TemplateResponse("login.html", {
        "request": request,
        "error": "Invalid credentials. Check firm ID, username, and password.",
        "firm_id": firm_id,
        "username": username,
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

    role = get_current_role(request)
    if role == 'attorney':
        return RedirectResponse(url="/attorneys", status_code=303)

    data = get_data(request)
    staff = data.get_staff_tasks(staff_name, include_completed=False)
    active_cases = data.get_staff_active_cases_list(staff_name)

    return templates.TemplateResponse("staff_tasks.html", {
        "request": request,
        "staff": staff,
        "active_cases": active_cases,
        "username": request.session.get("username"),
        "role": role,
    })


@router.get("/reports", response_class=HTMLResponse)
async def reports_list(request: Request):
    """Reports listing page."""
    if not is_authenticated(request):
        return RedirectResponse(url="/login", status_code=303)

    role = get_current_role(request)
    if role == 'attorney':
        return RedirectResponse(url="/attorneys", status_code=303)

    data = get_data(request)
    reports = data.get_recent_reports(limit=50)

    return templates.TemplateResponse("reports.html", {
        "request": request,
        "reports": reports,
        "username": request.session.get("username"),
        "role": role,
    })


@router.get("/reports/{filename}", response_class=HTMLResponse)
async def view_report(request: Request, filename: str):
    """View a specific report."""
    if not is_authenticated(request):
        return RedirectResponse(url="/login", status_code=303)

    role = get_current_role(request)
    if role == 'attorney':
        return RedirectResponse(url="/attorneys", status_code=303)

    data = get_data(request)
    content = data.get_report_content(filename)

    return templates.TemplateResponse("report_view.html", {
        "request": request,
        "filename": filename,
        "content": content,
        "username": request.session.get("username"),
        "role": role,
    })


@router.get("/change-password", response_class=HTMLResponse)
async def change_password_page(request: Request):
    """Change password page — available to all authenticated users."""
    if not is_authenticated(request):
        return RedirectResponse(url="/login", status_code=303)

    role = get_current_role(request)
    return templates.TemplateResponse("change_password.html", {
        "request": request,
        "username": request.session.get("username"),
        "role": role,
        "error": None,
        "success": None,
    })


@router.post("/change-password")
async def change_password_submit(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
):
    """Handle change password form submission."""
    if not is_authenticated(request):
        return RedirectResponse(url="/login", status_code=303)

    role = get_current_role(request)
    username = request.session.get("username")
    firm_id = get_current_firm_id(request)

    ctx = {
        "request": request,
        "username": username,
        "role": role,
        "error": None,
        "success": None,
    }

    # Verify current password
    user = get_user(username, firm_id)
    if not user or not check_password_hash(user["password_hash"], current_password):
        ctx["error"] = "Current password is incorrect."
        return templates.TemplateResponse("change_password.html", ctx)

    # Check new passwords match
    if new_password != confirm_password:
        ctx["error"] = "New passwords do not match."
        return templates.TemplateResponse("change_password.html", ctx)

    # Validate new password requirements
    is_valid, validation_error = validate_password(new_password)
    if not is_valid:
        ctx["error"] = validation_error
        return templates.TemplateResponse("change_password.html", ctx)

    # Don't allow reusing current password
    if check_password_hash(user["password_hash"], new_password):
        ctx["error"] = "New password must be different from your current password."
        return templates.TemplateResponse("change_password.html", ctx)

    # Update password
    if update_user_password(username, new_password, firm_id):
        ctx["success"] = "Password changed successfully."
    else:
        ctx["error"] = "Failed to update password. Please try again."

    return templates.TemplateResponse("change_password.html", ctx)
