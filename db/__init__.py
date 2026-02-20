"""
db/ — Unified PostgreSQL Database Layer

All data access goes through this package. No SQLite anywhere.
Every table uses firm_id for multi-tenant isolation.

Usage:
    from db.connection import get_connection
    from db.cache import ensure_cache_tables, batch_upsert_cases
    from db.tracking import ensure_tracking_tables, record_dunning_notice
    from db.phases import ensure_phases_tables, record_phase_entry
    from db.promises import ensure_promises_tables, add_promise
    from db.trends import ensure_trends_tables, record_snapshot
    from db.collections import ensure_collections_tables, upsert_noiw_case
    from db.documents import ensure_documents_tables, search_templates
    from db.attorneys import ensure_attorneys_tables, get_primary_attorney

Connection pool is initialized on first use from DATABASE_URL env var.
"""
from db.connection import get_connection, get_pool, close_pool


def ensure_all_tables():
    """Initialize all database tables. Call once at application startup."""
    from db.cache import ensure_cache_tables
    from db.tracking import ensure_tracking_tables
    from db.phases import ensure_phases_tables
    from db.promises import ensure_promises_tables
    from db.trends import ensure_trends_tables
    from db.collections import ensure_collections_tables
    from db.documents import ensure_documents_tables
    from db.attorneys import ensure_attorneys_tables

    ensure_cache_tables()
    ensure_tracking_tables()
    ensure_phases_tables()
    ensure_promises_tables()
    ensure_trends_tables()
    ensure_collections_tables()
    ensure_documents_tables()
    ensure_attorneys_tables()


__all__ = [
    "get_connection",
    "get_pool",
    "close_pool",
    "ensure_all_tables",
]
