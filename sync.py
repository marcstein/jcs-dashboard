"""
MyCase Sync Manager

Orchestrates syncing data from MyCase API to PostgreSQL cache.
Supports both full sync and incremental updates by comparing
updated_at timestamps between API and cache.
"""
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable, Tuple
from dataclasses import dataclass

from api_client import get_client, MyCaseClient
from db.cache import (
    batch_upsert_cases,
    batch_upsert_contacts,
    batch_upsert_clients,
    batch_upsert_invoices,
    batch_upsert_events,
    batch_upsert_tasks,
    batch_upsert_staff,
    batch_upsert_payments,
    batch_upsert_time_entries,
    batch_upsert_documents,
    get_cached_count,
    get_cached_updated_at,
    get_excluded_staff_ids,
    update_sync_status,
)
from db.connection import get_connection


@dataclass
class SyncResult:
    """Result of a sync operation."""
    entity_type: str
    total_in_api: int
    total_in_cache: int
    inserted: int
    updated: int
    unchanged: int
    duration_seconds: float
    error: Optional[str] = None

    @property
    def changes(self) -> int:
        return self.inserted + self.updated


class SyncManager:
    """
    Manages syncing MyCase API data to PostgreSQL cache.

    Strategies:
    - Full sync: Fetch all records and update cache (slow but complete)
    - Incremental sync: Compare updated_at timestamps, only process changes (fast)

    The incremental sync works by:
    1. Fetching all records from API (required since API doesn't filter by updated_since)
    2. Comparing each record's updated_at with cached version
    3. Only upserting records that have changed

    While this still fetches all data from the API, it:
    - Reduces database writes significantly
    - Enables fast reads from local cache
    - Provides accurate change detection for notifications
    """

    def __init__(self, client: MyCaseClient = None, firm_id: str = None):
        """
        Initialize sync manager.

        Args:
            client: MyCase API client (default: create new)
            firm_id: Firm ID for multi-tenant isolation (default: 'default')
        """
        self.client = client or get_client()
        self.firm_id = firm_id or "default"

    def sync_all(
        self,
        force_full: bool = False,
        max_cache_age_hours: int = 24,
        entities: List[str] = None
    ) -> Dict[str, SyncResult]:
        """
        Sync all entity types or specified entities.

        Args:
            force_full: Force full sync even if cache is fresh
            max_cache_age_hours: Hours before cache is considered stale
            entities: List of entity types to sync (default: all)

        Returns:
            Dict mapping entity type to SyncResult
        """
        all_entities = ['staff', 'cases', 'contacts', 'clients', 'invoices', 'events', 'tasks', 'payments', 'time_entries', 'documents']
        to_sync = entities or all_entities

        results = {}
        for entity_type in to_sync:
            print(f"\n{'='*50}")
            print(f"Syncing {entity_type}...")
            print('='*50)

            try:
                result = self.sync_entity(
                    entity_type,
                    force_full=force_full,
                    max_cache_age_hours=max_cache_age_hours
                )
                results[entity_type] = result

                print(f"  Completed: {result.inserted} new, {result.updated} updated, "
                      f"{result.unchanged} unchanged ({result.duration_seconds:.1f}s)")

            except Exception as e:
                print(f"  ERROR: {e}")
                results[entity_type] = SyncResult(
                    entity_type=entity_type,
                    total_in_api=0,
                    total_in_cache=0,
                    inserted=0,
                    updated=0,
                    unchanged=0,
                    duration_seconds=0,
                    error=str(e)
                )

        return results

    def sync_entity(
        self,
        entity_type: str,
        force_full: bool = False,
        max_cache_age_hours: int = 24
    ) -> SyncResult:
        """
        Sync a single entity type.

        Args:
            entity_type: One of 'cases', 'contacts', 'invoices', 'events', 'tasks', 'staff', 'payments'
            force_full: Force full sync
            max_cache_age_hours: Hours before cache needs refresh

        Returns:
            SyncResult with statistics
        """
        start_time = time.time()

        # Map entity types to sync methods
        sync_methods = {
            'cases': self._sync_cases,
            'contacts': self._sync_contacts,
            'clients': self._sync_clients,
            'invoices': self._sync_invoices,
            'events': self._sync_events,
            'tasks': self._sync_tasks,
            'staff': self._sync_staff,
            'payments': self._sync_payments,
            'time_entries': self._sync_time_entries,
            'documents': self._sync_documents,
        }

        if entity_type not in sync_methods:
            raise ValueError(f"Unknown entity type: {entity_type}")

        # Check if we need a full sync
        needs_full = force_full or self._needs_full_sync(entity_type, max_cache_age_hours)

        # Get cached updated_at timestamps for comparison
        cached_timestamps = get_cached_updated_at(self.firm_id, entity_type)

        # Perform sync
        result = sync_methods[entity_type](cached_timestamps, needs_full)
        result.duration_seconds = time.time() - start_time

        # Update sync metadata
        update_sync_status(
            firm_id=self.firm_id,
            entity_type=entity_type,
            total_records=result.total_in_cache,
            sync_duration=result.duration_seconds,
            full_sync=needs_full,
            error=result.error
        )

        return result

    def _needs_full_sync(self, entity_type: str, max_cache_age_hours: int) -> bool:
        """Check if a full sync is needed based on cache age."""
        from db.cache import get_sync_status

        status = get_sync_status(self.firm_id, entity_type)
        if status is None:
            return True

        last_sync = status.get('last_full_sync') or status.get('last_incremental_sync')
        if last_sync is None:
            return True

        if isinstance(last_sync, str):
            last_sync = datetime.fromisoformat(last_sync)

        age_hours = (datetime.utcnow() - last_sync).total_seconds() / 3600
        return age_hours > max_cache_age_hours

    def _sync_cases(self, cached_timestamps: Dict[int, str], full_sync: bool) -> SyncResult:
        """Sync cases from API to cache."""
        print("  Fetching cases from API...")
        cases = self.client.get_all_pages(
            self.client.get_cases,
            page_delay=0.3,
            per_page=100
        )

        inserted, updated, unchanged = 0, 0, 0
        to_upsert = []

        for case in cases:
            case_id = case.get('id')
            api_updated = case.get('updated_at')
            cached_updated = cached_timestamps.get(case_id)

            if cached_updated is None:
                inserted += 1
                to_upsert.append(case)
            elif api_updated != cached_updated:
                updated += 1
                to_upsert.append(case)
            else:
                unchanged += 1

        if to_upsert:
            batch_upsert_cases(self.firm_id, to_upsert)

        return SyncResult(
            entity_type='cases',
            total_in_api=len(cases),
            total_in_cache=get_cached_count(self.firm_id, 'cases'),
            inserted=inserted,
            updated=updated,
            unchanged=unchanged,
            duration_seconds=0
        )

    def _sync_contacts(self, cached_timestamps: Dict[int, str], full_sync: bool) -> SyncResult:
        """Sync contacts from API to cache."""
        print("  Fetching contacts from API...")
        contacts = self.client.get_all_pages(
            self.client.get_contacts,
            page_delay=0.3,
            per_page=100
        )

        inserted, updated, unchanged = 0, 0, 0
        to_upsert = []

        for contact in contacts:
            contact_id = contact.get('id')
            api_updated = contact.get('updated_at')
            cached_updated = cached_timestamps.get(contact_id)

            if cached_updated is None:
                inserted += 1
                to_upsert.append(contact)
            elif api_updated != cached_updated:
                updated += 1
                to_upsert.append(contact)
            else:
                unchanged += 1

        if to_upsert:
            batch_upsert_contacts(self.firm_id, to_upsert)

        return SyncResult(
            entity_type='contacts',
            total_in_api=len(contacts),
            total_in_cache=get_cached_count(self.firm_id, 'contacts'),
            inserted=inserted,
            updated=updated,
            unchanged=unchanged,
            duration_seconds=0
        )

    def _sync_clients(self, cached_timestamps: Dict[int, str], full_sync: bool) -> SyncResult:
        """Sync clients from API to cache (includes full address data)."""
        print("  Fetching clients from API (with addresses)...")
        clients = self.client.get_all_pages(
            self.client.get_clients,
            page_delay=0.3,
            per_page=100
        )

        inserted, updated, unchanged = 0, 0, 0
        to_upsert = []

        for client in clients:
            client_id = client.get('id')
            api_updated = client.get('updated_at')
            cached_updated = cached_timestamps.get(client_id)

            if cached_updated is None:
                inserted += 1
                to_upsert.append(client)
            elif api_updated != cached_updated:
                updated += 1
                to_upsert.append(client)
            else:
                unchanged += 1

        if to_upsert:
            batch_upsert_clients(self.firm_id, to_upsert)

        return SyncResult(
            entity_type='clients',
            total_in_api=len(clients),
            total_in_cache=get_cached_count(self.firm_id, 'clients'),
            inserted=inserted,
            updated=updated,
            unchanged=unchanged,
            duration_seconds=0
        )

    def _sync_invoices(self, cached_timestamps: Dict[int, str], full_sync: bool) -> SyncResult:
        """Sync invoices from API to cache."""
        print("  Fetching invoices from API...")
        invoices = self.client.get_all_pages(
            self.client.get_invoices,
            page_delay=0.3,
            per_page=100
        )

        inserted, updated, unchanged = 0, 0, 0
        to_upsert = []

        for invoice in invoices:
            invoice_id = invoice.get('id')
            api_updated = invoice.get('updated_at')
            cached_updated = cached_timestamps.get(invoice_id)

            if cached_updated is None:
                inserted += 1
                to_upsert.append(invoice)
            elif api_updated != cached_updated:
                updated += 1
                to_upsert.append(invoice)
            else:
                unchanged += 1

        if to_upsert:
            batch_upsert_invoices(self.firm_id, to_upsert)

        return SyncResult(
            entity_type='invoices',
            total_in_api=len(invoices),
            total_in_cache=get_cached_count(self.firm_id, 'invoices'),
            inserted=inserted,
            updated=updated,
            unchanged=unchanged,
            duration_seconds=0
        )

    def _sync_events(self, cached_timestamps: Dict[int, str], full_sync: bool) -> SyncResult:
        """Sync events from API to cache."""
        print("  Fetching events from API...")
        events = self.client.get_all_pages(
            self.client.get_events,
            page_delay=0.3,
            per_page=100
        )

        inserted, updated, unchanged = 0, 0, 0
        to_upsert = []

        for event in events:
            event_id = event.get('id')
            api_updated = event.get('updated_at')
            cached_updated = cached_timestamps.get(event_id)

            if cached_updated is None:
                inserted += 1
                to_upsert.append(event)
            elif api_updated != cached_updated:
                updated += 1
                to_upsert.append(event)
            else:
                unchanged += 1

        if to_upsert:
            batch_upsert_events(self.firm_id, to_upsert)

        return SyncResult(
            entity_type='events',
            total_in_api=len(events),
            total_in_cache=get_cached_count(self.firm_id, 'events'),
            inserted=inserted,
            updated=updated,
            unchanged=unchanged,
            duration_seconds=0
        )

    def _sync_tasks(self, cached_timestamps: Dict[int, str], full_sync: bool) -> SyncResult:
        """Sync tasks from API to cache."""
        print("  Fetching tasks from API...")
        tasks = self.client.get_all_pages(
            self.client.get_tasks,
            page_delay=0.3,
            per_page=100
        )

        inserted, updated, unchanged = 0, 0, 0
        to_upsert = []

        for task in tasks:
            task_id = task.get('id')
            api_updated = task.get('updated_at')
            cached_updated = cached_timestamps.get(task_id)

            if cached_updated is None:
                inserted += 1
                to_upsert.append(task)
            elif api_updated != cached_updated:
                updated += 1
                to_upsert.append(task)
            else:
                unchanged += 1

        if to_upsert:
            batch_upsert_tasks(self.firm_id, to_upsert)

        return SyncResult(
            entity_type='tasks',
            total_in_api=len(tasks),
            total_in_cache=get_cached_count(self.firm_id, 'tasks'),
            inserted=inserted,
            updated=updated,
            unchanged=unchanged,
            duration_seconds=0
        )

    def _sync_staff(self, cached_timestamps: Dict[int, str], full_sync: bool) -> SyncResult:
        """Sync staff from API to cache, skipping excluded staff."""
        print("  Fetching staff from API...")
        # Staff endpoint returns all at once (small dataset)
        staff_list = self.client.get_staff()

        # Load excluded staff IDs so we don't re-add deleted/inactive staff
        excluded_ids = get_excluded_staff_ids(self.firm_id)
        if excluded_ids:
            print(f"  Skipping {len(excluded_ids)} excluded staff members")

        inserted, updated, unchanged, skipped = 0, 0, 0, 0
        to_upsert = []

        for staff in staff_list:
            staff_id = staff.get('id')

            # Skip excluded staff — they were intentionally removed
            if staff_id in excluded_ids:
                skipped += 1
                continue

            api_updated = staff.get('updated_at')
            cached_updated = cached_timestamps.get(staff_id)

            if cached_updated is None:
                inserted += 1
                to_upsert.append(staff)
            elif api_updated != cached_updated:
                updated += 1
                to_upsert.append(staff)
            else:
                unchanged += 1

        if to_upsert:
            batch_upsert_staff(self.firm_id, to_upsert)

        return SyncResult(
            entity_type='staff',
            total_in_api=len(staff_list),
            total_in_cache=get_cached_count(self.firm_id, 'staff'),
            inserted=inserted,
            updated=updated,
            unchanged=unchanged,
            duration_seconds=0
        )

    def _sync_payments(self, cached_timestamps: Dict[int, str], full_sync: bool) -> SyncResult:
        """Sync payments from API to cache."""
        print("  Fetching payments from API...")
        payments = self.client.get_all_pages(
            self.client.get_payments,
            page_delay=0.3,
            per_page=100
        )

        inserted, updated, unchanged = 0, 0, 0
        to_upsert = []

        for payment in payments:
            payment_id = payment.get('id')
            api_updated = payment.get('updated_at')
            cached_updated = cached_timestamps.get(payment_id)

            if cached_updated is None:
                inserted += 1
                to_upsert.append(payment)
            elif api_updated != cached_updated:
                updated += 1
                to_upsert.append(payment)
            else:
                unchanged += 1

        if to_upsert:
            batch_upsert_payments(self.firm_id, to_upsert)

        return SyncResult(
            entity_type='payments',
            total_in_api=len(payments),
            total_in_cache=get_cached_count(self.firm_id, 'payments'),
            inserted=inserted,
            updated=updated,
            unchanged=unchanged,
            duration_seconds=0
        )

    def _sync_time_entries(self, cached_timestamps: Dict[int, str], full_sync: bool) -> SyncResult:
        """Sync time entries from API to cache."""
        print("  Fetching time entries from API...")
        entries = self.client.get_all_pages(
            self.client.get_time_entries,
            page_delay=0.3,
            per_page=100
        )

        inserted, updated, unchanged = 0, 0, 0
        to_upsert = []

        for entry in entries:
            entry_id = entry.get('id')
            api_updated = entry.get('updated_at')
            cached_updated = cached_timestamps.get(entry_id)

            if cached_updated is None:
                inserted += 1
                to_upsert.append(entry)
            elif api_updated != cached_updated:
                updated += 1
                to_upsert.append(entry)
            else:
                unchanged += 1

        if to_upsert:
            batch_upsert_time_entries(self.firm_id, to_upsert)

        return SyncResult(
            entity_type='time_entries',
            total_in_api=len(entries),
            total_in_cache=get_cached_count(self.firm_id, 'time_entries'),
            inserted=inserted,
            updated=updated,
            unchanged=unchanged,
            duration_seconds=0
        )

    def _sync_documents(self, cached_timestamps: Dict[int, str], full_sync: bool) -> SyncResult:
        """Sync documents from API to cache (fetches per-case)."""
        # Get all case IDs from cache
        print("  Fetching documents for all cases...")
        with get_connection() as conn:
            cursor = conn.cursor()
            # Only sync documents for 2025 cases to limit API calls
            cursor.execute("""
                SELECT id FROM cached_cases
                WHERE firm_id = %s
                AND EXTRACT(YEAR FROM created_at) = 2025
                ORDER BY created_at DESC
            """, (self.firm_id,))
            case_ids = [row['id'] for row in cursor.fetchall()]

        inserted, updated, unchanged = 0, 0, 0
        total_docs = 0
        to_upsert = []

        for i, case_id in enumerate(case_ids):
            if i % 50 == 0:
                print(f"    Processing case {i+1}/{len(case_ids)}...")

            try:
                documents = self.client.get_case_documents(case_id)
                total_docs += len(documents)

                for doc in documents:
                    doc_id = doc.get('id')
                    api_updated = doc.get('updated_at')
                    cached_updated = cached_timestamps.get(doc_id)

                    if cached_updated is None:
                        inserted += 1
                        to_upsert.append(doc)
                    elif api_updated != cached_updated:
                        updated += 1
                        to_upsert.append(doc)
                    else:
                        unchanged += 1

                time.sleep(0.1)  # Rate limiting
            except Exception as e:
                # Skip cases with document fetch errors
                continue

        if to_upsert:
            batch_upsert_documents(self.firm_id, to_upsert)

        return SyncResult(
            entity_type='documents',
            total_in_api=total_docs,
            total_in_cache=get_cached_count(self.firm_id, 'documents'),
            inserted=inserted,
            updated=updated,
            unchanged=unchanged,
            duration_seconds=0
        )

    def get_sync_summary(self) -> str:
        """Get a summary of sync status for all entity types."""
        from db.cache import get_all_sync_status

        status_list = get_all_sync_status(self.firm_id)

        if not status_list:
            return "No sync history found. Run a sync first."

        lines = [f"MyCase Cache Sync Status (Firm: {self.firm_id})", "=" * 50]

        for status in status_list:
            entity = status['entity_type']
            records = status.get('total_records') or 0
            last_sync = status.get('last_full_sync') or status.get('last_incremental_sync')
            duration = status.get('sync_duration_seconds') or 0
            error = status.get('last_error')

            if last_sync:
                if isinstance(last_sync, str):
                    last_sync_dt = datetime.fromisoformat(last_sync)
                else:
                    last_sync_dt = last_sync
                age = datetime.utcnow() - last_sync_dt
                age_str = f"{age.seconds // 3600}h {(age.seconds % 3600) // 60}m ago"
            else:
                age_str = "never"

            line = f"{entity:12} | {records:6} records | synced {age_str:15} | {duration:.1f}s"
            if error:
                line += f" | ERROR: {error[:30]}"
            lines.append(line)

        return "\n".join(lines)


# Singleton sync manager
_sync_manager = None


def get_sync_manager(firm_id: str = None) -> SyncManager:
    """Get or create a singleton sync manager."""
    global _sync_manager
    if _sync_manager is None:
        _sync_manager = SyncManager(firm_id=firm_id)
    return _sync_manager


if __name__ == "__main__":
    import sys

    manager = get_sync_manager()

    if len(sys.argv) > 1:
        if sys.argv[1] == "status":
            print(manager.get_sync_summary())
        elif sys.argv[1] == "full":
            print("Running full sync of all entities...")
            results = manager.sync_all(force_full=True)
            print("\n" + manager.get_sync_summary())
        else:
            # Sync specific entity
            entity = sys.argv[1]
            print(f"Syncing {entity}...")
            result = manager.sync_entity(entity)
            print(f"Result: {result}")
    else:
        print("Running incremental sync of all entities...")
        results = manager.sync_all()
        print("\n" + manager.get_sync_summary())
