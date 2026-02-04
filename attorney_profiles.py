"""
Attorney Profile Management

Stores attorney and firm information for automatic signature block population.
Each attorney belongs to a firm, and the signature block is generated based on
the logged-in attorney.

Supports both PostgreSQL (production) and SQLite (local dev).
"""

import sqlite3
from dataclasses import dataclass, asdict
from typing import Optional, List, Dict, Any, Union
from pathlib import Path
from datetime import datetime
from contextlib import contextmanager

from config import DATA_DIR

# Import PostgreSQL manager (falls back to SQLite if not configured)
try:
    from pg_database import get_pg_db, PostgresManager
    PG_AVAILABLE = True
except ImportError:
    PG_AVAILABLE = False
    get_pg_db = None
    PostgresManager = None


# Database path (SQLite fallback)
ATTORNEY_DB = DATA_DIR / "attorney_profiles.db"


@dataclass
class AttorneyProfile:
    """Attorney profile with all signature block information."""
    id: Optional[int] = None
    firm_id: str = ""

    # Attorney info
    attorney_name: str = ""
    bar_number: str = ""
    email: str = ""
    phone: str = ""
    fax: Optional[str] = None

    # Firm info
    firm_name: str = ""
    firm_address: str = ""
    firm_city: str = ""
    firm_state: str = "Missouri"
    firm_zip: str = ""

    # Additional
    is_primary: bool = False  # Primary attorney for the firm
    is_active: bool = True
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    def get_signature_block(self) -> str:
        """Generate the signature block text for this attorney."""
        lines = [
            self.firm_name,
            "",
            "",
            f"/s/{self.attorney_name}",
            f"{self.attorney_name}    #{self.bar_number}",
            self.firm_address,
            f"{self.firm_city}, {self.firm_state} {self.firm_zip}",
            f"Telephone: {self.phone}",
        ]
        if self.fax:
            lines.append(f"Facsimile: {self.fax}")
        lines.append(f"Email: {self.email}")

        return "\n".join(lines)

    def get_signature_dict(self) -> Dict[str, str]:
        """Get signature block as a dictionary for template substitution."""
        return {
            "attorney_name": self.attorney_name,
            "attorney_bar_number": self.bar_number,
            "attorney_email": self.email,
            "attorney_phone": self.phone,
            "attorney_fax": self.fax or "",
            "firm_name": self.firm_name,
            "firm_address": self.firm_address,
            "firm_city": self.firm_city,
            "firm_state": self.firm_state,
            "firm_zip": self.firm_zip,
            "firm_city_state_zip": f"{self.firm_city}, {self.firm_state} {self.firm_zip}",
            "firm_phone": self.phone,
            "firm_fax": self.fax or "",
            "firm_email": self.email,
        }


class AttorneyProfileDB:
    """Database manager for attorney profiles (PostgreSQL or SQLite)."""

    def __init__(self, db_path: Path = None):
        self.db_path = db_path or ATTORNEY_DB

        # Use PostgreSQL if available and configured
        self._pg_db = None
        if PG_AVAILABLE:
            try:
                self._pg_db = get_pg_db()
                if self._pg_db.is_postgres:
                    # PostgreSQL is active - schema already initialized
                    return
            except Exception:
                self._pg_db = None

        # Fall back to SQLite
        self._init_db()

    @property
    def is_postgres(self) -> bool:
        """Check if using PostgreSQL."""
        return self._pg_db is not None and self._pg_db.is_postgres

    @contextmanager
    def _get_connection(self):
        """Context manager for database connections."""
        if self.is_postgres:
            with self._pg_db.get_connection() as conn:
                yield conn
        else:
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

    def _convert_query(self, query: str) -> str:
        """Convert SQLite ? placeholders to PostgreSQL %s."""
        if self.is_postgres:
            return query.replace('?', '%s')
        return query

    def _init_db(self):
        """Initialize the SQLite database schema."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS attorneys (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    firm_id TEXT NOT NULL,
                    attorney_name TEXT NOT NULL,
                    bar_number TEXT NOT NULL,
                    email TEXT,
                    phone TEXT,
                    fax TEXT,
                    firm_name TEXT,
                    firm_address TEXT,
                    firm_city TEXT,
                    firm_state TEXT DEFAULT 'Missouri',
                    firm_zip TEXT,
                    is_primary INTEGER DEFAULT 0,
                    is_active INTEGER DEFAULT 1,
                    created_at TEXT,
                    updated_at TEXT,
                    UNIQUE(firm_id, bar_number)
                )
            """)

            # Create index for quick lookups
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_attorneys_firm
                ON attorneys(firm_id, is_active)
            """)

            conn.commit()

    def save_attorney(self, profile: AttorneyProfile) -> int:
        """Save or update an attorney profile. Returns the attorney ID."""
        now = datetime.now().isoformat()

        with self._get_connection() as conn:
            cursor = conn.cursor()
            if profile.id:
                # Update existing
                query = self._convert_query("""
                    UPDATE attorneys SET
                        firm_id = ?,
                        attorney_name = ?,
                        bar_number = ?,
                        email = ?,
                        phone = ?,
                        fax = ?,
                        firm_name = ?,
                        firm_address = ?,
                        firm_city = ?,
                        firm_state = ?,
                        firm_zip = ?,
                        is_primary = ?,
                        is_active = ?,
                        updated_at = ?
                    WHERE id = ?
                """)
                cursor.execute(query, (
                    profile.firm_id, profile.attorney_name, profile.bar_number,
                    profile.email, profile.phone, profile.fax,
                    profile.firm_name, profile.firm_address, profile.firm_city,
                    profile.firm_state, profile.firm_zip,
                    1 if profile.is_primary else 0,
                    1 if profile.is_active else 0,
                    now, profile.id
                ))
                return profile.id
            else:
                # Insert new - PostgreSQL uses ON CONFLICT, SQLite uses OR REPLACE
                if self.is_postgres:
                    cursor.execute("""
                        INSERT INTO attorneys (
                            firm_id, attorney_name, bar_number, email, phone, fax,
                            firm_name, firm_address, firm_city, firm_state, firm_zip,
                            is_primary, is_active, created_at, updated_at
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (firm_id, bar_number) DO UPDATE SET
                            attorney_name = EXCLUDED.attorney_name,
                            email = EXCLUDED.email,
                            phone = EXCLUDED.phone,
                            fax = EXCLUDED.fax,
                            firm_name = EXCLUDED.firm_name,
                            firm_address = EXCLUDED.firm_address,
                            updated_at = EXCLUDED.updated_at
                        RETURNING id
                    """, (
                        profile.firm_id, profile.attorney_name, profile.bar_number,
                        profile.email, profile.phone, profile.fax,
                        profile.firm_name, profile.firm_address, profile.firm_city,
                        profile.firm_state, profile.firm_zip,
                        profile.is_primary, profile.is_active,
                        now, now
                    ))
                    result = cursor.fetchone()
                    return result[0] if result else 0
                else:
                    cursor.execute("""
                        INSERT OR REPLACE INTO attorneys (
                            firm_id, attorney_name, bar_number, email, phone, fax,
                            firm_name, firm_address, firm_city, firm_state, firm_zip,
                            is_primary, is_active, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        profile.firm_id, profile.attorney_name, profile.bar_number,
                        profile.email, profile.phone, profile.fax,
                        profile.firm_name, profile.firm_address, profile.firm_city,
                        profile.firm_state, profile.firm_zip,
                        1 if profile.is_primary else 0,
                        1 if profile.is_active else 0,
                        now, now
                    ))
                    return cursor.lastrowid

    def get_attorney(self, attorney_id: int) -> Optional[AttorneyProfile]:
        """Get an attorney by ID."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            query = self._convert_query("SELECT * FROM attorneys WHERE id = ?")
            cursor.execute(query, (attorney_id,))
            row = cursor.fetchone()
            if row:
                return self._row_to_profile(row)
        return None

    def get_attorney_by_bar(self, firm_id: str, bar_number: str) -> Optional[AttorneyProfile]:
        """Get an attorney by firm ID and bar number."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            query = self._convert_query(
                "SELECT * FROM attorneys WHERE firm_id = ? AND bar_number = ?"
            )
            cursor.execute(query, (firm_id, bar_number))
            row = cursor.fetchone()
            if row:
                return self._row_to_profile(row)
        return None

    def get_primary_attorney(self, firm_id: str) -> Optional[AttorneyProfile]:
        """Get the primary attorney for a firm."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            query = self._convert_query(
                """SELECT * FROM attorneys
                   WHERE firm_id = ? AND is_primary = TRUE AND is_active = TRUE"""
            )
            cursor.execute(query, (firm_id,))
            row = cursor.fetchone()

            if row:
                return self._row_to_profile(row)

            # If no primary, return first active attorney
            query = self._convert_query(
                """SELECT * FROM attorneys
                   WHERE firm_id = ? AND is_active = TRUE
                   ORDER BY created_at LIMIT 1"""
            )
            cursor.execute(query, (firm_id,))
            row = cursor.fetchone()

            if row:
                return self._row_to_profile(row)

        return None

    def list_attorneys(self, firm_id: str, active_only: bool = True) -> List[AttorneyProfile]:
        """List all attorneys for a firm."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            if active_only:
                query = self._convert_query(
                    """SELECT * FROM attorneys
                       WHERE firm_id = ? AND is_active = TRUE
                       ORDER BY is_primary DESC, attorney_name"""
                )
            else:
                query = self._convert_query(
                    """SELECT * FROM attorneys
                       WHERE firm_id = ?
                       ORDER BY is_primary DESC, attorney_name"""
                )
            cursor.execute(query, (firm_id,))
            rows = cursor.fetchall()

            return [self._row_to_profile(row) for row in rows]

    def set_primary_attorney(self, firm_id: str, attorney_id: int) -> bool:
        """Set an attorney as the primary for their firm."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # First, unset all primary for this firm
            query = self._convert_query(
                "UPDATE attorneys SET is_primary = FALSE WHERE firm_id = ?"
            )
            cursor.execute(query, (firm_id,))
            # Set the new primary
            query = self._convert_query(
                "UPDATE attorneys SET is_primary = TRUE WHERE id = ? AND firm_id = ?"
            )
            cursor.execute(query, (attorney_id, firm_id))
            return True

    def deactivate_attorney(self, attorney_id: int) -> bool:
        """Deactivate an attorney (soft delete)."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            query = self._convert_query(
                "UPDATE attorneys SET is_active = FALSE, updated_at = ? WHERE id = ?"
            )
            cursor.execute(query, (datetime.now().isoformat(), attorney_id))
            return True

    def _row_to_profile(self, row: Union[sqlite3.Row, Dict, tuple]) -> AttorneyProfile:
        """Convert a database row to an AttorneyProfile."""
        # Handle both dict (PostgreSQL) and Row/tuple (SQLite)
        def get(key, default=None):
            if isinstance(row, dict):
                return row.get(key, default)
            elif hasattr(row, 'keys'):  # sqlite3.Row
                return row[key] if row[key] is not None else default
            else:  # tuple
                return default

        return AttorneyProfile(
            id=get("id"),
            firm_id=get("firm_id", ""),
            attorney_name=get("attorney_name", ""),
            bar_number=get("bar_number", ""),
            email=get("email", ""),
            phone=get("phone", ""),
            fax=get("fax"),
            firm_name=get("firm_name", ""),
            firm_address=get("firm_address", ""),
            firm_city=get("firm_city", ""),
            firm_state=get("firm_state", "Missouri"),
            firm_zip=get("firm_zip", ""),
            is_primary=bool(get("is_primary", False)),
            is_active=bool(get("is_active", True)),
            created_at=get("created_at"),
            updated_at=get("updated_at"),
        )


# Singleton instance
_db_instance: Optional[AttorneyProfileDB] = None


def get_attorney_db() -> AttorneyProfileDB:
    """Get the singleton database instance."""
    global _db_instance
    if _db_instance is None:
        _db_instance = AttorneyProfileDB()
    return _db_instance


# Convenience functions
def save_attorney(profile: AttorneyProfile) -> int:
    """Save an attorney profile."""
    return get_attorney_db().save_attorney(profile)


def get_attorney(attorney_id: int) -> Optional[AttorneyProfile]:
    """Get an attorney by ID."""
    return get_attorney_db().get_attorney(attorney_id)


def get_primary_attorney(firm_id: str) -> Optional[AttorneyProfile]:
    """Get the primary attorney for a firm."""
    return get_attorney_db().get_primary_attorney(firm_id)


def list_attorneys(firm_id: str) -> List[AttorneyProfile]:
    """List all active attorneys for a firm."""
    return get_attorney_db().list_attorneys(firm_id)
