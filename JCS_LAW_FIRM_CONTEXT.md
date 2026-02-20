# JCS Law Firm - LawMetrics.ai Dashboard & Analytics Context

**Last Updated:** February 20, 2026
**Purpose:** Comprehensive reference for continuing work in Cowork/Claude Desktop

---

## Table of Contents
1. [Project Overview](#1-project-overview)
2. [Server & Infrastructure](#2-server--infrastructure)
3. [Database Architecture](#3-database-architecture)
4. [Dashboard (models.py)](#4-dashboard-modelspy)
5. [Case Phases System](#5-case-phases-system)
6. [Document Generation System](#6-document-generation-system)
7. [Analytics Module Reference](#7-analytics-module-reference)
8. [Key Data & Current Metrics](#8-key-data--current-metrics)
9. [API Reference](#9-api-reference)
10. [Staff & Roles](#10-staff--roles)
11. [Known Issues & Remaining Work](#11-known-issues--remaining-work)
12. [Change Log - Feb 20 2026 Session](#12-change-log---feb-20-2026-session)

---

## 1. Project Overview

### Purpose
LawMetrics.ai - Legal analytics SaaS platform for JCS Law Firm, a criminal defense firm specializing in DUI/DWI cases in the St. Louis, Missouri metro area. Provides automated insights, notifications, case phase tracking, document generation, and business intelligence.

### Production URL
- **Dashboard:** https://jcs.lawmetrics.ai
- **Login:** session-based authentication

### Architecture (Current - Post Migration)
```
MyCase API (Cloud) → Celery Workers → PostgreSQL (DigitalOcean)
                                            ↓
                                   FastAPI Dashboard (models.py)
                                            ↓
                              Templates (Jinja2 HTML) → Browser
                                            
SQLite DBs (case_phases.db, attorney_profiles.db, document_engine.db)
    ↕ (local auxiliary data - phases, profiles, doc templates)
PostgreSQL (cached_cases, cached_invoices, etc. - main data)
```

### Server Directory Structure
```
/opt/jcs-mycase/
├── dashboard/
│   ├── models.py            # Data access layer (~2500+ lines)
│   ├── routes.py            # FastAPI route handlers
│   └── templates/           # Jinja2 HTML templates
│       ├── base.html
│       ├── phases.html      # Case phase tracking
│       ├── documents.html   # Document generation UI
│       ├── payments.html    # Payment analytics
│       └── ...
├── document_chat.py         # AI document generation chat engine
├── document_engine.py       # Template storage & variable engine
├── attorney_profiles.py     # Attorney profile management
├── data/
│   ├── case_phases.db       # SQLite - phase tracking
│   ├── attorney_profiles.db # SQLite - attorney signature data
│   ├── document_engine.db   # SQLite - doc templates (migrating to PG)
│   ├── mycase_cache.db      # SQLite - legacy cache (dashboard migrated to PG)
│   └── mycase_agent.db      # SQLite - agent/tracking
├── .env                     # DATABASE_URL and other config
└── .venv/                   # Python virtual environment
```

---

## 2. Server & Infrastructure

### Access
```bash
ssh jcs-server                    # SSH alias to DigitalOcean droplet
```

### Services
```bash
sudo systemctl restart mycase-dashboard   # Restart dashboard
sudo systemctl status mycase-dashboard    # Check status
sudo journalctl -u mycase-dashboard --since '5 min ago' --no-pager  # View logs
```

### Python Environment
```bash
# Use the venv directly (uv not available on server PATH)
/opt/jcs-mycase/.venv/bin/python3 -c "..."

# Or for scripts
cd /opt/jcs-mycase && python3 /tmp/script.py
```

### Firm ID (Multi-tenant)
```
d5AgNpGZZvZ9Lgpce7ri4Q
```
All PostgreSQL queries MUST be scoped with `AND firm_id = %s` using this ID.

---

## 3. Database Architecture

### PostgreSQL (Primary - DigitalOcean Managed)
Connection: via `DATABASE_URL` in `/opt/jcs-mycase/.env`

**Cache Tables** (synced from MyCase API):
| Table | Description | Key Columns |
|-------|-------------|-------------|
| cached_cases | All cases (2,845+) | id, status, practice_area, lead_attorney_id/name, date_opened, date_closed, firm_id |
| cached_invoices | Billing data | id, case_id, total_amount, paid_amount, balance_due, invoice_date, due_date, firm_id |
| cached_clients | Client records | id, first_name, last_name, zip_code, firm_id |
| cached_staff | Staff directory | id, name, title, firm_id |
| cached_tasks | Task assignments | id, case_id, assignee_name, completed (boolean), firm_id |
| cached_contacts | Basic contact info | id, firm_id |
| cached_events | Calendar events | id, firm_id |
| cached_payments | Payment records | id, firm_id |
| cached_time_entries | Time tracking | id, firm_id |

**Document Engine Tables** (created Feb 20, 2026):
| Table | Description |
|-------|-------------|
| firms | Firm registry for doc engine |
| templates | Document templates (SERIAL PK, BYTEA for file_content) |
| generated_documents | Audit log of generated docs |
| attorneys | Attorney profiles for signature blocks |

### SQLite Databases (Auxiliary - Server Local)

**case_phases.db** - `/opt/jcs-mycase/data/case_phases.db`
- `phases` - Phase definitions (intake, discovery, motions, strategy, trial_prep, disposition, post_disposition)
- `case_phase_history` - Tracks which phase each case is in (exited_at IS NULL = current)
- `case_workflows`, `stage_phase_mappings` - Workflow configuration

**attorney_profiles.db** - `/opt/jcs-mycase/data/attorney_profiles.db`
- `attorneys` table - Signature block data (name, bar#, firm address, etc.)
- Primary attorney: John C. Schleiffarth (bar #63222, firm_id='jcs_law')

**document_engine.db** - `/opt/jcs-mycase/data/document_engine.db`
- `templates`, `firms`, `generated_documents` - Legacy SQLite (now also in PG)
- Document engine auto-detects PG and prefers it

### Key PostgreSQL Syntax Notes (vs SQLite)
```sql
-- Date functions
strftime('%Y', x)           → EXTRACT(YEAR FROM x)
DATE('now', 'start of month') → date_trunc('month', CURRENT_DATE)
julianday('now') - julianday(x) → CURRENT_DATE - x::date

-- Placeholders
?                           → %s

-- Booleans
t.completed = 1             → t.completed = true

-- Auto-increment
INTEGER PRIMARY KEY AUTOINCREMENT → SERIAL PRIMARY KEY
```

---

## 4. Dashboard (models.py)

### File: `/opt/jcs-mycase/dashboard/models.py` (~2500+ lines)

### Connection Methods
```python
# PostgreSQL (main data) - added Feb 20, 2026
def _get_pg_connection(self):
    # Uses psycopg2 + RealDictCursor
    # Connection string from DATABASE_URL env var

# SQLite cache (legacy - being phased out)  
def _get_cache_connection(self):
    # sqlite3 connection to mycase_cache.db

# SQLite phases
def _get_phases_connection(self):
    # sqlite3 connection to case_phases.db
```

### Key Methods (Migrated to PostgreSQL Feb 20, 2026)

**Attorney Productivity** - `get_attorney_productivity_data(year=None)`
- **CRITICAL FIX:** active_cases counts ALL open cases regardless of year
- Financial metrics and closed counts filtered by year
- Uses `_get_pg_connection()`, scoped by `firm_id`

**Staff Caseload** - `get_staff_caseload_data(staff_name, year=None)`
- **CRITICAL FIX:** active_cases counts ALL open cases regardless of year
- Attorneys: counts by `lead_attorney_id`
- Non-attorneys: counts by task assignment (`assignee_name LIKE` patterns)
- Closed cases filtered by `date_closed` year, not `created_at`

**Attorney Detail** - `get_attorney_detail(attorney_id)`
- Active cases list query migrated to PG with firm_id scoping

### Phase Methods

**Phase Distribution** - `get_phase_distribution()`
- Queries `case_phase_history` from SQLite phases DB

**Phase by Case Type** - `get_phase_by_case_type()`
- Joins phases DB (SQLite) with cache (SQLite) for practice_area

**Phase by Case Type by Attorney** - `get_phase_by_case_type_by_attorney()` *(NEW - Feb 20)*
- Joins phases DB (SQLite) with PostgreSQL cache for practice_area + lead_attorney_name
- Returns: `[{attorney_name, case_types: [{practice_area, phases: {code: count}, total}], total}]`
- Sorted by total cases descending

---

## 5. Case Phases System

### Phase Codes
| Code | Display Name | Order |
|------|-------------|-------|
| intake | Intake | 1 |
| discovery | Discovery | 2 |
| motions | Motions | 3 |
| strategy | Strategy | 4 |
| trial_prep | Trial Prep | 5 |
| disposition | Disposition | 6 |
| post_disposition | Closing | 7 |

### How It Works
- `case_phase_history` tracks phase transitions
- Current phase: `WHERE exited_at IS NULL`
- Days in phase: `CURRENT_DATE - entered_at`
- Stalled cases: threshold_days parameter (default 30)

### Dashboard Pages
- **Phases page** (`/phases`): Shows phase distribution, stalled cases, velocity, by case type, by attorney & case type
- **Template:** `phases.html`
- **Route context:** summary, stalled, velocity, by_case_type, by_case_type_attorney, phase_cases

---

## 6. Document Generation System

### Architecture
```
documents.html (chat UI) → routes.py → DocumentChatEngine → Anthropic API
                                              ↓
                                    DocumentEngine (templates DB)
                                    AttorneyProfiles (signature data)
```

### Key Files
- `/opt/jcs-mycase/dashboard/templates/documents.html` - Chat UI
- `/opt/jcs-mycase/document_chat.py` - Chat engine with document type routing
- `/opt/jcs-mycase/document_engine.py` - Template storage, variable detection
- `/opt/jcs-mycase/attorney_profiles.py` - Attorney signature block data

### Document Types (from DOCUMENT_TYPES dict in document_chat.py)
- Motion to Dismiss (General, DOR, Criminal, and 10+ specific grounds)
- Motion to Continue
- Bond Assignment
- Entry of Appearance
- Subpoena for Records
- Waiver of Arraignment
- Preservation Letter
- Request for Discovery (Municipal, Circuit)
- And more...

### Attorney Profile (Configured Feb 20, 2026)
```
Attorney: John C. Schleiffarth
Bar Number: 63222
Email: john@jcsattorney.com
Firm: JCS Law - John C. Schleiffarth, P.C.
Address: 120 S Central Ave, Ste 1550, Clayton, Missouri 63105
Phone: 314-561-9690
Fax: 314-596-0658
Firm ID: jcs_law
Is Primary: Yes
```
Stored in BOTH:
- SQLite: `/opt/jcs-mycase/data/attorney_profiles.db` → `attorneys` table
- PostgreSQL: `attorneys` table

### Motion to Dismiss - Respondent Logic
- **General motion:** `respondent_name` is REQUIRED (user must provide)
- **DOR motion:** defaults to "DIRECTOR OF REVENUE"
- **Criminal motion:** uses defendant_name terminology

---

## 7. Analytics Module Reference

### File: `/opt/jcs-mycase/firm_analytics.py` (also `firm_analytics_mt.py` for multi-tenant PG)

The `FirmAnalytics` class provides 14 analytics methods. See original context doc for full method signatures.

### Key Methods
| Method | Returns |
|--------|---------|
| `get_revenue_by_case_type()` | case_type, billed, collected, count, rate |
| `get_revenue_by_attorney()` | attorney_name, billed, collected, count, rate |
| `get_revenue_by_attorney_monthly(months)` | attorney, month, billed, collected |
| `get_avg_case_length_by_type()` | category, avg/min/max days, count |
| `get_avg_fee_charged_by_type()` | case_type, avg charged/collected, count |
| `get_new_cases_past_12_months()` | total, monthly breakdown |
| `get_clients_by_zip_code()` | {zip: count} |
| `get_revenue_by_zip_code()` | {zip: {clients, cases, billed, collected}} |

---

## 8. Key Data & Current Metrics

### Top Attorneys by Revenue (All Time)
| Attorney | Cases | Billed | Collected | Rate |
|----------|------:|-------:|----------:|-----:|
| Heidi Leopold | 1,001 | $2,037,242 | $1,791,080 | 87.9% |
| Anthony Muhlenkamp | 175 | $1,827,386 | $1,446,564 | 79.2% |
| Leigh Hawk | 306 | $1,092,174 | $919,862 | 84.2% |
| John Schleiffarth | 230 | $852,591 | $702,128 | 82.4% |
| Christopher LaPee | 200 | $849,403 | $712,363 | 83.9% |
| Andy Morris | 258 | $837,790 | $770,082 | 91.9% |
| Jen Kusmer | 137 | $799,380 | $624,814 | 78.2% |

### Database Counts (Feb 2026)
| Table | Records |
|-------|---------|
| cached_cases | 2,845+ |
| cached_clients | 2,360+ |
| cached_invoices | 1,842+ |
| cached_events | 16,167+ |
| cached_staff | 24 |
| cached_tasks | 348+ |

### Anthony Muhlenkamp Active Cases
- **71 open cases** (all-time, no year filter)
- Previously showed 4 due to year filter bug (fixed Feb 20)

---

## 9. API Reference

### MyCase API Client
```python
from api_client import get_client
client = get_client()
cases = client.get_all_pages(client.get_cases, per_page=100)
```

### Available Endpoints
| Method | Endpoint | Notes |
|--------|----------|-------|
| `get_cases()` | `/cases` | Includes staff assignments |
| `get_clients()` | `/clients` | Full address data |
| `get_invoices()` | `/invoices` | Amounts, case links |
| `get_staff()` | `/staff` | Small dataset |
| `get_tasks()` | `/tasks` | OPEN cases only! |
| `get_events()` | `/events` | Calendar events |
| `get_payments()` | `/payments` | Payment records |
| `get_time_entries()` | `/time_entries` | Time tracking |

---

## 10. Staff & Roles

### Firm Info
```
JCS Law - John C. Schleiffarth, P.C.
120 S Central Ave, Ste 1550
Clayton, Missouri 63105
Office: 314-561-9690 | Fax: 314-596-0658
```

### Administrative Staff
| Name | Role | Responsibilities |
|------|------|------------------|
| Melissa Scarlett | AR Specialist | Collections, payment plans, aging reports |
| Ty Christian | Intake Lead | New client intake, lead tracking, case setup |
| Tiffany Willis | Senior Paralegal | Task management, team operations |
| Alison Ehrhard | Legal Assistant | Case tasks, discovery, license filings |
| Cole Chadderdon | Legal Assistant | Case tasks, discovery, license filings |

### Key Staff IDs
| Staff Member | ID | Role |
|-------------|-----|------|
| Tiffany Willis | 31928330 | Senior Paralegal |
| Alison Ehrhard | 41594387 | Legal Assistant |
| Cole Chadderdon | 56011402 | Legal Assistant |

---

## 11. Known Issues & Remaining Work

### Active Issues
1. **Document generation signature block** - Attorney profile exists in both SQLite and PG; doc engine loads it via `get_primary_attorney('jcs_law')` from PG `attorneys` table. Verify it renders in generated docs.
2. **Dashboard methods still on SQLite** - Many methods in models.py still use `_get_cache_connection()` (SQLite). Only attorney productivity, staff caseload, attorney detail, and phase-by-attorney have been migrated to PG.
3. **Document engine dual-DB** - `document_engine.py` auto-detects PG and uses it, but templates table is empty in both SQLite and PG. No actual .docx templates uploaded yet — AI generates from scratch.
4. **Tasks API limitation** - Only returns tasks for OPEN cases; historical task data incomplete.

### Remaining Dashboard Migration (SQLite → PostgreSQL)
These methods in `models.py` still use `_get_cache_connection()` and need migration:
- Revenue analytics methods
- Case analytics methods  
- Geographic analytics
- Payment/time-to-payment analytics
- Most other data methods

### Deployment Pattern for Patches
```bash
# 1. Create patch file locally or base64 encode
# 2. Transfer to server
ssh jcs-server "echo '<base64>' | base64 -d > /tmp/patchN.py && python3 /tmp/patchN.py"
# 3. Restart
ssh jcs-server "sudo systemctl restart mycase-dashboard"
# 4. Check logs
ssh jcs-server "sudo journalctl -u mycase-dashboard --since '2 min ago' --no-pager | tail -20"
```

---

## 12. Change Log - Feb 20, 2026 Session

### Bug Fix: Active Cases Year Filter
**Problem:** Dashboard showed Anthony Muhlenkamp with 4 active cases; actual count is 71.
**Root cause:** Active cases query in `get_attorney_productivity_data()` filtered by `created_at` year, showing only cases opened in the selected year that remain open.
**Fix:** Removed year filter from active_cases count. Active cases = ALL cases where `status = 'open'`, period. Year filter only applies to closed counts and financial metrics.
**Methods patched:**
- `get_attorney_productivity_data()` — Patch 2
- `get_staff_caseload_data()` — Patch 3  
- `get_attorney_detail()` — Patch 4

### Migration: Dashboard SQLite → PostgreSQL (Partial)
**Patch 1:** Added `_get_pg_connection()` method, `self.database_url`, `self.firm_id`
**Patches 2-4:** Migrated 3 methods from SQLite to PostgreSQL syntax:
- `?` → `%s` placeholders
- `strftime()` → `EXTRACT()`
- `DATE('now',...)` → `date_trunc()`
- `t.completed = 1` → `t.completed = true`
- Added `firm_id` scoping to all queries

### New Feature: Phase Distribution by Attorney & Case Type
**Patch 5:** Added `get_phase_by_case_type_by_attorney()` method
- Joins phases SQLite DB with PostgreSQL cache
- Returns breakdown: attorney → case_type → phase → count
- Added to routes.py and phases.html template
- Shows per-attorney tables with phase columns

### Fix: /payments 500 Error
**Cause:** Patch 5 string replacement accidentally added `by_case_type_attorney` to payments route context (routes.py line 312) without the data call.
**Fix:** Removed orphaned line from payments template context.

### Fix: Document Generation "templates" Table Missing
**Problem:** Document generation page threw "relation 'templates' does not exist"
**Cause:** `document_engine.py` auto-detects PostgreSQL and skips SQLite init, but PG tables were never created.
**Fix:** Created `firms`, `templates`, `generated_documents` tables in PostgreSQL with PG-compatible syntax (SERIAL, BYTEA).

### Fix: Attorney Profile for Signature Blocks
**Problem:** Generated documents showed `[Firm Name]`, `[Attorney Name]` placeholders instead of actual data.
**Cause:** `attorneys` table was empty in both SQLite and PostgreSQL.
**Fix:** 
- Inserted John C. Schleiffarth profile into SQLite `attorney_profiles.db`
- Created `attorneys` table in PostgreSQL and inserted same profile
- Attorney profile: bar #63222, JCS Law - John C. Schleiffarth, P.C., 120 S Central Ave Ste 1550, Clayton MO 63105

### Fix: Motion to Dismiss Respondent Default
**Problem:** General motion to dismiss defaulted respondent to "DIRECTOR OF REVENUE"
**Fix:** Made `respondent_name` a required variable for general motions (removed from defaults). DOR-specific motion keeps the Director of Revenue default.

### UI Fix: Document Generation Send Button
**Problem:** "Send" button text was truncated/clipped on doc gen page.
**Fix:** Changed button label from "Send" to "Go", removed SVG icon to fit smaller space. Also added CSS tweaks (flex-shrink, white-space, overflow adjustments).

### Backup
```
/opt/jcs-mycase/dashboard/models.py.bak.YYYYMMDD
```
