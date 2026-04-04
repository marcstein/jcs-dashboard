"""
Dashboard routes for phone integration:
- POST /api/phone/webhook/{firm_id}/{provider} — VoIP webhook receiver
- GET /api/phone/events/stream — SSE stream for screen pops
- GET /api/phone/test-pop — Test screen pop (admin only)
- GET /api/phone/stats — Call event statistics
- GET /api/phone/events — Recent call events
- GET /phone — Phone integration settings page
"""
import asyncio
import json
import logging
import time
from datetime import datetime

from fastapi import APIRouter, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from dashboard.auth import is_authenticated, get_current_role, get_current_firm_id

logger = logging.getLogger(__name__)
router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).parent.parent / "templates")


# ---------------------------------------------------------------------------
# Webhook Receiver (no auth — called by VoIP providers)
# ---------------------------------------------------------------------------

@router.post("/api/phone/webhook/{firm_id}/{provider}")
async def phone_webhook(request: Request, firm_id: str, provider: str):
    """
    Receive incoming call webhooks from VoIP providers.

    URL format: /api/phone/webhook/{firm_id}/{provider}
    Each firm gets a unique webhook URL per provider.

    Flow:
    1. Validate provider and load integration config
    2. Verify webhook signature
    3. Parse event via provider adapter
    4. If ringing event: lookup client, build screen pop, deliver via SSE
    5. Log call event
    """
    from phone.adapters import get_adapter, ADAPTERS
    from db.phone import get_phone_integration, log_call_event, get_extension_user
    from phone.lookup import build_screen_pop
    from phone.delivery import deliver_screen_pop

    # Validate provider
    if provider not in ADAPTERS:
        return JSONResponse(
            {"error": f"Unknown provider: {provider}"},
            status_code=400,
        )

    # Load integration config
    integration = get_phone_integration(firm_id, provider)
    if not integration or not integration.get('is_active'):
        logger.warning("Webhook received for inactive/missing integration: %s/%s", firm_id, provider)
        return JSONResponse(
            {"error": "Integration not found or inactive"},
            status_code=404,
        )

    # Get adapter
    adapter = get_adapter(provider)

    # Read raw body for signature verification
    body = await request.body()
    headers = {k.lower(): v for k, v in request.headers.items()}

    # Parse JSON payload
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)

    # Check for validation/challenge request (e.g. RingCentral)
    validation_response = adapter.get_validation_response(payload, headers)
    if validation_response:
        # RingCentral validation: return the token in the response header
        if "validation_token" in validation_response:
            resp = Response(status_code=200)
            resp.headers["Validation-Token"] = validation_response["validation_token"]
            return resp
        return JSONResponse(validation_response)

    # Verify webhook signature
    webhook_secret = integration.get('webhook_secret', '')
    if not adapter.verify_signature(body, headers, webhook_secret):
        logger.warning("Webhook signature verification failed: %s/%s", firm_id, provider)
        return JSONResponse({"error": "Invalid signature"}, status_code=401)

    # Check if this is a ringing event
    if not adapter.is_ringing_event(payload):
        # Not a ringing event — acknowledge but don't process
        return JSONResponse({"status": "ignored", "reason": "not a ringing event"})

    # Parse the event
    call_event = adapter.parse_event(payload, firm_id)
    if not call_event:
        return JSONResponse({"status": "ignored", "reason": "could not parse event"})

    # Look up extension → user mapping
    target_username = None
    if call_event.called_extension:
        target_username = get_extension_user(firm_id, call_event.called_extension)

    # Build screen pop (includes client lookup)
    pop = build_screen_pop(
        firm_id=firm_id,
        caller_number=call_event.caller_number,
        caller_number_normalized=call_event.caller_number_normalized,
        call_event_id=0,  # Will be set after logging
        target_username=target_username,
    )

    # Log the call event
    event_id = log_call_event(
        firm_id=firm_id,
        caller_number=call_event.caller_number,
        caller_number_normalized=call_event.caller_number_normalized,
        called_number=call_event.called_number,
        called_extension=call_event.called_extension,
        matched_client_id=pop.client_id,
        matched_client_name=pop.client_name if pop.matched else None,
        matched_case_count=len(pop.cases),
        provider=provider,
        event_type=call_event.event_type,
        raw_payload=payload,
    )
    pop.call_event_id = event_id

    # Deliver screen pop via SSE
    delivery_result = await deliver_screen_pop(pop)

    # Update pop_delivered flag
    if delivery_result.get("delivered") or delivery_result.get("delivered_count", 0) > 0:
        from db.connection import get_connection
        with get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE call_events SET pop_delivered = TRUE WHERE id = %s",
                (event_id,),
            )

    logger.info(
        "Webhook processed: %s/%s — %s → %s (event_id=%d, delivery=%s)",
        firm_id, provider, call_event.caller_number,
        pop.client_name if pop.matched else "Unknown",
        event_id, delivery_result,
    )

    return JSONResponse({
        "status": "processed",
        "event_id": event_id,
        "matched": pop.matched,
        "client_name": pop.client_name if pop.matched else None,
        "delivery": delivery_result,
    })


# ---------------------------------------------------------------------------
# SSE Stream (authenticated — dashboard users)
# ---------------------------------------------------------------------------

@router.get("/api/phone/events/stream")
async def phone_events_stream(request: Request):
    """
    Server-Sent Events stream for real-time screen pops.

    The dashboard opens this connection on page load and receives
    screen pop events as they occur. Auto-reconnects via EventSource API.
    """
    if not is_authenticated(request):
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    firm_id = get_current_firm_id(request)
    username = request.session.get("username", "")

    if not firm_id or not username:
        return JSONResponse({"error": "Missing session data"}, status_code=400)

    from phone.delivery import get_registry, format_sse_event

    registry = get_registry()
    queue = await registry.register(firm_id, username)

    async def event_generator():
        """Generate SSE events from the user's queue."""
        try:
            # Send initial connection confirmation
            yield format_sse_event({
                "type": "connected",
                "firm_id": firm_id,
                "username": username,
                "timestamp": time.time(),
            }, event_type="system")

            while True:
                try:
                    # Wait for events with a timeout for keepalive
                    event = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield format_sse_event(event["data"], event_type=event.get("type", "screen_pop"))
                except asyncio.TimeoutError:
                    # Send keepalive comment to prevent connection timeout
                    yield ": keepalive\n\n"
                except asyncio.CancelledError:
                    break
        finally:
            await registry.unregister(firm_id, username)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )


# ---------------------------------------------------------------------------
# Test & Admin Endpoints (authenticated)
# ---------------------------------------------------------------------------

@router.post("/api/phone/test-pop")
async def test_screen_pop(request: Request):
    """
    Send a test screen pop to the current user.

    Admin/collections only. Used for testing the SSE connection and UI.
    """
    if not is_authenticated(request):
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    role = get_current_role(request)
    if role not in ('admin',):
        return JSONResponse({"error": "Admin only"}, status_code=403)

    firm_id = get_current_firm_id(request)
    username = request.session.get("username", "")

    from phone.events import ScreenPopPayload
    from phone.delivery import deliver_screen_pop

    # Build a test screen pop
    test_pop = ScreenPopPayload(
        firm_id=firm_id,
        call_event_id=0,
        caller_number="(314) 555-0100",
        caller_number_normalized="+13145550100",
        matched=True,
        client_id=99999,
        client_name="Test Client (Demo)",
        client_email="test@example.com",
        cases=[
            {
                "id": 1,
                "name": "Test v. State",
                "case_number": "26XX-CR00001",
                "practice_area": "DWI",
                "lead_attorney": "Demo Attorney",
                "phase": "Discovery",
            }
        ],
        last_payment={"amount": 500.00, "date": "Mar 15, 2026"},
        balance_due=2500.00,
        mycase_url=f"https://jcs-law1.mycase.com/contacts/clients/99999",
        target_username=username,
        timestamp=datetime.utcnow().isoformat(),
    )

    result = await deliver_screen_pop(test_pop)
    return JSONResponse({
        "status": "sent",
        "delivery": result,
    })


@router.get("/api/phone/stats")
async def phone_stats(request: Request):
    """Get call event statistics for the current firm."""
    if not is_authenticated(request):
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    role = get_current_role(request)
    if role not in ('admin',):
        return JSONResponse({"error": "Admin only"}, status_code=403)

    firm_id = get_current_firm_id(request)

    from db.phone import get_call_stats
    stats = get_call_stats(firm_id)

    from phone.delivery import get_registry
    registry = get_registry()
    connected = await registry.get_connected_count(firm_id)
    connected_users = await registry.get_connected_users(firm_id)

    return JSONResponse({
        **stats,
        "connected_users": connected,
        "connected_usernames": connected_users,
    })


@router.get("/api/phone/events")
async def phone_events_list(request: Request, limit: int = 50, offset: int = 0):
    """Get recent call events for the current firm."""
    if not is_authenticated(request):
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    role = get_current_role(request)
    if role not in ('admin',):
        return JSONResponse({"error": "Admin only"}, status_code=403)

    firm_id = get_current_firm_id(request)

    from db.phone import get_call_events
    events = get_call_events(firm_id, limit=min(limit, 200), offset=offset)

    # Serialize datetimes
    for e in events:
        for k, v in e.items():
            if isinstance(v, datetime):
                e[k] = v.isoformat()

    return JSONResponse({"events": events, "count": len(events)})


# ---------------------------------------------------------------------------
# Phone Settings Page (authenticated, admin only)
# ---------------------------------------------------------------------------

@router.get("/phone", response_class=HTMLResponse)
async def phone_settings_page(request: Request):
    """Phone integration settings and call log page."""
    if not is_authenticated(request):
        return RedirectResponse(url="/login", status_code=303)

    role = get_current_role(request)
    if role != 'admin':
        return RedirectResponse(url="/", status_code=303)

    firm_id = get_current_firm_id(request)

    from db.phone import get_active_integrations, get_call_events, get_call_stats

    integrations = get_active_integrations(firm_id)
    recent_events = get_call_events(firm_id, limit=25)
    stats = get_call_stats(firm_id, days=30)

    # Format datetimes for display
    for e in recent_events:
        if e.get('created_at'):
            e['created_at_display'] = e['created_at'].strftime('%b %d %I:%M %p')

    return templates.TemplateResponse("phone.html", {
        "request": request,
        "role": role,
        "username": request.session.get("username", ""),
        "firm_id": firm_id,
        "integrations": integrations,
        "recent_events": recent_events,
        "stats": stats,
        "webhook_base_url": f"/api/phone/webhook/{firm_id}",
    })
