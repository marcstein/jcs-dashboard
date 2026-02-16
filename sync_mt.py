"""
Multi-Tenant Sync Manager

Orchestrates syncing data from MyCase API to local cache for multiple firms.
Each firm's data is synced to their isolated SQLite database.

Key changes from single-tenant:
1. sync_firm() operates on a specific firm
2. sync_all_firms() iterates over all active firms
3. Uses multi-tenant cache and API client
4. Updates platform database sync status
"""
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass

from api_client_mt import get_client_for_firm, MyCaseClient
from cache_mt import get_cache, MyCaseCache, initialize_firm_cache
from platform_db import get_platform_db
from tenant import TenantContextManager


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
    Manages syncing MyCase API data to local cache for a specific firm.
    """

    def __init__(self, firm_id: str):
        """
        Initialize sync manager for a specific firm.
        
        Args:
            firm_id: The firm ID to sync
        """
        self.firm_id = firm_id
        self._client = None
        self._cache = None

    @property
    def client(self) -> MyCaseClient:
        """Lazy-load API client."""
        if self._client is None:
            self._client = get_client_for_firm(self.firm_id)
        return self._client

    @property
    def cache(self) -> MyCaseCache:
        """Lazy-load cache instance."""
        if self._cache is None:
            self._cache = get_cache(self.firm_id)
        return self._cache

    def sync_all(
        self,
        force_full: bool = False,
        max_cache_age_hours: int = 24,
        entities: List[str] = None,
        update_platform_status: bool = True
    ) -> Dict[str, SyncResult]:
        """
        Sync all entity types for this firm.

        Args:
            force_full: Force full sync even if cache is fresh
            max_cache_age_hours: Hours before cache is considered stale
            entities: List of entity types to sync (default: all)
            update_platform_status: If True, update platform DB sync_status.
                Set to False when called from Celery tasks (tasks.py handles
                status updates with more detail including sync_history).

        Returns:
            Dict mapping entity type to SyncResult
        """
        all_entities = ['staff', 'cases', 'contacts', 'clients', 'invoices', 
                        'events', 'tasks', 'payments', 'time_entries']
        to_sync = entities or all_entities

        results = {}
        total_records = 0

        # Update platform DB status to running (skip if Celery manages this)
        db = get_platform_db()
        if update_platform_status:
            db.update_sync_status(self.firm_id, 'running')

        for entity_type in to_sync:
            print(f"\n{'='*50}")
            print(f"[{self.firm_id}] Syncing {entity_type}...")
            print('='*50)

            try:
                result = self.sync_entity(
                    entity_type,
                    force_full=force_full,
                    max_cache_age_hours=max_cache_age_hours
                )
                results[entity_type] = result
                total_records += result.total_in_cache

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

        # Update platform DB with completion status (skip if Celery manages this)
        if update_platform_status:
            errors = [r.error for r in results.values() if r.error]
            if errors:
                db.update_sync_status(
                    self.firm_id, 'failed',
                    records_synced=total_records,
                    error_message='; '.join(errors[:3])  # First 3 errors
                )
            else:
                db.update_sync_status(
                    self.firm_id, 'completed',
                    records_synced=total_records
                )

        return results

    def sync_entity(
        self,
        entity_type: str,
        force_full: bool = False,
        max_cache_age_hours: int = 24
    ) -> SyncResult:
        """Sync a single entity type."""
        start_time = time.time()

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
        }

        if entity_type not in sync_methods:
            raise ValueError(f"Unknown entity type: {entity_type}")

        needs_full = force_full or self.cache.needs_full_sync(entity_type, max_cache_age_hours)
        cached_timestamps = self.cache.get_cached_updated_at(entity_type)

        result = sync_methods[entity_type](cached_timestamps, needs_full)
        result.duration_seconds = time.time() - start_time

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
                self.cache.upsert_case(case)
                inserted += 1
            elif api_updated != cached_updated:
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

    def get_sync_summary(self) -> str:
        """Get a summary of sync status for this firm."""
        status_list = self.cache.get_all_sync_status()

        if not status_list:
            return f"[{self.firm_id}] No sync history found."

        lines = [f"[{self.firm_id}] Sync Status", "=" * 50]

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


# =============================================================================
# Multi-Firm Sync Functions
# =============================================================================

def sync_firm(firm_id: str, force_full: bool = False) -> Dict[str, SyncResult]:
    """
    Sync all data for a specific firm.
    
    Args:
        firm_id: The firm ID to sync
        force_full: Force full sync even if cache is fresh
        
    Returns:
        Dict mapping entity type to SyncResult
    """
    manager = SyncManager(firm_id)
    return manager.sync_all(force_full=force_full)


def sync_all_active_firms(force_full: bool = False) -> Dict[str, Dict[str, SyncResult]]:
    """
    Sync all active firms.
    
    Gets list of active firms from platform database and syncs each one.
    
    Args:
        force_full: Force full sync for all firms
        
    Returns:
        Dict mapping firm_id to their sync results
    """
    db = get_platform_db()
    firms = db.get_active_firms()
    
    all_results = {}
    
    print(f"\nSyncing {len(firms)} active firms...")
    
    for firm in firms:
        print(f"\n{'='*70}")
        print(f"SYNCING FIRM: {firm.name} ({firm.id})")
        print('='*70)
        
        try:
            results = sync_firm(firm.id, force_full=force_full)
            all_results[firm.id] = results
        except Exception as e:
            print(f"ERROR syncing firm {firm.id}: {e}")
            all_results[firm.id] = {'error': str(e)}
    
    return all_results


def initial_sync_firm(firm_id: str) -> Dict[str, SyncResult]:
    """
    Perform initial sync for a newly connected firm.
    
    This is called after a firm completes MyCase OAuth connection.
    
    Args:
        firm_id: The firm ID to sync
        
    Returns:
        Dict mapping entity type to SyncResult
    """
    # Initialize the firm's cache database
    initialize_firm_cache(firm_id)
    
    # Perform full sync
    return sync_firm(firm_id, force_full=True)


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python sync_mt.py <firm_id>           - Sync specific firm")
        print("  python sync_mt.py <firm_id> full      - Force full sync")
        print("  python sync_mt.py all                 - Sync all active firms")
        sys.exit(1)
    
    if sys.argv[1] == 'all':
        results = sync_all_active_firms()
        print(f"\nCompleted sync for {len(results)} firms")
    else:
        firm_id = sys.argv[1]
        force_full = len(sys.argv) > 2 and sys.argv[2] == 'full'
        
        manager = SyncManager(firm_id)
        results = manager.sync_all(force_full=force_full)
        print(f"\n{manager.get_sync_summary()}")
