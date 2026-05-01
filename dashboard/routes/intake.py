"""
Intake & CRM Pipeline routes — admin and collections roles.

Provides:
- /intake — Kanban pipeline board with drag-and-drop
- /intake/leads — List view with filters
- /intake/lead/<id> — Lead detail with activity timeline
- /intake/settings — Form builder, follow-up rules, availability
- /api/intake/* — JSON API for board interactions
- /api/intake/form/<token> — Public lead capture endpoint (no auth)
"""
import json
import logging
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Request, Form, Query
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from dashboard.auth import is_authenticated, get_data, get_current_role
from db.intake import (
    get_form_by_token, record_form_submission,
    get_available_slots, book_consultation,
    log_activity, update_lead, create_lead,
    get_lead, get_pipeline_stages,
    ensure_intake_tables, seed_pipeline_stages,
    seed_default_follow_up_rules,
)

logger = logging.getLogger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).parent.parent / "templates")


def _check_intake_access(request: Request):
    """Check auth and role. Returns (data, role) or RedirectResponse."""
    if not is_authenticated(request):
        return RedirectResponse(url="/login", status_code=303), None

    role = get_current_role(request)
    if role == 'attorney':
        return RedirectResponse(url="/attorneys", status_code=303), None

    data = get_data(request)
    # Auto-setup intake tables on first access
    data.ensure_intake_setup()
    return data, role


# ─── Dashboard Views ───────────────────────────────────────

@router.get("/intake", response_class=HTMLResponse)
async def intake_pipeline(request: Request):
    """Kanban pipeline board view."""
    result, role = _check_intake_access(request)
    if isinstance(result, RedirectResponse):
        return result
    data = result

    board = data.get_intake_board()
    metrics = data.get_intake_metrics(days=30)
    consultations = data.get_intake_consultations(days=7)

    # Get attorneys for assignment dropdown
    from db.connection import get_connection
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT DISTINCT attorney_name FROM dashboard_users
            WHERE firm_id = %s AND role = 'attorney' AND attorney_name IS NOT NULL
            ORDER BY attorney_name
        """, (data.firm_id,))
        attorneys = [row["attorney_name"] for row in cur.fetchall()]

    return templates.TemplateResponse("intake.html", {
        "request": request,
        "board": board,
        "stages": board["stages"],
        "stats": board["stats"],
        "metrics": metrics,
        "consultations": consultations,
        "attorneys": attorneys,
        "username": request.session.get("username"),
        "role": role,
    })


@router.get("/intake/lead/{lead_id}", response_class=HTMLResponse)
async def intake_lead_detail(request: Request, lead_id: int):
    """Lead detail page with activity timeline."""
    result, role = _check_intake_access(request)
    if isinstance(result, RedirectResponse):
        return result
    data = result

    lead = data.get_intake_lead(lead_id)
    if not lead:
        return RedirectResponse(url="/intake", status_code=303)

    activities = data.get_intake_lead_activities(lead_id)
    stages = data.get_intake_stages()

    return templates.TemplateResponse("intake_lead.html", {
        "request": request,
        "lead": lead,
        "activities": activities,
        "stages": stages,
        "username": request.session.get("username"),
        "role": role,
    })


@router.get("/intake/settings", response_class=HTMLResponse)
async def intake_settings(request: Request):
    """Intake settings: forms, follow-up rules, availability."""
    if not is_authenticated(request):
        return RedirectResponse(url="/login", status_code=303)

    role = get_current_role(request)
    if role != 'admin':
        return RedirectResponse(url="/intake", status_code=303)

    data = get_data(request)
    data.ensure_intake_setup()

    forms = data.get_intake_forms()
    rules = data.get_intake_follow_up_rules()
    stages = data.get_intake_stages()

    return templates.TemplateResponse("intake_settings.html", {
        "request": request,
        "forms": forms,
        "rules": rules,
        "stages": stages,
        "username": request.session.get("username"),
        "role": role,
    })


# ─── API Endpoints (authenticated) ─────────────────────────

@router.post("/api/intake/lead")
async def api_create_lead(request: Request):
    """Create a new lead via API."""
    result, role = _check_intake_access(request)
    if isinstance(result, RedirectResponse):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    data = result

    body = await request.json()
    lead_id = data.create_intake_lead(
        first_name=body.get("first_name", ""),
        last_name=body.get("last_name", ""),
        email=body.get("email"),
        phone=body.get("phone"),
        case_type=body.get("case_type"),
        source=body.get("source", "manual"),
        assigned_to=body.get("assigned_to"),
        notes=body.get("notes"),
        priority=body.get("priority", "normal"),
        created_by=request.session.get("username", "system"),
    )
    return JSONResponse({"id": lead_id, "success": True})


@router.post("/api/intake/lead/{lead_id}/stage")
async def api_update_lead_stage(request: Request, lead_id: int):
    """Move a lead to a different pipeline stage (drag-and-drop)."""
    result, role = _check_intake_access(request)
    if isinstance(result, RedirectResponse):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    data = result

    body = await request.json()
    new_stage = body.get("stage_name")
    if not new_stage:
        return JSONResponse({"error": "stage_name required"}, status_code=400)

    data.update_intake_lead(
        lead_id, updated_by=request.session.get("username", "system"),
        stage_name=new_stage
    )
    return JSONResponse({"success": True})


@router.post("/api/intake/lead/{lead_id}/update")
async def api_update_lead(request: Request, lead_id: int):
    """Update lead fields."""
    result, role = _check_intake_access(request)
    if isinstance(result, RedirectResponse):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    data = result

    body = await request.json()
    allowed_fields = {
        "first_name", "last_name", "email", "phone", "phone_alt",
        "case_type", "practice_area", "assigned_to", "priority",
        "referral_source", "notes", "estimated_value", "stage_name",
        "declined_reason", "consultation_type",
    }
    updates = {k: v for k, v in body.items() if k in allowed_fields}
    if not updates:
        return JSONResponse({"error": "No valid fields to update"}, status_code=400)

    data.update_intake_lead(
        lead_id, updated_by=request.session.get("username", "system"),
        **updates
    )
    return JSONResponse({"success": True})


@router.post("/api/intake/lead/{lead_id}/activity")
async def api_log_activity(request: Request, lead_id: int):
    """Log an activity (call, email, note) for a lead."""
    result, role = _check_intake_access(request)
    if isinstance(result, RedirectResponse):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    data = result

    body = await request.json()
    log_activity(
        data.firm_id, lead_id,
        activity_type=body.get("type", "note"),
        description=body.get("description"),
        performed_by=request.session.get("username", "system"),
    )
    return JSONResponse({"success": True})


@router.post("/api/intake/lead/{lead_id}/archive")
async def api_archive_lead(request: Request, lead_id: int):
    """Archive a lead."""
    result, role = _check_intake_access(request)
    if isinstance(result, RedirectResponse):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    data = result

    data.archive_intake_lead(lead_id)
    return JSONResponse({"success": True})


@router.post("/api/intake/lead/{lead_id}/consultation")
async def api_book_consultation(request: Request, lead_id: int):
    """Book a consultation for a lead."""
    result, role = _check_intake_access(request)
    if isinstance(result, RedirectResponse):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    data = result

    body = await request.json()
    consult_id = book_consultation(
        data.firm_id, lead_id,
        attorney_name=body.get("attorney_name"),
        consultation_date=date.fromisoformat(body["date"]),
        start_time=body["start_time"],
        end_time=body.get("end_time", ""),
        consultation_type=body.get("type", "phone"),
        notes=body.get("notes"),
    )
    return JSONResponse({"id": consult_id, "success": True})


@router.get("/api/intake/slots")
async def api_get_slots(request: Request, date: str = Query(...),
                        attorney: str = Query(None)):
    """Get available consultation slots for a date."""
    result, role = _check_intake_access(request)
    if isinstance(result, RedirectResponse):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    data = result

    from datetime import date as date_type
    target = date_type.fromisoformat(date)
    slots = get_available_slots(data.firm_id, target, attorney)
    return JSONResponse({"slots": slots})


# ─── Public Form Endpoint (NO AUTH) ────────────────────────

@router.get("/api/intake/form/{form_token}", response_class=HTMLResponse)
async def public_form_page(request: Request, form_token: str):
    """Serve the embeddable intake form (public, no auth)."""
    form = get_form_by_token(form_token)
    if not form:
        return HTMLResponse("<h3>Form not found</h3>", status_code=404)

    return templates.TemplateResponse("intake_form_public.html", {
        "request": request,
        "form": form,
    })


@router.post("/api/intake/form/{form_token}/submit")
async def public_form_submit(request: Request, form_token: str):
    """Handle public form submission (no auth, CORS-friendly)."""
    form = get_form_by_token(form_token)
    if not form:
        return JSONResponse({"error": "Form not found"}, status_code=404)

    # Accept both JSON and form data
    content_type = request.headers.get("content-type", "")
    if "json" in content_type:
        submission_data = await request.json()
    else:
        form_data = await request.form()
        submission_data = dict(form_data)

    # Basic validation
    if not submission_data.get("first_name") or not submission_data.get("last_name"):
        return JSONResponse({"error": "First and last name are required"}, status_code=400)

    try:
        lead_id = record_form_submission(
            form_id=form["id"],
            firm_id=form["firm_id"],
            submission_data=submission_data,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
            referrer_url=request.headers.get("referer"),
        )

        return JSONResponse({
            "success": True,
            "message": form.get("success_message", "Thank you! We will contact you shortly."),
            "redirect_url": form.get("redirect_url"),
        })
    except Exception as e:
        logger.error(f"Form submission error: {e}")
        return JSONResponse({"error": "Submission failed. Please try again."}, status_code=500)


# CORS preflight for embedded forms
@router.options("/api/intake/form/{form_token}/submit")
async def public_form_cors(form_token: str):
    return JSONResponse({}, headers={
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
    })


# ─── Embeddable Form Script ────────────────────────────────

@router.get("/api/intake/embed/{form_token}.js")
async def embed_script(request: Request, form_token: str):
    """Serve JavaScript snippet for embedding the form on external sites."""
    form = get_form_by_token(form_token)
    if not form:
        return HTMLResponse("// Form not found", status_code=404,
                           media_type="application/javascript")

    # Determine base URL
    host = request.headers.get("x-forwarded-host", request.headers.get("host", ""))
    scheme = request.headers.get("x-forwarded-proto", "https")
    base_url = f"{scheme}://{host}"

    fields_json = json.dumps(form.get("fields", []))
    success_msg = form.get("success_message", "Thank you! We will contact you shortly.")

    js = f"""
(function() {{
  var formToken = "{form_token}";
  var baseUrl = "{base_url}";
  var fields = {fields_json};
  var successMessage = "{success_msg}";

  var container = document.getElementById("lawmetrics-intake-form");
  if (!container) {{
    console.error("LawMetrics: No element with id='lawmetrics-intake-form' found");
    return;
  }}

  var form = document.createElement("form");
  form.style.cssText = "max-width:500px;font-family:Arial,sans-serif;";

  fields.forEach(function(field) {{
    var group = document.createElement("div");
    group.style.cssText = "margin-bottom:12px;";

    var label = document.createElement("label");
    label.textContent = field.label + (field.required ? " *" : "");
    label.style.cssText = "display:block;margin-bottom:4px;font-weight:600;font-size:14px;color:#333;";
    group.appendChild(label);

    var input;
    if (field.type === "textarea") {{
      input = document.createElement("textarea");
      input.rows = 3;
    }} else if (field.type === "select" && field.options) {{
      input = document.createElement("select");
      var opt = document.createElement("option");
      opt.value = "";
      opt.textContent = "Select...";
      input.appendChild(opt);
      field.options.forEach(function(o) {{
        var opt = document.createElement("option");
        opt.value = o;
        opt.textContent = o;
        input.appendChild(opt);
      }});
    }} else {{
      input = document.createElement("input");
      input.type = field.type || "text";
    }}

    input.name = field.name;
    input.required = field.required || false;
    input.style.cssText = "width:100%;padding:8px 12px;border:1px solid #ccc;border-radius:4px;font-size:14px;box-sizing:border-box;";
    group.appendChild(input);
    form.appendChild(group);
  }});

  var btn = document.createElement("button");
  btn.type = "submit";
  btn.textContent = "Submit";
  btn.style.cssText = "background:#2E5090;color:#fff;border:none;padding:10px 24px;border-radius:4px;font-size:16px;cursor:pointer;";
  form.appendChild(btn);

  form.addEventListener("submit", function(e) {{
    e.preventDefault();
    btn.disabled = true;
    btn.textContent = "Sending...";

    var data = {{}};
    fields.forEach(function(f) {{
      var el = form.querySelector("[name='" + f.name + "']");
      if (el) data[f.name] = el.value;
    }});

    fetch(baseUrl + "/api/intake/form/" + formToken + "/submit", {{
      method: "POST",
      headers: {{ "Content-Type": "application/json" }},
      body: JSON.stringify(data)
    }})
    .then(function(r) {{ return r.json(); }})
    .then(function(resp) {{
      if (resp.success) {{
        container.innerHTML = "<div style='padding:20px;background:#E8F5E9;border-radius:8px;text-align:center;'>" +
          "<h3 style='color:#2E7D32;margin:0 0 8px;'>&#10003; " + successMessage + "</h3></div>";
        if (resp.redirect_url) {{
          setTimeout(function() {{ window.location.href = resp.redirect_url; }}, 2000);
        }}
      }} else {{
        btn.disabled = false;
        btn.textContent = "Submit";
        alert(resp.error || "Submission failed. Please try again.");
      }}
    }})
    .catch(function() {{
      btn.disabled = false;
      btn.textContent = "Submit";
      alert("Connection error. Please try again.");
    }});
  }});

  container.appendChild(form);
}})();
"""
    return HTMLResponse(js, media_type="application/javascript")


# ─── Admin: Create Form ────────────────────────────────────

@router.post("/api/intake/form")
async def api_create_form(request: Request):
    """Create a new intake form (admin only)."""
    if not is_authenticated(request):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    if get_current_role(request) != "admin":
        return JSONResponse({"error": "Admin only"}, status_code=403)

    data = get_data(request)
    body = await request.json()

    from db.intake import create_form
    form = create_form(
        data.firm_id,
        form_name=body.get("form_name", "Contact Form"),
        notification_email=body.get("notification_email"),
        auto_assign_to=body.get("auto_assign_to"),
        success_message=body.get("success_message"),
        redirect_url=body.get("redirect_url"),
    )
    return JSONResponse({"success": True, "form": form})
