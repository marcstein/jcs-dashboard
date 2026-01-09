"""
MyCase Sync Manager

Orchestrates syncing data from MyCase API to local cache.
Supports both full sync and incremental updates by comparing
updated_at timestamps between API and cache.
"""
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable, Tuple
from dataclasses import dataclass

from api_client import get_client, MyCaseClient
from cache import get_cache, MyCaseCache


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
    Manages syncing MyCase API data to local cache.

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

    def __init__(self, client: MyCaseClient = None, cache: MyCaseCache = None):
        self.client = client or get_client()
        self.cache = cache or get_cache()

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
        needs_full = force_full or self.cache.needs_full_sync(entity_type, max_cache_age_hours)

        # Get cached updated_at timestamps for comparison
        cached_timestamps = self.cache.get_cached_updated_at(entity_type)

        # Perform sync
        result = sync_methods[entity_type](cached_timestamps, needs_full)
        result.duration_seconds = time.time() - start_time

        # Update sync metadata
        self.cache.update_sync_status(
            entity_type=entity_type,
            total_records=result.total_in_cache,
            sync_duration=result.duration_seconds,
            full_sync=needs_full,
            error=result.error
        )

        return result

    def _sync_cases(self, cached_timestamps: Dict[int, str], full_sync: bool) -> SyncResult:
        """Sync cases from API to cache."""
        # Fetch all cases from API
        print("  Fetching cases from API...")
        cases = self.client.get_all_pages(
            self.client.get_cases,
            page_delay=0.3,
            per_page=100
        )

        inserted, updated, unchanged = 0, 0, 0

        for case in cases:
            case_id = case.get('id')
            api_updated = case.get('updated_at')
            cached_updated = cached_timestamps.get(case_id)

            if cached_updated is None:
                # New record
                self.cache.upsert_case(case)
                inserted += 1
            elif api_updated != cached_updated:
                # Updated record
                self.cache.upsert_case(case)
                updated += 1
            else:
                unchanged += 1

        return SyncResult(
            entity_type='cases',
            total_in_api=len(cases),
            total_in_cache=self.cache.get_cached_count('cases'),
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

        for contact in contacts:
            contact_id = contact.get('id')
            api_updated = contact.get('updated_at')
            cached_updated = cached_timestamps.get(contact_id)

            if cached_updated is None:
                self.cache.upsert_contact(contact)
                inserted += 1
            elif api_updated != cached_updated:
                self.cache.upsert_contact(contact)
                updated += 1
            else:
                unchanged += 1

        return SyncResult(
            entity_type='contacts',
            total_in_api=len(contacts),
            total_in_cache=self.cache.get_cached_count('contacts'),
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

        for client in clients:
            client_id = client.get('id')
            api_updated = client.get('updated_at')
            cached_updated = cached_timestamps.get(client_id)

            if cached_updated is None:
                self.cache.upsert_client(client)
                inserted += 1
            elif api_updated != cached_updated:
                self.cache.upsert_client(client)
                updated += 1
            else:
                unchanged += 1

        return SyncResult(
            entity_type='clients',
            total_in_api=len(clients),
            total_in_cache=self.cache.get_cached_count('clients'),
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

        for invoice in invoices:
            invoice_id = invoice.get('id')
            api_updated = invoice.get('updated_at')
            cached_updated = cached_timestamps.get(invoice_id)

            if cached_updated is None:
                self.cache.upsert_invoice(invoice)
                inserted += 1
            elif api_updated != cached_updated:
                self.cache.upsert_invoice(invoice)
                updated += 1
            else:
                unchanged += 1

        return SyncResult(
            entity_type='invoices',
            total_in_api=len(invoices),
            total_in_cache=self.cache.get_cached_count('invoices'),
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

        for event in events:
            event_id = event.get('id')
            api_updated = event.get('updated_at')
            cached_updated = cached_timestamps.get(event_id)

            if cached_updated is None:
                self.cache.upsert_event(event)
                inserted += 1
            elif api_updated != cached_updated:
                self.cache.upsert_event(event)
                updated += 1
            else:
                unchanged += 1

        return SyncResult(
            entity_type='events',
            total_in_api=len(events),
            total_in_cache=self.cache.get_cached_count('events'),
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

        for task in tasks:
            task_id = task.get('id')
            api_updated = task.get('updated_at')
            cached_updated = cached_timestamps.get(task_id)

            if cached_updated is None:
                self.cache.upsert_task(task)
                inserted += 1
            elif api_updated != cached_updated:
                self.cache.upsert_task(task)
                updated += 1
            else:
                unchanged += 1

        return SyncResult(
            entity_type='tasks',
            total_in_api=len(tasks),
            total_in_cache=self.cache.get_cached_count('tasks'),
            inserted=inserted,
            updated=updated,
            unchanged=unchanged,
            duration_seconds=0
        )

    def _sync_staff(self, cached_timestamps: Dict[int, str], full_sync: bool) -> SyncResult:
        """Sync staff from API to cache."""
        print("  Fetching staff from API...")
        # Staff endpoint returns all at once (small dataset)
        staff_list = self.client.get_staff()

        inserted, updated, unchanged = 0, 0, 0

        for staff in staff_list:
            staff_id = staff.get('id')
            api_updated = staff.get('updated_at')
            cached_updated = cached_timestamps.get(staff_id)

            if cached_updated is None:
                self.cache.upsert_staff(staff)
                inserted += 1
            elif api_updated != cached_updated:
                self.cache.upsert_staff(staff)
                updated += 1
            else:
                unchanged += 1

        return SyncResult(
            entity_type='staff',
            total_in_api=len(staff_list),
            total_in_cache=self.cache.get_cached_count('staff'),
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

        for payment in payments:
            payment_id = payment.get('id')
            api_updated = payment.get('updated_at')
            cached_updated = cached_timestamps.get(payment_id)

            if cached_updated is None:
                self.cache.upsert_payment(payment)
                inserted += 1
            elif api_updated != cached_updated:
                self.cache.upsert_payment(payment)
                updated += 1
            else:
                unchanged += 1

        return SyncResult(
            entity_type='payments',
            total_in_api=len(payments),
            total_in_cache=self.cache.get_cached_count('payments'),
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

        for entry in entries:
            entry_id = entry.get('id')
            api_updated = entry.get('updated_at')
            cached_updated = cached_timestamps.get(entry_id)

            if cached_updated is None:
                self.cache.upsert_time_entry(entry)
                inserted += 1
            elif api_updated != cached_updated:
                self.cache.upsert_time_entry(entry)
                updated += 1
            else:
                unchanged += 1

        return SyncResult(
            entity_type='time_entries',
            total_in_api=len(entries),
            total_in_cache=self.cache.get_cached_count('time_entries'),
            inserted=inserted,
            updated=updated,
            unchanged=unchanged,
            duration_seconds=0
        )

    def _sync_documents(self, cached_timestamps: Dict[int, str], full_sync: bool) -> SyncResult:
        """Sync documents from API to cache (fetches per-case)."""
        import sqlite3

        # Get all case IDs from cache
        print("  Fetching documents for all cases...")
        with self.cache._get_connection() as conn:
            cursor = conn.cursor()
            # Only sync documents for 2025 cases to limit API calls
            cursor.execute("""
                SELECT id FROM cached_cases
                WHERE strftime('%Y', created_at) = '2025'
                ORDER BY created_at DESC
            """)
            case_ids = [row['id'] for row in cursor.fetchall()]

        inserted, updated, unchanged = 0, 0, 0
        total_docs = 0

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
                        self.cache.upsert_document(doc)
                        inserted += 1
                    elif api_updated != cached_updated:
                        self.cache.upsert_document(doc)
                        updated += 1
                    else:
                        unchanged += 1

                time.sleep(0.1)  # Rate limiting
            except Exception as e:
                # Skip cases with document fetch errors
                continue

        return SyncResult(
            entity_type='documents',
            total_in_api=total_docs,
            total_in_cache=self.cache.get_cached_count('documents'),
            inserted=inserted,
            updated=updated,
            unchanged=unchanged,
            duration_seconds=0
        )

    def get_sync_summary(self) -> str:
        """Get a summary of sync status for all entity types."""
        status_list = self.cache.get_all_sync_status()

        if not status_list:
            return "No sync history found. Run a sync first."

        lines = ["MyCase Cache Sync Status", "=" * 50]

        for status in status_list:
            entity = status['entity_type']
            records = status['total_records'] or 0
            last_sync = status.get('last_incremental_sync') or status.get('last_full_sync')
            duration = status.get('sync_duration_seconds') or 0
            error = status.get('last_error')

            if last_sync:
                last_sync_dt = datetime.fromisoformat(last_sync)
                age = datetime.now() - last_sync_dt
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


def get_sync_manager() -> SyncManager:
    """Get or create a singleton sync manager."""
    global _sync_manager
    if _sync_manager is None:
        _sync_manager = SyncManager()
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
