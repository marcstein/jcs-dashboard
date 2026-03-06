"""
PostgreSQL Connection Pool

Single shared connection pool for the entire application.
All modules use get_connection() — never create connections directly.

Includes automatic retry-on-disconnect logic for DigitalOcean Managed
PostgreSQL failover. During standby promotion (~30-60s), existing
connections go stale. The pool detects this and reconnects transparently.

Usage:
    from db.connection import get_connection

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM cached_cases WHERE firm_id = %s", (firm_id,))
        rows = cursor.fetchall()
"""
import os
import time
import logging
from contextlib import contextmanager
from typing import Optional

import psycopg2
from psycopg2.pool import ThreadedConnectionPool
from psycopg2.extras import RealDictCursor

logger = logging.getLogger(__name__)

# Module-level pool — initialized lazily on first get_connection() call
_pool: Optional[ThreadedConnectionPool] = None

# Retry config for failover resilience
MAX_CONN_RETRIES = int(os.environ.get("PG_CONN_RETRIES", "3"))
RETRY_DELAY_SECONDS = float(os.environ.get("PG_RETRY_DELAY", "2.0"))


def _get_database_url() -> str:
    """Get DATABASE_URL from environment. Required."""
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise ValueError(
            "DATABASE_URL environment variable is required. "
            "Example: postgresql://user:pass@host:5432/mycase"
        )
    return url


def _is_connection_error(exc: Exception) -> bool:
    """Check if an exception indicates a broken/stale connection.

    These errors occur during DigitalOcean managed DB failover when the
    primary switches to the standby node. The old connection's TCP socket
    is dead, so we need to discard it and get a fresh one.
    """
    if isinstance(exc, psycopg2.OperationalError):
        msg = str(exc).lower()
        stale_indicators = [
            "server closed the connection unexpectedly",
            "connection reset by peer",
            "could not connect to server",
            "connection refused",
            "connection timed out",
            "ssl connection has been closed unexpectedly",
            "terminating connection due to administrator command",
            "the database system is shutting down",
            "the database system is starting up",
            "cannot execute",  # read-only during promotion
        ]
        return any(indicator in msg for indicator in stale_indicators)
    if isinstance(exc, psycopg2.InterfaceError):
        msg = str(exc).lower()
        return "connection already closed" in msg or "cursor already closed" in msg
    return False


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


def _validate_connection(conn) -> bool:
    """Quick liveness check — catches stale connections before use."""
    try:
        cur = conn.cursor()
        cur.execute("SELECT 1")
        cur.fetchone()
        cur.close()
        return True
    except Exception:
        return False


def _get_healthy_connection(pool):
    """Get a connection from the pool and validate it.

    If the connection is stale (e.g. after failover), discard it and
    rebuild the pool with fresh connections to the new primary.
    """
    conn = pool.getconn()
    if _validate_connection(conn):
        return conn

    # Connection is stale — return it and rebuild the pool
    logger.warning("Stale connection detected, rebuilding pool (possible failover)")
    try:
        pool.putconn(conn, close=True)
    except Exception:
        pass  # Already broken, just discard

    # Reset the pool entirely — all cached connections are likely stale
    new_pool = reset_pool()
    return new_pool.getconn()


@contextmanager
def get_connection(autocommit: bool = False):
    """
    Get a connection from the pool as a context manager.

    Commits on success, rolls back on exception, always returns to pool.
    Uses RealDictCursor by default so rows come back as dicts.

    Includes automatic retry logic for DigitalOcean managed DB failover:
    if the connection drops mid-operation (primary→standby switch), the
    pool rebuilds and the caller gets a clean OperationalError to retry
    their business logic. The connection itself is always returned cleanly.

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
    conn = _get_healthy_connection(pool)
    conn.cursor_factory = RealDictCursor
    if autocommit:
        conn.autocommit = True
    try:
        yield conn
        if not autocommit:
            conn.commit()
    except Exception as exc:
        if not autocommit:
            try:
                conn.rollback()
            except Exception:
                pass  # Connection may already be dead
        # If this was a connection error, rebuild pool so next caller
        # gets a fresh connection to the new primary
        if _is_connection_error(exc):
            logger.warning("Connection error during operation: %s", exc)
            try:
                pool.putconn(conn, close=True)
            except Exception:
                pass
            reset_pool()
            raise  # Re-raise so caller knows the operation failed
        raise
    finally:
        try:
            conn.autocommit = False
            pool.putconn(conn)
        except Exception:
            # Connection is dead — discard it, don't return to pool
            try:
                pool.putconn(conn, close=True)
            except Exception:
                pass


@contextmanager
def get_connection_with_retry(autocommit: bool = False):
    """
    Like get_connection(), but automatically retries on connection failures.

    Use this for idempotent read operations (SELECT queries, reports) where
    retrying is safe. Do NOT use for writes unless the operation is truly
    idempotent (e.g. upserts).

    During DigitalOcean failover (~30-60s), this will retry up to
    MAX_CONN_RETRIES times with RETRY_DELAY_SECONDS between attempts,
    giving the new primary time to accept connections.

    Usage:
        with get_connection_with_retry() as conn:
            cur = conn.cursor()
            cur.execute("SELECT count(*) FROM cached_cases WHERE firm_id = %s", (firm_id,))
    """
    last_exc = None
    for attempt in range(1, MAX_CONN_RETRIES + 1):
        try:
            with get_connection(autocommit=autocommit) as conn:
                yield conn
                return  # Success — exit the retry loop
        except (psycopg2.OperationalError, psycopg2.InterfaceError) as exc:
            last_exc = exc
            if attempt < MAX_CONN_RETRIES:
                delay = RETRY_DELAY_SECONDS * attempt  # Linear backoff
                logger.warning(
                    "Connection failed (attempt %d/%d), retrying in %.1fs: %s",
                    attempt, MAX_CONN_RETRIES, delay, exc,
                )
                time.sleep(delay)
            else:
                logger.error(
                    "Connection failed after %d attempts: %s",
                    MAX_CONN_RETRIES, exc,
                )
    raise last_exc
