"""
Clio Sync Manager

Orchestrates syncing data from Clio Manage API v4 to PostgreSQL cache.
Supports both full sync and incremental updates using Clio's
updated_since parameter for efficient delta fetches.

Unlike MyCase (which has no server-side updated_since filter), Clio
supports ?updated_since=ISO8601 on most endpoints, so incremental
syncs only fetch changed records from the API.
"""
import time
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass

from clio_client import ClioClient, ClioAPIError
from db.clio_cache import (
    ensure_clio_cache_tables,
    batch_upsert_matters,
    batch_upsert_contacts,
    batch_upsert_bills,
    batch_upsert_tasks,
    batch_upsert_users,
    batch_upsert_activities,
    batch_upsert_calendar_entries,
    batch_upsert_payments,
    batch_upsert_trust_line_items,
    batch_upsert_practice_areas,
    batch_upsert_matter_stages,
    get_clio_sync_status,
    update_clio_sync_status,
    get_clio_cached_count,
)

logger = logging.getLogger(__name__)


@dataclass
class ClioSyncResult:
    """Result of a single entity sync operation."""
    entity_type: str
    records_fetched: int
    records_in_cache: int
    duration_seconds: float
    incremental: bool
    error: Optional[str] = None


class ClioSyncManager:
    """
    Manages syncing Clio Manage API data to PostgreSQL cache.

    Strategies:
    - Full sync: Fetch all records (no updated_since filter)
    - Incremental sync: Use updated_since from last sync timestamp —
      Clio supports this server-side, so only changed records are returned.
      Much more efficient than MyCase's client-side diffing.

    Usage:
        manager = ClioSyncManager("firm_id")
        results = manager.sync_all()
        for entity, result in results.items():
            print(f"{entity}: {result.records_fetched} records ({result.duration_seconds:.1f}s)")
    """

    # Entity sync order — reference data first, then core, then derived
    ENTITY_ORDER = [
        "practice_areas",
        "matter_stages",
        "users",
        "contacts",
        "matters",
        "tasks",
        "bills",
        "activities",
        "calendar_entries",
        "payments",
        "trust_line_items",
    ]

    def __init__(self, firm_id: str, client: ClioClient = None):
        self.firm_id = firm_id
        self.client = client or ClioClient(firm_id)
        self._owns_client = client is None

    def sync_all(
        self,
        force_full: bool = False,
        entities: List[str] = None,
    ) -> Dict[str, ClioSyncResult]:
        """
        Sync all or specified entity types from Clio.

        Args:
            force_full: Skip incremental, fetch everything
            entities: Specific entities to sync (default: all)

        Returns:
            Dict mapping entity_type → ClioSyncResult
        """
        ensure_clio_cache_tables()

        to_sync = entities or self.ENTITY_ORDER
        results = {}

        logger.info("Starting Clio sync for firm %s (%d entities%s)",
                     self.firm_id, len(to_sync),
                     ", FULL" if force_full else "")

        total_start = time.time()

        for entity_type in to_sync:
            if entity_type not in self.ENTITY_ORDER:
                logger.warning("Unknown Clio entity type: %s, skipping", entity_type)
                continue
            result = self._sync_entity(entity_type, force_full=force_full)
            results[entity_type] = result

        total_duration = time.time() - total_start
        total_records = sum(r.records_fetched for r in results.values())
        errors = [r for r in results.values() if r.error]

        logger.info(
            "Clio sync complete for firm %s: %d records across %d entities in %.1fs (%d errors)",
            self.firm_id, total_records, len(results), total_duration, len(errors),
        )

        return results

    def _sync_entity(self, entity_type: str, force_full: bool = False) -> ClioSyncResult:
        """Sync a single entity type."""
        start = time.time()

        # Determine if we can do incremental
        updated_since = None
        if not force_full:
            sync_status = get_clio_sync_status(self.firm_id, entity_type)
            if sync_status:
                last_sync = sync_status.get("last_incremental_sync") or sync_status.get("last_full_sync")
                if last_sync:
                    if isinstance(last_sync, str):
                        last_sync = datetime.fromisoformat(last_sync)
                    # Overlap by 5 minutes to catch edge cases
                    updated_since = last_sync - timedelta(minutes=5)

        incremental = updated_since is not None

        try:
            records = self._fetch_entity(entity_type, updated_since=updated_since)
            self._upsert_entity(entity_type, records)

            duration = time.time() - start
            cache_count = get_clio_cached_count(self.firm_id, entity_type)

            update_clio_sync_status(
                self.firm_id, entity_type,
                total_records=cache_count,
                sync_duration=duration,
                full_sync=not incremental,
            )

            logger.info(
                "Synced Clio %s for firm %s: %d records fetched (%s) in %.1fs, %d total in cache",
                entity_type, self.firm_id, len(records),
                "incremental" if incremental else "full",
                duration, cache_count,
            )

            return ClioSyncResult(
                entity_type=entity_type,
                records_fetched=len(records),
                records_in_cache=cache_count,
                duration_seconds=duration,
                incremental=incremental,
            )

        except Exception as e:
            duration = time.time() - start
            error_msg = str(e)
            logger.error("Error syncing Clio %s for firm %s: %s",
                         entity_type, self.firm_id, error_msg)

            update_clio_sync_status(
                self.firm_id, entity_type,
                total_records=0,
                sync_duration=duration,
                error=error_msg,
            )

            return ClioSyncResult(
                entity_type=entity_type,
                records_fetched=0,
                records_in_cache=get_clio_cached_count(self.firm_id, entity_type),
                duration_seconds=duration,
                incremental=incremental,
                error=error_msg,
            )

    def _fetch_entity(self, entity_type: str, updated_since: datetime = None) -> List[dict]:
        """Fetch records from Clio API for an entity type."""
        fetch_map = {
            "matters": lambda us: self.client.get_all_matters(updated_since=us),
            "contacts": lambda us: self.client.get_all_contacts(updated_since=us),
            "bills": lambda us: self.client.get_all_bills(updated_since=us),
            "tasks": lambda us: self.client.get_all_tasks(updated_since=us),
            "users": lambda _: self.client.get_all_users(),
            "activities": lambda us: self.client.get_all_activities(updated_since=us),
            "calendar_entries": lambda us: self.client.get_all_calendar_entries(updated_since=us),
            "payments": lambda us: self.client.get_all_payments(updated_since=us),
            "trust_line_items": lambda us: self.client.get_all_trust_line_items(updated_since=us),
            "practice_areas": lambda _: self.client.get_practice_areas(),
            "matter_stages": lambda _: self.client.get_matter_stages(),
        }

        fetcher = fetch_map.get(entity_type)
        if not fetcher:
            raise ValueError(f"Unknown entity type: {entity_type}")

        return fetcher(updated_since)

    def _upsert_entity(self, entity_type: str, records: List[dict]):
        """Upsert fetched records into cache."""
        if not records:
            return

        upsert_map = {
            "matters": batch_upsert_matters,
            "contacts": batch_upsert_contacts,
            "bills": batch_upsert_bills,
            "tasks": batch_upsert_tasks,
            "users": batch_upsert_users,
            "activities": batch_upsert_activities,
            "calendar_entries": batch_upsert_calendar_entries,
            "payments": batch_upsert_payments,
            "trust_line_items": batch_upsert_trust_line_items,
            "practice_areas": batch_upsert_practice_areas,
            "matter_stages": batch_upsert_matter_stages,
        }

        upserter = upsert_map.get(entity_type)
        if not upserter:
            raise ValueError(f"Unknown entity type: {entity_type}")

        upserter(self.firm_id, records)

    def test_connection(self) -> Dict:
        """Test the Clio API connection."""
        return self.client.test_connection()

    def get_sync_summary(self) -> Dict[str, dict]:
        """Get a summary of all entity sync statuses."""
        summary = {}
        for entity_type in self.ENTITY_ORDER:
            status = get_clio_sync_status(self.firm_id, entity_type)
            count = get_clio_cached_count(self.firm_id, entity_type)
            summary[entity_type] = {
                "cached_records": count,
                "last_sync": (status.get("last_incremental_sync") or status.get("last_full_sync"))
                             if status else None,
                "last_error": status.get("last_error") if status else None,
                "duration": status.get("sync_duration_seconds") if status else None,
            }
        return summary

    def close(self):
        """Close the API client if we own it."""
        if self._owns_client:
            self.client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
