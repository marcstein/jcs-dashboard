# JCS Law Firm - MyCase Automation Project

## Project Overview
Automated SOP compliance monitoring system for JCS Law Firm using MyCase API integration.

## Staff & Roles
- **Melissa Scarlett** - AR Specialist (collections, payment plans, aging reports)
- **Ty Christian** - Intake Lead (new client intake, lead tracking, case setup)
- **Tiffany Willis** - Senior Paralegal (task management, team operations, daily huddles)
- **Alison Ehrhard** - Legal Assistant (case tasks, discovery, license filings)
- **Cole Chadderdon** - Legal Assistant (case tasks, discovery, license filings)

## Key Files

### Core Modules
- `api_client.py` - MyCase API client with OAuth, rate limiting, pagination
- `agent.py` - CLI entry point using Click framework
- `kpi_tracker.py` - KPI tracking and reporting
- `intake_automation.py` - Intake metrics, leads/case tracking
- `task_sla.py` - Task SLA monitoring, overdue tracking
- `payment_plans.py` - Payment plan compliance, NOIW pipeline
- `case_quality.py` - Case quality audits, data integrity checks
- `scheduler.py` - Automated task scheduling and cron management
- `promises.py` - Payment promise tracking and monitoring
- `notifications.py` - Multi-channel notifications (Slack, Email, SMS)
- `trends.py` - Historical KPI trend analysis
- `case_phases.py` - Universal 7-phase case management framework

### Database
- `data/mycase_agent.db` - SQLite database for local tracking
- `data/case_phases.db` - Case phase tracking and history

### Templates
- `templates/` - Email/notification templates for SOPs

### Reports
- `reports/` - Generated SOP compliance reports

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
The sync uses **upsert logic** (`INSERT ... ON CONFLICT DO UPDATE`) - records are NEVER deleted:
- Records in API but not cache → inserted
- Records in both and changed → updated
- Records in both but unchanged → left alone
- Records in cache but not API → **preserved forever**

### Task Data Accumulation
Because the MyCase API only returns tasks for open cases:
1. Tasks from closed cases ARE preserved in cache once synced
2. The longer the cache runs, the more complete historical task data becomes
3. Tasks that were never synced (case closed before cache existed) will never appear
4. Paralegal metrics show tasks from their active cases at time of sync

### Key Staff IDs
| Staff Member | ID | Role |
|-------------|-----|------|
| Tiffany Willis | 31928330 | Senior Paralegal |
| Alison Ehrhard | 41594387 | Legal Assistant |
| Cole Chadderdon | 56011402 | Legal Assistant |

### Cache Files
- `data/mycase_cache.db` - Main cache database
- `dashboard/mycase_cache.db` - Dashboard copy (symlinked or copied)

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

### Slack Notifications
Set `SLACK_WEBHOOK_URL` environment variable or configure in `data/notifications_config.json`

### Email (SendGrid)
Set `SENDGRID_API_KEY` environment variable

### SMS (Twilio)
Set `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, and `TWILIO_FROM_NUMBER` environment variables

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

## Recent Fixes
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
