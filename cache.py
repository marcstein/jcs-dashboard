"""
MyCase Data Cache

Local SQLite cache for MyCase API data with incremental sync support.
Since the MyCase API doesn't support updated_since filtering, we:
1. Store all entity data locally with their updated_at timestamps
2. On sync, compare API updated_at with local updated_at to detect changes
3. Only process entities that have actually changed

This reduces API calls for reading and eliminates the need to re-fetch
all data when only a few records have changed.
"""
import sqlite3
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional, Any, Tuple
from contextlib import contextmanager

from config import DATA_DIR


class MyCaseCache:
    """
    Local cache for MyCase API data.

    Stores entities with their full JSON data and tracks sync metadata.
    Supports incremental updates by comparing updated_at timestamps.
    """

    def __init__(self, db_path: Path = None):
        self.db_path = db_path or DATA_DIR / "mycase_cache.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_tables()

    @contextmanager
    def _get_connection(self):
        """Context manager for database connections."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_tables(self):
        """Initialize cache tables."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Sync metadata - tracks when each entity type was last synced
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sync_metadata (
                    entity_type TEXT PRIMARY KEY,
                    last_full_sync TIMESTAMP,
                    last_incremental_sync TIMESTAMP,
                    total_records INTEGER DEFAULT 0,
                    sync_duration_seconds REAL,
                    last_error TEXT
                )
            """)

            # Cases cache
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS cached_cases (
                    id INTEGER PRIMARY KEY,
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
                    cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_cases_updated ON cached_cases(updated_at)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_cases_status ON cached_cases(status)")

            # Contacts cache
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS cached_contacts (
                    id INTEGER PRIMARY KEY,
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
                    cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_contacts_updated ON cached_contacts(updated_at)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_contacts_type ON cached_contacts(contact_type)")

            # Clients cache (separate from contacts - has full address data)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS cached_clients (
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
                    zip_code TEXT,
                    country TEXT,
                    birthdate DATE,
                    archived BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP,
                    updated_at TIMESTAMP,
                    data_json TEXT,
                    cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_clients_updated ON cached_clients(updated_at)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_clients_zip ON cached_clients(zip_code)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_clients_city ON cached_clients(city)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_clients_state ON cached_clients(state)")

            # Invoices cache
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS cached_invoices (
                    id INTEGER PRIMARY KEY,
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
                    cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_invoices_updated ON cached_invoices(updated_at)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_invoices_status ON cached_invoices(status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_invoices_case ON cached_invoices(case_id)")

            # Events cache
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS cached_events (
                    id INTEGER PRIMARY KEY,
                    name TEXT,
                    description TEXT,
                    event_type TEXT,
                    start_at TIMESTAMP,
                    end_at TIMESTAMP,
                    all_day BOOLEAN,
                    case_id INTEGER,
                    location TEXT,
                    created_at TIMESTAMP,
                    updated_at TIMESTAMP,
                    data_json TEXT,
                    cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_updated ON cached_events(updated_at)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_start ON cached_events(start_at)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_case ON cached_events(case_id)")

            # Tasks cache
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS cached_tasks (
                    id INTEGER PRIMARY KEY,
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
                    cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_tasks_updated ON cached_tasks(updated_at)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_tasks_due ON cached_tasks(due_date)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_tasks_case ON cached_tasks(case_id)")

            # Staff cache
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS cached_staff (
                    id INTEGER PRIMARY KEY,
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
                    cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_staff_updated ON cached_staff(updated_at)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_staff_active ON cached_staff(active)")

            # Payments cache
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS cached_payments (
                    id INTEGER PRIMARY KEY,
                    invoice_id INTEGER,
                    amount REAL,
                    payment_date DATE,
                    payment_method TEXT,
                    created_at TIMESTAMP,
                    updated_at TIMESTAMP,
                    data_json TEXT,
                    cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_payments_updated ON cached_payments(updated_at)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_payments_invoice ON cached_payments(invoice_id)")

            # Time entries cache
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS cached_time_entries (
                    id INTEGER PRIMARY KEY,
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
                    cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_time_entries_updated ON cached_time_entries(updated_at)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_time_entries_date ON cached_time_entries(entry_date)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_time_entries_staff ON cached_time_entries(staff_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_time_entries_case ON cached_time_entries(case_id)")

            # Documents cache
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS cached_documents (
                    id INTEGER PRIMARY KEY,
                    name TEXT,
                    filename TEXT,
                    path TEXT,
                    description TEXT,
                    assigned_date DATE,
                    case_id INTEGER,
                    folder_id INTEGER,
                    created_at TIMESTAMP,
                    updated_at TIMESTAMP,
                    data_json TEXT,
                    cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_documents_updated ON cached_documents(updated_at)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_documents_case ON cached_documents(case_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_documents_name ON cached_documents(name)")

            # Docket entries cache (Missouri courts)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS cached_docket_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    case_number TEXT NOT NULL,
                    case_name TEXT,
                    case_id INTEGER,
                    entry_date DATE NOT NULL,
                    entry_type TEXT NOT NULL,
                    entry_text TEXT,
                    scheduled_date DATE,
                    scheduled_time TEXT,
                    judge TEXT,
                    location TEXT,
                    filed_by TEXT,
                    on_behalf_of TEXT,
                    document_id TEXT,
                    associated_entries TEXT,
                    requires_action BOOLEAN DEFAULT FALSE,
                    action_due_date DATE,
                    notification_sent BOOLEAN DEFAULT FALSE,
                    notification_sent_at TIMESTAMP,
                    raw_text TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(case_number, entry_date, entry_type, entry_text)
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_docket_case_number ON cached_docket_entries(case_number)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_docket_case_id ON cached_docket_entries(case_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_docket_entry_date ON cached_docket_entries(entry_date)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_docket_scheduled ON cached_docket_entries(scheduled_date)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_docket_action_due ON cached_docket_entries(action_due_date)")

            conn.commit()

    # ========== Sync Metadata Methods ==========

    def get_sync_status(self, entity_type: str) -> Optional[Dict]:
        """Get sync status for an entity type."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM sync_metadata WHERE entity_type = ?",
                (entity_type,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def update_sync_status(
        self,
        entity_type: str,
        total_records: int,
        sync_duration: float,
        full_sync: bool = False,
        error: str = None
    ):
        """Update sync metadata after a sync operation."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            now = datetime.now().isoformat()

            if full_sync:
                cursor.execute("""
                    INSERT INTO sync_metadata
                    (entity_type, last_full_sync, last_incremental_sync, total_records,
                     sync_duration_seconds, last_error)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(entity_type) DO UPDATE SET
                        last_full_sync = excluded.last_full_sync,
                        last_incremental_sync = excluded.last_incremental_sync,
                        total_records = excluded.total_records,
                        sync_duration_seconds = excluded.sync_duration_seconds,
                        last_error = excluded.last_error
                """, (entity_type, now, now, total_records, sync_duration, error))
            else:
                cursor.execute("""
                    INSERT INTO sync_metadata
                    (entity_type, last_incremental_sync, total_records,
                     sync_duration_seconds, last_error)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(entity_type) DO UPDATE SET
                        last_incremental_sync = excluded.last_incremental_sync,
                        total_records = excluded.total_records,
                        sync_duration_seconds = excluded.sync_duration_seconds,
                        last_error = excluded.last_error
                """, (entity_type, now, total_records, sync_duration, error))

    def needs_full_sync(self, entity_type: str, max_age_hours: int = 24) -> bool:
        """Check if an entity type needs a full sync."""
        status = self.get_sync_status(entity_type)
        if not status or not status.get('last_full_sync'):
            return True

        last_sync = datetime.fromisoformat(status['last_full_sync'])
        age = datetime.now() - last_sync
        return age > timedelta(hours=max_age_hours)

    def get_all_sync_status(self) -> List[Dict]:
        """Get sync status for all entity types."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM sync_metadata ORDER BY entity_type")
            return [dict(row) for row in cursor.fetchall()]

    # ========== Generic Cache Methods ==========

    def get_cached_updated_at(self, entity_type: str) -> Dict[int, str]:
        """
        Get a map of entity ID -> updated_at for all cached entities.
        Used for incremental sync to detect what has changed.
        """
        table_name = f"cached_{entity_type}"
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"SELECT id, updated_at FROM {table_name}")
            return {row['id']: row['updated_at'] for row in cursor.fetchall()}

    def get_cached_count(self, entity_type: str) -> int:
        """Get count of cached entities."""
        table_name = f"cached_{entity_type}"
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"SELECT COUNT(*) as count FROM {table_name}")
            return cursor.fetchone()['count']

    # ========== Cases Cache Methods ==========

    def upsert_case(self, case: Dict) -> None:
        """Insert or update a case in the cache."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Extract lead attorney from staff array
            # Staff members have: {id, lead_lawyer, originating_lawyer, case_rate}
            staff = case.get('staff', [])
            lead_attorney_id = None
            lead_attorney_name = None
            for s in staff:
                if s.get('lead_lawyer'):
                    lead_attorney_id = s.get('id')
                    # Look up staff name from cache
                    cursor.execute("SELECT name FROM cached_staff WHERE id = ?", (lead_attorney_id,))
                    row = cursor.fetchone()
                    if row:
                        lead_attorney_name = row['name']
                    break

            cursor.execute("""
                INSERT INTO cached_cases
                (id, name, case_number, status, case_type, practice_area,
                 date_opened, date_closed, lead_attorney_id, lead_attorney_name,
                 stage, created_at, updated_at, data_json, cached_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    case_number = excluded.case_number,
                    status = excluded.status,
                    case_type = excluded.case_type,
                    practice_area = excluded.practice_area,
                    date_opened = excluded.date_opened,
                    date_closed = excluded.date_closed,
                    lead_attorney_id = excluded.lead_attorney_id,
                    lead_attorney_name = excluded.lead_attorney_name,
                    stage = excluded.stage,
                    created_at = excluded.created_at,
                    updated_at = excluded.updated_at,
                    data_json = excluded.data_json,
                    cached_at = CURRENT_TIMESTAMP
            """, (
                case.get('id'),
                case.get('name'),
                case.get('case_number'),
                case.get('status'),
                case.get('case_type', {}).get('name') if isinstance(case.get('case_type'), dict) else case.get('case_type'),
                case.get('practice_area', {}).get('name') if isinstance(case.get('practice_area'), dict) else case.get('practice_area'),
                case.get('date_opened') or case.get('opened_date'),
                case.get('date_closed') or case.get('closed_date'),
                lead_attorney_id,
                lead_attorney_name,
                case.get('case_stage', {}).get('name') if isinstance(case.get('case_stage'), dict) else None,
                case.get('created_at'),
                case.get('updated_at'),
                json.dumps(case),
            ))

    def get_case(self, case_id: int) -> Optional[Dict]:
        """Get a case from cache by ID."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT data_json FROM cached_cases WHERE id = ?", (case_id,))
            row = cursor.fetchone()
            return json.loads(row['data_json']) if row else None

    def get_cases(
        self,
        status: str = None,
        attorney_id: int = None,
        limit: int = None
    ) -> List[Dict]:
        """Get cases from cache with optional filters."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT data_json FROM cached_cases WHERE 1=1"
            params = []

            if status:
                query += " AND status = ?"
                params.append(status)
            if attorney_id:
                query += " AND lead_attorney_id = ?"
                params.append(attorney_id)

            query += " ORDER BY updated_at DESC"

            if limit:
                query += " LIMIT ?"
                params.append(limit)

            cursor.execute(query, params)
            return [json.loads(row['data_json']) for row in cursor.fetchall()]

    # ========== Invoices Cache Methods ==========

    def upsert_invoice(self, invoice: Dict) -> None:
        """Insert or update an invoice in the cache."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            case = invoice.get('case', {}) or {}
            contact = invoice.get('contact', {}) or {}

            total = float(invoice.get('total_amount', 0) or 0)
            paid = float(invoice.get('paid_amount', 0) or 0)

            cursor.execute("""
                INSERT INTO cached_invoices
                (id, invoice_number, case_id, contact_id, status,
                 total_amount, paid_amount, balance_due, invoice_date, due_date,
                 created_at, updated_at, data_json, cached_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(id) DO UPDATE SET
                    invoice_number = excluded.invoice_number,
                    case_id = excluded.case_id,
                    contact_id = excluded.contact_id,
                    status = excluded.status,
                    total_amount = excluded.total_amount,
                    paid_amount = excluded.paid_amount,
                    balance_due = excluded.balance_due,
                    invoice_date = excluded.invoice_date,
                    due_date = excluded.due_date,
                    created_at = excluded.created_at,
                    updated_at = excluded.updated_at,
                    data_json = excluded.data_json,
                    cached_at = CURRENT_TIMESTAMP
            """, (
                invoice.get('id'),
                invoice.get('invoice_number'),
                case.get('id'),
                contact.get('id'),
                invoice.get('status'),
                total,
                paid,
                total - paid,
                invoice.get('invoice_date'),
                invoice.get('due_date'),
                invoice.get('created_at'),
                invoice.get('updated_at'),
                json.dumps(invoice),
            ))

    def get_invoice(self, invoice_id: int) -> Optional[Dict]:
        """Get an invoice from cache by ID."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT data_json FROM cached_invoices WHERE id = ?", (invoice_id,))
            row = cursor.fetchone()
            return json.loads(row['data_json']) if row else None

    def get_invoices(
        self,
        status: str = None,
        case_id: int = None,
        overdue_only: bool = False,
        limit: int = None
    ) -> List[Dict]:
        """Get invoices from cache with optional filters."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT data_json FROM cached_invoices WHERE 1=1"
            params = []

            if status:
                query += " AND status = ?"
                params.append(status)
            if case_id:
                query += " AND case_id = ?"
                params.append(case_id)
            if overdue_only:
                query += " AND status IN ('overdue', 'partial') AND balance_due > 0"

            query += " ORDER BY due_date DESC"

            if limit:
                query += " LIMIT ?"
                params.append(limit)

            cursor.execute(query, params)
            return [json.loads(row['data_json']) for row in cursor.fetchall()]

    def get_overdue_invoices(self) -> List[Dict]:
        """Get all overdue invoices with balance due."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT data_json FROM cached_invoices
                WHERE status IN ('overdue', 'partial')
                AND balance_due > 0
                AND due_date < DATE('now')
                ORDER BY due_date ASC
            """)
            return [json.loads(row['data_json']) for row in cursor.fetchall()]

    # ========== Events Cache Methods ==========

    def upsert_event(self, event: Dict) -> None:
        """Insert or update an event in the cache."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            case = event.get('case', {}) or {}
            # Handle start/end which can be strings or dicts
            start = event.get('start')
            end = event.get('end')
            if isinstance(start, dict):
                start = start.get('date_time') or start.get('date')
            if isinstance(end, dict):
                end = end.get('date_time') or end.get('date')

            # Handle location which can be a dict with id or a string
            location = event.get('location')
            if isinstance(location, dict):
                location = location.get('id') or location.get('name')

            cursor.execute("""
                INSERT INTO cached_events
                (id, name, description, event_type, start_at, end_at, all_day,
                 case_id, location, created_at, updated_at, data_json, cached_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    description = excluded.description,
                    event_type = excluded.event_type,
                    start_at = excluded.start_at,
                    end_at = excluded.end_at,
                    all_day = excluded.all_day,
                    case_id = excluded.case_id,
                    location = excluded.location,
                    created_at = excluded.created_at,
                    updated_at = excluded.updated_at,
                    data_json = excluded.data_json,
                    cached_at = CURRENT_TIMESTAMP
            """, (
                event.get('id'),
                event.get('name'),
                event.get('description'),
                event.get('event_type'),
                start,
                end,
                event.get('all_day', False),
                case.get('id') if isinstance(case, dict) else case,
                location,
                event.get('created_at'),
                event.get('updated_at'),
                json.dumps(event),
            ))

    def get_events(
        self,
        start_date: str = None,
        end_date: str = None,
        case_id: int = None,
        limit: int = None
    ) -> List[Dict]:
        """Get events from cache with optional filters."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT data_json FROM cached_events WHERE 1=1"
            params = []

            if start_date:
                query += " AND start_at >= ?"
                params.append(start_date)
            if end_date:
                query += " AND start_at <= ?"
                params.append(end_date)
            if case_id:
                query += " AND case_id = ?"
                params.append(case_id)

            query += " ORDER BY start_at ASC"

            if limit:
                query += " LIMIT ?"
                params.append(limit)

            cursor.execute(query, params)
            return [json.loads(row['data_json']) for row in cursor.fetchall()]

    # ========== Tasks Cache Methods ==========

    def upsert_task(self, task: Dict) -> None:
        """Insert or update a task in the cache."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            case = task.get('case', {}) or {}
            # Staff can be a list (multiple assignees) or a dict (single assignee)
            staff_list = task.get('staff', []) or []
            if isinstance(staff_list, dict):
                staff_list = [staff_list]
            # Use first staff member for the assignee fields, store all in JSON
            first_staff = staff_list[0] if staff_list else {}
            staff_ids = ','.join(str(s.get('id')) for s in staff_list if s.get('id'))

            cursor.execute("""
                INSERT INTO cached_tasks
                (id, name, description, due_date, completed, completed_at,
                 priority, case_id, assignee_id, assignee_name,
                 created_at, updated_at, data_json, cached_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    description = excluded.description,
                    due_date = excluded.due_date,
                    completed = excluded.completed,
                    completed_at = excluded.completed_at,
                    priority = excluded.priority,
                    case_id = excluded.case_id,
                    assignee_id = excluded.assignee_id,
                    assignee_name = excluded.assignee_name,
                    created_at = excluded.created_at,
                    updated_at = excluded.updated_at,
                    data_json = excluded.data_json,
                    cached_at = CURRENT_TIMESTAMP
            """, (
                task.get('id'),
                task.get('name'),
                task.get('description'),
                task.get('due_date'),
                task.get('completed', False),
                task.get('completed_at'),
                task.get('priority'),
                case.get('id') if isinstance(case, dict) else case,
                first_staff.get('id') if isinstance(first_staff, dict) else None,
                staff_ids,  # Store all staff IDs as comma-separated string
                task.get('created_at'),
                task.get('updated_at'),
                json.dumps(task),
            ))

    def get_tasks(
        self,
        due_before: str = None,
        completed: bool = None,
        case_id: int = None,
        assignee_id: int = None,
        limit: int = None
    ) -> List[Dict]:
        """Get tasks from cache with optional filters."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT data_json FROM cached_tasks WHERE 1=1"
            params = []

            if due_before:
                query += " AND due_date <= ?"
                params.append(due_before)
            if completed is not None:
                query += " AND completed = ?"
                params.append(completed)
            if case_id:
                query += " AND case_id = ?"
                params.append(case_id)
            if assignee_id:
                query += " AND assignee_id = ?"
                params.append(assignee_id)

            query += " ORDER BY due_date ASC"

            if limit:
                query += " LIMIT ?"
                params.append(limit)

            cursor.execute(query, params)
            return [json.loads(row['data_json']) for row in cursor.fetchall()]

    # ========== Staff Cache Methods ==========

    def upsert_staff(self, staff: Dict) -> None:
        """Insert or update a staff member in the cache."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                INSERT INTO cached_staff
                (id, first_name, last_name, name, email, title, staff_type,
                 active, hourly_rate, created_at, updated_at, data_json, cached_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(id) DO UPDATE SET
                    first_name = excluded.first_name,
                    last_name = excluded.last_name,
                    name = excluded.name,
                    email = excluded.email,
                    title = excluded.title,
                    staff_type = excluded.staff_type,
                    active = excluded.active,
                    hourly_rate = excluded.hourly_rate,
                    created_at = excluded.created_at,
                    updated_at = excluded.updated_at,
                    data_json = excluded.data_json,
                    cached_at = CURRENT_TIMESTAMP
            """, (
                staff.get('id'),
                staff.get('first_name'),
                staff.get('last_name'),
                f"{staff.get('first_name', '')} {staff.get('last_name', '')}".strip(),
                staff.get('email'),
                staff.get('title'),
                staff.get('type'),
                staff.get('active', True),
                float(staff.get('default_hourly_rate') or 0) if staff.get('default_hourly_rate') else None,
                staff.get('created_at'),
                staff.get('updated_at'),
                json.dumps(staff),
            ))

    def get_staff(self, active_only: bool = False) -> List[Dict]:
        """Get staff from cache."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT data_json FROM cached_staff"
            params = []

            if active_only:
                query += " WHERE active = 1"

            query += " ORDER BY last_name, first_name"
            cursor.execute(query, params)
            return [json.loads(row['data_json']) for row in cursor.fetchall()]

    # ========== Contacts Cache Methods ==========

    def upsert_contact(self, contact: Dict) -> None:
        """Insert or update a contact in the cache."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                INSERT INTO cached_contacts
                (id, first_name, last_name, name, email, phone, contact_type,
                 company, created_at, updated_at, data_json, cached_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(id) DO UPDATE SET
                    first_name = excluded.first_name,
                    last_name = excluded.last_name,
                    name = excluded.name,
                    email = excluded.email,
                    phone = excluded.phone,
                    contact_type = excluded.contact_type,
                    company = excluded.company,
                    created_at = excluded.created_at,
                    updated_at = excluded.updated_at,
                    data_json = excluded.data_json,
                    cached_at = CURRENT_TIMESTAMP
            """, (
                contact.get('id'),
                contact.get('first_name'),
                contact.get('last_name'),
                contact.get('name') or f"{contact.get('first_name', '')} {contact.get('last_name', '')}".strip(),
                contact.get('email'),
                contact.get('phone'),
                contact.get('type'),
                contact.get('company', {}).get('name') if isinstance(contact.get('company'), dict) else contact.get('company'),
                contact.get('created_at'),
                contact.get('updated_at'),
                json.dumps(contact),
            ))

    def upsert_client(self, client: Dict) -> None:
        """Insert or update a client in the cache (with full address data)."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Extract address fields
            address = client.get('address', {}) or {}

            cursor.execute("""
                INSERT INTO cached_clients
                (id, first_name, last_name, email, cell_phone, work_phone, home_phone,
                 address1, address2, city, state, zip_code, country, birthdate, archived,
                 created_at, updated_at, data_json, cached_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(id) DO UPDATE SET
                    first_name = excluded.first_name,
                    last_name = excluded.last_name,
                    email = excluded.email,
                    cell_phone = excluded.cell_phone,
                    work_phone = excluded.work_phone,
                    home_phone = excluded.home_phone,
                    address1 = excluded.address1,
                    address2 = excluded.address2,
                    city = excluded.city,
                    state = excluded.state,
                    zip_code = excluded.zip_code,
                    country = excluded.country,
                    birthdate = excluded.birthdate,
                    archived = excluded.archived,
                    created_at = excluded.created_at,
                    updated_at = excluded.updated_at,
                    data_json = excluded.data_json,
                    cached_at = CURRENT_TIMESTAMP
            """, (
                client.get('id'),
                client.get('first_name'),
                client.get('last_name'),
                client.get('email'),
                client.get('cell_phone_number'),
                client.get('work_phone_number'),
                client.get('home_phone_number'),
                address.get('address1'),
                address.get('address2'),
                address.get('city'),
                address.get('state'),
                address.get('zip_code'),
                address.get('country'),
                client.get('birthdate'),
                client.get('archived', False),
                client.get('created_at'),
                client.get('updated_at'),
                json.dumps(client),
            ))

    def get_client(self, client_id: int) -> Optional[Dict]:
        """Get a client from cache by ID."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT data_json FROM cached_clients WHERE id = ?", (client_id,))
            row = cursor.fetchone()
            return json.loads(row['data_json']) if row else None

    def get_contact(self, contact_id: int) -> Optional[Dict]:
        """Get a contact from cache by ID."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT data_json FROM cached_contacts WHERE id = ?", (contact_id,))
            row = cursor.fetchone()
            return json.loads(row['data_json']) if row else None

    # ========== Payments Cache Methods ==========

    def upsert_payment(self, payment: Dict) -> None:
        """Insert or update a payment in the cache."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            invoice = payment.get('invoice', {}) or {}

            cursor.execute("""
                INSERT INTO cached_payments
                (id, invoice_id, amount, payment_date, payment_method,
                 created_at, updated_at, data_json, cached_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(id) DO UPDATE SET
                    invoice_id = excluded.invoice_id,
                    amount = excluded.amount,
                    payment_date = excluded.payment_date,
                    payment_method = excluded.payment_method,
                    created_at = excluded.created_at,
                    updated_at = excluded.updated_at,
                    data_json = excluded.data_json,
                    cached_at = CURRENT_TIMESTAMP
            """, (
                payment.get('id'),
                invoice.get('id'),
                float(payment.get('amount', 0) or 0),
                payment.get('payment_date'),
                payment.get('payment_method'),
                payment.get('created_at'),
                payment.get('updated_at'),
                json.dumps(payment),
            ))

    # ========== Time Entries Cache Methods ==========

    def upsert_time_entry(self, entry: Dict) -> None:
        """Insert or update a time entry in the cache."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            case = entry.get('case', {}) or {}
            staff = entry.get('staff', {}) or {}

            cursor.execute("""
                INSERT INTO cached_time_entries
                (id, description, entry_date, hours, rate, billable, flat_fee,
                 activity_name, case_id, staff_id, staff_name,
                 created_at, updated_at, data_json, cached_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(id) DO UPDATE SET
                    description = excluded.description,
                    entry_date = excluded.entry_date,
                    hours = excluded.hours,
                    rate = excluded.rate,
                    billable = excluded.billable,
                    flat_fee = excluded.flat_fee,
                    activity_name = excluded.activity_name,
                    case_id = excluded.case_id,
                    staff_id = excluded.staff_id,
                    staff_name = excluded.staff_name,
                    created_at = excluded.created_at,
                    updated_at = excluded.updated_at,
                    data_json = excluded.data_json,
                    cached_at = CURRENT_TIMESTAMP
            """, (
                entry.get('id'),
                entry.get('description'),
                entry.get('entry_date'),
                float(entry.get('hours', 0) or 0),
                float(entry.get('rate', 0) or 0),
                entry.get('billable', False),
                entry.get('flat_fee', False),
                entry.get('activity_name'),
                case.get('id'),
                staff.get('id'),
                None,  # Staff name would need separate lookup
                entry.get('created_at'),
                entry.get('updated_at'),
                json.dumps(entry),
            ))

    def get_time_entries(
        self,
        start_date: str = None,
        end_date: str = None,
        staff_id: int = None,
        case_id: int = None,
        billable_only: bool = False
    ) -> List[Dict]:
        """Get time entries from cache with optional filters."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT data_json FROM cached_time_entries WHERE 1=1"
            params = []

            if start_date:
                query += " AND entry_date >= ?"
                params.append(start_date)
            if end_date:
                query += " AND entry_date <= ?"
                params.append(end_date)
            if staff_id:
                query += " AND staff_id = ?"
                params.append(staff_id)
            if case_id:
                query += " AND case_id = ?"
                params.append(case_id)
            if billable_only:
                query += " AND billable = 1"

            query += " ORDER BY entry_date DESC"
            cursor.execute(query, params)
            return [json.loads(row['data_json']) for row in cursor.fetchall()]

    def get_time_summary_by_staff(
        self,
        start_date: str = None,
        end_date: str = None,
        billable_only: bool = False
    ) -> List[Dict]:
        """Get time entry summary grouped by staff member."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            query = """
                SELECT
                    staff_id,
                    SUM(hours) as total_hours,
                    SUM(CASE WHEN billable = 1 THEN hours ELSE 0 END) as billable_hours,
                    SUM(CASE WHEN billable = 1 THEN hours * rate ELSE 0 END) as billable_value,
                    COUNT(*) as entry_count,
                    COUNT(DISTINCT case_id) as case_count
                FROM cached_time_entries
                WHERE 1=1
            """
            params = []

            if start_date:
                query += " AND entry_date >= ?"
                params.append(start_date)
            if end_date:
                query += " AND entry_date <= ?"
                params.append(end_date)
            if billable_only:
                query += " AND billable = 1"

            query += " GROUP BY staff_id ORDER BY total_hours DESC"
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    # ========== Documents Cache Methods ==========

    def upsert_document(self, document: Dict) -> None:
        """Insert or update a document in the cache."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            case = document.get('case', {}) or {}
            folder = document.get('folder', {}) or {}

            cursor.execute("""
                INSERT INTO cached_documents
                (id, name, filename, path, description, assigned_date,
                 case_id, folder_id, created_at, updated_at, data_json, cached_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    filename = excluded.filename,
                    path = excluded.path,
                    description = excluded.description,
                    assigned_date = excluded.assigned_date,
                    case_id = excluded.case_id,
                    folder_id = excluded.folder_id,
                    created_at = excluded.created_at,
                    updated_at = excluded.updated_at,
                    data_json = excluded.data_json,
                    cached_at = CURRENT_TIMESTAMP
            """, (
                document.get('id'),
                document.get('name'),
                document.get('filename'),
                document.get('path'),
                document.get('description'),
                document.get('assigned_date'),
                case.get('id') if isinstance(case, dict) else case,
                folder.get('id') if isinstance(folder, dict) else folder,
                document.get('created_at'),
                document.get('updated_at'),
                json.dumps(document),
            ))

    def get_documents(
        self,
        case_id: int = None,
        name_pattern: str = None
    ) -> List[Dict]:
        """Get documents from cache with optional filters."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT data_json FROM cached_documents WHERE 1=1"
            params = []

            if case_id:
                query += " AND case_id = ?"
                params.append(case_id)
            if name_pattern:
                query += " AND name LIKE ?"
                params.append(f"%{name_pattern}%")

            query += " ORDER BY created_at DESC"
            cursor.execute(query, params)
            return [json.loads(row['data_json']) for row in cursor.fetchall()]

    def get_document_stats(self) -> Dict:
        """Get document statistics."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT
                    COUNT(*) as total_documents,
                    COUNT(DISTINCT case_id) as cases_with_documents,
                    MIN(created_at) as oldest_document,
                    MAX(created_at) as newest_document
                FROM cached_documents
            """)
            row = cursor.fetchone()
            return dict(row) if row else {}


# Singleton cache instance
_cache_instance = None


def get_cache() -> MyCaseCache:
    """Get or create a singleton cache instance."""
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = MyCaseCache()
    return _cache_instance


if __name__ == "__main__":
    # Test the cache
    cache = get_cache()
    print(f"Cache initialized at: {cache.db_path}")

    # Show sync status
    status = cache.get_all_sync_status()
    print(f"Sync status: {status}")
