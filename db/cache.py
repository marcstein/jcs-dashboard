"""
MyCase API Cache — PostgreSQL Multi-Tenant

Cached data from MyCase API. All tables keyed by (firm_id, id).
Uses upsert logic: records are never deleted.

Tables:
    sync_metadata, cached_cases, cached_contacts, cached_clients,
    cached_invoices, cached_events, cached_tasks, cached_staff,
    cached_payments, cached_time_entries
"""
import json
import logging
from datetime import datetime
from typing import List, Dict, Optional, Any

from psycopg2.extras import execute_values

from db.connection import get_connection

logger = logging.getLogger(__name__)


# ============================================================
# Schema
# ============================================================

CACHE_SCHEMA = """
CREATE TABLE IF NOT EXISTS sync_metadata (
    firm_id VARCHAR(36) NOT NULL,
    entity_type TEXT NOT NULL,
    last_full_sync TIMESTAMP,
    last_incremental_sync TIMESTAMP,
    total_records INTEGER DEFAULT 0,
    sync_duration_seconds REAL,
    last_error TEXT,
    PRIMARY KEY (firm_id, entity_type)
);

CREATE TABLE IF NOT EXISTS cached_cases (
    firm_id VARCHAR(36) NOT NULL,
    id INTEGER NOT NULL,
    name TEXT,
    case_number TEXT,
    status TEXT,
    case_type TEXT,
    practice_area TEXT,
    date_opened DATE,
    date_closed DATE,
    lead_attorney_id INTEGER,
    lead_attorney_name TEXT,
    stage TEXT,
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    data_json TEXT,
    cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (firm_id, id)
);
CREATE INDEX IF NOT EXISTS idx_cc_updated ON cached_cases(firm_id, updated_at);
CREATE INDEX IF NOT EXISTS idx_cc_status ON cached_cases(firm_id, status);

CREATE TABLE IF NOT EXISTS cached_contacts (
    firm_id VARCHAR(36) NOT NULL,
    id INTEGER NOT NULL,
    first_name TEXT,
    last_name TEXT,
    name TEXT,
    email TEXT,
    phone TEXT,
    contact_type TEXT,
    company TEXT,
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    data_json TEXT,
    cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (firm_id, id)
);
CREATE INDEX IF NOT EXISTS idx_cco_updated ON cached_contacts(firm_id, updated_at);

CREATE TABLE IF NOT EXISTS cached_clients (
    firm_id VARCHAR(36) NOT NULL,
    id INTEGER NOT NULL,
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
    zip_code TEXT,
    country TEXT,
    birthdate DATE,
    archived BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    data_json TEXT,
    cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (firm_id, id)
);
CREATE INDEX IF NOT EXISTS idx_ccl_updated ON cached_clients(firm_id, updated_at);
CREATE INDEX IF NOT EXISTS idx_ccl_zip ON cached_clients(firm_id, zip_code);

CREATE TABLE IF NOT EXISTS cached_invoices (
    firm_id VARCHAR(36) NOT NULL,
    id INTEGER NOT NULL,
    invoice_number TEXT,
    case_id INTEGER,
    contact_id INTEGER,
    status TEXT,
    total_amount REAL,
    paid_amount REAL,
    balance_due REAL,
    invoice_date DATE,
    due_date DATE,
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    data_json TEXT,
    cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (firm_id, id)
);
CREATE INDEX IF NOT EXISTS idx_ci_updated ON cached_invoices(firm_id, updated_at);
CREATE INDEX IF NOT EXISTS idx_ci_status ON cached_invoices(firm_id, status);
CREATE INDEX IF NOT EXISTS idx_ci_case ON cached_invoices(firm_id, case_id);

CREATE TABLE IF NOT EXISTS cached_events (
    firm_id VARCHAR(36) NOT NULL,
    id INTEGER NOT NULL,
    name TEXT,
    description TEXT,
    event_type TEXT,
    start_at TEXT,
    end_at TEXT,
    all_day BOOLEAN,
    case_id INTEGER,
    location TEXT,
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    data_json TEXT,
    cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (firm_id, id)
);
CREATE INDEX IF NOT EXISTS idx_ce_updated ON cached_events(firm_id, updated_at);
CREATE INDEX IF NOT EXISTS idx_ce_start ON cached_events(firm_id, start_at);

CREATE TABLE IF NOT EXISTS cached_tasks (
    firm_id VARCHAR(36) NOT NULL,
    id INTEGER NOT NULL,
    name TEXT,
    description TEXT,
    due_date DATE,
    completed BOOLEAN,
    completed_at TIMESTAMP,
    priority TEXT,
    case_id INTEGER,
    assignee_id INTEGER,
    assignee_name TEXT,
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    data_json TEXT,
    cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (firm_id, id)
);
CREATE INDEX IF NOT EXISTS idx_ct_updated ON cached_tasks(firm_id, updated_at);
CREATE INDEX IF NOT EXISTS idx_ct_due ON cached_tasks(firm_id, due_date);

CREATE TABLE IF NOT EXISTS cached_staff (
    firm_id VARCHAR(36) NOT NULL,
    id INTEGER NOT NULL,
    first_name TEXT,
    last_name TEXT,
    name TEXT,
    email TEXT,
    title TEXT,
    staff_type TEXT,
    active BOOLEAN,
    hourly_rate REAL,
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    data_json TEXT,
    cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (firm_id, id)
);
CREATE INDEX IF NOT EXISTS idx_cs_active ON cached_staff(firm_id, active);

CREATE TABLE IF NOT EXISTS cached_payments (
    firm_id VARCHAR(36) NOT NULL,
    id INTEGER NOT NULL,
    invoice_id INTEGER,
    amount REAL,
    payment_date DATE,
    payment_method TEXT,
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    data_json TEXT,
    cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (firm_id, id)
);
CREATE INDEX IF NOT EXISTS idx_cp_invoice ON cached_payments(firm_id, invoice_id);

CREATE TABLE IF NOT EXISTS cached_time_entries (
    firm_id VARCHAR(36) NOT NULL,
    id INTEGER NOT NULL,
    description TEXT,
    entry_date DATE,
    hours REAL,
    rate REAL,
    billable BOOLEAN,
    flat_fee BOOLEAN,
    activity_name TEXT,
    case_id INTEGER,
    staff_id INTEGER,
    staff_name TEXT,
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    data_json TEXT,
    cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (firm_id, id)
);
CREATE INDEX IF NOT EXISTS idx_cte_date ON cached_time_entries(firm_id, entry_date);
CREATE INDEX IF NOT EXISTS idx_cte_staff ON cached_time_entries(firm_id, staff_id);

CREATE TABLE IF NOT EXISTS cached_documents (
    firm_id VARCHAR(36) NOT NULL,
    id INTEGER NOT NULL,
    name TEXT,
    description TEXT,
    content_type TEXT,
    file_size INTEGER,
    case_id INTEGER,
    contact_id INTEGER,
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    data_json TEXT,
    cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (firm_id, id)
);
CREATE INDEX IF NOT EXISTS idx_cdoc_case ON cached_documents(firm_id, case_id);

CREATE TABLE IF NOT EXISTS staff_exclusions (
    firm_id VARCHAR(36) NOT NULL,
    staff_id INTEGER NOT NULL,
    staff_name TEXT,
    excluded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    reason TEXT,
    PRIMARY KEY (firm_id, staff_id)
);
"""


def ensure_cache_tables():
    """Create cache tables if they don't exist."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(CACHE_SCHEMA)
    logger.info("Cache tables ensured")


# ============================================================
# Sync Metadata
# ============================================================

def get_sync_status(firm_id: str, entity_type: str) -> Optional[Dict]:
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM sync_metadata WHERE firm_id = %s AND entity_type = %s",
            (firm_id, entity_type),
        )
        return dict(cur.fetchone()) if cur.fetchone() is not None else None


def update_sync_status(
    firm_id: str,
    entity_type: str,
    total_records: int,
    sync_duration: float,
    full_sync: bool = False,
    error: str = None,
):
    now = datetime.utcnow()
    with get_connection() as conn:
        cur = conn.cursor()
        if full_sync:
            cur.execute(
                """
                INSERT INTO sync_metadata
                    (firm_id, entity_type, last_full_sync, last_incremental_sync,
                     total_records, sync_duration_seconds, last_error)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (firm_id, entity_type) DO UPDATE SET
                    last_full_sync = EXCLUDED.last_full_sync,
                    last_incremental_sync = EXCLUDED.last_incremental_sync,
                    total_records = EXCLUDED.total_records,
                    sync_duration_seconds = EXCLUDED.sync_duration_seconds,
                    last_error = EXCLUDED.last_error
                """,
                (firm_id, entity_type, now, now, total_records, sync_duration, error),
            )
        else:
            cur.execute(
                """
                INSERT INTO sync_metadata
                    (firm_id, entity_type, last_incremental_sync,
                     total_records, sync_duration_seconds, last_error)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (firm_id, entity_type) DO UPDATE SET
                    last_incremental_sync = EXCLUDED.last_incremental_sync,
                    total_records = EXCLUDED.total_records,
                    sync_duration_seconds = EXCLUDED.sync_duration_seconds,
                    last_error = EXCLUDED.last_error
                """,
                (firm_id, entity_type, now, total_records, sync_duration, error),
            )


# ============================================================
# Cache Query Helpers
# ============================================================

# Maps entity type names to their cached table names
_ENTITY_TABLE_MAP = {
    'cases': 'cached_cases',
    'contacts': 'cached_contacts',
    'clients': 'cached_clients',
    'invoices': 'cached_invoices',
    'events': 'cached_events',
    'tasks': 'cached_tasks',
    'staff': 'cached_staff',
    'payments': 'cached_payments',
    'time_entries': 'cached_time_entries',
    'documents': 'cached_documents',
}


def get_cached_count(firm_id: str, entity_type: str) -> int:
    """Return the number of cached records for a given entity type."""
    table = _ENTITY_TABLE_MAP.get(entity_type)
    if not table:
        return 0
    try:
        with get_connection() as conn:
            cur = conn.cursor()
            cur.execute(f"SELECT COUNT(*) FROM {table} WHERE firm_id = %s", (firm_id,))
            row = cur.fetchone()
            return (row[0] if isinstance(row, tuple) else row['count']) if row else 0
    except Exception:
        return 0


def get_cached_updated_at(firm_id: str, entity_type: str) -> Dict[int, str]:
    """Return a dict mapping record ID → updated_at timestamp for change detection."""
    table = _ENTITY_TABLE_MAP.get(entity_type)
    if not table:
        return {}
    try:
        with get_connection() as conn:
            cur = conn.cursor()
            cur.execute(f"SELECT id, updated_at FROM {table} WHERE firm_id = %s", (firm_id,))
            result = {}
            for row in cur.fetchall():
                rid = row[0] if isinstance(row, tuple) else row['id']
                upd = row[1] if isinstance(row, tuple) else row['updated_at']
                result[rid] = str(upd) if upd else None
            return result
    except Exception:
        return {}


# ============================================================
# Batch Upsert Functions (use execute_values for performance)
# ============================================================

def batch_upsert_cases(firm_id: str, cases: List[Dict]):
    """Upsert a batch of cases. 10-50x faster than individual inserts."""
    if not cases:
        return
    rows = []
    for c in cases:
        rows.append((
            firm_id,
            c.get("id"),
            c.get("name"),
            c.get("case_number"),
            c.get("status"),
            c.get("case_type"),
            c.get("practice_area"),
            c.get("date_opened"),
            c.get("date_closed"),
            c.get("lead_attorney", {}).get("id") if isinstance(c.get("lead_attorney"), dict) else c.get("lead_attorney_id"),
            c.get("lead_attorney", {}).get("name") if isinstance(c.get("lead_attorney"), dict) else c.get("lead_attorney_name"),
            c.get("stage"),
            c.get("created_at"),
            c.get("updated_at"),
            json.dumps(c) if isinstance(c, dict) else c,
        ))

    sql = """
        INSERT INTO cached_cases
            (firm_id, id, name, case_number, status, case_type, practice_area,
             date_opened, date_closed, lead_attorney_id, lead_attorney_name,
             stage, created_at, updated_at, data_json)
        VALUES %s
        ON CONFLICT (firm_id, id) DO UPDATE SET
            name = EXCLUDED.name,
            case_number = EXCLUDED.case_number,
            status = EXCLUDED.status,
            case_type = EXCLUDED.case_type,
            practice_area = EXCLUDED.practice_area,
            date_opened = EXCLUDED.date_opened,
            date_closed = EXCLUDED.date_closed,
            lead_attorney_id = EXCLUDED.lead_attorney_id,
            lead_attorney_name = EXCLUDED.lead_attorney_name,
            stage = EXCLUDED.stage,
            updated_at = EXCLUDED.updated_at,
            data_json = EXCLUDED.data_json,
            cached_at = CURRENT_TIMESTAMP
    """
    with get_connection() as conn:
        cur = conn.cursor()
        execute_values(cur, sql, rows, page_size=500)
    logger.info("Upserted %d cases for firm %s", len(rows), firm_id)


def batch_upsert_contacts(firm_id: str, contacts: List[Dict]):
    if not contacts:
        return
    rows = []
    for c in contacts:
        rows.append((
            firm_id, c.get("id"), c.get("first_name"), c.get("last_name"),
            c.get("name"), c.get("email"), c.get("phone"),
            c.get("contact_type"), c.get("company"),
            c.get("created_at"), c.get("updated_at"), json.dumps(c),
        ))
    sql = """
        INSERT INTO cached_contacts
            (firm_id, id, first_name, last_name, name, email, phone,
             contact_type, company, created_at, updated_at, data_json)
        VALUES %s
        ON CONFLICT (firm_id, id) DO UPDATE SET
            first_name = EXCLUDED.first_name, last_name = EXCLUDED.last_name,
            name = EXCLUDED.name, email = EXCLUDED.email, phone = EXCLUDED.phone,
            contact_type = EXCLUDED.contact_type, company = EXCLUDED.company,
            updated_at = EXCLUDED.updated_at, data_json = EXCLUDED.data_json,
            cached_at = CURRENT_TIMESTAMP
    """
    with get_connection() as conn:
        cur = conn.cursor()
        execute_values(cur, sql, rows, page_size=500)
    logger.info("Upserted %d contacts for firm %s", len(rows), firm_id)


def batch_upsert_clients(firm_id: str, clients: List[Dict]):
    if not clients:
        return
    rows = []
    for cl in clients:
        address = cl.get('address', {}) or {}
        rows.append((
            firm_id, cl.get("id"), cl.get("first_name"), cl.get("last_name"),
            cl.get("email"), cl.get("cell_phone_number"),
            cl.get("work_phone_number"), cl.get("home_phone_number"),
            address.get("address1"), address.get("address2"),
            address.get("city"), address.get("state"), address.get("zip_code"),
            address.get("country"), cl.get("birthdate"), cl.get("archived", False),
            cl.get("created_at"), cl.get("updated_at"), json.dumps(cl),
        ))
    sql = """
        INSERT INTO cached_clients
            (firm_id, id, first_name, last_name, email, cell_phone, work_phone,
             home_phone, address1, address2, city, state, zip_code, country,
             birthdate, archived, created_at, updated_at, data_json)
        VALUES %s
        ON CONFLICT (firm_id, id) DO UPDATE SET
            first_name = EXCLUDED.first_name, last_name = EXCLUDED.last_name,
            email = EXCLUDED.email, cell_phone = EXCLUDED.cell_phone,
            work_phone = EXCLUDED.work_phone, home_phone = EXCLUDED.home_phone,
            address1 = EXCLUDED.address1, address2 = EXCLUDED.address2,
            city = EXCLUDED.city, state = EXCLUDED.state, zip_code = EXCLUDED.zip_code,
            country = EXCLUDED.country, birthdate = EXCLUDED.birthdate,
            archived = EXCLUDED.archived,
            updated_at = EXCLUDED.updated_at, data_json = EXCLUDED.data_json,
            cached_at = CURRENT_TIMESTAMP
    """
    with get_connection() as conn:
        cur = conn.cursor()
        execute_values(cur, sql, rows, page_size=500)
    logger.info("Upserted %d clients for firm %s", len(rows), firm_id)


def batch_upsert_invoices(firm_id: str, invoices: List[Dict]):
    if not invoices:
        return
    rows = []
    for inv in invoices:
        rows.append((
            firm_id, inv.get("id"), inv.get("invoice_number"),
            inv.get("case_id"), inv.get("contact_id"), inv.get("status"),
            inv.get("total_amount"), inv.get("paid_amount"), inv.get("balance_due"),
            inv.get("invoice_date"), inv.get("due_date"),
            inv.get("created_at"), inv.get("updated_at"), json.dumps(inv),
        ))
    sql = """
        INSERT INTO cached_invoices
            (firm_id, id, invoice_number, case_id, contact_id, status,
             total_amount, paid_amount, balance_due, invoice_date, due_date,
             created_at, updated_at, data_json)
        VALUES %s
        ON CONFLICT (firm_id, id) DO UPDATE SET
            invoice_number = EXCLUDED.invoice_number,
            case_id = EXCLUDED.case_id, contact_id = EXCLUDED.contact_id,
            status = EXCLUDED.status, total_amount = EXCLUDED.total_amount,
            paid_amount = EXCLUDED.paid_amount, balance_due = EXCLUDED.balance_due,
            invoice_date = EXCLUDED.invoice_date, due_date = EXCLUDED.due_date,
            updated_at = EXCLUDED.updated_at, data_json = EXCLUDED.data_json,
            cached_at = CURRENT_TIMESTAMP
    """
    with get_connection() as conn:
        cur = conn.cursor()
        execute_values(cur, sql, rows, page_size=500)
    logger.info("Upserted %d invoices for firm %s", len(rows), firm_id)


def batch_upsert_tasks(firm_id: str, tasks: List[Dict]):
    if not tasks:
        return
    rows = []
    for t in tasks:
        rows.append((
            firm_id, t.get("id"), t.get("name"), t.get("description"),
            t.get("due_date"), t.get("completed"), t.get("completed_at"),
            t.get("priority"), t.get("case_id"),
            t.get("assignee_id"), t.get("assignee_name"),
            t.get("created_at"), t.get("updated_at"), json.dumps(t),
        ))
    sql = """
        INSERT INTO cached_tasks
            (firm_id, id, name, description, due_date, completed, completed_at,
             priority, case_id, assignee_id, assignee_name,
             created_at, updated_at, data_json)
        VALUES %s
        ON CONFLICT (firm_id, id) DO UPDATE SET
            name = EXCLUDED.name, description = EXCLUDED.description,
            due_date = EXCLUDED.due_date, completed = EXCLUDED.completed,
            completed_at = EXCLUDED.completed_at, priority = EXCLUDED.priority,
            case_id = EXCLUDED.case_id, assignee_id = EXCLUDED.assignee_id,
            assignee_name = EXCLUDED.assignee_name,
            updated_at = EXCLUDED.updated_at, data_json = EXCLUDED.data_json,
            cached_at = CURRENT_TIMESTAMP
    """
    with get_connection() as conn:
        cur = conn.cursor()
        execute_values(cur, sql, rows, page_size=500)
    logger.info("Upserted %d tasks for firm %s", len(rows), firm_id)


def batch_upsert_events(firm_id: str, events: List[Dict]):
    if not events:
        return
    rows = []
    for e in events:
        rows.append((
            firm_id, e.get("id"), e.get("name"), e.get("description"),
            e.get("event_type"), e.get("start_at"), e.get("end_at"),
            e.get("all_day"), e.get("case_id"), e.get("location"),
            e.get("created_at"), e.get("updated_at"), json.dumps(e),
        ))
    sql = """
        INSERT INTO cached_events
            (firm_id, id, name, description, event_type, start_at, end_at,
             all_day, case_id, location, created_at, updated_at, data_json)
        VALUES %s
        ON CONFLICT (firm_id, id) DO UPDATE SET
            name = EXCLUDED.name, description = EXCLUDED.description,
            event_type = EXCLUDED.event_type, start_at = EXCLUDED.start_at,
            end_at = EXCLUDED.end_at, all_day = EXCLUDED.all_day,
            case_id = EXCLUDED.case_id, location = EXCLUDED.location,
            updated_at = EXCLUDED.updated_at, data_json = EXCLUDED.data_json,
            cached_at = CURRENT_TIMESTAMP
    """
    with get_connection() as conn:
        cur = conn.cursor()
        execute_values(cur, sql, rows, page_size=500)
    logger.info("Upserted %d events for firm %s", len(rows), firm_id)


def batch_upsert_staff(firm_id: str, staff: List[Dict]):
    if not staff:
        return
    rows = []
    for s in staff:
        rows.append((
            firm_id, s.get("id"), s.get("first_name"), s.get("last_name"),
            s.get("name"), s.get("email"), s.get("title"),
            s.get("staff_type"), s.get("active"), s.get("hourly_rate"),
            s.get("created_at"), s.get("updated_at"), json.dumps(s),
        ))
    sql = """
        INSERT INTO cached_staff
            (firm_id, id, first_name, last_name, name, email, title,
             staff_type, active, hourly_rate, created_at, updated_at, data_json)
        VALUES %s
        ON CONFLICT (firm_id, id) DO UPDATE SET
            first_name = EXCLUDED.first_name, last_name = EXCLUDED.last_name,
            name = EXCLUDED.name, email = EXCLUDED.email, title = EXCLUDED.title,
            staff_type = EXCLUDED.staff_type, active = EXCLUDED.active,
            hourly_rate = EXCLUDED.hourly_rate,
            updated_at = EXCLUDED.updated_at, data_json = EXCLUDED.data_json,
            cached_at = CURRENT_TIMESTAMP
    """
    with get_connection() as conn:
        cur = conn.cursor()
        execute_values(cur, sql, rows, page_size=500)
    logger.info("Upserted %d staff for firm %s", len(rows), firm_id)


def batch_upsert_payments(firm_id: str, payments: List[Dict]):
    if not payments:
        return
    rows = []
    for p in payments:
        rows.append((
            firm_id, p.get("id"), p.get("invoice_id"), p.get("amount"),
            p.get("payment_date"), p.get("payment_method"),
            p.get("created_at"), p.get("updated_at"), json.dumps(p),
        ))
    sql = """
        INSERT INTO cached_payments
            (firm_id, id, invoice_id, amount, payment_date, payment_method,
             created_at, updated_at, data_json)
        VALUES %s
        ON CONFLICT (firm_id, id) DO UPDATE SET
            invoice_id = EXCLUDED.invoice_id, amount = EXCLUDED.amount,
            payment_date = EXCLUDED.payment_date,
            payment_method = EXCLUDED.payment_method,
            updated_at = EXCLUDED.updated_at, data_json = EXCLUDED.data_json,
            cached_at = CURRENT_TIMESTAMP
    """
    with get_connection() as conn:
        cur = conn.cursor()
        execute_values(cur, sql, rows, page_size=500)
    logger.info("Upserted %d payments for firm %s", len(rows), firm_id)


def batch_upsert_time_entries(firm_id: str, entries: List[Dict]):
    if not entries:
        return
    rows = []
    for te in entries:
        rows.append((
            firm_id, te.get("id"), te.get("description"), te.get("entry_date"),
            te.get("hours"), te.get("rate"), te.get("billable"),
            te.get("flat_fee"), te.get("activity_name"),
            te.get("case_id"), te.get("staff_id"), te.get("staff_name"),
            te.get("created_at"), te.get("updated_at"), json.dumps(te),
        ))
    sql = """
        INSERT INTO cached_time_entries
            (firm_id, id, description, entry_date, hours, rate, billable,
             flat_fee, activity_name, case_id, staff_id, staff_name,
             created_at, updated_at, data_json)
        VALUES %s
        ON CONFLICT (firm_id, id) DO UPDATE SET
            description = EXCLUDED.description, entry_date = EXCLUDED.entry_date,
            hours = EXCLUDED.hours, rate = EXCLUDED.rate,
            billable = EXCLUDED.billable, flat_fee = EXCLUDED.flat_fee,
            activity_name = EXCLUDED.activity_name,
            case_id = EXCLUDED.case_id, staff_id = EXCLUDED.staff_id,
            staff_name = EXCLUDED.staff_name,
            updated_at = EXCLUDED.updated_at, data_json = EXCLUDED.data_json,
            cached_at = CURRENT_TIMESTAMP
    """
    with get_connection() as conn:
        cur = conn.cursor()
        execute_values(cur, sql, rows, page_size=500)
    logger.info("Upserted %d time entries for firm %s", len(rows), firm_id)


def batch_upsert_documents(firm_id: str, documents: List[Dict]):
    if not documents:
        return
    rows = []
    for d in documents:
        rows.append((
            firm_id, d.get("id"), d.get("name"), d.get("description"),
            d.get("content_type"), d.get("file_size"),
            d.get("case_id"), d.get("contact_id"),
            d.get("created_at"), d.get("updated_at"), json.dumps(d),
        ))
    sql = """
        INSERT INTO cached_documents
            (firm_id, id, name, description, content_type, file_size,
             case_id, contact_id, created_at, updated_at, data_json)
        VALUES %s
        ON CONFLICT (firm_id, id) DO UPDATE SET
            name = EXCLUDED.name, description = EXCLUDED.description,
            content_type = EXCLUDED.content_type, file_size = EXCLUDED.file_size,
            case_id = EXCLUDED.case_id, contact_id = EXCLUDED.contact_id,
            updated_at = EXCLUDED.updated_at, data_json = EXCLUDED.data_json,
            cached_at = CURRENT_TIMESTAMP
    """
    with get_connection() as conn:
        cur = conn.cursor()
        execute_values(cur, sql, rows, page_size=500)
    logger.info("Upserted %d documents for firm %s", len(rows), firm_id)


# ============================================================
# Query Helpers
# ============================================================

def get_cases(firm_id: str, status: str = None) -> List[Dict]:
    """Get cached cases for a firm, optionally filtered by status."""
    with get_connection() as conn:
        cur = conn.cursor()
        if status:
            cur.execute(
                "SELECT * FROM cached_cases WHERE firm_id = %s AND status = %s ORDER BY updated_at DESC",
                (firm_id, status),
            )
        else:
            cur.execute(
                "SELECT * FROM cached_cases WHERE firm_id = %s ORDER BY updated_at DESC",
                (firm_id,),
            )
        return [dict(r) for r in cur.fetchall()]


def get_invoices(firm_id: str, status: str = None) -> List[Dict]:
    with get_connection() as conn:
        cur = conn.cursor()
        if status:
            cur.execute(
                "SELECT * FROM cached_invoices WHERE firm_id = %s AND status = %s ORDER BY updated_at DESC",
                (firm_id, status),
            )
        else:
            cur.execute(
                "SELECT * FROM cached_invoices WHERE firm_id = %s ORDER BY updated_at DESC",
                (firm_id,),
            )
        return [dict(r) for r in cur.fetchall()]


def get_tasks(firm_id: str, completed: bool = None) -> List[Dict]:
    with get_connection() as conn:
        cur = conn.cursor()
        if completed is not None:
            cur.execute(
                "SELECT * FROM cached_tasks WHERE firm_id = %s AND completed = %s ORDER BY due_date",
                (firm_id, completed),
            )
        else:
            cur.execute(
                "SELECT * FROM cached_tasks WHERE firm_id = %s ORDER BY due_date",
                (firm_id,),
            )
        return [dict(r) for r in cur.fetchall()]


def get_staff(firm_id: str, active_only: bool = True) -> List[Dict]:
    with get_connection() as conn:
        cur = conn.cursor()
        if active_only:
            cur.execute(
                """SELECT s.* FROM cached_staff s
                   WHERE s.firm_id = %s AND s.active = TRUE
                     AND s.id NOT IN (SELECT staff_id FROM staff_exclusions WHERE firm_id = %s)
                   ORDER BY s.name""",
                (firm_id, firm_id),
            )
        else:
            cur.execute(
                """SELECT s.* FROM cached_staff s
                   WHERE s.firm_id = %s
                     AND s.id NOT IN (SELECT staff_id FROM staff_exclusions WHERE firm_id = %s)
                   ORDER BY s.name""",
                (firm_id, firm_id),
            )
        return [dict(r) for r in cur.fetchall()]


# ============================================================
# Staff Exclusions
# ============================================================

def get_excluded_staff_ids(firm_id: str) -> set:
    """Return set of staff IDs that should be skipped during sync."""
    _ensure_exclusions_table()
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT staff_id FROM staff_exclusions WHERE firm_id = %s",
            (firm_id,),
        )
        return {row[0] if isinstance(row, tuple) else row['staff_id'] for row in cur.fetchall()}


def _ensure_exclusions_table():
    """Create staff_exclusions table if it doesn't exist."""
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS staff_exclusions (
                firm_id VARCHAR(36) NOT NULL,
                staff_id INTEGER NOT NULL,
                staff_name TEXT,
                excluded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                reason TEXT,
                PRIMARY KEY (firm_id, staff_id)
            )
        """)


def exclude_staff(firm_id: str, staff_id: int, staff_name: str = None, reason: str = None):
    """Mark a staff member as excluded from sync. They won't be re-added."""
    _ensure_exclusions_table()
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO staff_exclusions (firm_id, staff_id, staff_name, reason)
               VALUES (%s, %s, %s, %s)
               ON CONFLICT (firm_id, staff_id) DO UPDATE SET
                   staff_name = EXCLUDED.staff_name,
                   reason = EXCLUDED.reason,
                   excluded_at = CURRENT_TIMESTAMP""",
            (firm_id, staff_id, staff_name, reason),
        )
    logger.info("Excluded staff %s (ID %d) for firm %s", staff_name, staff_id, firm_id)


def include_staff(firm_id: str, staff_id: int):
    """Remove a staff member from the exclusion list so they sync again."""
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM staff_exclusions WHERE firm_id = %s AND staff_id = %s",
            (firm_id, staff_id),
        )
    logger.info("Re-included staff ID %d for firm %s", staff_id, firm_id)


def get_excluded_staff(firm_id: str) -> List[Dict]:
    """List all excluded staff members."""
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM staff_exclusions WHERE firm_id = %s ORDER BY excluded_at",
            (firm_id,),
        )
        return [dict(r) for r in cur.fetchall()]


def get_contacts(firm_id: str) -> List[Dict]:
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM cached_contacts WHERE firm_id = %s ORDER BY name",
            (firm_id,),
        )
        return [dict(r) for r in cur.fetchall()]


def get_events(firm_id: str) -> List[Dict]:
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM cached_events WHERE firm_id = %s ORDER BY start_at DESC",
            (firm_id,),
        )
        return [dict(r) for r in cur.fetchall()]
