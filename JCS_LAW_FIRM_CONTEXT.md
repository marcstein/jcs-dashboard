# JCS Law Firm - MyCase Analytics & Automation Context Document

**Last Updated:** January 2026
**Purpose:** Comprehensive reference for continuing work in Claude Desktop

---

## Table of Contents
1. [Project Overview](#1-project-overview)
2. [Database Schema & Cache Structure](#2-database-schema--cache-structure)
3. [Analytics Module Reference](#3-analytics-module-reference)
4. [Key Data & Current Metrics](#4-key-data--current-metrics)
5. [API Reference](#5-api-reference)
6. [CLI Commands Reference](#6-cli-commands-reference)
7. [Generated Reports](#7-generated-reports)
8. [Staff & Roles](#8-staff--roles)
9. [Common Tasks & Queries](#9-common-tasks--queries)
10. [Known Issues & Limitations](#10-known-issues--limitations)

---

## 1. Project Overview

### Purpose
Automated SOP compliance monitoring and analytics system for JCS Law Firm, a criminal defense firm specializing in DUI/DWI cases in the St. Louis, Missouri metro area.

### Architecture
```
MyCase API (Cloud) → api_client.py → sync.py → SQLite Cache → Analytics/Reports
                                                    ↓
                                          firm_analytics.py
                                                    ↓
                                    generate_report.py / generate_heatmaps.py
```

### Project Directory Structure
```
/Users/marcstein/Desktop/Legal/
├── agent.py                 # CLI entry point (Click framework)
├── api_client.py            # MyCase API client
├── cache.py                 # SQLite cache management
├── sync.py                  # API → Cache sync manager
├── firm_analytics.py        # Analytics engine (14 report types)
├── generate_report.py       # Markdown report generator
├── generate_heatmaps.py     # Interactive map generator
├── config.py                # Configuration settings
├── data/
│   ├── mycase_cache.db      # Main cache database
│   └── mycase_agent.db      # Agent/tracking database
├── reports/
│   ├── analytics_report.md  # Comprehensive analytics report
│   ├── clients_heatmap.html # Client location heatmap
│   └── revenue_heatmap.html # Revenue by location heatmap
├── dashboard/               # FastAPI web dashboard
└── templates/               # Notification templates
```

---

## 2. Database Schema & Cache Structure

### Cache Database: `data/mycase_cache.db`

**Current Record Counts (as of Jan 2026):**
| Table | Records |
|-------|---------|
| cached_cases | 2,736 |
| cached_clients | 2,360 |
| cached_contacts | 2,363 |
| cached_events | 16,167 |
| cached_invoices | 1,842 |
| cached_staff | 24 |
| cached_tasks | 348 |
| cached_time_entries | 444 |

### Table Schemas

#### cached_cases
```sql
CREATE TABLE cached_cases (
    id INTEGER PRIMARY KEY,
    name TEXT,                    -- Case name (contains jurisdiction info)
    case_number TEXT,
    status TEXT,                  -- 'open', 'closed'
    case_type TEXT,
    practice_area TEXT,           -- 'DUI/DWI', 'Criminal Defense', etc.
    date_opened DATE,
    date_closed DATE,
    lead_attorney_id INTEGER,
    lead_attorney_name TEXT,
    stage TEXT,
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    data_json TEXT,               -- Full API response as JSON
    cached_at TIMESTAMP
);
```

#### cached_clients (with address data for heatmaps)
```sql
CREATE TABLE cached_clients (
    id INTEGER PRIMARY KEY,
    first_name TEXT,
    last_name TEXT,
    email TEXT,
    cell_phone TEXT,
    work_phone TEXT,
    home_phone TEXT,
    address1 TEXT,
    address2 TEXT,
    city TEXT,
    state TEXT,
    zip_code TEXT,                -- Key for geographic analysis
    country TEXT,
    birthdate DATE,
    archived BOOLEAN,
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    data_json TEXT,
    cached_at TIMESTAMP
);
-- Indexes: zip_code, city, state, updated_at
```

#### cached_invoices
```sql
CREATE TABLE cached_invoices (
    id INTEGER PRIMARY KEY,
    invoice_number TEXT,
    case_id INTEGER,              -- Links to cached_cases.id
    contact_id INTEGER,
    status TEXT,                  -- 'paid', 'overdue', 'partial', etc.
    total_amount REAL,            -- Amount billed
    paid_amount REAL,             -- Amount collected
    balance_due REAL,             -- total_amount - paid_amount
    invoice_date DATE,
    due_date DATE,
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    data_json TEXT,
    cached_at TIMESTAMP
);
-- Indexes: case_id, status, updated_at
```

#### cached_staff
```sql
CREATE TABLE cached_staff (
    id INTEGER PRIMARY KEY,
    first_name TEXT,
    last_name TEXT,
    name TEXT,                    -- Full name
    email TEXT,
    title TEXT,
    staff_type TEXT,
    active BOOLEAN,
    hourly_rate REAL,
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    data_json TEXT,
    cached_at TIMESTAMP
);
```

### Key Relationships
```
cached_cases.id ←→ cached_invoices.case_id
cached_cases.lead_attorney_id ←→ cached_staff.id
cached_cases.data_json.clients[] ←→ cached_clients.id
```

---

## 3. Analytics Module Reference

### File: `firm_analytics.py`

The `FirmAnalytics` class provides 14 analytics methods:

#### Revenue Analytics
```python
# 1. Revenue by Case Type
get_revenue_by_case_type() -> List[RevenueByType]
# Returns: case_type, total_billed, total_collected, case_count, collection_rate

# 2. Revenue by Attorney
get_revenue_by_attorney() -> List[RevenueByAttorney]
# Returns: attorney_name, total_billed, total_collected, case_count, collection_rate

# 3. Revenue by Attorney Monthly
get_revenue_by_attorney_monthly(months: int = 12) -> List[MonthlyRevenue]
# Returns: attorney_name, month (YYYY-MM), billed, collected
```

#### Case Analytics
```python
# 4. Average Case Length by Type
get_avg_case_length_by_type() -> List[CaseLengthStats]
# Returns: category, avg_days, min_days, max_days, case_count
# NOTE: Only includes closed cases with both open and close dates

# 5. Average Case Length by Type per Attorney
get_avg_case_length_by_type_attorney() -> Dict[str, List[CaseLengthStats]]
# Returns: Dict of attorney_name -> List of CaseLengthStats
```

#### Fee Analytics
```python
# 6 & 7. Average Fee by Case Type
get_avg_fee_charged_by_type() -> List[FeeStats]
# Returns: case_type, avg_fee_charged, avg_fee_collected, total_cases
```

#### Intake Analytics
```python
# 8. New Cases Past 12 Months
get_new_cases_past_12_months() -> Dict
# Returns: {'total': int, 'monthly': {YYYY-MM: count}}

# 9. New Cases Since August (Ty Start)
get_new_cases_since_august(year: int = 2025) -> Dict
# Returns: {'total': int, 'since_date': str, 'by_case_type': {type: count}}

# 10. Fee Comparison: Since August vs Prior 12 Months
get_fee_comparison_august_vs_prior(year: int = 2025) -> Dict
# Returns comparison data with change percentages

# 13. New Cases per Month per Attorney
get_new_cases_per_month_per_attorney(months: int = 12) -> List[NewCasesMonth]
# Returns: month, attorney_name, case_count
```

#### Geographic Analytics
```python
# 11. Clients by Zip Code (Heat Map Data)
get_clients_by_zip_code() -> Dict[str, int]
# Returns: {zip_code: client_count} sorted by count descending

# 12. Revenue by Zip Code (Heat Map Data)
get_revenue_by_zip_code() -> Dict[str, Dict]
# Returns: {zip_code: {clients, cases, billed, collected, collection_rate}}

# Alternative: Cases by Jurisdiction (from case names)
get_cases_by_jurisdiction() -> Dict[str, int]
get_revenue_by_jurisdiction() -> Dict[str, Dict]
```

#### Usage Example
```python
from firm_analytics import FirmAnalytics, format_currency, format_percent

analytics = FirmAnalytics()

# Get revenue by case type
for r in analytics.get_revenue_by_case_type():
    print(f"{r.case_type}: {format_currency(r.total_billed)} billed, "
          f"{format_percent(r.collection_rate)} collected")

# Get zip code heatmap data
zip_data = analytics.get_clients_by_zip_code()
print(f"Top zip: {list(zip_data.items())[0]}")
```

### Data Classes (from firm_analytics.py)
```python
@dataclass
class RevenueByType:
    case_type: str
    total_billed: float
    total_collected: float
    case_count: int
    collection_rate: float

@dataclass
class RevenueByAttorney:
    attorney_name: str
    total_billed: float
    total_collected: float
    case_count: int
    collection_rate: float

@dataclass
class MonthlyRevenue:
    attorney_name: str
    month: str  # YYYY-MM format
    billed: float
    collected: float

@dataclass
class CaseLengthStats:
    category: str  # Case type or attorney name
    avg_days: float
    min_days: int
    max_days: int
    case_count: int

@dataclass
class FeeStats:
    case_type: str
    avg_fee_charged: float
    avg_fee_collected: float
    total_cases: int

@dataclass
class NewCasesMonth:
    month: str
    attorney_name: str
    case_count: int
```

---

## 4. Key Data & Current Metrics

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

### Top Case Types by Revenue
| Case Type | Cases | Billed | Collected | Rate |
|-----------|------:|-------:|----------:|-----:|
| DUI/DWI | 536 | $2,509,031 | $2,260,126 | 90.1% |
| Criminal Defense | 675 | $2,207,292 | $1,887,477 | 85.5% |
| Criminal - Felony | 211 | $1,729,178 | $1,358,068 | 78.5% |
| Criminal - Federal | 85 | $848,390 | $666,699 | 78.6% |
| DUI/DWI-Muni | 137 | $790,828 | $633,140 | 80.1% |

### Average Fee by Case Type (Top 10)
| Case Type | Avg Charged | Avg Collected |
|-----------|------------:|--------------:|
| Post Conviction Relief | $25,000 | $25,000 |
| Criminal - Federal | $13,908 | $10,929 |
| Criminal - Felony | $9,938 | $7,805 |
| DWI/DUI - Felony | $7,270 | $6,261 |
| DUI/DWI-Muni | $6,227 | $4,985 |
| DUI/DWI-Federal | $5,816 | $4,695 |
| Criminal Defense | $5,718 | $4,890 |
| Criminal - Juvenile | $5,700 | $3,728 |
| DUI/DWI | $5,613 | $5,056 |

### New Cases (Past 12 Months)
- **Total:** 715 cases
- **Peak Month:** August 2025 (89 cases)
- **Since Ty Started (Aug 2025):** 361 cases

### Top Jurisdictions
| Jurisdiction | Cases | Billed |
|--------------|------:|-------:|
| Other/Unknown | 981 | $2,826,758 |
| St. Louis County | 363 | $1,194,767 |
| Franklin County | 138 | $889,817 |
| Jefferson County | 213 | $789,664 |
| Federal (EDMO) | 95 | $754,914 |
| St. Charles County | 136 | $422,504 |

### Top Client Zip Codes
| Zip Code | Clients | Revenue |
|----------|--------:|--------:|
| 63026 (Fenton) | 52 | $174,850 |
| 63123 (Affton) | 42 | $159,758 |
| 63033 (Florissant) | 36 | $105,473 |
| 63052 (Imperial) | 35 | $109,037 |
| 63301 (St. Charles) | 33 | $147,361 |
| 63368 (O'Fallon) | 31 | $154,197 |
| 63129 (Mehlville) | 31 | $135,336 |

---

## 5. API Reference

### MyCase API Client (api_client.py)

```python
from api_client import get_client

client = get_client()

# Get all cases (paginated)
cases = client.get_all_pages(client.get_cases, per_page=100)

# Get all clients with addresses
clients = client.get_all_pages(client.get_clients, per_page=100)

# Get invoices
invoices = client.get_all_pages(client.get_invoices, per_page=100)

# Get staff (small dataset, no pagination)
staff = client.get_staff()
```

### Available Endpoints
| Method | Endpoint | Returns |
|--------|----------|---------|
| `get_cases()` | `/cases` | Case list with staff assignments |
| `get_clients()` | `/clients` | **Full client data with addresses** |
| `get_contacts()` | `/contacts` | Basic contact info (id, name only) |
| `get_invoices()` | `/invoices` | Invoice with amounts, case link |
| `get_staff()` | `/staff` | Staff directory |
| `get_tasks()` | `/tasks` | Tasks (OPEN cases only!) |
| `get_events()` | `/events` | Calendar events |
| `get_payments()` | `/payments` | Payment records |
| `get_time_entries()` | `/time_entries` | Time tracking |

### Pagination
```python
# endpoint_map for pagination support
endpoint_map = {
    "get_cases": "/cases",
    "get_contacts": "/contacts",
    "get_clients": "/clients",     # Added for zip code support
    "get_invoices": "/invoices",
    "get_tasks": "/tasks",
    "get_events": "/events",
    "get_payments": "/payments",
    "get_time_entries": "/time_entries",
}

# Use get_all_pages() for automatic pagination
all_records = client.get_all_pages(
    client.get_cases,
    page_delay=0.3,  # Rate limiting
    per_page=100
)
```

---

## 6. CLI Commands Reference

### Analytics Commands
```bash
# Generate full console report
uv run python agent.py analytics report

# Individual reports
uv run python agent.py analytics revenue-type
uv run python agent.py analytics revenue-attorney
uv run python agent.py analytics revenue-monthly
uv run python agent.py analytics case-length
uv run python agent.py analytics fees
uv run python agent.py analytics new-cases
uv run python agent.py analytics since-august
uv run python agent.py analytics fee-comparison
uv run python agent.py analytics jurisdiction
uv run python agent.py analytics zip-codes
uv run python agent.py analytics attorney-monthly
```

### Report Generation
```bash
# Generate markdown report
uv run python generate_report.py
# Output: reports/analytics_report.md

# Generate heatmaps
uv run python generate_heatmaps.py
# Output: reports/clients_heatmap.html, reports/revenue_heatmap.html
```

### Sync Commands
```bash
# Sync all entities
uv run python sync.py

# Sync specific entity
uv run python sync.py cases
uv run python sync.py clients
uv run python sync.py invoices

# Force full sync
uv run python sync.py full

# Check sync status
uv run python sync.py status
```

### SOP Reports
```bash
uv run python agent.py sop melissa    # AR/Collections
uv run python agent.py sop ty         # Intake
uv run python agent.py sop tiffany    # Paralegal ops
uv run python agent.py sop alison     # Legal assistant
```

### Dashboard
```bash
uv run python agent.py dashboard --host 0.0.0.0 --port 3000
# Access: http://127.0.0.1:3000 (admin/admin)
```

---

## 7. Generated Reports

### Analytics Report (reports/analytics_report.md)
Contains 14 sections:
1. Revenue by Case Type
2. Revenue by Attorney
3. Revenue by Attorney (Last 12 Months)
4. Average Case Length by Type
5. Average Fee by Case Type
6. New Cases - Past 12 Months
7. New Cases Since August (Ty Start)
8. Fee Comparison: Since August vs Prior 12 Months
9. Cases by Jurisdiction
10. Revenue by Jurisdiction
11. Clients by Zip Code (Heat Map Data)
12. Revenue by Zip Code (Heat Map Data)
13. New Cases per Month per Attorney
14. Positive Reviews - Staff Analysis (placeholder)

### Heatmaps
- **clients_heatmap.html** - Interactive Folium map showing client concentration by zip code
- **revenue_heatmap.html** - Interactive Folium map showing revenue by zip code

---

## 8. Staff & Roles

### Administrative Staff
| Name | Role | Responsibilities |
|------|------|------------------|
| Melissa Scarlett | AR Specialist | Collections, payment plans, aging reports |
| Ty Christian | Intake Lead | New client intake, lead tracking, case setup |
| Tiffany Willis | Senior Paralegal | Task management, team operations, daily huddles |
| Alison Ehrhard | Legal Assistant | Case tasks, discovery, license filings |
| Cole Chadderdon | Legal Assistant | Case tasks, discovery, license filings |

### Key Staff IDs (for queries)
| Staff Member | ID | Role |
|-------------|-----|------|
| Tiffany Willis | 31928330 | Senior Paralegal |
| Alison Ehrhard | 41594387 | Legal Assistant |
| Cole Chadderdon | 56011402 | Legal Assistant |

### Attorneys (by Revenue)
| Attorney | Active Cases | Total Billed |
|----------|-------------|--------------|
| Heidi Leopold | 1,001 | $2,037,242 |
| Anthony Muhlenkamp | 175 | $1,827,386 |
| Leigh Hawk | 306 | $1,092,174 |
| John Schleiffarth | 230 | $852,591 |
| Christopher LaPee | 200 | $849,403 |
| Andy Morris | 258 | $837,790 |
| Jen Kusmer | 137 | $799,380 |

---

## 9. Common Tasks & Queries

### Direct SQLite Queries

```sql
-- Revenue by case type
SELECT
    COALESCE(c.practice_area, 'Unknown') as case_type,
    COUNT(DISTINCT c.id) as case_count,
    SUM(i.total_amount) as total_billed,
    SUM(i.paid_amount) as total_collected
FROM cached_cases c
LEFT JOIN cached_invoices i ON i.case_id = c.id
GROUP BY COALESCE(c.practice_area, 'Unknown')
ORDER BY total_billed DESC;

-- Clients by zip code
SELECT
    SUBSTR(zip_code, 1, 5) as zip,
    COUNT(*) as client_count
FROM cached_clients
WHERE zip_code IS NOT NULL AND zip_code != ''
GROUP BY SUBSTR(zip_code, 1, 5)
ORDER BY client_count DESC
LIMIT 20;

-- New cases since August 2025
SELECT
    COALESCE(practice_area, 'Unknown') as case_type,
    COUNT(*) as count
FROM cached_cases
WHERE date_opened >= '2025-08-01'
   OR (date_opened IS NULL AND created_at >= '2025-08-01')
GROUP BY COALESCE(practice_area, 'Unknown')
ORDER BY count DESC;

-- Monthly revenue by attorney
SELECT
    COALESCE(c.lead_attorney_name, 'Unassigned') as attorney,
    strftime('%Y-%m', i.invoice_date) as month,
    SUM(i.total_amount) as billed,
    SUM(i.paid_amount) as collected
FROM cached_invoices i
JOIN cached_cases c ON c.id = i.case_id
WHERE i.invoice_date >= date('now', '-12 months')
GROUP BY c.lead_attorney_name, strftime('%Y-%m', i.invoice_date)
ORDER BY month DESC, attorney;
```

### Python Snippets

```python
# Connect to cache directly
import sqlite3
conn = sqlite3.connect('/Users/marcstein/Desktop/Legal/data/mycase_cache.db')
conn.row_factory = sqlite3.Row

# Quick stats
cursor = conn.cursor()
cursor.execute("SELECT COUNT(*) FROM cached_cases WHERE status = 'open'")
print(f"Open cases: {cursor.fetchone()[0]}")

# Use analytics module
from firm_analytics import FirmAnalytics
analytics = FirmAnalytics()
report = analytics.generate_full_report()

# Access specific data
revenue = analytics.get_revenue_by_case_type()
zip_data = analytics.get_clients_by_zip_code()
```

---

## 10. Known Issues & Limitations

### API Limitations
1. **Tasks API only returns tasks for OPEN cases** - Historical task data is incomplete
2. **Contacts endpoint only returns id/name** - Use `/clients` for full address data
3. **No `updated_since` filter** - Must fetch all records and compare locally
4. **Rate limiting** - Use 0.3s delay between paginated requests

### Data Quality Issues
1. **Limited closed case data** - Only 1 case type has avg_days data (most cases still open or missing close dates)
2. **Missing zip codes** - ~530 clients out of 2,360 have no zip code data
3. **Jurisdiction extraction** - Case names don't always contain clear jurisdiction info
4. **Review data unavailable** - Reviews are on external platforms (Google, Avvo), not in MyCase

### Cache Behavior
- **Records are NEVER deleted** - Upsert only (INSERT ON CONFLICT UPDATE)
- **Closed case tasks preserved** - Once synced, tasks remain even after case closes
- **Client-case linking** - Uses data_json.clients[] array, may have inconsistencies

### Geographic Coverage
- Heatmap zip coordinates cover St. Louis metro area
- ~305 out of 445 zip codes missing coordinates (clients outside metro area)
- Fallback: Use jurisdiction extraction from case names

---

## Quick Reference Card

### Key File Paths
```
Cache DB:     /Users/marcstein/Desktop/Legal/data/mycase_cache.db
Analytics:    /Users/marcstein/Desktop/Legal/firm_analytics.py
Reports:      /Users/marcstein/Desktop/Legal/reports/
Heatmaps:     /Users/marcstein/Desktop/Legal/reports/*_heatmap.html
```

### Most Useful Commands
```bash
# Refresh data
uv run python sync.py

# Generate all reports
uv run python generate_report.py && uv run python generate_heatmaps.py

# Quick analytics
uv run python agent.py analytics report

# Start dashboard
uv run python agent.py dashboard
```

### Key Contacts
- **Firm Focus:** Criminal Defense / DUI/DWI
- **Location:** St. Louis, Missouri metro area
- **Ty Start Date:** August 1, 2025 (reference point for intake metrics)
