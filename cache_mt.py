"""
Multi-Tenant MyCase Data Cache — PostgreSQL Backend

All cached MyCase data (cases, events, invoices, etc.) stored in PostgreSQL
with firm_id column for multi-tenant isolation.

Replaces the per-firm SQLite approach with a single shared Postgres database.
"""
import json
import os
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
from contextlib import contextmanager

import psycopg2
from psycopg2.extras import RealDictCursor

from tenant import current_tenant, get_current_firm_id

logger = logging.getLogger(__name__)


def _get_database_url() -> str:
    url = os.environ.get('DATABASE_URL')
    if not url:
        raise ValueError("DATABASE_URL environment variable is required.")
    return url


class MyCaseCache:
    """
    PostgreSQL cache for MyCase API data.
    Multi-tenant: every query is scoped by firm_id.
    """

    def __init__(self, firm_id: str = None):
        self.firm_id = firm_id or current_tenant.get()
        self.database_url = _get_database_url()
        self._init_tables()

    @contextmanager
    def _get_connection(self):
        conn = psycopg2.connect(self.database_url, cursor_factory=RealDictCursor)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_tables(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sync_metadata (
                    firm_id VARCHAR(36) NOT NULL,
                    entity_type TEXT NOT NULL,
                    last_full_sync TIMESTAMP,
                    last_incremental_sync TIMESTAMP,
                    total_records INTEGER DEFAULT 0,
                    sync_duration_seconds REAL,
                    last_error TEXT,
                    PRIMARY KEY (firm_id, entity_type)
                )
            """)

            cursor.execute("""
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
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_cc_updated ON cached_cases(firm_id, updated_at)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_cc_status ON cached_cases(firm_id, status)")

            cursor.execute("""
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
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_cco_updated ON cached_contacts(firm_id, updated_at)")

            cursor.execute("""
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
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_ccl_updated ON cached_clients(firm_id, updated_at)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_ccl_zip ON cached_clients(firm_id, zip_code)")

            cursor.execute("""
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
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_ci_updated ON cached_invoices(firm_id, updated_at)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_ci_status ON cached_invoices(firm_id, status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_ci_case ON cached_invoices(firm_id, case_id)")

            cursor.execute("""
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
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_ce_updated ON cached_events(firm_id, updated_at)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_ce_start ON cached_events(firm_id, start_at)")

            cursor.execute("""
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
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_ct_updated ON cached_tasks(firm_id, updated_at)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_ct_due ON cached_tasks(firm_id, due_date)")

            cursor.execute("""
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
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_cs_active ON cached_staff(firm_id, active)")

            cursor.execute("""
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
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_cp_invoice ON cached_payments(firm_id, invoice_id)")

            cursor.execute("""
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
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_cte_date ON cached_time_entries(firm_id, entry_date)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_cte_staff ON cached_time_entries(firm_id, staff_id)")

    # ========== Sync Metadata ==========

    def get_sync_status(self, entity_type: str) -> Optional[Dict]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM sync_metadata WHERE firm_id = %s AND entity_type = %s",
                (self.firm_id, entity_type)
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def update_sync_status(self, entity_type: str, total_records: int,
                           sync_duration: float, full_sync: bool = False,
                           error: str = None):
        now = datetime.utcnow()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if full_sync:
                cursor.execute("""
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
                """, (self.firm_id, entity_type, now, now, total_records, sync_duration, error))
            else:
                cursor.execute("""
                    INSERT INTO sync_metadata
                    (firm_id, entity_type, last_incremental_sync,
                     total_records, sync_duration_seconds, last_error)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (firm_id, entity_type) DO UPDATE SET
                        last_incremental_sync = EXCLUDED.last_incremental_sync,
                        total_records = EXCLUDED.total_records,
                        sync_duration_seconds = EXCLUDED.sync_duration_seconds,
                        last_error = EXCLUDED.last_error
                """, (self.firm_id, entity_type, now, total_records, sync_duration, error))

    def needs_full_sync(self, entity_type: str, max_age_hours: int = 24) -> bool:
        status = self.get_sync_status(entity_type)
        if not status or not status.get('last_full_sync'):
            return True
        last_sync = status['last_full_sync']
        if isinstance(last_sync, str):
            last_sync = datetime.fromisoformat(last_sync)
        return (datetime.utcnow() - last_sync) > timedelta(hours=max_age_hours)

    def get_all_sync_status(self) -> List[Dict]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM sync_metadata WHERE firm_id = %s ORDER BY entity_type",
                           (self.firm_id,))
            return [dict(row) for row in cursor.fetchall()]

    # ========== Generic Methods ==========

    def get_cached_updated_at(self, entity_type: str) -> Dict[int, str]:
        table = f"cached_{entity_type}"
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"SELECT id, updated_at FROM {table} WHERE firm_id = %s",
                           (self.firm_id,))
            return {row['id']: str(row['updated_at']) if row['updated_at'] else None
                    for row in cursor.fetchall()}

    def get_cached_count(self, entity_type: str) -> int:
        table = f"cached_{entity_type}"
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"SELECT COUNT(*) as count FROM {table} WHERE firm_id = %s",
                           (self.firm_id,))
            return cursor.fetchone()['count']

    # ========== Cases ==========

    def upsert_case(self, case: Dict) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            staff = case.get('staff', [])
            lead_attorney_id = None
            lead_attorney_name = None
            for s in staff:
                if s.get('lead_lawyer'):
                    lead_attorney_id = s.get('id')
                    cursor.execute("SELECT name FROM cached_staff WHERE firm_id = %s AND id = %s",
                                   (self.firm_id, lead_attorney_id))
                    row = cursor.fetchone()
                    if row:
                        lead_attorney_name = row['name']
                    break

            cursor.execute("""
                INSERT INTO cached_cases
                (firm_id, id, name, case_number, status, case_type, practice_area,
                 date_opened, date_closed, lead_attorney_id, lead_attorney_name,
                 stage, created_at, updated_at, data_json, cached_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,CURRENT_TIMESTAMP)
                ON CONFLICT (firm_id, id) DO UPDATE SET
                    name=EXCLUDED.name, case_number=EXCLUDED.case_number,
                    status=EXCLUDED.status, case_type=EXCLUDED.case_type,
                    practice_area=EXCLUDED.practice_area, date_opened=EXCLUDED.date_opened,
                    date_closed=EXCLUDED.date_closed, lead_attorney_id=EXCLUDED.lead_attorney_id,
                    lead_attorney_name=EXCLUDED.lead_attorney_name, stage=EXCLUDED.stage,
                    created_at=EXCLUDED.created_at, updated_at=EXCLUDED.updated_at,
                    data_json=EXCLUDED.data_json, cached_at=CURRENT_TIMESTAMP
            """, (
                self.firm_id, case.get('id'), case.get('name'), case.get('case_number'),
                case.get('status'),
                case.get('case_type', {}).get('name') if isinstance(case.get('case_type'), dict) else case.get('case_type'),
                case.get('practice_area', {}).get('name') if isinstance(case.get('practice_area'), dict) else case.get('practice_area'),
                case.get('date_opened') or case.get('opened_date'),
                case.get('date_closed') or case.get('closed_date'),
                lead_attorney_id, lead_attorney_name,
                case.get('case_stage', {}).get('name') if isinstance(case.get('case_stage'), dict) else None,
                case.get('created_at'), case.get('updated_at'), json.dumps(case),
            ))

    def get_case(self, case_id: int) -> Optional[Dict]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT data_json FROM cached_cases WHERE firm_id=%s AND id=%s",
                           (self.firm_id, case_id))
            row = cursor.fetchone()
            return json.loads(row['data_json']) if row else None

    def get_cases(self, status: str = None, attorney_id: int = None,
                  limit: int = None) -> List[Dict]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT data_json FROM cached_cases WHERE firm_id=%s"
            params: list = [self.firm_id]
            if status:
                query += " AND status=%s"; params.append(status)
            if attorney_id:
                query += " AND lead_attorney_id=%s"; params.append(attorney_id)
            query += " ORDER BY updated_at DESC"
            if limit:
                query += " LIMIT %s"; params.append(limit)
            cursor.execute(query, params)
            return [json.loads(row['data_json']) for row in cursor.fetchall()]

    # ========== Invoices ==========

    def upsert_invoice(self, invoice: Dict) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            case = invoice.get('case', {}) or {}
            contact = invoice.get('contact', {}) or {}
            total = float(invoice.get('total_amount', 0) or 0)
            paid = float(invoice.get('paid_amount', 0) or 0)

            cursor.execute("""
                INSERT INTO cached_invoices
                (firm_id, id, invoice_number, case_id, contact_id, status,
                 total_amount, paid_amount, balance_due, invoice_date, due_date,
                 created_at, updated_at, data_json, cached_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,CURRENT_TIMESTAMP)
                ON CONFLICT (firm_id, id) DO UPDATE SET
                    invoice_number=EXCLUDED.invoice_number, case_id=EXCLUDED.case_id,
                    contact_id=EXCLUDED.contact_id, status=EXCLUDED.status,
                    total_amount=EXCLUDED.total_amount, paid_amount=EXCLUDED.paid_amount,
                    balance_due=EXCLUDED.balance_due, invoice_date=EXCLUDED.invoice_date,
                    due_date=EXCLUDED.due_date, created_at=EXCLUDED.created_at,
                    updated_at=EXCLUDED.updated_at, data_json=EXCLUDED.data_json,
                    cached_at=CURRENT_TIMESTAMP
            """, (
                self.firm_id, invoice.get('id'), invoice.get('invoice_number'),
                case.get('id'), contact.get('id'), invoice.get('status'),
                total, paid, total - paid,
                invoice.get('invoice_date'), invoice.get('due_date'),
                invoice.get('created_at'), invoice.get('updated_at'), json.dumps(invoice),
            ))

    def get_invoice(self, invoice_id: int) -> Optional[Dict]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT data_json FROM cached_invoices WHERE firm_id=%s AND id=%s",
                           (self.firm_id, invoice_id))
            row = cursor.fetchone()
            return json.loads(row['data_json']) if row else None

    def get_invoices(self, status: str = None, case_id: int = None,
                     overdue_only: bool = False, limit: int = None) -> List[Dict]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT data_json FROM cached_invoices WHERE firm_id=%s"
            params: list = [self.firm_id]
            if status:
                query += " AND status=%s"; params.append(status)
            if case_id:
                query += " AND case_id=%s"; params.append(case_id)
            if overdue_only:
                query += " AND status IN ('overdue','partial') AND balance_due > 0"
            query += " ORDER BY due_date DESC"
            if limit:
                query += " LIMIT %s"; params.append(limit)
            cursor.execute(query, params)
            return [json.loads(row['data_json']) for row in cursor.fetchall()]

    def get_overdue_invoices(self) -> List[Dict]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT data_json FROM cached_invoices
                WHERE firm_id=%s AND status IN ('overdue','partial')
                AND balance_due > 0 AND due_date < CURRENT_DATE
                ORDER BY due_date ASC
            """, (self.firm_id,))
            return [json.loads(row['data_json']) for row in cursor.fetchall()]

    # ========== Events ==========

    def upsert_event(self, event: Dict) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            case = event.get('case', {}) or {}
            start = event.get('start')
            end = event.get('end')
            if isinstance(start, dict):
                start = start.get('date_time') or start.get('date')
            if isinstance(end, dict):
                end = end.get('date_time') or end.get('date')
            location = event.get('location')
            if isinstance(location, dict):
                location = location.get('id') or location.get('name')

            cursor.execute("""
                INSERT INTO cached_events
                (firm_id, id, name, description, event_type, start_at, end_at, all_day,
                 case_id, location, created_at, updated_at, data_json, cached_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,CURRENT_TIMESTAMP)
                ON CONFLICT (firm_id, id) DO UPDATE SET
                    name=EXCLUDED.name, description=EXCLUDED.description,
                    event_type=EXCLUDED.event_type, start_at=EXCLUDED.start_at,
                    end_at=EXCLUDED.end_at, all_day=EXCLUDED.all_day,
                    case_id=EXCLUDED.case_id, location=EXCLUDED.location,
                    created_at=EXCLUDED.created_at, updated_at=EXCLUDED.updated_at,
                    data_json=EXCLUDED.data_json, cached_at=CURRENT_TIMESTAMP
            """, (
                self.firm_id, event.get('id'), event.get('name'), event.get('description'),
                event.get('event_type'), start, end, event.get('all_day', False),
                case.get('id') if isinstance(case, dict) else case,
                location, event.get('created_at'), event.get('updated_at'), json.dumps(event),
            ))

    def get_events(self, start_date: str = None, end_date: str = None,
                   case_id: int = None, limit: int = None) -> List[Dict]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT data_json FROM cached_events WHERE firm_id=%s"
            params: list = [self.firm_id]
            if start_date:
                query += " AND start_at >= %s"; params.append(start_date)
            if end_date:
                query += " AND start_at <= %s"; params.append(end_date)
            if case_id:
                query += " AND case_id=%s"; params.append(case_id)
            query += " ORDER BY start_at ASC"
            if limit:
                query += " LIMIT %s"; params.append(limit)
            cursor.execute(query, params)
            return [json.loads(row['data_json']) for row in cursor.fetchall()]

    # ========== Tasks ==========

    def upsert_task(self, task: Dict) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            case = task.get('case', {}) or {}
            staff_list = task.get('staff', []) or []
            if isinstance(staff_list, dict):
                staff_list = [staff_list]
            first_staff = staff_list[0] if staff_list else {}
            staff_ids = ','.join(str(s.get('id')) for s in staff_list if s.get('id'))

            cursor.execute("""
                INSERT INTO cached_tasks
                (firm_id, id, name, description, due_date, completed, completed_at,
                 priority, case_id, assignee_id, assignee_name,
                 created_at, updated_at, data_json, cached_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,CURRENT_TIMESTAMP)
                ON CONFLICT (firm_id, id) DO UPDATE SET
                    name=EXCLUDED.name, description=EXCLUDED.description,
                    due_date=EXCLUDED.due_date, completed=EXCLUDED.completed,
                    completed_at=EXCLUDED.completed_at, priority=EXCLUDED.priority,
                    case_id=EXCLUDED.case_id, assignee_id=EXCLUDED.assignee_id,
                    assignee_name=EXCLUDED.assignee_name, created_at=EXCLUDED.created_at,
                    updated_at=EXCLUDED.updated_at, data_json=EXCLUDED.data_json,
                    cached_at=CURRENT_TIMESTAMP
            """, (
                self.firm_id, task.get('id'), task.get('name'), task.get('description'),
                task.get('due_date'), task.get('completed', False), task.get('completed_at'),
                task.get('priority'),
                case.get('id') if isinstance(case, dict) else case,
                first_staff.get('id') if isinstance(first_staff, dict) else None,
                staff_ids, task.get('created_at'), task.get('updated_at'), json.dumps(task),
            ))

    def get_tasks(self, due_before: str = None, completed: bool = None,
                  case_id: int = None, assignee_id: int = None,
                  limit: int = None) -> List[Dict]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT data_json FROM cached_tasks WHERE firm_id=%s"
            params: list = [self.firm_id]
            if due_before:
                query += " AND due_date <= %s"; params.append(due_before)
            if completed is not None:
                query += " AND completed = %s"; params.append(completed)
            if case_id:
                query += " AND case_id=%s"; params.append(case_id)
            if assignee_id:
                query += " AND assignee_id=%s"; params.append(assignee_id)
            query += " ORDER BY due_date ASC"
            if limit:
                query += " LIMIT %s"; params.append(limit)
            cursor.execute(query, params)
            return [json.loads(row['data_json']) for row in cursor.fetchall()]

    # ========== Staff ==========

    def upsert_staff(self, staff: Dict) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO cached_staff
                (firm_id, id, first_name, last_name, name, email, title, staff_type,
                 active, hourly_rate, created_at, updated_at, data_json, cached_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,CURRENT_TIMESTAMP)
                ON CONFLICT (firm_id, id) DO UPDATE SET
                    first_name=EXCLUDED.first_name, last_name=EXCLUDED.last_name,
                    name=EXCLUDED.name, email=EXCLUDED.email, title=EXCLUDED.title,
                    staff_type=EXCLUDED.staff_type, active=EXCLUDED.active,
                    hourly_rate=EXCLUDED.hourly_rate, created_at=EXCLUDED.created_at,
                    updated_at=EXCLUDED.updated_at, data_json=EXCLUDED.data_json,
                    cached_at=CURRENT_TIMESTAMP
            """, (
                self.firm_id, staff.get('id'), staff.get('first_name'), staff.get('last_name'),
                f"{staff.get('first_name', '')} {staff.get('last_name', '')}".strip(),
                staff.get('email'), staff.get('title'), staff.get('type'),
                staff.get('active', True),
                float(staff.get('default_hourly_rate') or 0) if staff.get('default_hourly_rate') else None,
                staff.get('created_at'), staff.get('updated_at'), json.dumps(staff),
            ))

    def get_staff(self, active_only: bool = False) -> List[Dict]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT data_json FROM cached_staff WHERE firm_id=%s"
            params: list = [self.firm_id]
            if active_only:
                query += " AND active = TRUE"
            query += " ORDER BY last_name, first_name"
            cursor.execute(query, params)
            return [json.loads(row['data_json']) for row in cursor.fetchall()]

    # ========== Contacts ==========

    def upsert_contact(self, contact: Dict) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO cached_contacts
                (firm_id, id, first_name, last_name, name, email, phone, contact_type,
                 company, created_at, updated_at, data_json, cached_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,CURRENT_TIMESTAMP)
                ON CONFLICT (firm_id, id) DO UPDATE SET
                    first_name=EXCLUDED.first_name, last_name=EXCLUDED.last_name,
                    name=EXCLUDED.name, email=EXCLUDED.email, phone=EXCLUDED.phone,
                    contact_type=EXCLUDED.contact_type, company=EXCLUDED.company,
                    created_at=EXCLUDED.created_at, updated_at=EXCLUDED.updated_at,
                    data_json=EXCLUDED.data_json, cached_at=CURRENT_TIMESTAMP
            """, (
                self.firm_id, contact.get('id'), contact.get('first_name'), contact.get('last_name'),
                contact.get('name') or f"{contact.get('first_name', '')} {contact.get('last_name', '')}".strip(),
                contact.get('email'), contact.get('phone'), contact.get('type'),
                contact.get('company', {}).get('name') if isinstance(contact.get('company'), dict) else contact.get('company'),
                contact.get('created_at'), contact.get('updated_at'), json.dumps(contact),
            ))

    def upsert_client(self, client: Dict) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            address = client.get('address', {}) or {}
            cursor.execute("""
                INSERT INTO cached_clients
                (firm_id, id, first_name, last_name, email, cell_phone, work_phone,
                 home_phone, address1, address2, city, state, zip_code, country,
                 birthdate, archived, created_at, updated_at, data_json, cached_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,CURRENT_TIMESTAMP)
                ON CONFLICT (firm_id, id) DO UPDATE SET
                    first_name=EXCLUDED.first_name, last_name=EXCLUDED.last_name,
                    email=EXCLUDED.email, cell_phone=EXCLUDED.cell_phone,
                    work_phone=EXCLUDED.work_phone, home_phone=EXCLUDED.home_phone,
                    address1=EXCLUDED.address1, address2=EXCLUDED.address2,
                    city=EXCLUDED.city, state=EXCLUDED.state, zip_code=EXCLUDED.zip_code,
                    country=EXCLUDED.country, birthdate=EXCLUDED.birthdate,
                    archived=EXCLUDED.archived, created_at=EXCLUDED.created_at,
                    updated_at=EXCLUDED.updated_at, data_json=EXCLUDED.data_json,
                    cached_at=CURRENT_TIMESTAMP
            """, (
                self.firm_id, client.get('id'), client.get('first_name'), client.get('last_name'),
                client.get('email'), client.get('cell_phone_number'),
                client.get('work_phone_number'), client.get('home_phone_number'),
                address.get('address1'), address.get('address2'),
                address.get('city'), address.get('state'), address.get('zip_code'),
                address.get('country'), client.get('birthdate'), client.get('archived', False),
                client.get('created_at'), client.get('updated_at'), json.dumps(client),
            ))

    def get_client(self, client_id: int) -> Optional[Dict]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT data_json FROM cached_clients WHERE firm_id=%s AND id=%s",
                           (self.firm_id, client_id))
            row = cursor.fetchone()
            return json.loads(row['data_json']) if row else None

    def get_contact(self, contact_id: int) -> Optional[Dict]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT data_json FROM cached_contacts WHERE firm_id=%s AND id=%s",
                           (self.firm_id, contact_id))
            row = cursor.fetchone()
            return json.loads(row['data_json']) if row else None

    # ========== Payments ==========

    def upsert_payment(self, payment: Dict) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            invoice = payment.get('invoice', {}) or {}
            cursor.execute("""
                INSERT INTO cached_payments
                (firm_id, id, invoice_id, amount, payment_date, payment_method,
                 created_at, updated_at, data_json, cached_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,CURRENT_TIMESTAMP)
                ON CONFLICT (firm_id, id) DO UPDATE SET
                    invoice_id=EXCLUDED.invoice_id, amount=EXCLUDED.amount,
                    payment_date=EXCLUDED.payment_date, payment_method=EXCLUDED.payment_method,
                    created_at=EXCLUDED.created_at, updated_at=EXCLUDED.updated_at,
                    data_json=EXCLUDED.data_json, cached_at=CURRENT_TIMESTAMP
            """, (
                self.firm_id, payment.get('id'), invoice.get('id'),
                float(payment.get('amount', 0) or 0), payment.get('payment_date'),
                payment.get('payment_method'), payment.get('created_at'),
                payment.get('updated_at'), json.dumps(payment),
            ))

    # ========== Time Entries ==========

    def upsert_time_entry(self, entry: Dict) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            case = entry.get('case', {}) or {}
            staff = entry.get('staff', {}) or {}
            cursor.execute("""
                INSERT INTO cached_time_entries
                (firm_id, id, description, entry_date, hours, rate, billable, flat_fee,
                 activity_name, case_id, staff_id, staff_name,
                 created_at, updated_at, data_json, cached_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,CURRENT_TIMESTAMP)
                ON CONFLICT (firm_id, id) DO UPDATE SET
                    description=EXCLUDED.description, entry_date=EXCLUDED.entry_date,
                    hours=EXCLUDED.hours, rate=EXCLUDED.rate, billable=EXCLUDED.billable,
                    flat_fee=EXCLUDED.flat_fee, activity_name=EXCLUDED.activity_name,
                    case_id=EXCLUDED.case_id, staff_id=EXCLUDED.staff_id,
                    staff_name=EXCLUDED.staff_name, created_at=EXCLUDED.created_at,
                    updated_at=EXCLUDED.updated_at, data_json=EXCLUDED.data_json,
                    cached_at=CURRENT_TIMESTAMP
            """, (
                self.firm_id, entry.get('id'), entry.get('description'),
                entry.get('entry_date'), float(entry.get('hours', 0) or 0),
                float(entry.get('rate', 0) or 0), entry.get('billable', False),
                entry.get('flat_fee', False), entry.get('activity_name'),
                case.get('id'), staff.get('id'), None,
                entry.get('created_at'), entry.get('updated_at'), json.dumps(entry),
            ))

    def get_time_entries(self, start_date: str = None, end_date: str = None,
                         staff_id: int = None, case_id: int = None,
                         billable_only: bool = False) -> List[Dict]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT data_json FROM cached_time_entries WHERE firm_id=%s"
            params: list = [self.firm_id]
            if start_date:
                query += " AND entry_date >= %s"; params.append(start_date)
            if end_date:
                query += " AND entry_date <= %s"; params.append(end_date)
            if staff_id:
                query += " AND staff_id=%s"; params.append(staff_id)
            if case_id:
                query += " AND case_id=%s"; params.append(case_id)
            if billable_only:
                query += " AND billable = TRUE"
            query += " ORDER BY entry_date DESC"
            cursor.execute(query, params)
            return [json.loads(row['data_json']) for row in cursor.fetchall()]


# =========================================================================
# Factory
# =========================================================================

_cache_instances: Dict[str, MyCaseCache] = {}


def get_cache(firm_id: str = None) -> MyCaseCache:
    firm_id = firm_id or current_tenant.get()
    if firm_id is None:
        raise ValueError("firm_id required — set tenant context or pass explicitly")
    if firm_id not in _cache_instances:
        _cache_instances[firm_id] = MyCaseCache(firm_id=firm_id)
    return _cache_instances[firm_id]


def initialize_firm_cache(firm_id: str) -> MyCaseCache:
    cache = MyCaseCache(firm_id=firm_id)
    _cache_instances[firm_id] = cache
    return cache


def clear_firm_cache(firm_id: str) -> None:
    if firm_id in _cache_instances:
        del _cache_instances[firm_id]
