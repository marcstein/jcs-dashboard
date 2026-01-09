# JCS Law Firm - MyCase Automation System
## Comprehensive User Guide

**Version:** 1.0
**Last Updated:** December 2025

---

## Table of Contents

1. [Overview](#overview)
2. [Getting Started](#getting-started)
3. [Staff Roles & Daily Workflows](#staff-roles--daily-workflows)
4. [SOP Reports](#sop-reports)
5. [Payment Plans & Collections](#payment-plans--collections)
6. [Payment Promise Tracking](#payment-promise-tracking)
7. [Task Management & SLAs](#task-management--slas)
8. [Case Quality Audits](#case-quality-audits)
9. [Intake Tracking](#intake-tracking)
10. [Scheduled Automation](#scheduled-automation)
11. [Notifications (Slack/Email/SMS)](#notifications)
12. [Trend Analysis & KPI Tracking](#trend-analysis--kpi-tracking)
13. [Configuration Reference](#configuration-reference)
14. [Troubleshooting](#troubleshooting)

---

## Overview

The MyCase Automation System is a command-line tool that monitors SOP compliance for JCS Law Firm. It connects to MyCase via API to track:

- **Accounts Receivable** - Aging, payment plans, collections
- **Intake** - New cases, lead conversion, contact rates
- **Tasks** - SLA monitoring, overdue tracking, license deadlines
- **Quality** - Case setup audits, data integrity checks

The system generates daily/weekly reports, sends automated notifications, and tracks historical trends to identify areas needing attention.

### Key Metrics Monitored

| Metric | Target | Current Status |
|--------|--------|----------------|
| AR over 60 days | <25% | 82.2% (Critical) |
| Payment plan compliance | ≥90% | 7.6% (Critical) |
| Case quality score | ≥90% | 58.1% |
| Same-day client contact | 100% | - |
| Overdue tasks | 0 | 42 |

---

## Getting Started

### Prerequisites

- Python 3.11+
- MyCase API credentials (OAuth)
- Virtual environment with dependencies installed

### Basic Usage

```bash
# Activate the virtual environment
source .venv/bin/activate

# Run any command
uv run python agent.py <command> <subcommand> [options]

# Get help
uv run python agent.py --help
uv run python agent.py <command> --help
```

### First-Time Setup

1. **Authenticate with MyCase:**
   ```bash
   uv run python auth.py
   ```
   This opens a browser for OAuth authentication and stores tokens in `data/tokens.json`.

2. **Sync initial data:**
   ```bash
   uv run python agent.py tasks sync
   uv run python agent.py plans sync
   ```

3. **Run a test report:**
   ```bash
   uv run python agent.py sop melissa
   ```

---

## Staff Roles & Daily Workflows

### Melissa Scarlett - AR Specialist

**Responsibilities:** Collections, payment plans, aging reports, NOIW pipeline

**Daily Tasks:**
1. Check payment plan compliance report
2. Review NOIW pipeline (30+ days delinquent)
3. Make outreach calls to delinquent accounts
4. Record payment promises from calls
5. Process payments and update promise status

**Key Commands:**
```bash
uv run python agent.py sop melissa              # Full AR report
uv run python agent.py plans compliance         # Payment plan status
uv run python agent.py plans noiw-pipeline      # Cases needing NOIW
uv run python agent.py promises list            # Pending payment promises
uv run python agent.py promises due-today       # Promises due today
```

**Weekly:**
- Monday 9am: Weekly A/R Report
- Wednesday 9am: A/R Huddle (with Tiffany & John)
- Friday 2pm: NOIW Pipeline Review

---

### Ty Christian - Intake Lead

**Responsibilities:** New client intake, lead tracking, case setup verification

**Daily Tasks:**
1. Review new leads/cases from previous day
2. Ensure same-day contact for new clients
3. Verify case setup completeness
4. Track conversion metrics

**Key Commands:**
```bash
uv run python agent.py sop ty                   # Intake report
uv run python agent.py intake metrics           # Weekly metrics
uv run python agent.py quality audit --days 1   # New case quality check
```

**Weekly:**
- Monday 9:30am: Weekly Intake Report (due by 10am)

---

### Tiffany Willis - Senior Paralegal

**Responsibilities:** Task management, team operations, daily huddles, quality oversight

**Daily Tasks:**
1. Run ops huddle report (7:45am)
2. Review overdue tasks by assignee
3. Monitor case quality scores
4. Coordinate with attorneys on deadlines

**Key Commands:**
```bash
uv run python agent.py sop tiffany              # Ops huddle report
uv run python agent.py sop tiffany --quality    # Quality summary
uv run python agent.py tasks overdue            # All overdue tasks
uv run python agent.py quality summary          # Quality dashboard
```

**Weekly:**
- Friday 4pm: Weekly Quality Summary

---

### Alison Ehrhard & Cole Chadderdon - Legal Assistants

**Responsibilities:** Case tasks, discovery, license filings

**Critical Deadlines:**
- **DOR Filing:** 15 days from arrest (client did NOT refuse test)
- **PFR Filing:** 30 days from arrest (client REFUSED test)

**Daily Tasks:**
1. Check license deadline alerts
2. Complete assigned tasks within SLA
3. Monitor Case.net for new charges

**Key Commands:**
```bash
uv run python agent.py sop alison               # Alison's task report
uv run python agent.py sop cole                 # Cole's task report
uv run python agent.py tasks license-deadlines  # DOR/PFR deadlines
uv run python agent.py tasks casenet            # Case.net checklist
```

---

## SOP Reports

Generate role-specific compliance reports:

```bash
# Melissa - AR/Collections
uv run python agent.py sop melissa
uv run python agent.py sop melissa --weekly     # Weekly summary

# Ty - Intake
uv run python agent.py sop ty
uv run python agent.py sop ty --weekly          # Weekly metrics

# Tiffany - Operations
uv run python agent.py sop tiffany              # Ops huddle
uv run python agent.py sop tiffany --quality    # Quality focus

# Alison/Cole - Legal Assistants
uv run python agent.py sop alison
uv run python agent.py sop cole
```

### Report Contents

**Melissa's Report includes:**
- Total AR and aging breakdown
- Payment plan compliance rate
- Delinquent accounts by age bucket
- NOIW pipeline (30+ days)
- Collections hold list
- Wonky invoice queue

**Ty's Report includes:**
- New cases this week
- Case type breakdown (DWI, Traffic, etc.)
- Same-day contact rate
- Conversion metrics
- Lead sources

**Tiffany's Report includes:**
- Overdue tasks by assignee
- Tasks due today
- Quality scores by attorney
- 3-day attorney outreach compliance

---

## Payment Plans & Collections

### Syncing Payment Plans

```bash
uv run python agent.py plans sync
```

This pulls invoice data from MyCase and identifies accounts with partial payments (payment plans).

### Compliance Check

```bash
uv run python agent.py plans compliance
```

Shows all active payment plans with their status:
- **Current** - On track
- **1-15 days late** - Needs friendly reminder
- **16-30 days late** - Firm demand, NOIW warning
- **31-60 days late** - NOIW preparation
- **60+ days late** - Escalate to attorney

### NOIW Pipeline

```bash
uv run python agent.py plans noiw-pipeline
```

Lists all cases 30+ days delinquent that need Notice of Intent to Withdraw consideration.

### Collections Holds

Some cases are exempt from collections (e.g., pending settlement, special arrangement):

```bash
# View holds due for review
uv run python agent.py plans holds

# Add a hold (done via database, not CLI currently)
```

### Dunning Sequence

The system tracks automated dunning notices:

| Days Past Due | Action | Template |
|---------------|--------|----------|
| 1-15 | Friendly reminder | `sop_friendly_reminder.txt` |
| 16-30 | Firm demand | `sop_firm_demand.txt` |
| 31-60 | NOIW cover letter | `sop_noiw_cover.txt` |
| 60+ | Attorney escalation | - |

---

## Payment Promise Tracking

Track verbal payment commitments made during collections calls.

### Recording a Promise

When a client promises to pay during a call:

```bash
uv run python agent.py promises add <contact_id> <amount> <date> [options]
```

**Example:**
```bash
uv run python agent.py promises add 12345 500.00 2025-01-15 \
  --contact-name "John Smith" \
  --case-name "Smith DWI" \
  --recorded-by "Melissa" \
  --notes "Client will pay after payday on the 15th"
```

**Parameters:**
- `contact_id` - MyCase contact ID
- `amount` - Promised payment amount
- `date` - Expected payment date (YYYY-MM-DD format)

**Options:**
- `--contact-name` - Client name for display
- `--case-name` - Related case name
- `--case-id` - Related case ID
- `--invoice-id` - Related invoice ID
- `--recorded-by` - Staff member recording (default: "Staff")
- `--notes` - Additional notes

### Viewing Promises

```bash
# List all pending promises
uv run python agent.py promises list

# Promises due today
uv run python agent.py promises due-today

# Overdue/broken promises
uv run python agent.py promises overdue

# Filter by contact or case
uv run python agent.py promises list --contact-id 12345
uv run python agent.py promises list --case-id 67890
```

### Updating Promise Status

When payment is received:
```bash
uv run python agent.py promises kept <promise_id> <actual_amount>

# Example
uv run python agent.py promises kept 1 500.00
```

When payment is not received by the promise date:
```bash
uv run python agent.py promises broken <promise_id> [--notes "reason"]

# Example
uv run python agent.py promises broken 1 --notes "No payment, left voicemail"
```

### Daily Promise Check

Run the daily monitoring report:

```bash
uv run python agent.py promises check
```

This report shows:
- Promises due today (need to verify payment)
- Newly broken promises (auto-detected overnight)
- Upcoming promises (next 7 days)
- Promise-keeping statistics

### Promise Statistics

```bash
uv run python agent.py promises stats
uv run python agent.py promises stats --days 60  # Look back 60 days
```

**Output includes:**
- Total promises in period
- Keep rate (% of promises kept)
- Kept/Broken/Partial/Pending counts
- Total promised vs collected amounts

### How Auto-Detection Works

The system automatically marks promises as "broken" when:
1. The promise date has passed
2. No payment has been recorded
3. The promise wasn't manually updated

This happens during the daily `promises check` run or when scheduled automation runs.

### Client Reliability Scoring

Each client gets a reliability score based on their promise history:

| Keep Rate | Broken Count | Risk Level |
|-----------|--------------|------------|
| ≥75% | 0 | Low |
| 50-75% | 1+ | Medium |
| <50% | 3+ | High |

High-risk clients may warrant different collection strategies (e.g., require payment before work continues).

---

## Task Management & SLAs

### Task SLA Definitions

| Task Type | SLA | Notes |
|-----------|-----|-------|
| Case setup | 24 hours | New matter setup tasks |
| Entry of appearance | 24 hours | Must file promptly |
| Discovery request | 24 hours | Time-sensitive |
| Client response | 4 hours | Same business day |
| Document upload | 4 hours | Same business day |
| DOR filing | 15 days | From arrest date |
| PFR filing | 30 days | From arrest date |

### Viewing Tasks

```bash
# Sync tasks from MyCase
uv run python agent.py tasks sync

# View overdue tasks
uv run python agent.py tasks overdue

# View by assignee
uv run python agent.py tasks by-assignee
```

### License Filing Deadlines

Critical DUI/DWI deadlines:

```bash
uv run python agent.py tasks license-deadlines
uv run python agent.py tasks license-deadlines --days 14  # Next 14 days
```

**DOR (Department of Revenue) Hearing:**
- 15 days from arrest
- Client did NOT refuse the test
- Administrative license hearing

**PFR (Petition for Review):**
- 30 days from arrest
- Client REFUSED the test
- Court petition required

### Case.net Monitoring

For pre-charge cases, regularly check Case.net:

```bash
uv run python agent.py tasks casenet
```

This shows a checklist of cases that need Case.net monitoring for new charges.

---

## Case Quality Audits

### Quality Checklist (Day-1 New Matter)

Each new case is scored on these criteria:

| Item | Weight | Description |
|------|--------|-------------|
| Lead attorney assigned | 2.0 | Must have attorney |
| Client contact info | 1.5 | Phone/email present |
| Engagement Agreement | 2.0 | EA uploaded |
| Invoice created | 2.0 | Billing set up |
| Fee matches EA | 1.5 | Invoice = agreement |
| Payment plan setup | 1.5 | If applicable |
| Portal access | 1.0 | Client can log in |
| Case type set | 1.0 | DWI, Traffic, etc. |
| Court info | 1.0 | Venue/court set |
| 3-day attorney outreach | 2.0 | Attorney contacted client |

### Running Audits

```bash
# Audit recent cases
uv run python agent.py quality audit
uv run python agent.py quality audit --days 7   # Last 7 days

# Summary dashboard
uv run python agent.py quality summary

# Specific case
uv run python agent.py quality check <case_id>
```

### Quality Grades

| Score | Grade | Action |
|-------|-------|--------|
| 90-100% | Excellent | No action needed |
| 75-89% | Good | Minor improvements |
| 50-74% | Needs Attention | Review required |
| <50% | Critical | Immediate attention |

### 3-Day Attorney Outreach

Every new client must receive contact from their attorney within 3 business days. The system tracks:
- Cases where outreach is overdue
- Compliance rate by attorney
- Target: 100%

---

## Intake Tracking

### Weekly Metrics

```bash
uv run python agent.py intake metrics
```

**Tracks:**
- New cases this week
- Case type breakdown
- Lead sources (if using leads feature)
- Same-day contact rate
- Conversion rate

### Case Type Distribution

Typical breakdown:
- DWI: 44%
- Traffic: 25%
- Other: 19%
- Municipal: 6%
- Expungement: 6%

### Lead Tracking

If using MyCase leads:

```bash
uv run python agent.py intake leads
```

Note: The firm historically used leads in 2022 but not actively now. The system uses case creation dates as a proxy for intake metrics.

---

## Scheduled Automation

### Overview

The scheduler runs automated tasks at specified times without manual intervention.

### Viewing Scheduled Tasks

```bash
# Show all tasks with status
uv run python agent.py scheduler status

# Detailed task list
uv run python agent.py scheduler list
uv run python agent.py scheduler list --frequency daily
```

### Daily Schedule (Weekdays)

| Time | Task | Owner | Description |
|------|------|-------|-------------|
| 6:00 AM | Data Sync | - | Sync invoices, tasks, events |
| 7:00 AM | Payment Plan Compliance | Melissa | Check plan status |
| 7:30 AM | Dunning Cycle | Melissa | Send collection notices |
| 7:45 AM | Ops Huddle Prep | Tiffany | Generate huddle report |
| 8:00 AM | Deadline Notifications | - | Alert on upcoming deadlines |
| 8:00 AM | License Deadline Check | Alison | DOR/PFR alerts |
| 8:30 AM | Overdue Task Alerts | - | Notify on overdue tasks |
| 9:00 AM | Quality Audit | Tiffany | Audit yesterday's cases |

### Weekly Schedule

| Day | Time | Task | Owner |
|-----|------|------|-------|
| Monday | 9:00 AM | Weekly A/R Report | Melissa |
| Monday | 9:30 AM | Weekly Intake Report | Ty |
| Wednesday | 9:00 AM | A/R Huddle Report | Melissa |
| Friday | 2:00 PM | NOIW Pipeline Review | Melissa |
| Friday | 4:00 PM | Weekly Quality Summary | Tiffany |

### Monthly Schedule

| Day | Time | Task | Owner |
|-----|------|------|-------|
| 1st | 10:00 AM | Monthly Intake Review | Ty |
| 1st | 10:00 AM | Monthly Collections Report | Melissa |

### Running Tasks Manually

```bash
# Run a specific task
uv run python agent.py scheduler run <task_name>
uv run python agent.py scheduler run quality_audit --force

# Run all due tasks
uv run python agent.py scheduler run-due
```

### Enabling/Disabling Tasks

```bash
# Disable a task
uv run python agent.py scheduler disable dunning_cycle

# Re-enable
uv run python agent.py scheduler enable dunning_cycle
```

### Installing Cron Jobs

To run automation automatically:

```bash
# Preview cron entries
uv run python agent.py scheduler cron show

# Install (dry run first)
uv run python agent.py scheduler cron install

# Actually install
uv run python agent.py scheduler cron install --execute

# Remove if needed
uv run python agent.py scheduler cron remove
```

The cron runs the scheduler every 15 minutes during business hours (6am-6pm weekdays) to check for and execute due tasks.

---

## Notifications

### Supported Channels

1. **Slack** - Team channel alerts and reports
2. **Email** - Individual notifications via SendGrid
3. **SMS** - Critical alerts via Twilio
4. **Console** - Default dry-run mode (no external sending)

### Checking Status

```bash
uv run python agent.py notify status
```

Shows:
- Dry run mode (on/off)
- Enabled channels
- Configuration status for each channel

### Testing Notifications

```bash
# Test Slack
uv run python agent.py notify test-slack
uv run python agent.py notify test-slack --message "Custom test message"

# Test Email
uv run python agent.py notify test-email recipient@example.com
uv run python agent.py notify test-email recipient@example.com --subject "Test Subject"
```

### Sending Reports to Slack

```bash
# Daily AR report
uv run python agent.py notify send-report daily_ar

# Weekly intake report
uv run python agent.py notify send-report intake_weekly

# Overdue tasks alert
uv run python agent.py notify send-report overdue_tasks
```

### Viewing Notification History

```bash
uv run python agent.py notify log
uv run python agent.py notify log --limit 50
```

### Configuration

#### Slack Setup

1. Create a Slack webhook at https://api.slack.com/messaging/webhooks
2. Set environment variable:
   ```bash
   export SLACK_WEBHOOK_URL="https://hooks.slack.com/services/xxx/yyy/zzz"
   ```

Or edit `data/notifications_config.json`:
```json
{
  "slack": {
    "webhook_url": "https://hooks.slack.com/services/xxx/yyy/zzz",
    "default_channel": "#mycase-alerts",
    "username": "MyCase Bot"
  }
}
```

#### Email Setup (SendGrid)

```bash
export SENDGRID_API_KEY="SG.xxxxxxxxxxxxx"
```

#### SMS Setup (Twilio)

```bash
export TWILIO_ACCOUNT_SID="ACxxxxxxxxxxxxxxx"
export TWILIO_AUTH_TOKEN="your_auth_token"
export TWILIO_FROM_NUMBER="+15551234567"
```

### Dry Run Mode

By default, notifications run in dry-run mode (console output only). To enable actual sending, edit `data/notifications_config.json`:

```json
{
  "dry_run": false,
  "enabled_channels": ["slack", "email"]
}
```

---

## Trend Analysis & KPI Tracking

### Recording Daily Snapshots

```bash
uv run python agent.py trends record
```

This saves today's KPI values to the database for historical tracking. Should run daily (included in scheduled automation).

### Viewing the Dashboard

```bash
uv run python agent.py trends dashboard
```

Shows a table with:
- Current value
- Target
- Trend direction (improving/declining/stable)
- Sparkline visualization
- % change

**Example output:**
```
                    KPI Trends Dashboard
┏━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━┳━━━━━━━━┳━━━━━━━┳━━━━━━━━━━━━━━┳━━━━━━━━━┓
┃ Metric                  ┃ Current ┃ Target ┃ Trend ┃ Sparkline    ┃  Change ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━╇━━━━━━━━╇━━━━━━━╇━━━━━━━━━━━━━━╇━━━━━━━━━┩
│ Ar Over 60 Pct          │    82.2 │   25.0 │   -   │ ▇▇▆▆▅▅▄▄▃▃▂ │   -5.2% │
│ Payment Plan Compliance │     7.6 │   90.0 │   +   │ ▁▁▂▂▃▃▄▄▅▅▆ │  +12.3% │
│ Quality Score           │    58.1 │   90.0 │   +   │ ▂▂▃▃▄▄▅▅▆▆▇ │   +8.7% │
└─────────────────────────┴─────────┴────────┴───────┴──────────────┴─────────┘
```

### Generating a Report

```bash
uv run python agent.py trends report
uv run python agent.py trends report --days 60  # Last 60 days
```

Provides:
- Metrics needing attention (off-target)
- On-target metrics
- Week-over-week summary
- Insights and recommendations

### Analyzing Specific Metrics

```bash
uv run python agent.py trends analyze ar_over_60_pct
uv run python agent.py trends analyze payment_plan_compliance --days 14
```

Shows:
- Current vs previous value
- Target and gap
- Direction (improving/declining/stable)
- Change percentage
- Sparkline
- Generated insight

### Period Comparisons

```bash
# Week over week
uv run python agent.py trends compare ar_over_60_pct --period week

# Month over month
uv run python agent.py trends compare payment_plan_compliance --period month
```

### Available Metrics

| Metric Name | Target | Higher is Better? |
|-------------|--------|-------------------|
| `ar_over_60_pct` | 25.0 | No (lower = better) |
| `payment_plan_compliance` | 90.0 | Yes |
| `quality_score` | 90.0 | Yes |
| `overdue_tasks` | 0 | No (lower = better) |
| `attorney_outreach_compliance` | 100.0 | Yes |
| `same_day_contact_rate` | 100.0 | Yes |

---

## Configuration Reference

### File Locations

| File | Purpose |
|------|---------|
| `data/tokens.json` | MyCase OAuth tokens |
| `data/mycase_agent.db` | SQLite database |
| `data/notifications_config.json` | Notification settings |
| `data/scheduler_config.json` | Scheduler settings |
| `data/scheduler_last_run.json` | Last run timestamps |
| `logs/scheduler.log` | Scheduler execution log |
| `logs/cron.log` | Cron output log |

### Environment Variables

| Variable | Purpose |
|----------|---------|
| `MYCASE_CLIENT_ID` | OAuth client ID |
| `MYCASE_CLIENT_SECRET` | OAuth client secret |
| `SLACK_WEBHOOK_URL` | Slack incoming webhook |
| `SENDGRID_API_KEY` | SendGrid API key |
| `TWILIO_ACCOUNT_SID` | Twilio account SID |
| `TWILIO_AUTH_TOKEN` | Twilio auth token |
| `TWILIO_FROM_NUMBER` | Twilio sending number |

### Database Tables

| Table | Purpose |
|-------|---------|
| `payment_plans` | Payment plan tracking |
| `payment_promises` | Promise tracking |
| `dunning_notices` | Dunning history |
| `payments` | Payment records |
| `case_deadlines` | Deadline tracking |
| `attorney_notifications` | Notification log |
| `invoice_snapshots` | AR analytics |
| `kpi_snapshots` | Trend data |
| `outreach_log` | Collections outreach |
| `collections_holds` | Hold list |

---

## Troubleshooting

### Authentication Issues

**Error:** "Access token expired" or "401 Unauthorized"

**Solution:**
```bash
uv run python auth.py
```

Re-authenticate with MyCase.

### No Data Returned

**Cause:** Data not synced from MyCase

**Solution:**
```bash
uv run python agent.py tasks sync
uv run python agent.py plans sync
```

### Scheduler Not Running

**Check status:**
```bash
uv run python agent.py scheduler status
```

**Check if task is enabled:**
```bash
uv run python agent.py scheduler list
```

**Check cron installation:**
```bash
crontab -l | grep mycase
```

### Notifications Not Sending

**Check configuration:**
```bash
uv run python agent.py notify status
```

**Common issues:**
1. Dry run mode enabled (default)
2. Missing API keys/webhook URLs
3. Channel not in `enabled_channels`

**Test individually:**
```bash
uv run python agent.py notify test-slack
uv run python agent.py notify test-email test@example.com
```

### Database Errors

**Cause:** Corrupted or locked database

**Solution:**
```bash
# Check database
sqlite3 data/mycase_agent.db ".tables"

# If needed, backup and reinitialize
mv data/mycase_agent.db data/mycase_agent.db.backup
uv run python agent.py tasks sync
```

### Rate Limiting

**Error:** "429 Too Many Requests"

The system automatically handles rate limiting (25 requests/second), but if you see this:

1. Wait a few minutes
2. Reduce concurrent operations
3. Check for runaway scripts

---

## Quick Reference Card

### Daily Commands (Melissa)

```bash
uv run python agent.py sop melissa
uv run python agent.py promises due-today
uv run python agent.py promises check
uv run python agent.py plans compliance
```

### Daily Commands (Tiffany)

```bash
uv run python agent.py sop tiffany
uv run python agent.py tasks overdue
uv run python agent.py quality audit --days 1
```

### Daily Commands (Alison/Cole)

```bash
uv run python agent.py sop alison
uv run python agent.py tasks license-deadlines
```

### Weekly Commands

```bash
uv run python agent.py sop melissa --weekly
uv run python agent.py sop ty --weekly
uv run python agent.py trends report
uv run python agent.py quality summary
```

### Recording a Payment Promise

```bash
uv run python agent.py promises add <contact_id> <amount> <YYYY-MM-DD> \
  --contact-name "Name" --case-name "Case" --recorded-by "Staff"
```

### Marking Promise Outcomes

```bash
uv run python agent.py promises kept <id> <amount>
uv run python agent.py promises broken <id>
```

---

## Support

For issues or feature requests:
- Check this documentation first
- Review the CLAUDE.md file for technical details
- Contact system administrator

---

*Document generated December 2025*
