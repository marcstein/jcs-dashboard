"""
PostgreSQL Connection Pool

Single shared connection pool for the entire application.
All modules use get_connection() — never create connections directly.

Usage:
    from db.connection import get_connection

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM cached_cases WHERE firm_id = %s", (firm_id,))
        rows = cursor.fetchall()
"""
import os
import logging
from contextlib import contextmanager
from typing import Optional

import psycopg2
from psycopg2.pool import ThreadedConnectionPool
from psycopg2.extras import RealDictCursor

logger = logging.getLogger(__name__)

# Module-level pool — initialized lazily on first get_connection() call
_pool: Optional[ThreadedConnectionPool] = None


def _get_database_url() -> str:
    """Get DATABASE_URL from environment. Required."""
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise ValueError(
            "DATABASE_URL environment variable is required. "
            "Example: postgresql://user:pass@host:5432/mycase"
        )
    return url


def get_pool() -> ThreadedConnectionPool:
    """Get or create the shared connection pool."""
    global _pool
    if _pool is None:
        url = _get_database_url()
        min_conn = int(os.environ.get("PG_POOL_MIN", "2"))
        max_conn = int(os.environ.get("PG_POOL_MAX", "10"))
        _pool = ThreadedConnectionPool(
            minconn=min_conn,
            maxconn=max_conn,
            dsn=url,
        )
        logger.info("PostgreSQL connection pool initialized (min=%d, max=%d)", min_conn, max_conn)
    return _pool


def close_pool():
    """Close the connection pool. Call on application shutdown."""
    global _pool
    if _pool is not None:
        _pool.closeall()
        _pool = None
        logger.info("PostgreSQL connection pool closed")


def reset_pool():
    """Close and re-create the pool. Useful for testing or reconnection."""
    close_pool()
    return get_pool()


@contextmanager
def get_connection(autocommit: bool = False):
    """
    Get a connection from the pool as a context manager.

    Commits on success, rolls back on exception, always returns to pool.
    Uses RealDictCursor by default so rows come back as dicts.

    Args:
        autocommit: If True, set connection to autocommit mode (for DDL).

    Usage:
        with get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT 1")

    Note: cursor() returns RealDictCursor by default.
    For execute_values(), create a regular cursor:
        cur = conn.cursor(cursor_factory=psycopg2.extensions.cursor)
    """
    pool = get_pool()
    conn = pool.getconn()
    conn.cursor_factory = RealDictCursor
    if autocommit:
        conn.autocommit = True
    try:
        yield conn
        if not autocommit:
            conn.commit()
    except Exception:
        if not autocommit:
            conn.rollback()
        raise
    finally:
        conn.autocommit = False
        pool.putconn(conn)
