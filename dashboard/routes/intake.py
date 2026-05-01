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
    # Conflict checks
    get_lead_conflicts, resolve_conflict, has_unresolved_conflicts,
    # Conversion
    get_conversion_data, mark_lead_converted,
    # Custom fields
    get_custom_fields, create_custom_field, update_custom_field,
    delete_custom_field, set_lead_custom_field,
    # Marketing & ROI
    save_lead_attribution, get_marketing_spend, add_marketing_spend,
    delete_marketing_spend, get_marketing_roi_summary, get_marketing_trends,
    MARKETING_SOURCES, SOURCE_LABELS,
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
    conflicts = data.get_intake_lead_conflicts(lead_id)
    has_conflicts = any(c["status"] == "unresolved" for c in conflicts)
    custom_fields = data.get_intake_custom_fields()

    return templates.TemplateResponse("intake_lead.html", {
        "request": request,
        "lead": lead,
        "activities": activities,
        "stages": stages,
        "conflicts": conflicts,
        "has_unresolved_conflicts": has_conflicts,
        "custom_fields": custom_fields,
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
    custom_fields = data.get_intake_custom_fields()

    return templates.TemplateResponse("intake_settings.html", {
        "request": request,
        "forms": forms,
        "rules": rules,
        "stages": stages,
        "custom_fields": custom_fields,
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
    source = body.get("source", "manual")
    lead_id = data.create_intake_lead(
        first_name=body.get("first_name", ""),
        last_name=body.get("last_name", ""),
        email=body.get("email"),
        phone=body.get("phone"),
        case_type=body.get("case_type"),
        source=source,
        assigned_to=body.get("assigned_to"),
        notes=body.get("notes"),
        priority=body.get("priority", "normal"),
        created_by=request.session.get("username", "system"),
    )

    # Save attribution for manual leads too
    try:
        from db.intake import save_lead_attribution
        firm_id = request.session.get("firm_id")
        save_lead_attribution(firm_id, lead_id, source_field=source)
    except Exception:
        pass

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

    // Capture UTM params from page URL
    var params = new URLSearchParams(window.location.search);
    ['utm_source','utm_medium','utm_campaign','utm_content','utm_term'].forEach(function(k) {{
      if (params.get(k)) data[k] = params.get(k);
    }});
    data['landing_page'] = window.location.href.split('?')[0];

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


# ─── Conflict Checks ─────────────────────────────────────────

@router.get("/api/intake/lead/{lead_id}/conflicts")
async def api_get_conflicts(request: Request, lead_id: int):
    """Get conflict check results for a lead."""
    result, role = _check_intake_access(request)
    if isinstance(result, RedirectResponse):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    data = result

    conflicts = data.get_intake_lead_conflicts(lead_id)
    return JSONResponse({"conflicts": conflicts, "count": len(conflicts)})


@router.post("/api/intake/conflict/{conflict_id}/resolve")
async def api_resolve_conflict(request: Request, conflict_id: int):
    """Resolve a conflict (clear or flag)."""
    result, role = _check_intake_access(request)
    if isinstance(result, RedirectResponse):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    body = await request.json()
    resolve_conflict(
        conflict_id,
        resolved_by=request.session.get("username", "system"),
        status=body.get("status", "cleared"),
        notes=body.get("notes"),
    )
    return JSONResponse({"success": True})


# ─── Lead → MyCase Conversion ────────────────────────────────

@router.post("/api/intake/lead/{lead_id}/convert")
async def api_convert_lead(request: Request, lead_id: int):
    """Convert a retained lead to a MyCase case."""
    result, role = _check_intake_access(request)
    if isinstance(result, RedirectResponse):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    data = result

    # Check for unresolved conflicts
    if has_unresolved_conflicts(data.firm_id, lead_id):
        return JSONResponse({
            "error": "Lead has unresolved conflicts. Please review conflicts before converting.",
            "conflicts": True,
        }, status_code=400)

    conversion_data = get_conversion_data(data.firm_id, lead_id)
    if not conversion_data:
        return JSONResponse({"error": "Lead not found"}, status_code=404)

    # Try to create in MyCase
    mycase_case_id = None
    mycase_contact_id = None
    try:
        from api_client import MyCaseAPI
        api = MyCaseAPI()

        # Create contact first
        contact_payload = {
            "contact": {
                "first_name": conversion_data["contact"]["first_name"],
                "last_name": conversion_data["contact"]["last_name"],
                "email": conversion_data["contact"].get("email"),
                "phone": conversion_data["contact"].get("phone"),
                "type": "Person",
            }
        }
        contact_resp = api.post("/contacts", data=contact_payload)
        if contact_resp and "contact" in contact_resp:
            mycase_contact_id = contact_resp["contact"].get("id")

        # Create case
        case_payload = {
            "case": {
                "name": conversion_data["case"]["name"],
                "description": conversion_data["case"].get("description", ""),
                "status": "Open",
            }
        }
        case_resp = api.post("/cases", data=case_payload)
        if case_resp and "case" in case_resp:
            mycase_case_id = case_resp["case"].get("id")

    except Exception as e:
        logger.warning(f"MyCase API conversion failed: {e}")
        # Still mark as converted even if API fails — user can link manually
        pass

    # Mark lead as converted
    mark_lead_converted(data.firm_id, lead_id,
                        mycase_case_id=mycase_case_id,
                        mycase_contact_id=mycase_contact_id)

    return JSONResponse({
        "success": True,
        "mycase_case_id": mycase_case_id,
        "mycase_contact_id": mycase_contact_id,
        "api_created": mycase_case_id is not None,
    })


# ─── Custom Fields ────────────────────────────────────────────

@router.get("/api/intake/custom-fields")
async def api_get_custom_fields(request: Request):
    """Get custom field definitions."""
    result, role = _check_intake_access(request)
    if isinstance(result, RedirectResponse):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    data = result

    fields = data.get_intake_custom_fields()
    return JSONResponse({"fields": fields})


@router.post("/api/intake/custom-fields")
async def api_create_custom_field(request: Request):
    """Create a new custom field (admin only)."""
    if not is_authenticated(request):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    if get_current_role(request) != "admin":
        return JSONResponse({"error": "Admin only"}, status_code=403)

    data = get_data(request)
    body = await request.json()

    field_key = body.get("field_key", "").strip().lower().replace(" ", "_")
    field_label = body.get("field_label", "").strip()

    if not field_key or not field_label:
        return JSONResponse({"error": "field_key and field_label required"}, status_code=400)

    field_id = data.create_intake_custom_field(
        field_key=field_key,
        field_label=field_label,
        field_type=body.get("field_type", "text"),
        field_options=body.get("field_options"),
        is_required=body.get("is_required", False),
        show_on_card=body.get("show_on_card", False),
        show_on_form=body.get("show_on_form", True),
    )
    return JSONResponse({"success": True, "id": field_id})


@router.post("/api/intake/custom-fields/{field_id}/update")
async def api_update_custom_field(request: Request, field_id: int):
    """Update a custom field (admin only)."""
    if not is_authenticated(request):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    if get_current_role(request) != "admin":
        return JSONResponse({"error": "Admin only"}, status_code=403)

    data = get_data(request)
    body = await request.json()
    data.update_intake_custom_field(field_id, **body)
    return JSONResponse({"success": True})


@router.post("/api/intake/custom-fields/{field_id}/delete")
async def api_delete_custom_field(request: Request, field_id: int):
    """Soft-delete a custom field (admin only)."""
    if not is_authenticated(request):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    if get_current_role(request) != "admin":
        return JSONResponse({"error": "Admin only"}, status_code=403)

    data = get_data(request)
    data.delete_intake_custom_field(field_id)
    return JSONResponse({"success": True})


@router.post("/api/intake/lead/{lead_id}/custom-field")
async def api_set_lead_custom_field(request: Request, lead_id: int):
    """Set a custom field value on a lead."""
    result, role = _check_intake_access(request)
    if isinstance(result, RedirectResponse):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    data = result

    body = await request.json()
    field_key = body.get("field_key")
    value = body.get("value")

    if not field_key:
        return JSONResponse({"error": "field_key required"}, status_code=400)

    data.set_intake_lead_custom_field(lead_id, field_key, value)
    return JSONResponse({"success": True})


# ============================================================
# Marketing Analytics & ROI
# ============================================================

@router.get("/intake/marketing")
async def intake_marketing(request: Request):
    """Marketing analytics dashboard — admin only."""
    result, role = _check_intake_access(request)
    if isinstance(result, RedirectResponse):
        return result
    if role != "admin":
        return RedirectResponse(url="/intake", status_code=303)
    data = result
    firm_id = request.session.get("firm_id")

    roi = get_marketing_roi_summary(firm_id)
    trends = get_marketing_trends(firm_id, months=12)
    spend_entries = get_marketing_spend(firm_id)

    return templates.TemplateResponse("intake_marketing.html", {
        "request": request,
        "role": role,
        "roi": roi,
        "trends": trends,
        "spend_entries": spend_entries,
        "sources": MARKETING_SOURCES,
        "source_labels": SOURCE_LABELS,
    })


@router.post("/api/intake/marketing/spend")
async def api_add_spend(request: Request):
    """Add or update a monthly spend entry."""
    result, role = _check_intake_access(request)
    if isinstance(result, RedirectResponse):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    if role != "admin":
        return JSONResponse({"error": "Admin only"}, status_code=403)

    firm_id = request.session.get("firm_id")
    body = await request.json()

    try:
        period = datetime.strptime(body["period"], "%Y-%m").date()
        spend_id = add_marketing_spend(
            firm_id=firm_id,
            source=body["source"],
            period_start=period,
            spend_amount=float(body["amount"]),
            campaign_name=body.get("campaign") or None,
            impressions=int(body["impressions"]) if body.get("impressions") else None,
            clicks=int(body["clicks"]) if body.get("clicks") else None,
            notes=body.get("notes"),
        )
        return JSONResponse({"success": True, "id": spend_id})
    except (KeyError, ValueError) as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@router.post("/api/intake/marketing/spend/{spend_id}/delete")
async def api_delete_spend(request: Request, spend_id: int):
    """Delete a spend entry."""
    result, role = _check_intake_access(request)
    if isinstance(result, RedirectResponse):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    if role != "admin":
        return JSONResponse({"error": "Admin only"}, status_code=403)

    firm_id = request.session.get("firm_id")
    ok = delete_marketing_spend(firm_id, spend_id)
    return JSONResponse({"success": ok})
