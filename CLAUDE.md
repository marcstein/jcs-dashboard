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
- `firms`, `templates`, `generated_documents` — Document engine
- `attorneys` — Attorney profiles

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
│   └── test_dashboard.py
├── templates/             # Email/notification templates
├── reports/               # Generated SOP compliance reports
├── data/templates/        # Templated .docx files with {{placeholders}}
│   ├── Filing_Fee_Memo_Unified.docx
│   ├── Bond_Assignment_Templated.docx
│   └── Waiver_of_Arraignment_Generic.docx
├── import_filing_fee_memo.py   # Template import script (Filing Fee Memo)
├── reimport_bond_template.py   # Template import script (Bond Assignment)
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
Access at: http://127.0.0.1:3000 (login: admin/admin)

### Dashboard Routes
- `/` - Main dashboard with SOP widgets
- `/attorneys` - Attorney productivity with invoice aging buckets
- `/ar` - A/R and collections dashboard
- `/noiw` - NOIW pipeline with workflow status filtering
- `/phases` - Case phase distribution and stalled cases
- `/trends` - Historical KPI trends with sparklines
- `/promises` - Payment promise tracking and reliability
- `/payments` - Payment analytics: time-to-payment by attorney and case type
- `/dunning` - Dunning notices preview and approval
- `/staff/{name}` - Individual staff detail pages
- `/wonky` - Invoices requiring attention

### Dashboard Files
- `dashboard/app.py` - FastAPI application
- `dashboard/routes.py` - Route handlers
- `dashboard/models.py` - Data methods for dashboard queries
- `dashboard/templates/` - Jinja2 templates
- `dashboard/static/` - CSS styles

### Key Metrics Displayed
- **A/R Overview**: Total AR, 60-120 day, 180+ day (uncollectible)
- **Attorney Productivity**: Active cases, invoice aging by DPD buckets
- **Staff Widgets**: Active cases, tasks done (ratio format), overdue tasks
- **Firm Tasks Overview**: Open tasks, done this week, overdue count

## Change Log

### v2.0 — PostgreSQL Migration (In Progress)
- Removing all SQLite — unified PostgreSQL multi-tenant database layer
- Split `agent.py` (3,665 lines) into `commands/` package
- Split `dashboard/models.py` (2,543 lines) into `dashboard/models/` package
- Split `dashboard/routes.py` (1,154 lines) into `dashboard/routes/` package
- Added pytest test suite for business logic
- Migrated FTS5 full-text search to PostgreSQL `tsvector`/`tsquery`
- Removed legacy `.db` files and duplicate modules

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
ANTHROPIC_API_KEY=sk-ant-...  # Required for AI document generation
MYCASE_CLIENT_ID=...          # MyCase OAuth
MYCASE_CLIENT_SECRET=...      # MyCase OAuth
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

### Template Import Scripts

Standalone scripts to import/update specific templates in the database. These use upsert logic (`ON CONFLICT DO UPDATE`) so they are safe to re-run.

| Script | Template | Purpose |
|--------|----------|---------|
| `import_filing_fee_memo.py` | `data/templates/Filing_Fee_Memo_Unified.docx` | Deactivates old variants, imports unified template |
| `reimport_bond_template.py` | `data/templates/Bond_Assignment_Templated.docx` | Updates Bond Assignment with proper `{{placeholder}}` patterns |

**Usage (on production server):**
```bash
cd /opt/jcs-mycase
export $(grep -v '^#' .env | xargs)
.venv/bin/python import_filing_fee_memo.py
```

**Note:** Production uses `RealDictCursor` (returns dicts, not tuples). Import scripts handle both formats with `row['id'] if isinstance(row, dict) else row[0]`.

### Template Consolidation Strategy

When multiple template variants exist for the same document type (e.g., per-attorney or per-county variants), consolidate into a single template with `{{placeholder}}` variables:

1. Compare all variants to identify differences (county, attorney, party names, fees, etc.)
2. Choose the most complete variant as the base (e.g., the one with Certificate of Service)
3. Unpack the .docx XML, replace case-specific values with `{{placeholders}}`
4. Repack using the docx skill's `pack.py` script
5. Add a `DOCUMENT_TYPES` entry in `document_chat.py` with required/optional vars
6. Add template name detection in the `_select_template` method
7. Create an import script (follow `import_filing_fee_memo.py` pattern)
8. Commit, push, `git pull` on server, run import script

### Deployment Workflow

Both local and production (`/opt/jcs-mycase`) are git repos on the same `main` branch:

```bash
# Local: commit and push
git add <files> && git commit -m "message" && git push origin main

# Production: pull and run
cd /opt/jcs-mycase
git pull
export $(grep -v '^#' .env | xargs)
.venv/bin/python <import_script>.py    # If importing templates
# Restart dashboard if code changed:
# (dashboard auto-reloads on file change if running with --reload)
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

**Example transformations**:
- "I need a bond assignment" → "bond OR assignment"
- "assignment of cash bond" → "bond OR assignment" (synonym expanded)
- "mtd for Jefferson County" → "motion OR dismiss OR jefferson OR county"

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

#### Code Organization Rules
- No module should exceed ~500 lines — split into submodules if growing beyond that
- No `import sqlite3` anywhere — if you see it, it's a bug
- Dashboard routes grouped by domain in `dashboard/routes/`
- Dashboard data access grouped by domain in `dashboard/models/`
