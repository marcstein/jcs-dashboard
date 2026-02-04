"""
PostgreSQL Database Connection Manager for LawMetrics.ai

Supports both PostgreSQL (production/multi-firm) and SQLite (local development).
Connection configured via environment variables:
- DATABASE_URL: Full connection string (preferred for Digital Ocean)
- Or individual variables: PG_HOST, PG_PORT, PG_DATABASE, PG_USER, PG_PASSWORD
"""

import os
import logging
from typing import Optional, Dict, Any, List, Tuple
from contextlib import contextmanager
from pathlib import Path

# Try to import psycopg2 for PostgreSQL
try:
    import psycopg2
    import psycopg2.extras
    from psycopg2.pool import ThreadedConnectionPool
    POSTGRES_AVAILABLE = True
except ImportError:
    POSTGRES_AVAILABLE = False
    psycopg2 = None
    ThreadedConnectionPool = None

import sqlite3

logger = logging.getLogger(__name__)


class PostgresConfig:
    """Database configuration from environment variables."""

    def __init__(self):
        # Digital Ocean connection string (preferred)
        self.database_url = os.getenv('DATABASE_URL')

        # Individual PostgreSQL settings (fallback)
        self.pg_host = os.getenv('PG_HOST', 'localhost')
        self.pg_port = os.getenv('PG_PORT', '25060')  # Digital Ocean default
        self.pg_database = os.getenv('PG_DATABASE', 'lawmetrics')
        self.pg_user = os.getenv('PG_USER', 'lawmetrics')
        self.pg_password = os.getenv('PG_PASSWORD', '')
        self.pg_sslmode = os.getenv('PG_SSLMODE', 'require')

        # Pool settings
        self.pool_min = int(os.getenv('PG_POOL_MIN', '2'))
        self.pool_max = int(os.getenv('PG_POOL_MAX', '10'))

        # SQLite fallback paths (for local dev)
        from config import DATA_DIR
        self.sqlite_templates_path = DATA_DIR / "document_engine.db"
        self.sqlite_attorneys_path = DATA_DIR / "attorney_profiles.db"

    @property
    def use_postgres(self) -> bool:
        """Determine if PostgreSQL should be used."""
        return bool(self.database_url or self.pg_password) and POSTGRES_AVAILABLE

    def get_connection_string(self) -> str:
        """Get PostgreSQL connection string."""
        if self.database_url:
            # Digital Ocean format: postgresql://user:password@host:port/database?sslmode=require
            return self.database_url
        return (
            f"postgresql://{self.pg_user}:{self.pg_password}@"
            f"{self.pg_host}:{self.pg_port}/{self.pg_database}"
            f"?sslmode={self.pg_sslmode}"
        )


class PostgresManager:
    """
    PostgreSQL database manager for multi-firm document system.

    Usage:
        db = PostgresManager()
        
        # Query with automatic placeholder conversion
        results = db.query("SELECT * FROM templates WHERE firm_id = ?", (firm_id,))
        
        # Execute insert/update
        db.execute("INSERT INTO firms (id, name) VALUES (?, ?)", (firm_id, name))
        
        # Get single result
        template = db.query_one("SELECT * FROM templates WHERE id = ?", (template_id,))
    """

    _instance = None
    _pool = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self.config = PostgresConfig()
        self._initialized = True

        if self.config.use_postgres:
            try:
                self._init_postgres_pool()
                logger.info(f"PostgreSQL connected: {self.config.pg_host}:{self.config.pg_port}/{self.config.pg_database}")
            except Exception as e:
                logger.warning(f"PostgreSQL connection failed, falling back to SQLite: {e}")
                self._pool = None
        else:
            logger.info(f"Using SQLite fallback: {self.config.sqlite_templates_path}")

    def _init_postgres_pool(self):
        """Initialize PostgreSQL connection pool."""
        if not POSTGRES_AVAILABLE:
            raise RuntimeError("psycopg2 not installed. Run: pip install psycopg2-binary")

        self._pool = ThreadedConnectionPool(
            minconn=self.config.pool_min,
            maxconn=self.config.pool_max,
            dsn=self.config.get_connection_string()
        )
        logger.info("PostgreSQL connection pool initialized")

    @property
    def is_postgres(self) -> bool:
        """Check if using PostgreSQL."""
        return self.config.use_postgres and self._pool is not None

    @contextmanager
    def get_connection(self, sqlite_path: Path = None):
        """Get a database connection (context manager)."""
        if self.is_postgres:
            conn = self._pool.getconn()
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                self._pool.putconn(conn)
        else:
            # SQLite fallback
            path = sqlite_path or self.config.sqlite_templates_path
            conn = sqlite3.connect(path)
            conn.row_factory = sqlite3.Row
            try:
                yield conn
                conn.commit()
            finally:
                conn.close()

    def _convert_query(self, query: str) -> str:
        """Convert SQLite ? placeholders to PostgreSQL %s."""
        if self.is_postgres:
            # Simple conversion - handles most cases
            return query.replace('?', '%s')
        return query

    def query(self, query: str, params: tuple = None, sqlite_path: Path = None) -> List[Dict]:
        """Execute a SELECT query and return results as list of dicts."""
        with self.get_connection(sqlite_path) as conn:
            if self.is_postgres:
                cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
                cursor.execute(self._convert_query(query), params or ())
                return [dict(row) for row in cursor.fetchall()]
            else:
                cursor = conn.cursor()
                cursor.execute(query, params or ())
                if cursor.description:
                    return [dict(row) for row in cursor.fetchall()]
                return []

    def query_one(self, query: str, params: tuple = None, sqlite_path: Path = None) -> Optional[Dict]:
        """Execute a SELECT query and return first result."""
        results = self.query(query, params, sqlite_path)
        return results[0] if results else None

    def execute(self, query: str, params: tuple = None, sqlite_path: Path = None) -> int:
        """Execute an INSERT/UPDATE/DELETE query. Returns lastrowid for inserts."""
        with self.get_connection(sqlite_path) as conn:
            cursor = conn.cursor()
            cursor.execute(self._convert_query(query), params or ())
            return cursor.lastrowid if hasattr(cursor, 'lastrowid') else 0

    def execute_many(self, query: str, params_list: List[tuple], sqlite_path: Path = None):
        """Execute a query with multiple parameter sets."""
        with self.get_connection(sqlite_path) as conn:
            cursor = conn.cursor()
            cursor.executemany(self._convert_query(query), params_list)

    def execute_returning(self, query: str, params: tuple = None, sqlite_path: Path = None) -> Optional[Dict]:
        """Execute an INSERT with RETURNING clause (PostgreSQL) or return last inserted row."""
        with self.get_connection(sqlite_path) as conn:
            if self.is_postgres:
                cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
                cursor.execute(self._convert_query(query), params or ())
                result = cursor.fetchone()
                return dict(result) if result else None
            else:
                cursor = conn.cursor()
                # Remove RETURNING clause for SQLite
                sqlite_query = query.split(' RETURNING ')[0] if ' RETURNING ' in query else query
                cursor.execute(sqlite_query, params or ())
                lastid = cursor.lastrowid
                # Fetch the inserted row
                table_match = query.lower().split('insert into ')[1].split()[0] if 'insert into' in query.lower() else None
                if table_match and lastid:
                    cursor.execute(f"SELECT * FROM {table_match} WHERE id = ?", (lastid,))
                    row = cursor.fetchone()
                    return dict(row) if row else None
                return None

    def close(self):
        """Close all connections."""
        if self._pool:
            self._pool.closeall()
            logger.info("PostgreSQL connection pool closed")


# Global instance
_pg_manager = None


def get_pg_db() -> PostgresManager:
    """Get the global PostgreSQL manager instance."""
    global _pg_manager
    if _pg_manager is None:
        _pg_manager = PostgresManager()
    return _pg_manager


def reset_pg_db():
    """Reset the global instance (useful for testing or reconnecting)."""
    global _pg_manager
    if _pg_manager:
        _pg_manager.close()
    _pg_manager = None


# Schema creation for PostgreSQL
POSTGRES_SCHEMA = """
-- Firms table
CREATE TABLE IF NOT EXISTS firms (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    settings JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Templates table (with BYTEA for file content)
CREATE TABLE IF NOT EXISTS templates (
    id SERIAL PRIMARY KEY,
    firm_id TEXT NOT NULL REFERENCES firms(id),
    name TEXT NOT NULL,
    original_filename TEXT,
    category TEXT,
    subcategory TEXT,
    court_type TEXT,
    jurisdiction TEXT,
    case_types TEXT,
    variables JSONB DEFAULT '[]',
    variable_mappings JSONB DEFAULT '{}',
    tags TEXT,
    file_content BYTEA,
    file_hash TEXT,
    file_size INTEGER,
    is_active BOOLEAN DEFAULT TRUE,
    upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_used TIMESTAMP,
    usage_count INTEGER DEFAULT 0,
    UNIQUE(firm_id, name)
);

-- Generated documents history
CREATE TABLE IF NOT EXISTS generated_documents (
    id SERIAL PRIMARY KEY,
    firm_id TEXT NOT NULL REFERENCES firms(id),
    template_id INTEGER REFERENCES templates(id),
    template_name TEXT,
    case_id TEXT,
    client_name TEXT,
    variables_used JSONB DEFAULT '{}',
    generated_by TEXT,
    generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    output_filename TEXT
);

-- Attorney profiles
CREATE TABLE IF NOT EXISTS attorneys (
    id SERIAL PRIMARY KEY,
    firm_id TEXT NOT NULL REFERENCES firms(id),
    attorney_name TEXT NOT NULL,
    bar_number TEXT,
    email TEXT,
    phone TEXT,
    fax TEXT,
    firm_name TEXT,
    firm_address TEXT,
    firm_city TEXT,
    firm_state TEXT,
    firm_zip TEXT,
    is_primary BOOLEAN DEFAULT FALSE,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(firm_id, bar_number)
);

-- Full-text search index (PostgreSQL uses tsvector)
CREATE INDEX IF NOT EXISTS idx_templates_fts ON templates 
USING GIN (to_tsvector('english', name || ' ' || COALESCE(category, '') || ' ' || COALESCE(tags, '')));

-- Other useful indexes
CREATE INDEX IF NOT EXISTS idx_templates_firm ON templates(firm_id);
CREATE INDEX IF NOT EXISTS idx_templates_category ON templates(firm_id, category);
CREATE INDEX IF NOT EXISTS idx_attorneys_firm ON attorneys(firm_id);
CREATE INDEX IF NOT EXISTS idx_generated_docs_firm ON generated_documents(firm_id);
CREATE INDEX IF NOT EXISTS idx_generated_docs_case ON generated_documents(case_id);
"""


def init_postgres_schema():
    """Initialize PostgreSQL schema (run once on setup)."""
    db = get_pg_db()
    if not db.is_postgres:
        raise RuntimeError("PostgreSQL not configured. Set DATABASE_URL or PG_* environment variables.")
    
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(POSTGRES_SCHEMA)
        conn.commit()
    logger.info("PostgreSQL schema initialized")


if __name__ == "__main__":
    # Test connection
    print("Testing PostgreSQL connection...")
    db = get_pg_db()
    print(f"Using PostgreSQL: {db.is_postgres}")
    
    if db.is_postgres:
        # Test query
        result = db.query("SELECT version()")
        print(f"PostgreSQL version: {result[0]['version'] if result else 'Unknown'}")
    else:
        print("Falling back to SQLite - set DATABASE_URL to use PostgreSQL")
