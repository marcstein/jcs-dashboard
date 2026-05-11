"""
Clio Manage API Cache — PostgreSQL Multi-Tenant

Cached data from Clio Manage API v4. All tables keyed by (firm_id, id).
Uses upsert logic: records are never deleted.

Separate from MyCase cache (db/cache.py) — each PMS keeps its own
table namespace to avoid schema conflicts.

Tables:
    clio_sync_metadata, clio_cached_matters, clio_cached_contacts,
    clio_cached_bills, clio_cached_tasks, clio_cached_users,
    clio_cached_activities, clio_cached_calendar_entries,
    clio_cached_payments, clio_cached_trust_line_items,
    clio_cached_practice_areas, clio_cached_matter_stages
"""
import json
import logging
from datetime import datetime
from typing import List, Dict, Optional

from psycopg2.extras import execute_values

from db.connection import get_connection

logger = logging.getLogger(__name__)


# ============================================================
# Schema
# ============================================================

CLIO_CACHE_SCHEMA = """
CREATE TABLE IF NOT EXISTS clio_sync_metadata (
    firm_id VARCHAR(36) NOT NULL,
    entity_type TEXT NOT NULL,
    last_full_sync TIMESTAMP,
    last_incremental_sync TIMESTAMP,
    total_records INTEGER DEFAULT 0,
    sync_duration_seconds REAL,
    last_error TEXT,
    PRIMARY KEY (firm_id, entity_type)
);

-- Matters (= MyCase Cases)
CREATE TABLE IF NOT EXISTS clio_cached_matters (
    firm_id VARCHAR(36) NOT NULL,
    id INTEGER NOT NULL,
    display_number TEXT,
    custom_number TEXT,
    description TEXT,
    status TEXT,
    open_date DATE,
    close_date DATE,
    pending_date DATE,
    practice_area_id INTEGER,
    practice_area_name TEXT,
    client_id INTEGER,
    client_name TEXT,
    responsible_attorney_id INTEGER,
    responsible_attorney_name TEXT,
    originating_attorney_id INTEGER,
    originating_attorney_name TEXT,
    matter_stage_id INTEGER,
    matter_stage_name TEXT,
    group_id INTEGER,
    group_name TEXT,
    statute_of_limitations_date DATE,
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    data_json TEXT,
    cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (firm_id, id)
);
CREATE INDEX IF NOT EXISTS idx_clio_mat_updated ON clio_cached_matters(firm_id, updated_at);
CREATE INDEX IF NOT EXISTS idx_clio_mat_status ON clio_cached_matters(firm_id, status);
CREATE INDEX IF NOT EXISTS idx_clio_mat_client ON clio_cached_matters(firm_id, client_id);
CREATE INDEX IF NOT EXISTS idx_clio_mat_attorney ON clio_cached_matters(firm_id, responsible_attorney_id);

-- Contacts (persons + companies)
CREATE TABLE IF NOT EXISTS clio_cached_contacts (
    firm_id VARCHAR(36) NOT NULL,
    id INTEGER NOT NULL,
    name TEXT,
    first_name TEXT,
    last_name TEXT,
    middle_name TEXT,
    type TEXT,
    title TEXT,
    company TEXT,
    is_client BOOLEAN,
    primary_email TEXT,
    primary_phone TEXT,
    emails_json TEXT,
    phones_json TEXT,
    addresses_json TEXT,
    custom_fields_json TEXT,
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    data_json TEXT,
    cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (firm_id, id)
);
CREATE INDEX IF NOT EXISTS idx_clio_con_updated ON clio_cached_contacts(firm_id, updated_at);
CREATE INDEX IF NOT EXISTS idx_clio_con_client ON clio_cached_contacts(firm_id, is_client);
CREATE INDEX IF NOT EXISTS idx_clio_con_email ON clio_cached_contacts(firm_id, primary_email);

-- Bills (= MyCase Invoices)
CREATE TABLE IF NOT EXISTS clio_cached_bills (
    firm_id VARCHAR(36) NOT NULL,
    id INTEGER NOT NULL,
    number TEXT,
    subject TEXT,
    purchase_order TEXT,
    type TEXT,
    status TEXT,
    issued_at DATE,
    due_at DATE,
    start_at DATE,
    end_at DATE,
    total REAL,
    paid REAL,
    pending REAL,
    due REAL,
    discount REAL,
    tax_rate REAL,
    matter_id INTEGER,
    matter_display_number TEXT,
    client_id INTEGER,
    client_name TEXT,
    responsible_attorney_id INTEGER,
    responsible_attorney_name TEXT,
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    data_json TEXT,
    cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (firm_id, id)
);
CREATE INDEX IF NOT EXISTS idx_clio_bill_updated ON clio_cached_bills(firm_id, updated_at);
CREATE INDEX IF NOT EXISTS idx_clio_bill_status ON clio_cached_bills(firm_id, status);
CREATE INDEX IF NOT EXISTS idx_clio_bill_matter ON clio_cached_bills(firm_id, matter_id);
CREATE INDEX IF NOT EXISTS idx_clio_bill_due ON clio_cached_bills(firm_id, due_at);

-- Tasks
CREATE TABLE IF NOT EXISTS clio_cached_tasks (
    firm_id VARCHAR(36) NOT NULL,
    id INTEGER NOT NULL,
    name TEXT,
    description TEXT,
    priority TEXT,
    status TEXT,
    due_at DATE,
    completed_at TIMESTAMP,
    is_private BOOLEAN,
    is_statute_of_limitations BOOLEAN,
    assignee_id INTEGER,
    assignee_name TEXT,
    matter_id INTEGER,
    matter_display_number TEXT,
    task_type_id INTEGER,
    task_type_name TEXT,
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    data_json TEXT,
    cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (firm_id, id)
);
CREATE INDEX IF NOT EXISTS idx_clio_task_updated ON clio_cached_tasks(firm_id, updated_at);
CREATE INDEX IF NOT EXISTS idx_clio_task_due ON clio_cached_tasks(firm_id, due_at);
CREATE INDEX IF NOT EXISTS idx_clio_task_status ON clio_cached_tasks(firm_id, status);
CREATE INDEX IF NOT EXISTS idx_clio_task_matter ON clio_cached_tasks(firm_id, matter_id);

-- Users (= MyCase Staff)
CREATE TABLE IF NOT EXISTS clio_cached_users (
    firm_id VARCHAR(36) NOT NULL,
    id INTEGER NOT NULL,
    name TEXT,
    first_name TEXT,
    last_name TEXT,
    email TEXT,
    phone_number TEXT,
    type TEXT,
    enabled BOOLEAN,
    subscription_type TEXT,
    rate REAL,
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    data_json TEXT,
    cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (firm_id, id)
);
CREATE INDEX IF NOT EXISTS idx_clio_user_enabled ON clio_cached_users(firm_id, enabled);

-- Activities (Time Entries + Expenses)
CREATE TABLE IF NOT EXISTS clio_cached_activities (
    firm_id VARCHAR(36) NOT NULL,
    id INTEGER NOT NULL,
    type TEXT,
    date DATE,
    quantity REAL,
    price REAL,
    total REAL,
    note TEXT,
    flat_rate BOOLEAN,
    billed BOOLEAN,
    on_bill BOOLEAN,
    matter_id INTEGER,
    matter_display_number TEXT,
    user_id INTEGER,
    user_name TEXT,
    activity_description_id INTEGER,
    activity_description_name TEXT,
    expense_category_id INTEGER,
    expense_category_name TEXT,
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    data_json TEXT,
    cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (firm_id, id)
);
CREATE INDEX IF NOT EXISTS idx_clio_act_date ON clio_cached_activities(firm_id, date);
CREATE INDEX IF NOT EXISTS idx_clio_act_matter ON clio_cached_activities(firm_id, matter_id);
CREATE INDEX IF NOT EXISTS idx_clio_act_user ON clio_cached_activities(firm_id, user_id);

-- Calendar Entries (= MyCase Events)
CREATE TABLE IF NOT EXISTS clio_cached_calendar_entries (
    firm_id VARCHAR(36) NOT NULL,
    id INTEGER NOT NULL,
    summary TEXT,
    description TEXT,
    location TEXT,
    start_at TEXT,
    end_at TEXT,
    all_day BOOLEAN,
    recurrence_rule TEXT,
    matter_id INTEGER,
    matter_display_number TEXT,
    calendar_owner_id INTEGER,
    calendar_owner_name TEXT,
    attendees_json TEXT,
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    data_json TEXT,
    cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (firm_id, id)
);
CREATE INDEX IF NOT EXISTS idx_clio_cal_updated ON clio_cached_calendar_entries(firm_id, updated_at);
CREATE INDEX IF NOT EXISTS idx_clio_cal_start ON clio_cached_calendar_entries(firm_id, start_at);
CREATE INDEX IF NOT EXISTS idx_clio_cal_matter ON clio_cached_calendar_entries(firm_id, matter_id);

-- Payments
CREATE TABLE IF NOT EXISTS clio_cached_payments (
    firm_id VARCHAR(36) NOT NULL,
    id INTEGER NOT NULL,
    date DATE,
    amount REAL,
    apply_interest BOOLEAN,
    contact_id INTEGER,
    contact_name TEXT,
    allocation_json TEXT,
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    data_json TEXT,
    cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (firm_id, id)
);
CREATE INDEX IF NOT EXISTS idx_clio_pay_date ON clio_cached_payments(firm_id, date);
CREATE INDEX IF NOT EXISTS idx_clio_pay_contact ON clio_cached_payments(firm_id, contact_id);

-- Trust Line Items (IOLTA)
CREATE TABLE IF NOT EXISTS clio_cached_trust_line_items (
    firm_id VARCHAR(36) NOT NULL,
    id INTEGER NOT NULL,
    date DATE,
    description TEXT,
    total REAL,
    type TEXT,
    matter_id INTEGER,
    matter_display_number TEXT,
    contact_id INTEGER,
    contact_name TEXT,
    bank_account_id INTEGER,
    bank_account_name TEXT,
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    data_json TEXT,
    cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (firm_id, id)
);
CREATE INDEX IF NOT EXISTS idx_clio_trust_matter ON clio_cached_trust_line_items(firm_id, matter_id);
CREATE INDEX IF NOT EXISTS idx_clio_trust_date ON clio_cached_trust_line_items(firm_id, date);

-- Practice Areas (reference data)
CREATE TABLE IF NOT EXISTS clio_cached_practice_areas (
    firm_id VARCHAR(36) NOT NULL,
    id INTEGER NOT NULL,
    name TEXT,
    code TEXT,
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    data_json TEXT,
    cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (firm_id, id)
);

-- Matter Stages (reference data)
CREATE TABLE IF NOT EXISTS clio_cached_matter_stages (
    firm_id VARCHAR(36) NOT NULL,
    id INTEGER NOT NULL,
    name TEXT,
    "order" INTEGER,
    data_json TEXT,
    cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (firm_id, id)
);
"""


def ensure_clio_cache_tables():
    """Create Clio cache tables if they don't exist."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(CLIO_CACHE_SCHEMA)
    logger.info("Clio cache tables ensured")


# ============================================================
# Sync Metadata
# ============================================================

def get_clio_sync_status(firm_id: str, entity_type: str) -> Optional[Dict]:
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM clio_sync_metadata WHERE firm_id = %s AND entity_type = %s",
            (firm_id, entity_type),
        )
        row = cur.fetchone()
        return dict(row) if row is not None else None


def update_clio_sync_status(
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
            cur.execute("""
                INSERT INTO clio_sync_metadata
                    (firm_id, entity_type, last_full_sync, last_incremental_sync,
                     total_records, sync_duration_seconds, last_error)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (firm_id, entity_type) DO UPDATE SET
                    last_full_sync = EXCLUDED.last_full_sync,
                    last_incremental_sync = EXCLUDED.last_incremental_sync,
                    total_records = EXCLUDED.total_records,
                    sync_duration_seconds = EXCLUDED.sync_duration_seconds,
                    last_error = EXCLUDED.last_error
            """, (firm_id, entity_type, now, now, total_records, sync_duration, error))
        else:
            cur.execute("""
                INSERT INTO clio_sync_metadata
                    (firm_id, entity_type, last_incremental_sync,
                     total_records, sync_duration_seconds, last_error)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (firm_id, entity_type) DO UPDATE SET
                    last_incremental_sync = EXCLUDED.last_incremental_sync,
                    total_records = EXCLUDED.total_records,
                    sync_duration_seconds = EXCLUDED.sync_duration_seconds,
                    last_error = EXCLUDED.last_error
            """, (firm_id, entity_type, now, total_records, sync_duration, error))


# ============================================================
# Entity Table Map
# ============================================================

_CLIO_ENTITY_TABLE_MAP = {
    'matters': 'clio_cached_matters',
    'contacts': 'clio_cached_contacts',
    'bills': 'clio_cached_bills',
    'tasks': 'clio_cached_tasks',
    'users': 'clio_cached_users',
    'activities': 'clio_cached_activities',
    'calendar_entries': 'clio_cached_calendar_entries',
    'payments': 'clio_cached_payments',
    'trust_line_items': 'clio_cached_trust_line_items',
    'practice_areas': 'clio_cached_practice_areas',
    'matter_stages': 'clio_cached_matter_stages',
}


def get_clio_cached_count(firm_id: str, entity_type: str) -> int:
    """Return the number of cached Clio records for a given entity type."""
    table = _CLIO_ENTITY_TABLE_MAP.get(entity_type)
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


# ============================================================
# Helpers — extract nested Clio objects
# ============================================================

def _nested(obj: dict, key: str, field: str = "id"):
    """Safely extract a field from a nested Clio object."""
    nested = obj.get(key)
    if isinstance(nested, dict):
        return nested.get(field)
    return None


def _nested_name(obj: dict, key: str) -> str:
    """Extract .name from a nested Clio object, or None."""
    return _nested(obj, key, "name")


def _nested_id(obj: dict, key: str) -> int:
    """Extract .id from a nested Clio object, or None."""
    return _nested(obj, key, "id")


# ============================================================
# Batch Upsert Functions
# ============================================================

def batch_upsert_matters(firm_id: str, matters: List[Dict]):
    """Upsert a batch of Clio matters."""
    if not matters:
        return
    rows = []
    for m in matters:
        sol = _nested(m, "statute_of_limitations", "due_at")
        rows.append((
            firm_id,
            m.get("id"),
            m.get("display_number"),
            m.get("custom_number"),
            m.get("description"),
            m.get("status"),
            m.get("open_date"),
            m.get("close_date"),
            m.get("pending_date"),
            _nested_id(m, "practice_area"),
            _nested_name(m, "practice_area"),
            _nested_id(m, "client"),
            _nested_name(m, "client"),
            _nested_id(m, "responsible_attorney"),
            _nested_name(m, "responsible_attorney"),
            _nested_id(m, "originating_attorney"),
            _nested_name(m, "originating_attorney"),
            _nested_id(m, "matter_stage"),
            _nested_name(m, "matter_stage"),
            _nested_id(m, "group"),
            _nested_name(m, "group"),
            sol,
            m.get("created_at"),
            m.get("updated_at"),
            json.dumps(m),
        ))

    sql = """
        INSERT INTO clio_cached_matters
            (firm_id, id, display_number, custom_number, description, status,
             open_date, close_date, pending_date,
             practice_area_id, practice_area_name,
             client_id, client_name,
             responsible_attorney_id, responsible_attorney_name,
             originating_attorney_id, originating_attorney_name,
             matter_stage_id, matter_stage_name,
             group_id, group_name,
             statute_of_limitations_date,
             created_at, updated_at, data_json)
        VALUES %s
        ON CONFLICT (firm_id, id) DO UPDATE SET
            display_number = EXCLUDED.display_number,
            custom_number = EXCLUDED.custom_number,
            description = EXCLUDED.description,
            status = EXCLUDED.status,
            open_date = EXCLUDED.open_date,
            close_date = EXCLUDED.close_date,
            pending_date = EXCLUDED.pending_date,
            practice_area_id = EXCLUDED.practice_area_id,
            practice_area_name = EXCLUDED.practice_area_name,
            client_id = EXCLUDED.client_id,
            client_name = EXCLUDED.client_name,
            responsible_attorney_id = EXCLUDED.responsible_attorney_id,
            responsible_attorney_name = EXCLUDED.responsible_attorney_name,
            originating_attorney_id = EXCLUDED.originating_attorney_id,
            originating_attorney_name = EXCLUDED.originating_attorney_name,
            matter_stage_id = EXCLUDED.matter_stage_id,
            matter_stage_name = EXCLUDED.matter_stage_name,
            group_id = EXCLUDED.group_id,
            group_name = EXCLUDED.group_name,
            statute_of_limitations_date = EXCLUDED.statute_of_limitations_date,
            updated_at = EXCLUDED.updated_at,
            data_json = EXCLUDED.data_json,
            cached_at = CURRENT_TIMESTAMP
    """
    with get_connection() as conn:
        cur = conn.cursor()
        execute_values(cur, sql, rows, page_size=500)
    logger.info("Upserted %d Clio matters for firm %s", len(rows), firm_id)


def batch_upsert_contacts(firm_id: str, contacts: List[Dict]):
    """Upsert a batch of Clio contacts."""
    if not contacts:
        return
    rows = []
    for c in contacts:
        # Extract primary email/phone from nested objects
        primary_email = None
        pe = c.get("primary_email_address")
        if isinstance(pe, dict):
            primary_email = pe.get("address")

        primary_phone = None
        pp = c.get("primary_phone_number")
        if isinstance(pp, dict):
            primary_phone = pp.get("number")

        # Serialize nested arrays
        emails = c.get("email_addresses")
        phones = c.get("phone_numbers")
        addresses = c.get("addresses")
        custom_fields = c.get("custom_field_values")

        rows.append((
            firm_id,
            c.get("id"),
            c.get("name"),
            c.get("first_name"),
            c.get("last_name"),
            c.get("middle_name"),
            c.get("type"),
            c.get("title"),
            c.get("company"),
            c.get("is_client"),
            primary_email,
            primary_phone,
            json.dumps(emails) if emails else None,
            json.dumps(phones) if phones else None,
            json.dumps(addresses) if addresses else None,
            json.dumps(custom_fields) if custom_fields else None,
            c.get("created_at"),
            c.get("updated_at"),
            json.dumps(c),
        ))

    sql = """
        INSERT INTO clio_cached_contacts
            (firm_id, id, name, first_name, last_name, middle_name,
             type, title, company, is_client,
             primary_email, primary_phone,
             emails_json, phones_json, addresses_json, custom_fields_json,
             created_at, updated_at, data_json)
        VALUES %s
        ON CONFLICT (firm_id, id) DO UPDATE SET
            name = EXCLUDED.name,
            first_name = EXCLUDED.first_name,
            last_name = EXCLUDED.last_name,
            middle_name = EXCLUDED.middle_name,
            type = EXCLUDED.type,
            title = EXCLUDED.title,
            company = EXCLUDED.company,
            is_client = EXCLUDED.is_client,
            primary_email = EXCLUDED.primary_email,
            primary_phone = EXCLUDED.primary_phone,
            emails_json = EXCLUDED.emails_json,
            phones_json = EXCLUDED.phones_json,
            addresses_json = EXCLUDED.addresses_json,
            custom_fields_json = EXCLUDED.custom_fields_json,
            updated_at = EXCLUDED.updated_at,
            data_json = EXCLUDED.data_json,
            cached_at = CURRENT_TIMESTAMP
    """
    with get_connection() as conn:
        cur = conn.cursor()
        execute_values(cur, sql, rows, page_size=500)
    logger.info("Upserted %d Clio contacts for firm %s", len(rows), firm_id)


def batch_upsert_bills(firm_id: str, bills: List[Dict]):
    """Upsert a batch of Clio bills (invoices)."""
    if not bills:
        return
    rows = []
    for b in bills:
        rows.append((
            firm_id,
            b.get("id"),
            b.get("number"),
            b.get("subject"),
            b.get("purchase_order"),
            b.get("type"),
            b.get("status"),
            b.get("issued_at"),
            b.get("due_at"),
            b.get("start_at"),
            b.get("end_at"),
            b.get("total"),
            b.get("paid"),
            b.get("pending"),
            b.get("due"),
            b.get("discount"),
            b.get("tax_rate"),
            _nested_id(b, "matter"),
            _nested(b, "matter", "display_number"),
            _nested_id(b, "client"),
            _nested_name(b, "client"),
            _nested_id(b, "responsible_attorney"),
            _nested_name(b, "responsible_attorney"),
            b.get("created_at"),
            b.get("updated_at"),
            json.dumps(b),
        ))

    sql = """
        INSERT INTO clio_cached_bills
            (firm_id, id, number, subject, purchase_order, type, status,
             issued_at, due_at, start_at, end_at,
             total, paid, pending, due, discount, tax_rate,
             matter_id, matter_display_number,
             client_id, client_name,
             responsible_attorney_id, responsible_attorney_name,
             created_at, updated_at, data_json)
        VALUES %s
        ON CONFLICT (firm_id, id) DO UPDATE SET
            number = EXCLUDED.number,
            subject = EXCLUDED.subject,
            purchase_order = EXCLUDED.purchase_order,
            type = EXCLUDED.type,
            status = EXCLUDED.status,
            issued_at = EXCLUDED.issued_at,
            due_at = EXCLUDED.due_at,
            start_at = EXCLUDED.start_at,
            end_at = EXCLUDED.end_at,
            total = EXCLUDED.total,
            paid = EXCLUDED.paid,
            pending = EXCLUDED.pending,
            due = EXCLUDED.due,
            discount = EXCLUDED.discount,
            tax_rate = EXCLUDED.tax_rate,
            matter_id = EXCLUDED.matter_id,
            matter_display_number = EXCLUDED.matter_display_number,
            client_id = EXCLUDED.client_id,
            client_name = EXCLUDED.client_name,
            responsible_attorney_id = EXCLUDED.responsible_attorney_id,
            responsible_attorney_name = EXCLUDED.responsible_attorney_name,
            updated_at = EXCLUDED.updated_at,
            data_json = EXCLUDED.data_json,
            cached_at = CURRENT_TIMESTAMP
    """
    with get_connection() as conn:
        cur = conn.cursor()
        execute_values(cur, sql, rows, page_size=500)
    logger.info("Upserted %d Clio bills for firm %s", len(rows), firm_id)


def batch_upsert_tasks(firm_id: str, tasks: List[Dict]):
    """Upsert a batch of Clio tasks."""
    if not tasks:
        return
    rows = []
    for t in tasks:
        rows.append((
            firm_id,
            t.get("id"),
            t.get("name"),
            t.get("description"),
            t.get("priority"),
            t.get("status"),
            t.get("due_at"),
            t.get("completed_at"),
            t.get("is_private"),
            t.get("is_statute_of_limitations"),
            _nested_id(t, "assignee"),
            _nested_name(t, "assignee"),
            _nested_id(t, "matter"),
            _nested(t, "matter", "display_number"),
            _nested_id(t, "task_type"),
            _nested_name(t, "task_type"),
            t.get("created_at"),
            t.get("updated_at"),
            json.dumps(t),
        ))

    sql = """
        INSERT INTO clio_cached_tasks
            (firm_id, id, name, description, priority, status,
             due_at, completed_at, is_private, is_statute_of_limitations,
             assignee_id, assignee_name,
             matter_id, matter_display_number,
             task_type_id, task_type_name,
             created_at, updated_at, data_json)
        VALUES %s
        ON CONFLICT (firm_id, id) DO UPDATE SET
            name = EXCLUDED.name,
            description = EXCLUDED.description,
            priority = EXCLUDED.priority,
            status = EXCLUDED.status,
            due_at = EXCLUDED.due_at,
            completed_at = EXCLUDED.completed_at,
            is_private = EXCLUDED.is_private,
            is_statute_of_limitations = EXCLUDED.is_statute_of_limitations,
            assignee_id = EXCLUDED.assignee_id,
            assignee_name = EXCLUDED.assignee_name,
            matter_id = EXCLUDED.matter_id,
            matter_display_number = EXCLUDED.matter_display_number,
            task_type_id = EXCLUDED.task_type_id,
            task_type_name = EXCLUDED.task_type_name,
            updated_at = EXCLUDED.updated_at,
            data_json = EXCLUDED.data_json,
            cached_at = CURRENT_TIMESTAMP
    """
    with get_connection() as conn:
        cur = conn.cursor()
        execute_values(cur, sql, rows, page_size=500)
    logger.info("Upserted %d Clio tasks for firm %s", len(rows), firm_id)


def batch_upsert_users(firm_id: str, users: List[Dict]):
    """Upsert a batch of Clio users (staff)."""
    if not users:
        return
    rows = []
    for u in users:
        name = u.get("name")
        if not name and (u.get("first_name") or u.get("last_name")):
            name = f"{u.get('first_name', '')} {u.get('last_name', '')}".strip()
        rows.append((
            firm_id,
            u.get("id"),
            name,
            u.get("first_name"),
            u.get("last_name"),
            u.get("email"),
            u.get("phone_number"),
            u.get("type"),
            u.get("enabled"),
            u.get("subscription_type"),
            u.get("rate"),
            u.get("created_at"),
            u.get("updated_at"),
            json.dumps(u),
        ))

    sql = """
        INSERT INTO clio_cached_users
            (firm_id, id, name, first_name, last_name, email,
             phone_number, type, enabled, subscription_type, rate,
             created_at, updated_at, data_json)
        VALUES %s
        ON CONFLICT (firm_id, id) DO UPDATE SET
            name = EXCLUDED.name,
            first_name = EXCLUDED.first_name,
            last_name = EXCLUDED.last_name,
            email = EXCLUDED.email,
            phone_number = EXCLUDED.phone_number,
            type = EXCLUDED.type,
            enabled = EXCLUDED.enabled,
            subscription_type = EXCLUDED.subscription_type,
            rate = EXCLUDED.rate,
            updated_at = EXCLUDED.updated_at,
            data_json = EXCLUDED.data_json,
            cached_at = CURRENT_TIMESTAMP
    """
    with get_connection() as conn:
        cur = conn.cursor()
        execute_values(cur, sql, rows, page_size=500)
    logger.info("Upserted %d Clio users for firm %s", len(rows), firm_id)


def batch_upsert_activities(firm_id: str, activities: List[Dict]):
    """Upsert a batch of Clio activities (time entries + expenses)."""
    if not activities:
        return
    rows = []
    for a in activities:
        rows.append((
            firm_id,
            a.get("id"),
            a.get("type"),
            a.get("date"),
            a.get("quantity"),
            a.get("price"),
            a.get("total"),
            a.get("note"),
            a.get("flat_rate"),
            a.get("billed"),
            a.get("on_bill"),
            _nested_id(a, "matter"),
            _nested(a, "matter", "display_number"),
            _nested_id(a, "user"),
            _nested_name(a, "user"),
            _nested_id(a, "activity_description"),
            _nested_name(a, "activity_description"),
            _nested_id(a, "expense_category"),
            _nested_name(a, "expense_category"),
            a.get("created_at"),
            a.get("updated_at"),
            json.dumps(a),
        ))

    sql = """
        INSERT INTO clio_cached_activities
            (firm_id, id, type, date, quantity, price, total, note,
             flat_rate, billed, on_bill,
             matter_id, matter_display_number,
             user_id, user_name,
             activity_description_id, activity_description_name,
             expense_category_id, expense_category_name,
             created_at, updated_at, data_json)
        VALUES %s
        ON CONFLICT (firm_id, id) DO UPDATE SET
            type = EXCLUDED.type,
            date = EXCLUDED.date,
            quantity = EXCLUDED.quantity,
            price = EXCLUDED.price,
            total = EXCLUDED.total,
            note = EXCLUDED.note,
            flat_rate = EXCLUDED.flat_rate,
            billed = EXCLUDED.billed,
            on_bill = EXCLUDED.on_bill,
            matter_id = EXCLUDED.matter_id,
            matter_display_number = EXCLUDED.matter_display_number,
            user_id = EXCLUDED.user_id,
            user_name = EXCLUDED.user_name,
            activity_description_id = EXCLUDED.activity_description_id,
            activity_description_name = EXCLUDED.activity_description_name,
            expense_category_id = EXCLUDED.expense_category_id,
            expense_category_name = EXCLUDED.expense_category_name,
            updated_at = EXCLUDED.updated_at,
            data_json = EXCLUDED.data_json,
            cached_at = CURRENT_TIMESTAMP
    """
    with get_connection() as conn:
        cur = conn.cursor()
        execute_values(cur, sql, rows, page_size=500)
    logger.info("Upserted %d Clio activities for firm %s", len(rows), firm_id)


def batch_upsert_calendar_entries(firm_id: str, entries: List[Dict]):
    """Upsert a batch of Clio calendar entries (events)."""
    if not entries:
        return
    rows = []
    for e in entries:
        attendees = e.get("attendees")
        rows.append((
            firm_id,
            e.get("id"),
            e.get("summary"),
            e.get("description"),
            e.get("location"),
            e.get("start_at"),
            e.get("end_at"),
            e.get("all_day"),
            e.get("recurrence_rule"),
            _nested_id(e, "matter"),
            _nested(e, "matter", "display_number"),
            _nested_id(e, "calendar_owner"),
            _nested_name(e, "calendar_owner"),
            json.dumps(attendees) if attendees else None,
            e.get("created_at"),
            e.get("updated_at"),
            json.dumps(e),
        ))

    sql = """
        INSERT INTO clio_cached_calendar_entries
            (firm_id, id, summary, description, location,
             start_at, end_at, all_day, recurrence_rule,
             matter_id, matter_display_number,
             calendar_owner_id, calendar_owner_name,
             attendees_json,
             created_at, updated_at, data_json)
        VALUES %s
        ON CONFLICT (firm_id, id) DO UPDATE SET
            summary = EXCLUDED.summary,
            description = EXCLUDED.description,
            location = EXCLUDED.location,
            start_at = EXCLUDED.start_at,
            end_at = EXCLUDED.end_at,
            all_day = EXCLUDED.all_day,
            recurrence_rule = EXCLUDED.recurrence_rule,
            matter_id = EXCLUDED.matter_id,
            matter_display_number = EXCLUDED.matter_display_number,
            calendar_owner_id = EXCLUDED.calendar_owner_id,
            calendar_owner_name = EXCLUDED.calendar_owner_name,
            attendees_json = EXCLUDED.attendees_json,
            updated_at = EXCLUDED.updated_at,
            data_json = EXCLUDED.data_json,
            cached_at = CURRENT_TIMESTAMP
    """
    with get_connection() as conn:
        cur = conn.cursor()
        execute_values(cur, sql, rows, page_size=500)
    logger.info("Upserted %d Clio calendar entries for firm %s", len(rows), firm_id)


def batch_upsert_payments(firm_id: str, payments: List[Dict]):
    """Upsert a batch of Clio payments."""
    if not payments:
        return
    rows = []
    for p in payments:
        allocation = p.get("allocation")
        rows.append((
            firm_id,
            p.get("id"),
            p.get("date"),
            p.get("amount"),
            p.get("apply_interest"),
            _nested_id(p, "contact"),
            _nested_name(p, "contact"),
            json.dumps(allocation) if allocation else None,
            p.get("created_at"),
            p.get("updated_at"),
            json.dumps(p),
        ))

    sql = """
        INSERT INTO clio_cached_payments
            (firm_id, id, date, amount, apply_interest,
             contact_id, contact_name, allocation_json,
             created_at, updated_at, data_json)
        VALUES %s
        ON CONFLICT (firm_id, id) DO UPDATE SET
            date = EXCLUDED.date,
            amount = EXCLUDED.amount,
            apply_interest = EXCLUDED.apply_interest,
            contact_id = EXCLUDED.contact_id,
            contact_name = EXCLUDED.contact_name,
            allocation_json = EXCLUDED.allocation_json,
            updated_at = EXCLUDED.updated_at,
            data_json = EXCLUDED.data_json,
            cached_at = CURRENT_TIMESTAMP
    """
    with get_connection() as conn:
        cur = conn.cursor()
        execute_values(cur, sql, rows, page_size=500)
    logger.info("Upserted %d Clio payments for firm %s", len(rows), firm_id)


def batch_upsert_trust_line_items(firm_id: str, items: List[Dict]):
    """Upsert a batch of Clio trust line items."""
    if not items:
        return
    rows = []
    for t in items:
        rows.append((
            firm_id,
            t.get("id"),
            t.get("date"),
            t.get("description"),
            t.get("total"),
            t.get("type"),
            _nested_id(t, "matter"),
            _nested(t, "matter", "display_number"),
            _nested_id(t, "contact"),
            _nested_name(t, "contact"),
            _nested_id(t, "bank_account"),
            _nested_name(t, "bank_account"),
            t.get("created_at"),
            t.get("updated_at"),
            json.dumps(t),
        ))

    sql = """
        INSERT INTO clio_cached_trust_line_items
            (firm_id, id, date, description, total, type,
             matter_id, matter_display_number,
             contact_id, contact_name,
             bank_account_id, bank_account_name,
             created_at, updated_at, data_json)
        VALUES %s
        ON CONFLICT (firm_id, id) DO UPDATE SET
            date = EXCLUDED.date,
            description = EXCLUDED.description,
            total = EXCLUDED.total,
            type = EXCLUDED.type,
            matter_id = EXCLUDED.matter_id,
            matter_display_number = EXCLUDED.matter_display_number,
            contact_id = EXCLUDED.contact_id,
            contact_name = EXCLUDED.contact_name,
            bank_account_id = EXCLUDED.bank_account_id,
            bank_account_name = EXCLUDED.bank_account_name,
            updated_at = EXCLUDED.updated_at,
            data_json = EXCLUDED.data_json,
            cached_at = CURRENT_TIMESTAMP
    """
    with get_connection() as conn:
        cur = conn.cursor()
        execute_values(cur, sql, rows, page_size=500)
    logger.info("Upserted %d Clio trust line items for firm %s", len(rows), firm_id)


def batch_upsert_practice_areas(firm_id: str, areas: List[Dict]):
    """Upsert Clio practice areas (reference data)."""
    if not areas:
        return
    rows = []
    for a in areas:
        rows.append((
            firm_id, a.get("id"), a.get("name"), a.get("code"),
            a.get("created_at"), a.get("updated_at"), json.dumps(a),
        ))

    sql = """
        INSERT INTO clio_cached_practice_areas
            (firm_id, id, name, code, created_at, updated_at, data_json)
        VALUES %s
        ON CONFLICT (firm_id, id) DO UPDATE SET
            name = EXCLUDED.name,
            code = EXCLUDED.code,
            updated_at = EXCLUDED.updated_at,
            data_json = EXCLUDED.data_json,
            cached_at = CURRENT_TIMESTAMP
    """
    with get_connection() as conn:
        cur = conn.cursor()
        execute_values(cur, sql, rows, page_size=500)
    logger.info("Upserted %d Clio practice areas for firm %s", len(rows), firm_id)


def batch_upsert_matter_stages(firm_id: str, stages: List[Dict]):
    """Upsert Clio matter stages (reference data)."""
    if not stages:
        return
    rows = []
    for s in stages:
        rows.append((
            firm_id, s.get("id"), s.get("name"), s.get("order"), json.dumps(s),
        ))

    sql = """
        INSERT INTO clio_cached_matter_stages
            (firm_id, id, name, "order", data_json)
        VALUES %s
        ON CONFLICT (firm_id, id) DO UPDATE SET
            name = EXCLUDED.name,
            "order" = EXCLUDED."order",
            data_json = EXCLUDED.data_json,
            cached_at = CURRENT_TIMESTAMP
    """
    with get_connection() as conn:
        cur = conn.cursor()
        execute_values(cur, sql, rows, page_size=500)
    logger.info("Upserted %d Clio matter stages for firm %s", len(rows), firm_id)


# ============================================================
# Query Helpers
# ============================================================

def get_matters(firm_id: str, status: str = None) -> List[Dict]:
    """Get cached Clio matters, optionally filtered by status."""
    with get_connection() as conn:
        cur = conn.cursor()
        if status:
            cur.execute(
                "SELECT * FROM clio_cached_matters WHERE firm_id = %s AND status = %s ORDER BY updated_at DESC",
                (firm_id, status),
            )
        else:
            cur.execute(
                "SELECT * FROM clio_cached_matters WHERE firm_id = %s ORDER BY updated_at DESC",
                (firm_id,),
            )
        return [dict(r) for r in cur.fetchall()]


def get_bills(firm_id: str, status: str = None) -> List[Dict]:
    """Get cached Clio bills, optionally filtered by status."""
    with get_connection() as conn:
        cur = conn.cursor()
        if status:
            cur.execute(
                "SELECT * FROM clio_cached_bills WHERE firm_id = %s AND status = %s ORDER BY updated_at DESC",
                (firm_id, status),
            )
        else:
            cur.execute(
                "SELECT * FROM clio_cached_bills WHERE firm_id = %s ORDER BY updated_at DESC",
                (firm_id,),
            )
        return [dict(r) for r in cur.fetchall()]


def get_contacts(firm_id: str, clients_only: bool = False) -> List[Dict]:
    """Get cached Clio contacts, optionally only clients."""
    with get_connection() as conn:
        cur = conn.cursor()
        if clients_only:
            cur.execute(
                "SELECT * FROM clio_cached_contacts WHERE firm_id = %s AND is_client = TRUE ORDER BY name",
                (firm_id,),
            )
        else:
            cur.execute(
                "SELECT * FROM clio_cached_contacts WHERE firm_id = %s ORDER BY name",
                (firm_id,),
            )
        return [dict(r) for r in cur.fetchall()]


def get_tasks(firm_id: str, status: str = None) -> List[Dict]:
    """Get cached Clio tasks, optionally filtered by status."""
    with get_connection() as conn:
        cur = conn.cursor()
        if status:
            cur.execute(
                "SELECT * FROM clio_cached_tasks WHERE firm_id = %s AND status = %s ORDER BY due_at",
                (firm_id, status),
            )
        else:
            cur.execute(
                "SELECT * FROM clio_cached_tasks WHERE firm_id = %s ORDER BY due_at",
                (firm_id,),
            )
        return [dict(r) for r in cur.fetchall()]


def get_users(firm_id: str, enabled_only: bool = True) -> List[Dict]:
    """Get cached Clio users (staff)."""
    with get_connection() as conn:
        cur = conn.cursor()
        if enabled_only:
            cur.execute(
                "SELECT * FROM clio_cached_users WHERE firm_id = %s AND enabled = TRUE ORDER BY name",
                (firm_id,),
            )
        else:
            cur.execute(
                "SELECT * FROM clio_cached_users WHERE firm_id = %s ORDER BY name",
                (firm_id,),
            )
        return [dict(r) for r in cur.fetchall()]


def get_activities(firm_id: str, matter_id: int = None) -> List[Dict]:
    """Get cached Clio activities, optionally filtered by matter."""
    with get_connection() as conn:
        cur = conn.cursor()
        if matter_id:
            cur.execute(
                "SELECT * FROM clio_cached_activities WHERE firm_id = %s AND matter_id = %s ORDER BY date DESC",
                (firm_id, matter_id),
            )
        else:
            cur.execute(
                "SELECT * FROM clio_cached_activities WHERE firm_id = %s ORDER BY date DESC",
                (firm_id,),
            )
        return [dict(r) for r in cur.fetchall()]
