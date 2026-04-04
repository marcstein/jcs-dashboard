# LawMetrics Caller ID Screen Pop — Feature Spec

**Author:** Marc Stein / LawMetrics
**Date:** April 4, 2026
**Status:** Draft

---

## Problem Statement

When a current client calls, staff have no context until they manually look up the caller. They answer blind, ask "who's calling," put the caller on hold, search the practice management system, then resume the conversation. This costs 30–90 seconds per call, creates a poor client experience, and happens dozens of times daily at every law firm. A screen pop that instantly identifies the caller, surfaces their active cases, and shows relevant status (upcoming deadlines, last payment, open tasks) would save significant time and make every client feel known.

## Goals

1. **Instant client identification:** When a call rings, the caller's name, active cases, and key status appear on screen within 2 seconds.
2. **Zero manual lookup:** Staff should never need to search for a client during an incoming call.
3. **Multi-provider support:** Work with the VoIP platforms law firms actually use — not locked to a single vendor.
4. **Multi-tenant by design:** Each firm configures their own phone provider, credentials, and preferences. No shared infrastructure between firms.
5. **Deep link to case record:** One click from the screen pop opens the full case in the firm's practice management system (MyCase, Clio, etc.).

## Non-Goals

1. **Outbound call initiation** — This feature handles incoming calls only. Click-to-dial from LawMetrics is a separate feature.
2. **Call recording or transcription** — Some VoIP APIs offer this, but it's out of scope. We surface caller identity, not call content.
3. **Traditional landline/PRI support** — The target market is on VoIP. Hardware CTI middleware is not worth the engineering investment.
4. **Phone system replacement** — We integrate with the firm's existing phone system. We don't handle call routing, IVR, or voicemail.
5. **Call logging/billing integration** — Logging calls to MyCase as billable time entries is a natural follow-on but not in this spec.

---

## User Stories

### Receptionist / Legal Assistant
- As a receptionist, I want to see who's calling before I answer so I can greet them by name.
- As a legal assistant, I want to see the caller's active cases so I can route the call to the right attorney without putting the client on hold.

### Attorney
- As an attorney, I want to see the caller's case status (phase, next deadline, last payment) when they ring my extension so I'm prepared before answering.
- As an attorney, I want to click directly to the client's case in MyCase so I can review details during the call.

### Firm Administrator
- As an admin, I want to connect our VoIP system to LawMetrics in a few clicks without needing a developer.
- As an admin, I want to see a log of matched and unmatched incoming calls to monitor how well the system is working.

---

## VoIP Provider Feasibility

| Provider | API Type | Incoming Call Event | Phase | Notes |
|---|---|---|---|---|
| **RingCentral** | REST + Webhooks | `telephony/sessions` subscription | Phase 1 | Best documented, largest market share |
| **Quo (OpenPhone)** | REST + Webhooks | `call.ringing` event | Phase 1 | Clean modern API, strong in small law firms |
| **Vonage** | REST + Webhooks | Answer URL / Event URL | Phase 1 | Very developer-friendly, strong docs |
| **Nextiva** | SDK + WebSocket | Real-time call events via SDK | Phase 2 | SDK-based, requires more integration work |
| **Ooma** | Enterprise API | Webhook action in callflows | Phase 2 | Enterprise tier only — not available on Office plans |
| **Corvum** | Zapier (beta) | No direct API | Phase 3 | Legal-specific but limited integration surface |
| **Grasshopper** | None | None | Not planned | No API — cannot integrate |

**Phase 1 covers 3 providers with the cleanest webhook support. These are likely the majority of the target market.**

---

## Architecture

### System Components

```
[VoIP Provider] --webhook--> [LawMetrics Webhook Service]
                                       |
                                       v
                              [Number Normalization]
                                       |
                                       v
                              [Client Lookup (PostgreSQL)]
                                       |
                                       v
                              [WebSocket Push to Dashboard]
                                       |
                                       v
                              [Screen Pop UI (Browser)]
```

### 1. Webhook Receiver (per-provider adapter)

Each VoIP provider sends call events in a different format. A thin adapter per provider normalizes the incoming payload to a standard internal event:

```python
# Internal call event (provider-agnostic)
{
    "firm_id": "jcs_law",
    "event_type": "call.ringing",
    "caller_number": "+13145551234",
    "called_number": "+13145559999",
    "called_extension": "101",         # if available
    "timestamp": "2026-04-04T10:30:00Z",
    "provider": "ringcentral",
    "raw_event_id": "abc123"
}
```

**Webhook endpoints:** Each firm gets a unique webhook URL:
```
POST /api/phone/webhook/{firm_id}/{provider}
```

The provider adapter validates the webhook signature (each provider has its own verification mechanism), extracts the caller number and called extension, and emits the normalized event.

### 2. Number Normalization

All phone numbers normalized to E.164 format before lookup:
- `(314) 555-1234` → `+13145551234`
- `314-555-1234` → `+13145551234`
- `+1 314 555 1234` → `+13145551234`
- `3145551234` → `+13145551234`

Client phone numbers in the database are also normalized on sync. A `phone_normalized` column on `cached_clients` stores the E.164 version for indexed lookup.

### 3. Client Lookup

Query path:
1. Normalize incoming number to E.164
2. Query `cached_clients` by `phone_normalized` (indexed)
3. If match: pull active cases from `cached_cases`, current phase, upcoming deadlines, last invoice status
4. If no match: return "Unknown Caller" with the phone number displayed
5. Return result as a screen pop payload

```sql
-- Fast indexed lookup
SELECT cc.id, cc.name, cc.email, cc.phone
FROM cached_clients cc
WHERE cc.firm_id = %s AND cc.phone_normalized = %s
LIMIT 1;

-- Then get active cases for the matched client
SELECT c.id, c.name, c.case_number, c.practice_area, c.status,
       c.lead_attorney_name,
       cph.current_phase
FROM cached_cases c
LEFT JOIN case_phase_history cph ON c.id = cph.case_id AND c.firm_id = cph.firm_id
WHERE c.firm_id = %s
  AND c.data_json::jsonb -> 'billing_contact' ->> 'id' = %s
  AND c.status = 'open'
ORDER BY c.created_at DESC;
```

### 4. Real-Time Delivery (WebSocket)

The LawMetrics dashboard maintains a WebSocket connection per logged-in user. When a call event matches a client:

1. Webhook receiver normalizes the event
2. Client lookup returns the match
3. Server pushes a `screen_pop` message over WebSocket to all logged-in users at that firm (or just the user whose extension is ringing, if extension mapping is configured)
4. Dashboard renders the pop-up card

**Fallback for firms without WebSocket:** Server-Sent Events (SSE) as a simpler alternative. The dashboard opens an SSE connection to `/api/phone/events/{firm_id}` and receives screen pop events as they occur.

### 5. Screen Pop UI

A slide-in card on the right side of the LawMetrics dashboard:

```
┌─────────────────────────────────┐
│  📞 Incoming Call               │
│  ─────────────────────────────  │
│  John Smith                     │
│  (314) 555-1234                 │
│                                 │
│  Active Cases:                  │
│  • Smith v. State - DWI         │
│    Phase: Discovery             │
│    Attorney: Anthony Muhlenkamp │
│    Next deadline: Apr 15        │
│                                 │
│  Last Payment: Mar 12 ($500)    │
│  Balance Due: $2,500            │
│                                 │
│  [Open in MyCase]  [Dismiss]    │
└─────────────────────────────────┘
```

The card auto-dismisses after 30 seconds (configurable) or when the user clicks Dismiss. "Open in MyCase" deep-links to the contact/case record.

---

## Database Changes

### New Tables

```sql
-- Phone integration config per firm
CREATE TABLE phone_integrations (
    id SERIAL PRIMARY KEY,
    firm_id VARCHAR(36) NOT NULL,
    provider VARCHAR(50) NOT NULL,        -- ringcentral, quo, vonage, nextiva, ooma
    is_active BOOLEAN DEFAULT TRUE,
    webhook_secret TEXT,                   -- provider-specific verification secret
    config JSONB NOT NULL DEFAULT '{}',   -- provider-specific config (API keys, account IDs)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(firm_id, provider)
);

-- Call event log (for analytics and debugging)
CREATE TABLE call_events (
    id SERIAL PRIMARY KEY,
    firm_id VARCHAR(36) NOT NULL,
    caller_number VARCHAR(20),
    caller_number_normalized VARCHAR(20),
    called_number VARCHAR(20),
    called_extension VARCHAR(20),
    matched_client_id INTEGER,            -- NULL if no match
    matched_client_name TEXT,
    provider VARCHAR(50),
    event_type VARCHAR(50),
    raw_payload JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_call_events_firm_date ON call_events(firm_id, created_at DESC);
CREATE INDEX idx_call_events_caller ON call_events(firm_id, caller_number_normalized);

-- Extension-to-user mapping (optional, for targeted pops)
CREATE TABLE phone_extensions (
    id SERIAL PRIMARY KEY,
    firm_id VARCHAR(36) NOT NULL,
    extension VARCHAR(20) NOT NULL,
    dashboard_username TEXT NOT NULL,      -- maps to dashboard_users.username
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(firm_id, extension)
);
```

### Modified Tables

```sql
-- Add normalized phone column to cached_clients
ALTER TABLE cached_clients ADD COLUMN IF NOT EXISTS phone_normalized VARCHAR(20);
CREATE INDEX IF NOT EXISTS idx_clients_phone_norm ON cached_clients(firm_id, phone_normalized);
```

The sync process populates `phone_normalized` by stripping all non-digit characters and prepending `+1` (US numbers).

---

## Requirements

### P0 — Must Have

| # | Requirement | Acceptance Criteria |
|---|---|---|
| 1 | Webhook receiver accepts incoming call events from RingCentral | RingCentral webhook fires on ring → LawMetrics receives and logs the event within 1 second |
| 2 | Phone number normalization to E.164 | All common US formats (parentheses, dashes, spaces, with/without country code) normalize correctly |
| 3 | Client lookup by normalized phone number | Incoming number matched to `cached_clients` record with >95% accuracy for numbers stored in the database |
| 4 | Screen pop displayed on dashboard | Matched caller's name, active cases, and key status appear in a slide-in card within 2 seconds of the call ringing |
| 5 | Unknown caller handling | Unmatched numbers display "Unknown Caller" with the phone number — no error, no blank screen |
| 6 | Call event logging | Every incoming call event (matched and unmatched) is logged to `call_events` table for analytics |
| 7 | Per-firm webhook URL | Each firm gets a unique webhook endpoint; events are scoped by `firm_id` |
| 8 | Webhook signature verification | Provider signatures are validated to prevent spoofed events |

### P1 — Nice to Have

| # | Requirement | Acceptance Criteria |
|---|---|---|
| 9 | Quo (OpenPhone) adapter | `call.ringing` webhook processed and normalized identically to RingCentral |
| 10 | Vonage adapter | Answer URL webhook processed and normalized |
| 11 | Deep link to MyCase case/contact record | "Open in MyCase" button navigates to the correct case page |
| 12 | Extension-to-user mapping | Screen pop only appears for the user whose extension is ringing |
| 13 | Screen pop auto-dismiss timer | Card disappears after configurable timeout (default 30s) |
| 14 | Dashboard setup wizard for phone integration | Admin can connect their VoIP provider from the firm settings page without CLI commands |

### P2 — Future Considerations

| # | Requirement |
|---|---|
| 15 | Nextiva adapter (SDK-based integration) |
| 16 | Ooma Enterprise adapter |
| 17 | Call logging to MyCase (post-call activity creation via API) |
| 18 | Call duration tracking and billable time suggestions |
| 19 | SMS/text message integration (incoming texts trigger similar lookup) |
| 20 | Click-to-dial from LawMetrics dashboard |
| 21 | Analytics dashboard: call volume trends, match rates, busiest hours |
| 22 | Browser extension for screen pop outside the LawMetrics dashboard |

---

## Success Metrics

### Leading Indicators (first 30 days)
- **Match rate:** >80% of incoming calls to the firm's main number match a client record
- **Pop latency:** <2 seconds from ring event to screen pop displayed
- **Webhook reliability:** <0.1% failed/dropped webhook deliveries

### Lagging Indicators (90 days)
- **Adoption:** >70% of firm staff have the dashboard open during business hours
- **Client satisfaction:** Reduction in "please hold while I look you up" moments (qualitative from firm feedback)
- **Feature retention:** Firms that enable caller ID keep it enabled (churn rate <5%)

---

## Open Questions

| # | Question | Owner |
|---|---|---|
| 1 | Does MyCase support direct URL deep-linking to a contact or case? (e.g., `https://firm.mycase.com/contacts/12345`) | Engineering — test against MyCase instance |
| 2 | What percentage of client records in a typical firm have phone numbers stored? Low coverage = low match rate. | Data — **ANSWERED**: JCS has 92.6% phone coverage (2,364 of 2,554 clients have at least one phone number; 89.7% have cell phone specifically). Well above 80% target. |
| 3 | Do firms want the screen pop on every user's screen, or only the person whose extension is ringing? | Product — survey 3-5 target firms |
| 4 | Should the screen pop include financial info (balance due, last payment) for all roles, or only admin/collections? | Product — align with existing RBAC model |
| 5 | What is the acceptable monthly cost per firm for webhook infrastructure? RingCentral and Quo APIs may have per-event pricing. | Business — review provider pricing tiers |
| 6 | Do we need HIPAA/confidentiality considerations for call event logging? | Legal |

---

## Timeline

### Phase 1: Core Infrastructure + RingCentral (Week 1–2)
- Database tables (`phone_integrations`, `call_events`, `phone_extensions`)
- Phone number normalization service + `phone_normalized` column on `cached_clients`
- Webhook receiver framework with provider adapter pattern
- RingCentral adapter (first provider)
- Client lookup service
- WebSocket or SSE push to dashboard
- Screen pop UI component
- Firm settings page for phone integration config

### Phase 2: Additional Providers + Polish (Week 3–4)
- Quo (OpenPhone) adapter
- Vonage adapter
- Deep-link to MyCase (pending answer to Open Question #1)
- Extension-to-user mapping
- Call event analytics (match rate, volume)
- Dashboard setup wizard

### Phase 3: Advanced Features (Week 5+)
- Nextiva SDK adapter
- Ooma Enterprise adapter
- Call logging to MyCase
- Browser notification fallback (for when dashboard isn't open)

---

## Key Files (Planned)

```
├── phone/                          # Phone integration package
│   ├── __init__.py
│   ├── normalize.py                # E.164 phone number normalization
│   ├── lookup.py                   # Client lookup by phone number
│   ├── events.py                   # Internal call event model
│   ├── adapters/                   # Per-provider webhook adapters
│   │   ├── __init__.py
│   │   ├── base.py                 # Abstract adapter interface
│   │   ├── ringcentral.py
│   │   ├── quo.py
│   │   └── vonage.py
│   └── delivery.py                 # WebSocket/SSE push to dashboard
├── db/
│   └── phone.py                    # Phone integration DB schema + queries
├── dashboard/
│   ├── routes/
│   │   └── phone.py                # Webhook endpoints + SSE stream
│   └── templates/
│       └── components/
│           └── screen_pop.html     # Screen pop card component
└── commands/
    └── phone.py                    # CLI: test webhook, check coverage, etc.
```

---

## Competitive Advantage

Most practice management tools (MyCase, Clio, PracticePanther) do not offer built-in caller ID screen pop. The few that do require specific VoIP partnerships (e.g., Clio + Corvum) or expensive third-party middleware. LawMetrics offering this as a multi-provider, plug-and-play feature at no extra charge would be a significant differentiator — especially for firms already evaluating VoIP-PM integration and finding it clunky or expensive.
