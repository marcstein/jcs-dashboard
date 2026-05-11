# Session Notes — May 4, 2026

## Completed This Session

### Clio Manage API Integration (Full Build)
Built complete Clio Manage API v4 integration — parallel to the existing MyCase integration. Firms using Clio get the same cache-and-query infrastructure.

#### Files Created
- **`clio_client.py`** (~570 lines) — Full API client:
  - `ClioAuth`: OAuth 2.0 with 7-day tokens, non-expiring refresh tokens. Stores in firms table.
  - `ClioClient`: HTTP client with rate limiting, retry, cursor-based pagination.
  - Methods for all resources: matters, contacts, tasks, bills, activities, users, calendar entries, payments, trust line items, practice areas, matter stages.
  - Field selection constants per resource (Clio only returns id+etag by default).

- **`db/clio_cache.py`** (~750 lines) — Cache layer:
  - 12 tables: `clio_cached_matters`, `clio_cached_contacts`, `clio_cached_bills`, `clio_cached_tasks`, `clio_cached_users`, `clio_cached_activities`, `clio_cached_calendar_entries`, `clio_cached_payments`, `clio_cached_trust_line_items`, `clio_cached_practice_areas`, `clio_cached_matter_stages`, `clio_sync_metadata`
  - All keyed by `(firm_id, id)` with multi-tenant isolation
  - Batch upsert functions using `execute_values()` for each resource
  - Nested object extraction helpers (`_nested_id`, `_nested_name`)
  - Query helpers: `get_matters()`, `get_bills()`, `get_contacts()`, `get_tasks()`, `get_users()`, `get_activities()`

- **`clio_sync.py`** (~250 lines) — Sync manager:
  - `ClioSyncManager` orchestrates full and incremental syncs
  - Unlike MyCase, Clio supports server-side `updated_since` filtering — incremental syncs only fetch changed records
  - 5-minute overlap on incremental to catch edge cases
  - Entity sync order: reference data first, then core, then derived
  - Context manager support for clean client lifecycle

- **`commands/clio.py`** (~220 lines) — CLI commands:
  - `clio test` — Test API connection
  - `clio auth-url` — Get OAuth authorization URL
  - `clio exchange-code` — Exchange auth code for tokens
  - `clio refresh-token` — Manual token refresh
  - `clio sync` — Sync all/specific entities (supports --force, --entity)
  - `clio status` — Show cache status and last sync times
  - `clio setup` — Configure Clio credentials for a firm

#### Files Modified
- **`db/firms.py`** — Added 7 columns: `pms_type`, `clio_client_id`, `clio_client_secret`, `clio_oauth_token`, `clio_oauth_refresh`, `clio_token_expires_at`, `clio_connected`. Added to migration list.
- **`firm_settings.py`** — Added `get_clio_credentials()`, `is_clio_connected()`, `pms_type` property, `is_mycase_firm()`, `is_clio_firm()`.
- **`agent.py`** — Registered `clio` command group.

#### Architecture Decision: Separate Tables per PMS
- Chose `clio_cached_*` tables (separate from `cached_*` MyCase tables)
- `firms.pms_type` column routes to correct PMS (`'mycase'` or `'clio'`)
- Avoids schema conflicts between PMS data models
- Each PMS keeps full data fidelity

#### Clio → MyCase Resource Mapping
| Clio | MyCase | Cache Table |
|------|--------|-------------|
| Matters | Cases | `clio_cached_matters` |
| Bills | Invoices | `clio_cached_bills` |
| Users | Staff | `clio_cached_users` |
| Activities | Time Entries | `clio_cached_activities` |
| Calendar Entries | Events | `clio_cached_calendar_entries` |
| Contacts | Contacts/Clients | `clio_cached_contacts` |
| Tasks | Tasks | `clio_cached_tasks` |
| Payments | Payments | `clio_cached_payments` |
| Trust Line Items | (none) | `clio_cached_trust_line_items` |

#### Onboarding a Clio Firm
```bash
# 1. Create firm record (if new)
python agent.py firms create "Firm Name" --id firm_id

# 2. Set Clio credentials
python agent.py clio setup --firm-id firm_id --client-id <ID> --client-secret <SECRET>

# 3. OAuth flow
python agent.py clio auth-url --firm-id firm_id
# Open URL, authorize, copy code
python agent.py clio exchange-code --firm-id firm_id --code <CODE>

# 4. Initial sync
python agent.py clio sync --firm-id firm_id
```

## Open Items (Carried Forward)
- Marketing analytics dashboard page (`/intake/marketing`) — in progress
- End-to-end verification: form → UTM → spend → ROI display
- LawPay integration staged, waiting for client approval
- Old `clio/` directory contains a Jan 2026 prototype — can be deleted once new integration is verified on production
