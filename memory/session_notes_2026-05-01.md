# Session Notes — May 1, 2026

## User
- **Marc Stein** (marc.stein@gmail.com) — LawMetrics.ai platform builder. Works with JCS Law Firm as primary client.

## Completed This Session

### 1. Competitive Analysis (LawMetrics vs Clio)
- Created two .docx reports: LawMetrics vs Clio standalone, then LawMetrics + ClientShield vs Clio + Vincent AI
- Key finding: Clio all-in cost is $228-330+/user/month (much higher than surface pricing)
- LawMetrics + ClientShield bundle wins 3 of 6 categories vs Clio, biggest edge in operations depth and privacy
- ClientShield: 8.3M case decisions, anonymization, Shepardizing, private VPC

### 2. Intake Automation System (Full Build)
- **`db/intake.py`**: Schema for leads, appointments, follow_ups, intake_forms, lead_custom_fields, marketing_spend, lead_utm_tracking
- **`dashboard/models/intake.py`**: Full intake data model (CRUD, pipeline, metrics, ROI calculations)
- **`dashboard/routes/intake.py`**: Routes for pipeline, lead detail, marketing ROI, public lead form, appointment scheduling
- **`dashboard/templates/intake.html`**: Pipeline view with Kanban-style cards, lead detail modal
- Features built: UTM parameter capture, marketing spend tracking, ROI calculations, conflict of interest checks, automated follow-up emails, appointment reminders (email + SMS), lead → MyCase case conversion, custom fields
- **Status**: Code complete, marketing analytics dashboard page in progress

### 3. LawPay Payment Links for Dunning (STAGED — NOT LIVE)
- **Purpose**: Add "Pay Now" buttons to dunning emails so clients can pay online via LawPay
- **Key constraint**: All payments are deferred retainer fees → IOLTA trust account. LawPay guarantees fee separation (fees from operating, deposits to trust). This is why Stripe can't be used.
- **Feature flag**: `lawpay_enabled` in `firms.notification_config` JSONB. Default OFF.

#### Files Created
- **`payments/__init__.py`** — Package init
- **`payments/lawpay.py`** (~295 lines) — Core LawPay API integration:
  - `create_payment_link()` → calls LawPay API, routes to trust account, returns PaymentLinkResult
  - `verify_webhook_signature()` → HMAC-SHA256 verification
  - `process_payment_webhook()` → records payment, updates payment_links
  - Reuses unexpired links (30-day expiry)
  - API base: `https://api.affinipay.com`
- **`db/payments.py`** (~250 lines) — Database layer:
  - Tables: `payment_links` (per-invoice tracking), `online_payments` (webhook records)
  - Functions: save/get/mark payment links, record online payments, stats (click rate, conversion)

#### Files Modified
- **`firm_settings.py`** — Added `get_lawpay_config()`, `is_lawpay_enabled()`, `get_lawpay_trust_account_id()`
- **`dunning_emails.py`** — Added:
  - `_payment_button_html(payment_url, stage)` — "Pay Now" button, color escalates by stage (blue→amber→red→black)
  - `_payment_button_text(payment_url)` — Plain text payment link
  - All 4 HTML generators + text generator accept `payment_url` param
  - `_get_payment_url()` on DunningEmailManager — creates link via LawPay, failures never block email
- **`dashboard/routes/api.py`** — Added 3 endpoints:
  - `POST /api/payments/webhook/{firm_id}` — LawPay webhook (signature verified, no session auth)
  - `GET /api/payments/link-click/{firm_id}/{invoice_id}` — Click tracking + redirect
  - `GET /api/payments/stats` — Admin/collections analytics

#### LawPay Config Keys (in firms.notification_config JSONB)
- `lawpay_enabled` (bool), `lawpay_public_key`, `lawpay_secret_key`
- `lawpay_trust_account_id`, `lawpay_operating_account_id`, `lawpay_webhook_secret`

#### Activation Steps (when firm approves)
1. Get LawPay API credentials from JCS's LawPay account
2. Set config: `UPDATE firms SET notification_config = notification_config || '{"lawpay_enabled": true, "lawpay_secret_key": "...", "lawpay_trust_account_id": "...", "lawpay_webhook_secret": "..."}'::jsonb WHERE id = 'jcs_law';`
3. Run `ensure_payment_tables()` from `db/payments.py` to create tables
4. Configure webhook URL in LawPay dashboard: `https://jcs.lawmetrics.ai/api/payments/webhook/jcs_law`

### 4. Spec Document Created
- **`Online_Payment_Links_Spec.docx`** — 10-section feature spec for LawPay integration. Covers business case, LawPay vs Stripe comparison, technical scope (7 components), implementation phases (6 phases, 5-7 weeks), prerequisites, cost analysis, security/compliance, risks, success metrics.

### 5. Test Lead Cleanup
- Deleted 2 test leads from intake testing (Marc Stein ID=1, BETH MARCADO ID=2)

## Open Items
- Marketing analytics dashboard page (`/intake/marketing`) — in progress, not yet complete
- End-to-end verification: public form → UTM capture → spend → ROI display
- LawPay integration staged but waiting for client approval before going live

## Key Decisions & Context
- **LawPay not Stripe**: Missouri Rule 4-1.15 — processing fees CANNOT be deducted from IOLTA trust deposits. LawPay guarantees this; Stripe doesn't.
- **LawPay fees**: Cards 2.99% + $0.30, Amex 3.90% + $0.30, eCheck 1% capped $10, monthly $19 + $4.99
- **Dunning payments = deferred retainer fees**: All go to trust account, not operating. IOLTA compliance is Day 1 requirement.
- **ClientShield integration**: LawMetrics bundles with ClientShield.ai for legal research, anonymization, Shepardizing capabilities that Clio lacks.
