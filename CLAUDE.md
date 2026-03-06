# JCS Law Firm - MyCase Automation Project

## Project Overview
Automated SOP compliance monitoring system for JCS Law Firm using MyCase API integration. Multi-tenant architecture powered by PostgreSQL.

## Architecture

### Database: PostgreSQL Only (No SQLite)
All data storage uses PostgreSQL with multi-tenant isolation via `firm_id`. There is NO SQLite anywhere in the codebase. Every module connects through the shared `db/connection.py` pool.

**Connection:** Set `DATABASE_URL` env var (e.g., `postgresql://user:pass@host:5432/mycase`)

**Key tables** (all include `firm_id` column):
- `cached_cases`, `cached_contacts`, `cached_invoices`, `cached_tasks`, `cached_events`, `cached_staff`, `cached_payments` — MyCase API cache
- `dunning_notices`, `payments`, `case_deadlines`, `attorney_notifications`, `invoice_snapshots`, `case_stage_history` — Tracking/analytics
- `case_phases`, `phase_history` — Case phase management
- `payment_promises` — Promise tracking
- `kpi_snapshots` — Trend analysis
- `payment_plan_payments`, `outreach_log`, `collections_holds`, `noiw_tracking` — Collections
- `aging_invoice_uploads` — Aging invoice CSV uploads (batch-based, latest batch used by dunning)
- `dashboard_users` — Dashboard login accounts with roles (admin, collections, attorney)
- `firms`, `templates`, `generated_documents` — Document engine
- `attorneys` — Attorney profiles
- `jurisdictions`, `courts`, `document_type_taxonomy` — Multi-state jurisdiction layer
- `jurisdiction_templates`, `court_forms`, `court_form_field_mappings` — Multi-state templates & PDF forms
- `attorney_bar_admissions`, `firm_jurisdictions`, `firm_office_locations` — Multi-state attorney/firm profiles

### Project Structure
```
├── commands/              # CLI command groups (Click)
│   ├── __init__.py
│   ├── collections.py     # Dunning, aging reports, preview
│   ├── documents.py       # Document generation, templates, attorneys
│   ├── notifications.py   # Slack/Email/SMS alerts
│   ├── phases.py          # Case phase tracking
│   ├── plans.py           # Payment plans, NOIW pipeline
│   ├── promises.py        # Payment promise tracking
│   ├── quality.py         # Case quality audits
│   ├── scheduler.py       # Automated task scheduling
│   ├── sop.py             # Staff SOP reports
│   ├── sync.py            # Data sync from MyCase
│   ├── tasks.py           # Task SLA, overdue tracking
│   └── trends.py          # KPI trend analysis
├── db/                    # Database layer (PostgreSQL only)
│   ├── __init__.py
│   ├── connection.py      # Connection pool, get_connection()
│   ├── cache.py           # MyCase API cache (multi-tenant)
│   ├── tracking.py        # Dunning, payments, deadlines, notifications
│   ├── phases.py          # Case phase schema and queries
│   ├── promises.py        # Payment promise schema and queries
│   ├── trends.py          # KPI snapshot schema and queries
│   ├── documents.py       # Template storage, FTS
│   └── attorneys.py       # Attorney profile schema and queries
├── dashboard/             # FastAPI web dashboard
│   ├── app.py
│   ├── routes/            # Route handlers split by domain
│   │   ├── main.py        # Home, staff pages
│   │   ├── ar.py          # A/R and collections
│   │   ├── attorneys.py   # Attorney productivity
│   │   ├── documents.py   # Document generation UI
│   │   ├── noiw.py        # NOIW pipeline
│   │   ├── phases.py      # Case phases
│   │   ├── trends.py      # KPI trends
│   │   └── ...
│   ├── models/            # Data access split by domain
│   │   ├── ar.py
│   │   ├── attorneys.py
│   │   ├── tasks.py
│   │   └── ...
│   ├── templates/
│   └── static/
├── tests/                 # Test suite
│   ├── conftest.py        # Shared fixtures, test DB setup
│   ├── test_collections.py
│   ├── test_phases.py
│   ├── test_promises.py
│   ├── test_noiw.py
│   ├── test_dunning.py
│   ├── test_cache.py
│   ├── test_documents.py
│   ├── test_dashboard.py
│   ├── test_template_generation.py  # Template fill tests (all 56 templates)
│   ├── test_prelaunch_docgen.py     # Pre-launch: document generation harness
│   ├── test_prelaunch_chat.py       # Pre-launch: AI chat harness
│   ├── run_prelaunch.py             # Pre-launch: test runner + report generator
│   └── reports/                     # Generated test reports
├── templates/             # Email/notification templates
├── reports/               # Generated SOP compliance reports
├── data/templates/        # Templated .docx files with {{placeholders}}
│   ├── Filing_Fee_Memo_Unified.docx
│   ├── Bond_Assignment_Templated.docx
│   └── Waiver_of_Arraignment_Generic.docx
├── import_filing_fee_memo.py   # Template import script (Filing Fee Memo)
├── reimport_bond_template.py   # Template import script (Bond Assignment)
├── setup_users.py         # Dashboard user provisioning (RBAC accounts from caseload)
├── agent.py               # CLI entry point (thin — registers command groups)
├── api_client.py          # MyCase API client with OAuth, rate limiting
├── config.py              # Configuration (DATABASE_URL, env vars)
└── ...                    # Business logic modules
```

## Staff & Roles
- **Melissa Scarlett** - AR Specialist (collections, payment plans, aging reports)
- **Ty Christian** - Intake Lead (new client intake, lead tracking, case setup)
- **Tiffany Willis** - Senior Paralegal (task management, team operations, daily huddles)
- **Alison Ehrhard** - Legal Assistant (case tasks, discovery, license filings)
- **Cole Chadderdon** - Legal Assistant (case tasks, discovery, license filings)

### Key Staff IDs
| Staff Member | ID | Role |
|-------------|-----|------|
| Tiffany Willis | 31928330 | Senior Paralegal |
| Alison Ehrhard | 41594387 | Legal Assistant |
| Cole Chadderdon | 56011402 | Legal Assistant |

## Key Modules

### Business Logic
- `api_client.py` - MyCase API client with OAuth, rate limiting, pagination
- `kpi_tracker.py` - KPI tracking and reporting
- `intake_automation.py` - Intake metrics, leads/case tracking
- `task_sla.py` - Task SLA monitoring, overdue tracking
- `payment_plans.py` - Payment plan compliance, NOIW pipeline
- `case_quality.py` - Case quality audits, data integrity checks
- `promises.py` - Payment promise tracking and monitoring
- `notifications.py` - Multi-channel notifications (Slack, Email, SMS)
- `trends.py` - Historical KPI trend analysis
- `case_phases.py` - Universal 7-phase case management framework
- `scheduler.py` - Automated task scheduling and cron management

### Document Generation
- `document_chat.py` - Conversational document generation engine
- `document_engine.py` - Multi-tenant template database and generation
- `attorney_profiles.py` - Attorney/firm signature block management
- `courts_db.py` - Missouri courts and agencies registry

## API Notes

### MyCase API Endpoints Used
- `/cases` - Case management
- `/contacts` - Client contacts
- `/leads` - Lead tracking (discovered - separate from contacts)
- `/tasks` - Task management
- `/invoices` - Billing/AR
- `/staff` - Staff directory

### Important API Quirks
- Tasks use `staff` field (array of `{id: ...}` objects), not `assignee`
- Need staff lookup table to resolve IDs to names
- Leads endpoint exists at `/leads` (not filtered contacts)
- Historical leads from 2022 - feature not actively used
- Use case creation dates as proxy for intake metrics
- **Tasks API only returns tasks for OPEN cases** - closed case tasks are not returned
- **Invoices have NULL `contact_id`** - the `cached_invoices.contact_id` column is never populated by MyCase API. To find the client for an invoice, join through the case: `cached_invoices.case_id` → `cached_cases.data_json::jsonb -> 'billing_contact' ->> 'id'` → `cached_clients.id`. The case `data_json` also has `clients` and `contacts` arrays (all contain `{id: N}` objects).
- **`cached_contacts` has no emails** - only `id` and `name` from MyCase API. Client emails are in `cached_clients.email` (2,247 of 2,475 have emails).

## Cache & Sync Behavior

### How Sync Works
The sync uses **upsert logic** (`INSERT ... ON CONFLICT DO UPDATE`) in PostgreSQL — records are NEVER deleted:
- Records in API but not cache → inserted
- Records in both and changed → updated
- Records in both but unchanged → left alone
- Records in cache but not API → **preserved forever**
- All cache tables include `firm_id` for multi-tenant isolation
- Batch operations use `psycopg2.extras.execute_values()` for 10-50x performance

### Task Data Accumulation
Because the MyCase API only returns tasks for open cases:
1. Tasks from closed cases ARE preserved in cache once synced
2. The longer the cache runs, the more complete historical task data becomes
3. Tasks that were never synced (case closed before cache existed) will never appear
4. Paralegal metrics show tasks from their active cases at time of sync

### Important: RealDictCursor Gotcha
`get_connection()` sets `conn.cursor_factory = RealDictCursor`, so `conn.cursor()` returns dict-like rows. **Iterating a RealDictRow yields keys, not values** — `dict(zip(columns, row))` will map column names to column names. For code that needs tuple rows (e.g. `execute_chat_query`), use a direct `psycopg2.connect()` instead of the pool. Passing `cursor_factory=psycopg2.extensions.cursor` to `conn.cursor()` does NOT reliably override the connection-level setting.

### Aging Invoice Uploads
- Table: `aging_invoice_uploads` with `upload_batch_id` for batch grouping
- Each CSV upload creates a new batch; old batches preserved for audit trail
- Dunning query uses CTE `latest_aging_batch` to find most recent batch per firm
- LEFT JOIN with dunning invoices: matched invoices show `amount_now_due` from aging; unmatched fall back to `balance_due`
- Upload endpoint: `POST /api/aging-upload` (FastAPI UploadFile)
- History endpoint: `GET /api/aging-upload/history` (last 10 uploads)
- Flexible CSV parsing: `_normalize_header()` maps various column names; `_parse_currency()` handles `$1,234.56`; `_parse_date()` handles multiple formats

### AI Chat (Dashboard)
- System prompt in `CHAT_SYSTEM_PROMPT` tells Claude to generate PostgreSQL queries
- `execute_chat_query()` uses direct `psycopg2.connect()` (NOT the pool) for plain tuple cursor
- `format_query_results()` handles float, int, Decimal types; detects currency/rate/year columns
- PostgreSQL `ROUND()` requires `::numeric` cast — system prompt instructs this
- `EXTRACT(YEAR FROM ...)` returns float — formatter detects year-like values and displays as int
- **Production restart**: always clear `__pycache__` before restart: `find /opt/jcs-mycase -name __pycache__ -type d -exec rm -rf {} +`

## Current Metrics (Jan 2026)

### AR/Collections
- Total AR: $1.45M
- 82.2% over 60 days (target <25%) - CRITICAL
- Payment plan compliance: 7.6% (target ≥90%) - CRITICAL
- NOIW pipeline: 163 open cases 30+ days delinquent ($620K total)
  - 147 critical (60+ days), 16 high (30-59 days)
  - 83 cases over 180 days delinquent

### Intake
- 16 new cases/week
- Case types: DWI (44%), Traffic (25%), Other (19%), Municipal (6%), Expungement (6%)
- 100% lead attorney assigned

### Tasks
- 42 overdue tasks
- Top offenders: Heidi Leopold (25), Anthony Muhlenkamp (13)
- Common: Review Discovery, Client History Worksheet, Signed EA Agreement

### Quality
- Average score: 58.1% (target ≥90%)
- Issues: Missing lead attorney, missing client contact info

## CLI Commands

```bash
# Activate environment
source .venv/bin/activate

# SOP Reports
uv run python agent.py sop melissa    # AR/Collections report
uv run python agent.py sop ty         # Intake report
uv run python agent.py sop tiffany    # Paralegal ops huddle
uv run python agent.py sop alison     # Legal assistant tasks

# Payment Plans
uv run python agent.py plans sync       # Sync from MyCase
uv run python agent.py plans compliance # Compliance report

# NOIW Pipeline (Notice of Intent to Withdraw)
uv run python agent.py plans noiw-pipeline            # Show NOIW pipeline with summary
uv run python agent.py plans noiw-pipeline --limit 20 # Limit results
uv run python agent.py plans noiw-pipeline --export   # Export to CSV
uv run python agent.py plans noiw-sync                # Sync pipeline to tracking table
uv run python agent.py plans noiw-status              # Show workflow status summary
uv run python agent.py plans noiw-list pending        # List cases by status
uv run python agent.py plans noiw-update <case> <inv> <status>  # Update case status

# Dunning / Collections
uv run python agent.py collections report             # Generate aging report
uv run python agent.py collections preview            # Preview dunning queue (all stages)
uv run python agent.py collections preview --stage 1  # Preview stage 1 only (5-14 days)
uv run python agent.py collections preview --stage 4  # Preview stage 4 only (45+ days)
uv run python agent.py collections preview --export   # Export queue to CSV
uv run python agent.py collections dunning --dry-run  # Simulate sending notices
uv run python agent.py collections dunning --execute  # LIVE: Actually send notices
uv run python agent.py collections test-email --stage 1 --to email@example.com  # Test email config

# Quality
uv run python agent.py quality summary  # Quality audit
uv run python agent.py quality audit    # Run audit on recent cases

# Tasks
uv run python agent.py tasks sync       # Sync tasks from MyCase

# Scheduler (Automated Tasks)
uv run python agent.py scheduler status          # Show all scheduled tasks & last run times
uv run python agent.py scheduler list            # List all tasks with details
uv run python agent.py scheduler run <task>      # Run a specific task
uv run python agent.py scheduler run-due         # Run all tasks that are currently due
uv run python agent.py scheduler enable <task>   # Enable a task
uv run python agent.py scheduler disable <task>  # Disable a task

# Cron Management
uv run python agent.py scheduler cron show       # Show cron entries
uv run python agent.py scheduler cron install    # Install cron jobs (use --execute to actually install)
uv run python agent.py scheduler cron remove     # Remove cron jobs

# Payment Promises
uv run python agent.py promises add <contact_id> <amount> <YYYY-MM-DD>  # Record a promise
uv run python agent.py promises list             # List pending promises
uv run python agent.py promises due-today        # Promises due today
uv run python agent.py promises overdue          # Overdue promises
uv run python agent.py promises kept <id> <amt>  # Mark promise as kept
uv run python agent.py promises broken <id>      # Mark promise as broken
uv run python agent.py promises check            # Daily promise report
uv run python agent.py promises stats            # Promise-keeping statistics

# Notifications (Slack/Email/SMS)
uv run python agent.py notify status             # Show notification config status
uv run python agent.py notify test-slack         # Test Slack webhook
uv run python agent.py notify test-email <addr>  # Test email
uv run python agent.py notify send-report <type> # Send report to Slack
  # Report types: daily_ar, intake_weekly, overdue_tasks, noiw_daily, noiw_critical, noiw_workflow
uv run python agent.py notify log                # View notification history

# NOIW Notifications (quick access)
uv run python agent.py plans noiw-notify daily    # Send daily NOIW summary to Slack
uv run python agent.py plans noiw-notify critical # Send critical cases alert
uv run python agent.py plans noiw-notify workflow # Send workflow status update

# Trend Analysis
uv run python agent.py trends record             # Record today's KPI snapshot
uv run python agent.py trends dashboard          # Show trends dashboard with sparklines
uv run python agent.py trends report             # Generate trend analysis report
uv run python agent.py trends analyze <metric>   # Analyze specific metric trend
uv run python agent.py trends compare <metric>   # Week-over-week or month-over-month comparison

# Case Phases (integrated into agent CLI)
uv run python agent.py phases init           # Initialize phases, mappings, and workflows
uv run python agent.py phases list           # List all 7 universal phases
uv run python agent.py phases mappings       # List MyCase stage → phase mappings
uv run python agent.py phases workflows      # List case-type specific workflows
uv run python agent.py phases sync           # Sync case phases from cache
uv run python agent.py phases sync --stages-only  # Sync stages from MyCase API
uv run python agent.py phases report         # Generate phase distribution report
uv run python agent.py phases stalled        # List cases stalled in current phase
uv run python agent.py phases case <id>      # Show phase history for a case
```

## Scheduled Tasks

### Daily Tasks (Weekdays)
| Time | Task | Owner | Command |
|------|------|-------|---------|
| 6:00 AM | Data Sync | - | `sync` |
| 7:00 AM | Payment Plan Compliance | Melissa | `plans compliance` |
| 7:15 AM | NOIW Sync | Melissa | `plans noiw-sync` |
| 7:30 AM | Dunning Cycle | Melissa | `collections dunning` |
| 7:45 AM | Ops Huddle Prep | Tiffany | `tasks ops-huddle` |
| 8:00 AM | NOIW Daily Alert | Melissa | `plans noiw-notify daily` |
| 8:00 AM | Deadline Notifications | - | `deadlines notify` |
| 8:00 AM | License Deadline Check | Alison | `tasks license-deadlines` |
| 8:30 AM | Overdue Task Alerts | - | `deadlines overdue` |
| 9:00 AM | Quality Audit | Tiffany | `quality audit` |

### Weekly Tasks
| Day | Time | Task | Owner |
|-----|------|------|-------|
| Monday | 9:00 AM | Weekly A/R Report | Melissa |
| Monday | 9:30 AM | Weekly Intake Report | Ty |
| Wednesday | 9:00 AM | A/R Huddle Report | Melissa |
| Friday | 2:00 PM | NOIW Pipeline Review | Melissa |
| Friday | 2:30 PM | NOIW Workflow Report | Melissa |
| Friday | 4:00 PM | Weekly Quality Summary | Tiffany |

### Monthly Tasks
| Day | Time | Task | Owner |
|-----|------|------|-------|
| 1st | 10:00 AM | Monthly Intake Review | Ty |
| 1st | 10:00 AM | Monthly Collections Report | Melissa |

## License Filing Deadlines (Critical)
- **DOR (Administrative Hearing)**: 15 days from arrest (client did NOT refuse test)
- **PFR (Petition for Review)**: 30 days from arrest (client REFUSED test)

## New Features

### Payment Promise Tracking
Track client payment promises during collections calls:
- Record promises with expected date and amount
- Auto-detect broken promises (payment not received by date)
- Track promise-keeping rate by client (for risk assessment)
- Daily promise monitoring report

### Multi-Channel Notifications
Send alerts via Slack, Email (SendGrid), or SMS (Twilio):
- Configure via environment variables or `data/notifications_config.json`
- Dry-run mode for testing (default)
- Slack webhooks for team alerts and daily reports
- Email for individual notifications
- SMS for critical alerts

### Historical Trend Analysis
Track and visualize KPI trends over time:
- Daily KPI snapshots stored in database
- Week-over-week and month-over-month comparisons
- Sparkline visualizations in terminal
- Trend direction detection (improving/declining/stable)
- Gap-to-target analysis

### Case Phase Tracking
Universal 7-phase framework mapping MyCase stages to standardized phases:

**The 7 Universal Phases:**
| # | Phase | Short Name | Owner | Typical Duration |
|---|-------|------------|-------|------------------|
| 1 | Intake & Case Initiation | Intake | Intake Team | 1-3 days |
| 2 | Discovery & Investigation | Discovery | Paralegals | 14-56 days |
| 3 | Legal Analysis & Motion Practice | Motions | Attorneys | 21-70 days |
| 4 | Case Strategy & Negotiation | Strategy | Attorneys | 14-42 days |
| 5 | Trial Preparation | Trial Prep | Attorneys | 14-56 days |
| 6 | Disposition & Sentencing | Disposition | Attorneys | 1-42 days |
| 7 | Post-Disposition & Case Closure | Closing | Admin | 7-28 days |

**Current Distribution (749 cases):**
- Intake: 128 | Discovery: 265 | Motions: 106 | Strategy: 165
- Trial Prep: 10 | Disposition: 17 | Closing: 58

**Case-Type Workflows:** Municipal, DWI/PFR, Expungement, License Reinstatement

## Configuration

All configuration via environment variables (see Environment Variables section under Document System). No file-based config — notification preferences stored in PostgreSQL `notification_config` table per firm.

## Dashboard

### Running the Dashboard
```bash
uv run python agent.py dashboard --host 0.0.0.0 --port 3000
```
Access at: http://127.0.0.1:3000 (login: firm_id=jcs_law, username=admin, password=admin)
Production: https://jcs.lawmetrics.ai

### Dashboard Routes
- `/` - Main dashboard with SOP widgets
- `/attorneys` - Attorney productivity with invoice aging buckets
- `/ar` - A/R and collections dashboard
- `/noiw` - NOIW pipeline with workflow status filtering
- `/phases` - Case phase distribution and stalled cases
- `/trends` - Historical KPI trends with sparklines
- `/promises` - Payment promise tracking and reliability
- `/payments` - Payment analytics: time-to-payment by attorney and case type
- `/dunning` - Dunning notices preview and approval (two-amount columns: Amount Due Now + Total Balance)
- `/aging-upload` - Aging invoice CSV upload (drag-and-drop, upload history)
- `/staff/{name}` - Individual staff detail pages
- `/wonky` - Invoices requiring attention

### Dashboard Files
- `dashboard/app.py` - FastAPI application
- `dashboard/auth.py` - Authentication (multi-tenant, firm_id from login), role/attorney_name session management
- `dashboard/config.py` - Configuration (env vars, admin credentials)
- `dashboard/routes/` - Route handlers split by domain (main, ar, attorneys, noiw, phases, trends, promises, payments, api, documents) — each has role guards
- `dashboard/models/` - Data access split by domain (base, ar, attorneys, tasks, etc.) — all support attorney data scoping
- `dashboard/templates/` - Jinja2 templates (base.html has role-conditional navigation)
- `dashboard/static/` - CSS styles

### Multi-Tenant Authentication
- Login requires **firm_id**, username, and password
- firm_id is stored in session and used by `get_data(request)` to create per-request `DashboardData(firm_id=X, attorney_name=Y)`
- Each route handler calls `data = get_data(request)` — NO module-level `DashboardData()` singletons
- Env-based admin fallback: `DASHBOARD_ADMIN_USER`/`DASHBOARD_ADMIN_PASSWORD_HASH` (works with any valid firm_id)
- DB users: `dashboard_users` table with `UNIQUE(firm_id, username)` constraint

### Role-Based Access Control (RBAC)

Three roles control what users see and access:

| Role | Navigation | Data Scope | Home Page |
|------|-----------|------------|-----------|
| `admin` | Full: Home, Attorneys, AR, NOIW, Phases, Trends, Payments, Dunning, Documents | All firm data | `/` (main dashboard) |
| `collections` | AR, NOIW, Dunning, Payments, Aging Upload | All firm financial data | `/ar` |
| `attorney` | Attorneys, Documents, Phases, Trends, Payments | **Own cases only** (filtered by `lead_attorney_name`) | `/attorneys` |

**Session variables**: `role`, `attorney_name` (set at login from `dashboard_users` table)

**Route guards**: Each route checks `request.session.get("role")` and returns 403 if unauthorized. Attorney role is blocked from: `/` (home), `/ar`, `/noiw`, `/promises`, `/dunning`, `/aging-upload`.

**Attorney data scoping**: When `attorney_name` is set in session, `DashboardData` passes it through to all model classes. The `_attorney_case_filter(table_alias)` helper in `dashboard/models/base.py` returns a `(sql_fragment, params)` tuple that appends `AND {table}.lead_attorney_name = %s` to queries. This filters:
- Attorney productivity (active cases, invoices, aging buckets)
- A/R and payment analytics (invoices joined through `cached_cases`)
- Phase distribution and velocity (joins `case_phase_history` → `cached_cases`)
- Trends (live-computed metrics instead of firm-wide KPI snapshots)
- Cross-attorney page access is blocked (attorney can only view their own `/attorneys/{name}` page)

**Navigation**: `base.html` uses `{% if role != 'attorney' %}` to conditionally show/hide nav items. Promises tab removed from all roles.

### Dashboard Users
- Login: `dashboard_users` table checked first, then env-based admin fallback
- Table columns: `firm_id`, `username`, `password_hash`, `role` (admin/collections/attorney), `attorney_name` (for attorney role)
- DB-created users: `firm_id` must match what user enters on login form (e.g. `jcs_law`)
- Env admin: `DASHBOARD_ADMIN_USER`/`DASHBOARD_ADMIN_PASSWORD_HASH` in `.env`; if hash not set, defaults to password `admin`
- Generate password hash: `python -c "from werkzeug.security import generate_password_hash; print(generate_password_hash('your_password'))"`

### User Provisioning (setup_users.py)
```bash
python setup_users.py --firm-id jcs_law --admin-password <password>
```
- Discovers lead attorneys from `cached_cases` (only those with open cases)
- Creates one `attorney` account per lead attorney (username = lowercase first name, e.g. `anthony`)
- Creates `collections` account for Melissa Scarlett (username = `melissa`)
- Updates admin password if specified
- Prints credential table — save output since passwords are randomly generated
- Uses upsert logic — safe to re-run (updates existing users, adds new ones)

### Key Metrics Displayed
- **A/R Overview**: Total AR, 60-120 day, 180+ day (uncollectible)
- **Attorney Productivity**: Active cases, invoice aging by DPD buckets
- **Staff Widgets**: Active cases, tasks done (ratio format), overdue tasks
- **Firm Tasks Overview**: Open tasks, done this week, overdue count

## Change Log

### v3.0 — Multi-State Document Engine (Planned)
- Architecture specification complete: `MULTI_STATE_ARCHITECTURE.md` and `.docx`
- Phase 1 states: California, Iowa, Illinois, Minnesota, Kentucky, Oklahoma
- 8 new database tables for jurisdiction layer (see architecture doc Section 3)
- PDF form engine for mandatory court forms via `pypdf`
- Multi-state attorney profiles with per-jurisdiction bar admissions and office addresses
- Court registry with ~297 court entries across 6 states
- ~130 new state-specific .docx templates + ~28 PDF form integrations
- 16-week implementation roadmap across 8 work packages
- Iowa first (proof-of-concept), California largest market target

### v2.0 — PostgreSQL Migration & Multi-Tenant Isolation (In Progress)
- Removing all SQLite — unified PostgreSQL multi-tenant database layer
- Split `agent.py` (3,665 lines) into `commands/` package
- Split `dashboard/models.py` (2,543 lines) into `dashboard/models/` package
- Split `dashboard/routes.py` (1,154 lines) into `dashboard/routes/` package
- Added pytest test suite for business logic
- Migrated FTS5 full-text search to PostgreSQL `tsvector`/`tsquery`
- Removed legacy `.db` files and duplicate modules
- **Multi-tenant firm_id isolation**: Removed all module-level `DashboardData()` singletons from route files; each handler uses `data = get_data(request)` for per-request scoping
- **Login with firm_id**: Added firm_id field to login screen; firm_id stored in session for all subsequent data queries
- **Removed "default" firm_id**: No fallback to "default" — only real firm_ids are valid
- **Dunning computed live**: Dunning queue now computed from `cached_invoices` (all years, all open cases with balance > 0 and 5+ days overdue) instead of `dunning_notices` table
- **Dashboard buttons replace CLI**: Dunning page has Preview/Send/Export buttons; removed CLI command references from dashboard, promises, trends, and reports templates
- **Rebranded to LawMetrics**: Removed all ClientShield references; branding is now LawMetrics.ai across all templates and navigation
- **Production deployment**: `jcs.lawmetrics.ai` on port 3000, service `jcs-dashboard`
- **FIRM_ID env var**: SyncManager reads `FIRM_ID` env var first (e.g. `jcs_law`), avoiding the MyCase API UUID (`d5AgNpGZZvZ9Lgpce7ri4Q`) as firm_id
- **Fixed INTERVAL parameterization**: Rolling 6-month attorney queries used `INTERVAL '%s months'` which psycopg2 doesn't substitute inside quotes; changed to `INTERVAL '1 month' * %s`
- **Fixed dunning due_date casting**: Added `::date` cast in dunning queries to handle timestamp columns; handle both int and timedelta returns from date subtraction
- **Role-based access control**: Three roles (admin, collections, attorney) with role-conditional navigation, route guards, and attorney-scoped data filtering via `lead_attorney_name` on `cached_cases`
- **Attorney data scoping**: `_attorney_case_filter()` helper in `dashboard/models/base.py` provides reusable SQL fragment for attorney isolation across all model classes (attorneys, AR, phases, trends, payments)
- **Attorney live metrics**: Trends page computes attorney-specific KPIs live (total_ar, ar_over_60_pct, overdue_tasks) instead of using firm-wide `kpi_snapshots`
- **User provisioning script**: `setup_users.py` auto-discovers attorneys from caseload and creates dashboard accounts with appropriate roles
- **Removed Promises from nav**: Promises tab hidden from all roles (feature deprioritized)
- **Fixed template identification bugs**: Added cross-check in `_identify_template()` to correct variant mismatches — "motion to dismiss" no longer resolves to DOR variant, "entry of appearance for municipal court" no longer resolves to state variant
- **E2E chat test resilience**: Broadened expected column matching with synonym dictionary to handle Claude's non-deterministic column aliases across runs
- **Change password page**: `/change-password` route with 8-char minimum, one number, one special character requirement. Server-side (`validate_password()` in `auth.py`) and client-side validation. Nav username is now a clickable link to change password.
- **Auto-set signing attorney from session**: Document chat endpoint looks up logged-in attorney's profile and passes `attorney_id` to `DocumentChatEngine`
- **Attorney name override for document signing**: When logged-in attorney has no row in `attorneys` table, `attorney_name_override` parameter overrides name-related fields (attorney_name, signing_attorney, service_signatory, etc.) while keeping firm details (address, phone, fax) from primary attorney profile
- **Dunning emails switched to Outlook**: Draft button uses `mailto:` link instead of Gmail compose URL — opens pre-filled email in Outlook desktop
- **Fixed firm phone number**: Dunning email drafts now use correct firm phone (314) 561-9690
- **Planned: Outlook SMTP batch dunning**: Batch email sending via firm's Outlook/Exchange SMTP server (replacing SendGrid for dunning notices), triggered by dashboard button

### v1.x — Feature Build-Out (Completed)
1. Fixed task assignee display - now uses staff lookup table
2. Added `/leads` endpoint support to API client
3. Added case creation proxy for intake metrics when no leads data
4. Fixed NoneType error on lead status with null-safe accessor
5. Added scheduled automation with cron support (`scheduler.py`)
6. Added payment promise tracking (`promises.py`)
7. Added multi-channel notifications (`notifications.py`)
8. Added historical trend analysis (`trends.py`)
9. Fixed paralegal widgets: changed from "Closed Cases" to "Tasks Done" (ratio format)
10. Fixed Firm Tasks Overview widget: removed misleading 0% quality score, added balanced metrics
11. Added attorney productivity dashboard with invoice aging buckets (60-180 DPD, 180+ DPD)
12. Added year-based billing columns to attorney productivity page
13. Added case phase tracking module (`case_phases.py`) with 7-phase universal framework
14. Mapped 30 MyCase stages to universal phases (749 cases tracked)
15. Added dashboard Case Phases page (`/phases`) with distribution, velocity, stalled cases
16. Added dashboard Trends page (`/trends`) with sparklines and WoW/MoM comparisons
17. Added license deadline SMS alerts (`tasks license-notify --sms`)
18. Added dashboard Promises page (`/promises`) with promise-keeping rate tracking
19. Added NOIW/payment email templates (noiw_warning, noiw_final_notice, payment_plan_confirmation, promise_reminder, promise_broken)
20. Added attorney stalled case notifications (`phases notify-attorneys`)
21. Added dashboard Payment Analytics page (`/payments`) with time-to-payment by attorney and case type
22. Added dashboard Dunning Preview page (`/dunning`) with stage breakdown and approval workflow
23. Added `collections preview` CLI command to preview dunning notices before sending
24. Added `collections test-email` CLI command to test email configuration

---

## LawMetrics.ai Document Generation System

### Overview
Multi-tenant, AI-powered document generation platform for law firms. Lawyers can request documents in natural language, and the system identifies templates, collects required variables, and generates professional legal documents.

### Key Files

#### Document Generation
- `document_chat.py` - Conversational document generation engine
- `document_engine.py` - Multi-tenant template database and generation
- `attorney_profiles.py` - Attorney/firm signature block management
- `courts_db.py` - Missouri courts and agencies registry

#### Multi-State Expansion
- `MULTI_STATE_ARCHITECTURE.md` - Full architecture spec (10 sections, SQL DDL, pipeline diagrams)
- `MULTI_STATE_ARCHITECTURE.docx` - Same content, formatted Word document
- `Multi_State_Expansion_Analysis.xlsx` - State comparison spreadsheet (3 tabs: State Overview, Document Type Mapping, Expansion Phases)

#### Configuration
- `docs/TEMPLATE_FOLDER_STRUCTURE.md` - Recommended folder structure for firms
- `docs/API_COST_ANALYSIS.md` - Claude API cost projections

### Document Types Supported

The system has predefined document types in `DOCUMENT_TYPES` registry:

#### Motions to Dismiss
| Type | Key | Description |
|------|-----|-------------|
| General | `motion_to_dismiss_general` | Voluntary dismissal, no grounds |
| DOR | `motion_to_dismiss_dor` | DOR case (Petitioner/Respondent) |
| Criminal | `motion_to_dismiss_criminal` | Criminal case (Defendant) |
| Failure to State Claim | `motion_to_dismiss_failure_to_state_claim` | Rule 55.27(a)(6) |
| Lack of Jurisdiction | `motion_to_dismiss_lack_jurisdiction` | Rule 55.27(a)(1) |
| Improper Venue | `motion_to_dismiss_improper_venue` | Rule 55.27(a)(3) |
| Statute of Limitations | `motion_to_dismiss_sol` | Time-barred claims |
| Failure to Prosecute | `motion_to_dismiss_failure_to_prosecute` | Rule 67.02 |

#### Filing Fee Memo
| Type | Key | Variables Asked | Auto-Filled from Attorney Profile |
|------|-----|-----------------|-----------------------------------|
| Filing Fee Memorandum | `filing_fee_memo` | petitioner_name, case_number, county, respondent_name, filing_fee | firm_name, attorney_name, attorney_bar, firm_address, firm_city_state_zip, firm_phone, firm_fax, attorney_email |

Optional variables (with defaults): signing_attorney, signing_attorney_bar, signing_attorney_email, party_role (default: "Petitioner"), service_signatory

**Template consolidation:** 4 variants (ATM, DCC, Memo.docx, Memo.doc) were consolidated into a single unified template (`data/templates/Filing_Fee_Memo_Unified.docx`) with 18 `{{placeholder}}` variables. Old templates deactivated in database.

#### Bond Documents
| Type | Key | Variables Asked | Auto-Filled from Attorney Profile |
|------|-----|-----------------|-----------------------------------|
| Assignment of Cash Bond | `bond_assignment` | defendant_name, case_number, county, bond_amount, division | assignee_name, assignee_address |

#### Other Documents
- Waiver of Arraignment
- Request for Jury Trial
- Entry of Appearance
- Motion to Continue
- Preservation Letters
- Disposition Letters

### CLI Commands

```bash
# Attorney Profile Management
python agent.py attorney setup --firm-id jcs_law    # Interactive setup
python agent.py attorney add --firm-id jcs_law \
  --name "John Doe" --bar "12345" --email "john@firm.com" \
  --phone "(314) 555-1234" --firm-name "Doe Law, P.C." \
  --address "123 Main St" --city "St. Louis" --state "Missouri" \
  --zip "63101" --primary
python agent.py attorney list --firm-id jcs_law     # List attorneys
python agent.py attorney show 1                      # Show attorney details
python agent.py attorney set-primary --firm-id jcs_law 1  # Set primary

# Document Generation - Interactive Chat
python agent.py engine chat --firm-id jcs_law
python agent.py engine chat --firm-id jcs_law --attorney-id 1

# Quick Document Generation
python agent.py generate-doc motion to dismiss for Jefferson County --firm-id jcs_law

# Template Management
python agent.py engine import 'Templates/' --firm-id jcs_law  # Import templates
python agent.py engine list --firm-id jcs_law                  # List templates
python agent.py engine search --firm-id jcs_law "motion"       # Search templates
python agent.py engine show 1                                  # Show template details
python agent.py engine analyze document.docx                   # Analyze for variables
```

### Chat Interface Usage

```
You: I need a motion to dismiss for Jefferson County

A: I found **Motion to Dismiss (General)** for Jefferson County.
   I'll need the following information:
   1. **Petitioner Name** - Full legal name of the petitioner
   2. **Case Number** - Court case number
   3. **County** - County where case is filed

You: RICHARD HORAK, 24JE-CC00191, Jefferson

A: Here's the draft **Motion to Dismiss (General)**:
   [Document preview]
   Does this look correct? Say **'yes'** to export, or tell me what to change.

You: yes

A: Document exported to: data/generated/Motion_to_Dismiss_24JE-CC00191.docx
```

### Special Responses
- **"draft it"** - Generate document with placeholders for missing values
- **"none"** / **"n/a"** - Skip current variable (not applicable)
- **"yes"** - Approve and export document
- **"change X to Y"** - Modify a value in the draft

### Attorney Profile System

Attorney profiles store signature block info for automatic population:

```python
# Profile includes:
- attorney_name, bar_number, email, phone, fax
- firm_name, firm_address, firm_city, firm_state, firm_zip
- is_primary (default attorney for firm)
```

**Auto-fill uses:**
- **Signature blocks** - All documents get attorney signature block filled automatically
- **Bond Assignment** - Assignee name/address filled from firm_name, firm_address
- **Letters** - Firm letterhead info filled automatically

When generating documents, the signature block is automatically filled from the attorney's profile.

### Template Folder Structure

Recommended structure for law firm templates:

```
Templates/
├── Criminal/
│   ├── Motions/
│   ├── Pleadings/
│   ├── Letters/
│   └── Discovery/
├── Traffic/
├── DWI/
├── DOR/
├── Civil/
├── Family/
├── Personal_Injury/
├── _Common/
└── _Jurisdiction_Specific/
```

See `docs/TEMPLATE_FOLDER_STRUCTURE.md` for complete structure.

### Variable Syntax

Templates use `{{variable_name}}` syntax:

```
IN THE CIRCUIT COURT OF {{county}} COUNTY, MISSOURI

{{petitioner_name}},                   )
                                       )
            Petitioner,                )    Case No.: {{case_number}}
                                       )
v.                                     )
                                       )
{{respondent_name}},                   )
                                       )
            Respondent.                )
```

### Party Terminology

Different case types use different party terms:

| Case Type | Filing Party | Opposing Party |
|-----------|--------------|----------------|
| DOR | Petitioner | Respondent (Director of Revenue) |
| Criminal | Defendant | State of Missouri |
| Civil | Plaintiff/Defendant | Defendant/Plaintiff |
| Family | Petitioner | Respondent |

### API Cost Estimates

| Metric | Value |
|--------|-------|
| Cost per document | ~$0.054 (5.4 cents) |
| 100 docs/week | $23/month |
| 100 docs/week | $281/year |
| With optimization | ~$0.027/doc |

See `docs/API_COST_ANALYSIS.md` for detailed projections.

### Database Tables (PostgreSQL)

#### Document Engine Tables
- `firms` - Registered law firms
- `templates` - Imported document templates (with full-text search via `tsvector`)
- `generated_documents` - Document generation history

#### Attorney Tables
- `attorneys` - Attorney profiles with signature block info

### Environment Variables

```bash
DATABASE_URL=postgresql://user:pass@host:5432/mycase  # Required - PostgreSQL connection
FIRM_ID=jcs_law               # Human-friendly firm identifier (used by sync, dashboard)
ANTHROPIC_API_KEY=sk-ant-...  # Required for AI document generation
MYCASE_CLIENT_ID=...          # MyCase OAuth
MYCASE_CLIENT_SECRET=...      # MyCase OAuth
DASHBOARD_ADMIN_USER=admin    # Dashboard admin username
DASHBOARD_ADMIN_PASSWORD_HASH=...  # Werkzeug scrypt hash of admin password
SLACK_WEBHOOK_URL=...         # Slack notifications
SENDGRID_API_KEY=...          # Email notifications
TWILIO_ACCOUNT_SID=...        # SMS notifications
TWILIO_AUTH_TOKEN=...         # SMS notifications
TWILIO_FROM_NUMBER=...        # SMS notifications
```

All env vars stored in `.env` file in the project root.

### Recent Document System Fixes
1. Fixed FTS5 syntax errors on special characters (commas, periods, parentheses)
2. Fixed Motion to Dismiss General - no longer requires grounds
3. Added DOR-specific motion type with Petitioner/Respondent terminology
4. Added handling for "none" / "n/a" responses to skip variables
5. Fixed document_type_key passthrough to use DOCUMENT_TYPES registry
6. Added party_terminology field to distinguish case types
7. **Fixed natural language search** - FTS now removes stop words and uses OR logic
   - Before: "I need a bond assignment" → 0 results (FTS required ALL words)
   - After: "I need a bond assignment" → finds "Bond Assignment" templates
   - Stop words removed: i, me, my, need, want, looking, for, please, the, a, an, etc.
8. **Fixed document generation to use actual templates** - System now:
   - Extracts text from stored .docx template files
   - Fills in variables using pattern matching ({{var}}, [var], and known placeholders)
   - Preserves original template format (e.g., "ASSIGNMENT OF CASH BOND" title, first-person language)
   - Only falls back to AI generation if no template content is available
9. **Added Bond Assignment document type** - System now:
   - Recognizes "bond assignment" and "cash bond" as bond_assignment type
   - Only asks for case-specific variables: defendant_name, case_number, county, bond_amount, division
   - Assignee name/address automatically filled from attorney profile (firm_name, firm_address)
   - Template detection maps template names to DOCUMENT_TYPES keys for proper variable handling
10. **Fixed Word document formatting preservation** - System now:
    - Does in-place variable substitution directly in the .docx file
    - Preserves all original formatting: alignment, tabs, underscores, tables, fonts
    - Uses structural regex patterns to find values (e.g., case number after "Case No.:")
    - Exports the filled .docx directly instead of regenerating from text
    - Signature lines, Name:/Address: alignment, and notary sections preserved
11. **Fixed `replace_in_paragraph` two-pass strategy** - System now:
    - Pass 1: Run-level replacement (preserves tabs & formatting across runs)
    - Pass 2: Cross-run placeholder handling with safe prefix preservation
    - County uppercase detection uses full paragraph context, not just the run text
12. **Added Filing Fee Memo document type** - System now:
    - Consolidated 4 template variants (ATM, DCC, Memo.docx, Memo.doc) into 1 unified template
    - Recognizes "filing fee" in template names → `filing_fee_memo` type
    - 8 variables auto-filled from attorney profile, 5 required + 5 optional from user
    - Template stored at `data/templates/Filing_Fee_Memo_Unified.docx`
    - Import script: `import_filing_fee_memo.py` (uses upsert for idempotent re-runs)
13. **Added Bond Assignment properly-templated version** - System now:
    - Template stored at `data/templates/Bond_Assignment_Templated.docx` with correct `{{placeholder}}` positions
    - Import script: `reimport_bond_template.py`
    - Preserves title "ASSIGNMENT OF CASH BOND", signature labels, all formatting
14. **Batch template consolidation (10 templates replacing ~989 variants)** - System now:
    - Batch 1: Entry of Appearance (State/Muni), Motion for Continuance, Request for Discovery, Potential Prosecution Letter
    - Batch 2: Preservation/Supplemental Letter, Preservation Letter, Motion to Recall Warrant, Proposed Stay Order, Disposition Letter to Client
    - Master import script: `import_consolidated_templates.py` with `deactivate_patterns` per template
    - All consolidated templates stored in `data/templates/` with `{{placeholder}}` syntax
15. **Fixed uppercase name placeholders in templates** - Changed `{{DEFENDANT_NAME}}` → `{{defendant_name}}`, `{{PETITIONER_NAME}}` → `{{petitioner_name}}`, `{{FIRM_NAME}}` → `{{firm_name}}` across 6 templates so names preserve user input casing. `{{COUNTY}}` remains uppercase (correct for court captions).
16. **Wired consolidated templates into document generation UI** - System now:
    - Updated `DOCUMENT_TYPES` registry with entries for all 13 consolidated templates
    - Dashboard Quick Generate panel with 10 buttons + More Documents panel with 4 buttons
    - Attorney profile auto-fill maps: `attorney_bar`, `attorney_email`, `firm_phone`, `firm_fax`, `attorney_full_name`, `firm_address_line1`
    - Fallback `document_type_key` detection from user's original request text (not just template name)
    - Import script deactivates old per-county/per-attorney variants on import
17. **Batch 3 automated consolidation (24 templates replacing ~291 variants)** - System now:
    - Built `batch_consolidate.py` automation tool for XML extraction, placeholder substitution, and repacking
    - Templates: Motion for COJ, Notice of Hearing, PFR, After Supp. Disclosure Ltr, Waiver of Arraignment, Notice to Take Deposition, Motion for Bond Reduction, Motion to Certify, 3x Ltr to DOR, DOR Motion to Dismiss, NOH for MTW, Motion to Shorten Time, Motion to Appear via WebEx, Motion to Place on Docket, Notice of Change of Address, Request for Supplemental Discovery, Motion to Amend Bond Conditions, Ltr to Client with Discovery, Motion to Compel, Motion to Terminate Probation, Request for Jury Trial, DL Reinstatement Letter
    - All 24 templates have DOCUMENT_TYPES entries with `uses_attorney_profile_for` and `_identify_template()` detection
    - Added synonyms: coj, pfr, webex, dl reinstatement
18. **Reorganized dashboard Quick Generate into 7 collapsible categories** - Pleadings & Appearances, Motions, Discovery, Letters, Notices & Orders, Bond & Fees, Recent Documents. All panels except first start collapsed.
19. **Batch 4 consolidation (13 templates replacing ~221 variants)** - Request for Rec Letter to PA (130 variants, 84% corrupted), Entry (Generic), Plea of Guilty, Motion to Dismiss (County), Request for Stay Order, Waiver of Preliminary Hearing, Request for Transcripts, Motion to Withdraw Guilty Plea, PH Waiver, Answer for Request to Produce, Available Court Dates for Trial, Requirements for Rec Letter to Client, Motion to Withdraw. All have DOCUMENT_TYPES entries, `_identify_template()` detection, and dashboard buttons.
20. **Investigated .doc-format templates** - 33 templates across 3 groups (Admin Continuance, Admin Hearing, Petition for TDN) use legacy OLE/Office 97-2003 format. Require LibreOffice conversion before consolidation. Motion to Withdraw partially consolidated using 4 available DOCX-format variants.
21. **Batch 5 consolidation (3 templates replacing ~35 variants)** - Converted legacy .doc (OLE) templates to .docx via LibreOffice, then consolidated: Admin Continuance Request (10 variants), Admin Hearing Request (20 variants), Petition for Trial De Novo (5 variants). **Template consolidation is now complete — all variant groups processed.**
22. **Batch 6 final cleanup (2 templates + deactivation of client-filled duplicates)** - NOH Bond Reduction (3 county variants), OOP Entry (2 variants). Added extra cleanup deactivation for client-filled 90 Day Letters, Client Status Updates, and duplicate Motion to Set Aside templates. **56 consolidated templates total.**
23. **Fixed XML repack document corruption** - Using stale `ZipInfo` objects when repacking .docx after hyperlink placeholder substitution caused CRC/file size mismatches. Fixed by passing filename strings to `writestr()` instead of `ZipInfo` objects in both `document_chat.py` and `tests/test_template_generation.py`.
24. **Fixed doubled email in 16 templates** - `paragraph.text` includes `<w:hyperlink>` text but `paragraph.runs` does not. Pass 2 (cross-run replacement) was seeing `{{attorney_email}}` from the hyperlink in `paragraph.text`, writing it into regular runs, then XML pass also replaced the hyperlink copy. Fixed by using `''.join(r.text for r in para.runs)` instead of `paragraph.text` for remaining-placeholder detection.
25. **Fixed Disposition Letter payment text** - `{{payment_instructions}}{{payment_deadline}}` were adjacent with no separator. Changed to `{{payment_instructions}} by {{payment_deadline}}` so output reads "...above by March 15, 2026."
26. **Fixed `attorney_names` typo** - Entry_of_Appearance_Muni.docx and Entry_of_Appearance_State.docx both had `{{attorney_names}}` (plural) instead of `{{attorney_name}}`. Fixed in template XML and database.
27. **Purged 1,307 inactive templates** - Deleted old per-county/per-attorney variants from database (42 MB freed). 400 active templates remain. All 55 test templates pass.
28. **Multi-state architecture specification** - Created `MULTI_STATE_ARCHITECTURE.md` and `.docx` covering jurisdiction layer, PDF form engine, court registry, attorney profile expansion, and 16-week implementation roadmap for 6 Phase 1 states.
29. **Added dunning click-to-draft email** - Dunning preview page now has Client column and Action column. Clicking "Draft" opens a modal with stage-appropriate email content (friendly reminder → collections referral), then "Open in Outlook" uses `mailto:` link to open Outlook desktop with pre-filled To/Subject/Body. API endpoint `POST /api/dunning/draft-email` generates email content per stage. Firm phone: (314) 561-9690.
30. **Fixed dunning client email lookup** - `cached_invoices.contact_id` is NULL for all records. Client emails (2,247 of 2,475 clients have emails) are in `cached_clients`. The join path goes through case `data_json`: invoice → `cached_cases` (via `case_id`) → `data_json::jsonb -> 'billing_contact' ->> 'id'` → `cached_clients` (email). Both `get_dunning_preview()` and `get_open_invoices_list()` in `dashboard/models/ar.py` use this JSONB extraction join.
31. **Added aging invoice CSV upload** - New `aging_invoice_uploads` table and `/aging-upload` dashboard page with drag-and-drop CSV upload. Melissa can upload the aging invoice report (up to daily). Each upload gets a unique `upload_batch_id`; old batches preserved for audit trail. Flexible CSV parsing handles various header names and date/currency formats. Upload history shows last 10 batches with row counts and timestamps.
32. **Integrated aging data into dunning system** - Dunning queue now shows two amount columns: "Amount Due Now" (from latest aging batch via LEFT JOIN) and "Total Remaining Balance" (from `cached_invoices.balance_due`). Draft emails show both amounts when they differ, or a single "Amount Due" when same. The dunning model uses a CTE (`latest_aging_batch`) to find the most recent upload per firm. 212 of 296 dunning queue invoices matched aging data (71% coverage); remaining fall back to cached balance.
33. **Fixed AI chat table rendering** - `get_connection()` sets `RealDictCursor` on the connection, so iterating rows yielded column names instead of values. Fixed `execute_chat_query()` to bypass the connection pool with a direct `psycopg2.connect()` and plain tuple cursor. Also fixed `ROUND()` errors by adding `::numeric` cast guidance to the AI system prompt, and added `Decimal`-to-float conversion in `format_query_results()`.
34. **Fixed AI chat year/float formatting** - `EXTRACT(YEAR FROM ...)` returns `double precision`, which was displaying as `2,026.0`. Added detection for year-like values (1900-2100 range) and whole-number floats to format as integers. Also fixed stale `__pycache__` issue on production causing service to crash-loop on port 3000 — must clear bytecode cache (`find ... -name __pycache__ -exec rm -rf {}`) before restart.
35. **Fixed SQLite syntax in AI chat MYCASE_SCHEMA** - System prompt contained SQLite functions (`strftime()`, `julianday()`) that would cause PostgreSQL query failures. Replaced with `EXTRACT(YEAR FROM ...)` and `CURRENT_DATE - date::date`. Also added notes about lowercase status values (`'open'`/`'closed'`) and boolean `completed` column to prevent AI from generating incorrect SQL.
36. **Fixed negative currency formatting** - `format_query_results()` displayed negative amounts as `$-500.00` instead of `-$500.00`. Added sign-aware formatting with `abs()`.
37. **Added pre-launch test harness** - Comprehensive test suites for the two most critical subsystems:
    - `test_prelaunch_docgen.py`: 249 tests — catalog validation (5), template fill across all 56 templates (220), template identification (20), edge cases (2), DB existence checks (2). All 56 templates produce valid .docx with zero unfilled placeholders.
    - `test_prelaunch_chat.py`: 71+ tests — `format_query_results()` unit tests (17), MYCASE_SCHEMA validation (8), SQL execution patterns (7), E2E Claude API→SQL→format pipeline (22 questions × 3 test types).
    - `run_prelaunch.py`: Runner script that executes both suites and generates `tests/reports/PRELAUNCH_REPORT.md`.
    - **Known identification bugs found**: "motion to dismiss" resolves to DOR variant instead of general; "entry of appearance for municipal court" resolves to state instead of muni. Both are `_identify_template()` DB search order issues.

### Template Consolidation

The firm's original template folder had ~4,800 files — mostly per-county or per-attorney duplicates of the same document with only the county name, attorney signature block, or court address changed. These have been consolidated into universal templates with `{{placeholder}}` variables. Attorney profile fields (firm name, address, bar number, etc.) are auto-filled from the database.

#### Consolidated Templates (56 total)

**Batch 1-2 (13 templates, ~989 variants replaced):**

| # | Template | File | Replaces | Key Placeholders |
|---|----------|------|----------|-----------------|
| 1 | Entry of Appearance (State) | `Entry_of_Appearance_State.docx` | ~30 county variants | county, plaintiff_name, defendant_name, case_number |
| 2 | Entry of Appearance (Muni) | `Entry_of_Appearance_Muni.docx` | ~76 muni variants | city, defendant_name, case_number, prosecutor_* |
| 3 | Motion for Continuance | `Motion_for_Continuance.docx` | ~34 variants | county, defendant_name, case_number, hearing_date, continuance_reason |
| 4 | Request for Discovery | `Request_for_Discovery.docx` | ~36 variants | county, defendant_name, case_number |
| 5 | Potential Prosecution Letter | `Potential_Prosecution_Letter.docx` | ~21 variants | client_name, prosecutor_*, court_name |
| 6 | Preservation/Supplemental Discovery Letter | `Preservation_Supplemental_Discovery_Letter.docx` | ~164 variants | agency_*, defendant_*, arrest_date, ticket_number |
| 7 | Preservation Letter | `Preservation_Letter.docx` | ~105 variants | agency_*, defendant_*, arrest_date, ticket_number |
| 8 | Motion to Recall Warrant | `Motion_to_Recall_Warrant.docx` | ~70 variants | county, defendant_name, case_number |
| 9 | Proposed Stay Order | `Proposed_Stay_Order.docx` | ~54 variants | county, petitioner_name, dln, dob, arrest_date, judge_* |
| 10 | Disposition Letter to Client | `Disposition_Letter_to_Client.docx` | ~399 variants | client_*, disposition_paragraph, court_*, payment_* |
| 11 | Filing Fee Memo | `Filing_Fee_Memo_Unified.docx` | 4 variants | petitioner_name, case_number, county, filing_fee |
| 12 | Bond Assignment | `Bond_Assignment_Templated.docx` | 3 variants | defendant_name, case_number, county, bond_amount |
| 13 | Motion to Dismiss (General) | (AI-generated) | N/A | defendant_name, case_number, county |

**Batch 3 (24 templates, ~291 variants replaced — automated consolidation):**

| # | Template | File | Key Placeholders |
|---|----------|------|-----------------|
| 14 | Motion for Change of Judge | `Motion_for_COJ.docx` | county, defendant_name, case_number |
| 15 | Notice of Hearing (General) | `Notice_of_Hearing.docx` | county, defendant_name, case_number, hearing_date, hearing_time, division, motion_type |
| 16 | Petition for Review (PFR) | `Petition_for_Review.docx` | county, petitioner_name, case_number, dob |
| 17 | After Supplemental Disclosure Letter | `After_Supplemental_Disclosure_Ltr.docx` | prosecutor_*, defendant_name, case_number, disclosure_date |
| 18 | Waiver of Arraignment | `Waiver_of_Arraignment.docx` | county, defendant_name, case_number |
| 19 | Notice to Take Deposition | `Notice_to_Take_Deposition.docx` | county, defendant_name, case_number, deponent_*, deposition_* |
| 20 | Motion for Bond Reduction | `Motion_for_Bond_Reduction.docx` | county, defendant_name, case_number, division, bond_amount |
| 21 | Motion to Certify for Jury Trial | `Motion_to_Certify.docx` | city, defendant_name, case_number |
| 22 | Letter to DOR with PFR | `Ltr_to_DOR_with_PFR.docx` | petitioner_name |
| 23 | Letter to DOR with Stay Order | `Ltr_to_DOR_with_Stay_Order.docx` | petitioner_name, case_number |
| 24 | DOR Motion to Dismiss | `DOR_Motion_to_Dismiss.docx` | county, petitioner_name, case_number |
| 25 | Notice of Hearing - Motion to Withdraw | `Notice_of_Hearing_MTW.docx` | county, defendant_name, case_number, division, hearing_date, hearing_time |
| 26 | Motion to Shorten Time | `Motion_to_Shorten_Time.docx` | county, defendant_name, case_number |
| 27 | Letter to DOR with Judgment | `Ltr_to_DOR_with_Judgment.docx` | petitioner_name, dln |
| 28 | Motion to Appear via WebEx | `Motion_to_Appear_via_WebEx.docx` | county, petitioner_name, respondent_name, case_number |
| 29 | Motion to Place on Docket | `Motion_to_Place_on_Docket.docx` | county, defendant_name, case_number |
| 30 | Notice of Change of Address | `Notice_of_Change_of_Address.docx` | county, defendant_name, case_number |
| 31 | Request for Supplemental Discovery | `Request_for_Supplemental_Discovery.docx` | county, defendant_name, case_number |
| 32 | Motion to Amend Bond Conditions | `Motion_to_Amend_Bond_Conditions.docx` | county, defendant_name, case_number, division, bond_amount |
| 33 | Letter to Client with Discovery | `Ltr_to_Client_with_Discovery.docx` | client_name, client_salutation, client_address, client_city_state_zip, case_number |
| 34 | Motion to Compel Discovery | `Motion_to_Compel.docx` | county, defendant_name, case_number |
| 35 | Motion to Terminate Probation | `Motion_to_Terminate_Probation.docx` | county, defendant_name, case_number |
| 36 | Request for Jury Trial | `Request_for_Jury_Trial.docx` | county, defendant_name, case_number |
| 37 | DL Reinstatement Letter | `DL_Reinstatement_Ltr.docx` | client_name, client_first_name, client_email, client_address, client_city_state_zip |

All consolidated templates stored in `data/templates/`. Each has a matching `DOCUMENT_TYPES` entry in `document_chat.py` that defines `required_vars` (user provides), `optional_vars`, and `uses_attorney_profile_for` (auto-filled from DB). Dashboard Quick Generate panel organized into 7 collapsible categories (Pleadings, Motions, Discovery, Letters, Notices, Bond/Fees, Recent).

**Batch 4 (12 templates — Rec Letter to PA + 11 remaining groups):**

| # | Template | File | Replaces | Key Placeholders |
|---|----------|------|----------|-----------------|
| 38 | Request for Rec Letter to PA | `Request_for_Recommendation_Letter_to_PA.docx` | ~130 variants | service_date, defendant_name, case_number, prosecutor_*, court_* |
| 39 | Entry (Generic) | `Entry_Generic.docx` | ~13 variants | county, defendant_name, case_number |
| 40 | Plea of Guilty | `Plea_of_Guilty.docx` | ~8 variants | county, defendant_name, case_number |
| 41 | Motion to Dismiss (County) | `Motion_to_Dismiss_County.docx` | ~10 variants | county, defendant_name, case_number |
| 42 | Request for Stay Order | `Request_for_Stay_Order.docx` | ~6 variants | county, petitioner_name, case_number |
| 43 | Waiver of Preliminary Hearing | `Waiver_of_Preliminary_Hearing.docx` | ~5 variants | county, defendant_name, case_number |
| 44 | Request for Transcripts | `Request_for_Transcripts.docx` | ~5 variants | county, defendant_name, case_number |
| 45 | Motion to Withdraw Guilty Plea | `Motion_to_Withdraw_Guilty_Plea.docx` | ~5 variants | county, defendant_name, case_number |
| 46 | PH Waiver | `PH_Waiver.docx` | ~4 variants | county, defendant_name, case_number |
| 47 | Answer for Request to Produce | `Answer_for_Request_to_Produce.docx` | ~4 variants | county, defendant_name, case_number |
| 48 | Available Court Dates for Trial | `Available_Court_Dates_for_Trial.docx` | ~3 variants | county, defendant_name, case_number, available_dates |
| 49 | Requirements for Rec Letter to Client | `Requirements_for_Rec_Letter_to_Client.docx` | ~3 variants | client_name, case_number |
| 50 | Motion to Withdraw | `Motion_to_Withdraw.docx` | ~25 variants | county, defendant_name, case_number, service_date |
| 51 | Closing Letter | `Closing_Letter.docx` | ~28 variants | client_name, client_first_name, client_address, client_city_state_zip, case_reference, county, disposition_paragraph, closing_paragraph |

**Batch 5 (3 templates — former .doc/OLE format, converted via LibreOffice):**

| # | Template | File | Replaces | Key Placeholders |
|---|----------|------|----------|-----------------|
| 52 | Admin Continuance Request | `Admin_Continuance_Request.docx` | ~10 variants | petitioner_name, docket_number, case_number, dln, hearing_date |
| 53 | Admin Hearing Request | `Admin_Hearing_Request.docx` | ~20 variants | petitioner_name, dob, drivers_license_number, arrest_county, arrest_date, case_number |
| 54 | Petition for Trial De Novo | `Petition_for_TDN.docx` | ~5 variants | county, case_number, petitioner_name, arrest_date, officer_name, police_department, hearing_date |

**Batch 6 (2 templates — final cleanup):**

| # | Template | File | Replaces | Key Placeholders |
|---|----------|------|----------|-----------------|
| 55 | NOH Bond Reduction | `NOH_Bond_Reduction.docx` | ~3 variants | county, case_number, defendant_name, service_date, division, hearing_time |
| 56 | OOP Entry | `OOP_Entry.docx` | ~2 variants | county, case_number, defendant_name |

#### Remaining Variant Groups (not yet consolidated)

No remaining groups — **all template consolidation is complete**.

#### Import Scripts

| Script | Purpose |
|--------|---------|
| `import_consolidated_templates.py` | Master import — all 56 consolidated templates + deactivation of old variants + cleanup of client-filled duplicates |
| `import_filing_fee_memo.py` | Filing Fee Memo (standalone, predates master script) |
| `reimport_bond_template.py` | Bond Assignment (standalone, predates master script) |
| `batch_consolidate.py` | Automated consolidation tool (extracts from DB, unpacks XML, applies replacements, repacks) |

All use upsert logic (`ON CONFLICT DO UPDATE`) — safe to re-run.

**Deploy on production:**
```bash
cd /opt/jcs-mycase
git pull
export $(grep -v '^#' .env | xargs)
.venv/bin/python import_consolidated_templates.py
```

**Note:** Production uses `RealDictCursor` (returns dicts, not tuples). Import scripts handle both formats with `row['id'] if isinstance(row, dict) else row[0]`.

#### Placeholder Naming Convention

- `{{COUNTY}}` — uppercase = displayed in ALL CAPS (court caption: "JEFFERSON COUNTY")
- `{{defendant_name}}` — lowercase = preserves user's input casing
- Profile variables (firm_name, attorney_bar, etc.) are never asked — auto-filled from attorney profile

#### Consolidation Workflow

When consolidating a new template group:

1. Extract a representative variant from DB or source folder
2. Unpack the .docx XML with `unpack.py`
3. Replace case-specific values with `{{placeholders}}` in `document.xml`
4. Repack with `pack.py` → save to `data/templates/`
5. Add entry to `TEMPLATES` list in `import_consolidated_templates.py` with `deactivate_patterns`
6. Add `DOCUMENT_TYPES` entry in `document_chat.py` with required/optional vars and `uses_attorney_profile_for`
7. Add template name detection in `_identify_template()` if/elif chain
8. Add button to `dashboard/templates/documents.html` Quick Generate panel
9. Commit, push, `git pull` on server, run `import_consolidated_templates.py`

### Deployment Workflow

Both local and production (`/opt/jcs-mycase`) are git repos on the same `main` branch:

```bash
# Local: commit and push
git add <files> && git commit -m "message" && git push origin main

# Production: pull and restart
cd /opt/jcs-mycase
git pull
sudo systemctl restart jcs-dashboard
# If importing templates:
export $(grep -v '^#' .env | xargs)
.venv/bin/python import_consolidated_templates.py
```

### Template Search Behavior
The template search uses PostgreSQL full-text search (`tsvector`/`tsquery`) with these enhancements:
- **Synonym expansion**: Alternate legal terms mapped to database names
- **Stop word removal**: Common words like "I", "need", "a", "the", "please" are filtered out
- **OR logic**: Remaining words use OR matching (find ANY of the words)
- **Fallback**: If full-text search fails, falls back to ILIKE search on name field

**Synonym mappings** (alternate name → database name):
| User Says | Searches For |
|-----------|--------------|
| cash bond, assignment of cash bond | bond assignment |
| mtd | motion to dismiss |
| mtc | motion to continue |
| eoa | entry of appearance |
| noh | notice of hearing |
| rog, rogs | interrogatories |
| rfp | request for production |
| rfa | request for admission |
| nol pros, nolle pros | nolle prosequi |
| dor | director of revenue |
| coj | change of judge |
| pfr | petition for review |
| webex | appear via webex |
| dl reinstatement, drivers license reinstatement | reinstatement letter |

**Example transformations**:
- "I need a bond assignment" → "bond OR assignment"
- "assignment of cash bond" → "bond OR assignment" (synonym expanded)
- "mtd for Jefferson County" → "motion OR dismiss OR jefferson OR county"

---

## Multi-State Document Engine Expansion

### Overview
Architecture specification for expanding the document generation engine from Missouri-only to multi-state operation. Full spec in `MULTI_STATE_ARCHITECTURE.md` (and `.docx`).

### Phase 1 States

| State | Court System | Custom .docx | PDF Forms | Court Entries | Priority |
|-------|-------------|-------------|-----------|---------------|----------|
| Iowa | District Court (unified) | ~15 | ~4 | 8 | First (proof-of-concept) |
| California | 58 Superior Courts | ~30 | ~7 | 58 | Largest market |
| Illinois | Circuit Court (unified) | ~20 | TBD | 24 | Adjacent to MO |
| Minnesota | District Court (unified) | ~20 | ~5 | 10 | Word-format forms |
| Kentucky | Court of Justice (unified) | ~20 | TBD | 120 | Unified since 1975 |
| Oklahoma | District Court + CCA | ~25 | ~12 | 77 | Rule 13 mandatory forms |

### New Database Tables (Multi-State)

| Table | Purpose |
|-------|---------|
| `jurisdictions` | State-level config: caption templates, party terminology, pleading format (JSONB), admin agency |
| `courts` | Individual courts with addresses, divisions, local rules, local form flags |
| `document_type_taxonomy` | Universal document types spanning jurisdictions (e.g., "motion_for_continuance") |
| `jurisdiction_templates` | Maps document type + jurisdiction → state-specific template (.docx or PDF) |
| `court_forms` | Official fillable PDF forms from state judiciaries (stored as BYTEA) |
| `court_form_field_mappings` | Maps PDF form field names → universal placeholder keys with optional transforms |
| `attorney_bar_admissions` | Per-attorney, per-state bar numbers and status |
| `firm_jurisdictions` | Which states a firm is licensed in; controls template provisioning |
| `firm_office_locations` | Per-jurisdiction office addresses for signature block auto-fill |

### Key Architecture Decisions

1. **Missouri engine unchanged** — New `multi_state_engine.py` entry point runs alongside existing `document_chat.py`
2. **Dual output formats** — .docx for free-form filings, filled PDF for mandatory court forms (via `pypdf`)
3. **Jurisdiction resolution** — Court-level resolution: explicit court → county+state → state only → inferred from case data
4. **California formatting** — 28-line numbered pleading paper stored as JSONB in `jurisdictions.pleading_format`
5. **Attorney auto-fill per state** — Bar number and office address resolve per `jurisdiction_id`
6. **Additive migration** — New tables alongside existing; `templates` gets `jurisdiction_id DEFAULT 'MO'` column; rollback = drop new tables

### Implementation Roadmap (16 Weeks)

| WP | Description | Weeks | Dependencies |
|----|-------------|-------|-------------|
| 1 | Data Model & Foundation | 1–3 | None |
| 2 | PDF Form Engine | 2–4 | WP1 |
| 3 | Iowa (first state) | 3–6 | WP1, WP2 |
| 4 | California | 5–10 | WP1–3 |
| 5 | Illinois | 7–10 | WP1, WP2 |
| 6 | Minnesota, Kentucky, Oklahoma | 8–12 | WP1, WP2 |
| 7 | Dashboard & Onboarding | 10–14 | WP3–6 |
| 8 | Testing & QA | 12–16 | All |

### Reference Documents
- `MULTI_STATE_ARCHITECTURE.md` — Full architecture spec (10 sections, SQL DDL, pipeline diagrams)
- `MULTI_STATE_ARCHITECTURE.docx` — Same content, formatted Word document
- `Multi_State_Expansion_Analysis.xlsx` — State comparison spreadsheet (3 tabs)

---

## Architecture Migration: SQLite → PostgreSQL

### Status: IN PROGRESS

This project is migrating from a mixed SQLite/PostgreSQL codebase to **PostgreSQL only** with full multi-tenant support. The goals are:

1. **Remove all SQLite** — no `import sqlite3` anywhere, no `.db` files, no file-based databases
2. **Single database layer** — one `db/` package replaces `cache.py`, `cache_mt.py`, `database.py`, `pg_database.py`
3. **Multi-tenant everywhere** — all tables use `firm_id`, all queries scoped by tenant
4. **Break up monoliths** — `agent.py` (3,665 lines) → thin entry point + `commands/` package; `dashboard/models.py` (2,543 lines) → `dashboard/models/` package
5. **Add test coverage** — pytest suite covering business logic, especially financial calculations, state machines, and NOIW pipeline
6. **Clean up artifacts** — remove legacy `.db` files, duplicate modules, debug scripts

### Files to Remove After Migration
- `cache.py` — replaced by `db/cache.py` (PostgreSQL)
- `database.py` — replaced by `db/tracking.py` (PostgreSQL)
- `pg_database.py` — absorbed into `db/` package
- `cache_mt.py` — absorbed into `db/cache.py`
- `migrate_to_postgres.py` — one-time migration script, archive after use
- `data/*.db` — all SQLite database files
- `dashboard/mycase_cache.db` — symlinked SQLite copy
- Root-level empty `.db` files: `mycase.db`, `mycase_cache.db`, `mycase_data.db`
- Legacy profiles: `data/attorney_profiles_new.db`, `data/attorney_profiles_v2.db`

### Migration Order
1. **`db/` package** — Create unified PostgreSQL database layer with connection pool
2. **`commands/` package** — Split `agent.py` into command groups
3. **Business logic modules** — Update each to use `db/` instead of `sqlite3`
4. **Dashboard** — Split `models.py` and `routes.py`, connect to PostgreSQL
5. **Document engine** — Migrate FTS5 → PostgreSQL `tsvector`/`tsquery`
6. **Tests** — Add pytest coverage for each migrated module
7. **Cleanup** — Remove SQLite files, legacy modules, debug scripts

### Development Standards

#### Database Access
- All database access goes through `db/connection.py` which manages a `psycopg2` connection pool
- Use `get_connection()` context manager — never create connections directly
- All queries MUST include `firm_id` in WHERE clauses (multi-tenant isolation)
- Use `%s` parameter placeholders (PostgreSQL), never f-strings or string formatting
- Bulk operations use `psycopg2.extras.execute_values()` for performance

#### CLI Structure
- `agent.py` is a thin entry point that registers Click command groups from `commands/`
- Each file in `commands/` defines one `@click.group()` with related subcommands
- Command functions should be thin — call into business logic modules, format output with Rich

#### Testing
- Tests in `tests/` using pytest
- `conftest.py` provides test database fixtures (isolated PostgreSQL schema or test database)
- Every module with financial calculations, state transitions, or SLA logic MUST have tests
- Run: `uv run pytest tests/ -v`
- **Pre-launch test harness** (requires `pytest` in venv — `pip install pytest`):
  - `tests/test_prelaunch_docgen.py` — 249 tests: catalog validation, template fill (all 56), identification, edge cases
  - `tests/test_prelaunch_chat.py` — 71+ tests: `format_query_results()` unit tests, schema validation, SQL execution, E2E chat
  - `tests/run_prelaunch.py` — Runs both suites, generates `tests/reports/PRELAUNCH_REPORT.md`
  - Production: `.venv/bin/python -m pytest tests/test_prelaunch_docgen.py tests/test_prelaunch_chat.py -v`
  - E2E chat tests require `ANTHROPIC_API_KEY` (skipped if not set)
- **Note**: `.gitignore` has `test_*.py` — use `git add -f` for test files in `tests/`

#### AI Chat Schema (MYCASE_SCHEMA)
- Located in `dashboard/routes/api.py` — instructs Claude to generate PostgreSQL SQL
- **Case status values are lowercase**: `'open'`, `'closed'` (NOT `'Open'` or `'Closed'`)
- **Task `completed` is boolean**: use `completed = false` (NOT `completed = 0`)
- **DPD calculation**: `CURRENT_DATE - due_date::date` (NOT `julianday()`)
- **Year filtering**: `EXTRACT(YEAR FROM date_column) = 2025` (NOT `strftime()`)
- **ROUND() requires cast**: `ROUND(expr::numeric, 2)` (PostgreSQL requirement)

#### Dashboard RBAC Pattern
- Every route handler must call `data = get_data(request)` — this creates a `DashboardData` with the session's `firm_id` and `attorney_name`
- Role checks: `if request.session.get("role") == "attorney": return RedirectResponse(...)` or raise 403
- Model classes inherit `attorney_name` from `DashboardData` and use `_attorney_case_filter(table_alias)` for SQL filtering
- `_attorney_case_filter()` returns `("", ())` when `attorney_name` is None (admin/collections) — no filter applied
- When adding new model methods that query case-related data, always JOIN to `cached_cases` and include `{af_sql}` in the WHERE clause
- Template context must include `role=request.session.get("role")` for nav rendering

#### Code Organization Rules
- No module should exceed ~500 lines — split into submodules if growing beyond that
- No `import sqlite3` anywhere — if you see it, it's a bug
- Dashboard routes grouped by domain in `dashboard/routes/`
- Dashboard data access grouped by domain in `dashboard/models/`
