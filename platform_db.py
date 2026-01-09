"""
Platform Database Module

Manages the shared PostgreSQL database for multi-tenant platform data:
- Firms (customers)
- Users (firm members)
- Subscriptions
- Audit logs
- Sync status

This is separate from the per-firm SQLite cache databases.
"""
import os
import json
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, asdict
from contextlib import contextmanager
import secrets
import hashlib

# Try to import psycopg2, fall back to sqlite for local development
try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    HAS_POSTGRES = True
except ImportError:
    HAS_POSTGRES = False
    import sqlite3

# Try to import cryptography for token encryption
try:
    from cryptography.fernet import Fernet
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False


@dataclass
class Firm:
    """Represents a customer firm."""
    id: str
    name: str
    subscription_status: str  # 'trial', 'active', 'cancelled', 'suspended'
    subscription_tier: str  # 'standard', 'professional'
    mycase_connected: bool
    mycase_firm_id: Optional[int]
    created_at: datetime
    updated_at: datetime
    trial_ends_at: Optional[datetime] = None
    stripe_customer_id: Optional[str] = None
    stripe_subscription_id: Optional[str] = None


@dataclass
class User:
    """Represents a user within a firm."""
    id: str
    firm_id: str
    email: str
    name: str
    role: str  # 'admin', 'attorney', 'staff', 'readonly'
    mycase_staff_id: Optional[int]
    auth_provider_id: Optional[str]  # Auth0/Clerk user ID
    created_at: datetime
    last_login_at: Optional[datetime]
    is_active: bool


@dataclass
class FirmCredentials:
    """MyCase OAuth credentials for a firm."""
    firm_id: str
    access_token: str
    refresh_token: str
    token_expires_at: datetime
    mycase_firm_id: int


class PlatformDB:
    """
    Platform database manager.
    
    Uses PostgreSQL in production, falls back to SQLite for local development.
    """
    
    def __init__(self, database_url: str = None):
        self.database_url = database_url or os.environ.get('DATABASE_URL')
        self.use_postgres = HAS_POSTGRES and self.database_url and self.database_url.startswith('postgres')
        
        # Encryption key for OAuth tokens
        self.encryption_key = os.environ.get('ENCRYPTION_KEY')
        if HAS_CRYPTO and self.encryption_key:
            self.fernet = Fernet(self.encryption_key.encode() if isinstance(self.encryption_key, str) else self.encryption_key)
        else:
            self.fernet = None
        
        # Initialize database
        self._init_tables()
    
    @contextmanager
    def _get_connection(self):
        """Get database connection."""
        if self.use_postgres:
            conn = psycopg2.connect(self.database_url, cursor_factory=RealDictCursor)
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()
        else:
            # SQLite fallback for local development
            from config import DATA_DIR
            db_path = DATA_DIR / "platform.db"
            conn = sqlite3.connect(str(db_path))
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
        """Initialize platform database tables."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            if self.use_postgres:
                # PostgreSQL schema
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS firms (
                        id VARCHAR(36) PRIMARY KEY,
                        name VARCHAR(255) NOT NULL,
                        subscription_status VARCHAR(20) DEFAULT 'trial',
                        subscription_tier VARCHAR(20) DEFAULT 'standard',
                        mycase_connected BOOLEAN DEFAULT FALSE,
                        mycase_firm_id INTEGER,
                        mycase_oauth_token TEXT,
                        mycase_oauth_refresh TEXT,
                        mycase_token_expires_at TIMESTAMP,
                        stripe_customer_id VARCHAR(255),
                        stripe_subscription_id VARCHAR(255),
                        trial_ends_at TIMESTAMP,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        id VARCHAR(36) PRIMARY KEY,
                        firm_id VARCHAR(36) REFERENCES firms(id) ON DELETE CASCADE,
                        email VARCHAR(255) NOT NULL,
                        name VARCHAR(255),
                        role VARCHAR(20) DEFAULT 'readonly',
                        mycase_staff_id INTEGER,
                        auth_provider_id VARCHAR(255),
                        is_active BOOLEAN DEFAULT TRUE,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        last_login_at TIMESTAMP
                    )
                """)
                
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS sync_status (
                        firm_id VARCHAR(36) REFERENCES firms(id) ON DELETE CASCADE,
                        status VARCHAR(20) DEFAULT 'pending',
                        started_at TIMESTAMP,
                        completed_at TIMESTAMP,
                        records_synced INTEGER DEFAULT 0,
                        error_message TEXT,
                        PRIMARY KEY (firm_id)
                    )
                """)
                
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS audit_log (
                        id SERIAL PRIMARY KEY,
                        firm_id VARCHAR(36) REFERENCES firms(id) ON DELETE CASCADE,
                        user_id VARCHAR(36),
                        action VARCHAR(100) NOT NULL,
                        details JSONB,
                        ip_address VARCHAR(45),
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # Create indexes
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_firm ON users(firm_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_firm ON audit_log(firm_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_log(created_at)")
                
            else:
                # SQLite schema (for local development)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS firms (
                        id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        subscription_status TEXT DEFAULT 'trial',
                        subscription_tier TEXT DEFAULT 'standard',
                        mycase_connected INTEGER DEFAULT 0,
                        mycase_firm_id INTEGER,
                        mycase_oauth_token TEXT,
                        mycase_oauth_refresh TEXT,
                        mycase_token_expires_at TEXT,
                        stripe_customer_id TEXT,
                        stripe_subscription_id TEXT,
                        trial_ends_at TEXT,
                        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        id TEXT PRIMARY KEY,
                        firm_id TEXT REFERENCES firms(id),
                        email TEXT NOT NULL,
                        name TEXT,
                        role TEXT DEFAULT 'readonly',
                        mycase_staff_id INTEGER,
                        auth_provider_id TEXT,
                        is_active INTEGER DEFAULT 1,
                        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                        last_login_at TEXT
                    )
                """)
                
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS sync_status (
                        firm_id TEXT PRIMARY KEY REFERENCES firms(id),
                        status TEXT DEFAULT 'pending',
                        started_at TEXT,
                        completed_at TEXT,
                        records_synced INTEGER DEFAULT 0,
                        error_message TEXT
                    )
                """)
                
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS audit_log (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        firm_id TEXT REFERENCES firms(id),
                        user_id TEXT,
                        action TEXT NOT NULL,
                        details TEXT,
                        ip_address TEXT,
                        created_at TEXT DEFAULT CURRENT_TIMESTAMP
                    )
                """)
    
    def _encrypt(self, value: str) -> str:
        """Encrypt a value for storage."""
        if self.fernet:
            return self.fernet.encrypt(value.encode()).decode()
        # In development without encryption, use base64
        import base64
        return base64.b64encode(value.encode()).decode()
    
    def _decrypt(self, value: str) -> str:
        """Decrypt a stored value."""
        if self.fernet:
            return self.fernet.decrypt(value.encode()).decode()
        import base64
        return base64.b64decode(value.encode()).decode()
    
    # =========================================================================
    # Firm Methods
    # =========================================================================
    
    def create_firm(self, name: str, trial_days: int = 14) -> Firm:
        """Create a new firm with trial subscription."""
        firm_id = secrets.token_urlsafe(16)
        now = datetime.utcnow()
        trial_ends = now + timedelta(days=trial_days)
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            if self.use_postgres:
                cursor.execute("""
                    INSERT INTO firms (id, name, subscription_status, trial_ends_at, created_at, updated_at)
                    VALUES (%s, %s, 'trial', %s, %s, %s)
                """, (firm_id, name, trial_ends, now, now))
            else:
                cursor.execute("""
                    INSERT INTO firms (id, name, subscription_status, trial_ends_at, created_at, updated_at)
                    VALUES (?, ?, 'trial', ?, ?, ?)
                """, (firm_id, name, trial_ends.isoformat(), now.isoformat(), now.isoformat()))
        
        return Firm(
            id=firm_id,
            name=name,
            subscription_status='trial',
            subscription_tier='standard',
            mycase_connected=False,
            mycase_firm_id=None,
            created_at=now,
            updated_at=now,
            trial_ends_at=trial_ends
        )
    
    def get_firm(self, firm_id: str) -> Optional[Firm]:
        """Get a firm by ID."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            if self.use_postgres:
                cursor.execute("SELECT * FROM firms WHERE id = %s", (firm_id,))
            else:
                cursor.execute("SELECT * FROM firms WHERE id = ?", (firm_id,))
            
            row = cursor.fetchone()
            if not row:
                return None
            
            row = dict(row)
            return Firm(
                id=row['id'],
                name=row['name'],
                subscription_status=row['subscription_status'],
                subscription_tier=row['subscription_tier'],
                mycase_connected=bool(row['mycase_connected']),
                mycase_firm_id=row['mycase_firm_id'],
                created_at=row['created_at'] if isinstance(row['created_at'], datetime) else datetime.fromisoformat(row['created_at']),
                updated_at=row['updated_at'] if isinstance(row['updated_at'], datetime) else datetime.fromisoformat(row['updated_at']),
                trial_ends_at=row.get('trial_ends_at'),
                stripe_customer_id=row.get('stripe_customer_id'),
                stripe_subscription_id=row.get('stripe_subscription_id')
            )
    
    def get_firm_by_mycase_id(self, mycase_firm_id: int) -> Optional[Firm]:
        """Get a firm by MyCase firm ID."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            if self.use_postgres:
                cursor.execute("SELECT * FROM firms WHERE mycase_firm_id = %s", (mycase_firm_id,))
            else:
                cursor.execute("SELECT * FROM firms WHERE mycase_firm_id = ?", (mycase_firm_id,))
            
            row = cursor.fetchone()
            if row:
                return self.get_firm(dict(row)['id'])
            return None
    
    def get_active_firms(self) -> List[Firm]:
        """Get all active firms (for sync operations)."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT id FROM firms 
                WHERE subscription_status IN ('trial', 'active')
                AND mycase_connected = TRUE
            """)
            
            firms = []
            for row in cursor.fetchall():
                firm = self.get_firm(dict(row)['id'])
                if firm:
                    firms.append(firm)
            return firms
    
    def update_firm_subscription(self, firm_id: str, status: str, tier: str = None,
                                  stripe_customer_id: str = None, stripe_subscription_id: str = None):
        """Update firm subscription status."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            updates = ["subscription_status = %s" if self.use_postgres else "subscription_status = ?",
                      "updated_at = %s" if self.use_postgres else "updated_at = ?"]
            params = [status, datetime.utcnow() if self.use_postgres else datetime.utcnow().isoformat()]
            
            if tier:
                updates.append("subscription_tier = %s" if self.use_postgres else "subscription_tier = ?")
                params.append(tier)
            if stripe_customer_id:
                updates.append("stripe_customer_id = %s" if self.use_postgres else "stripe_customer_id = ?")
                params.append(stripe_customer_id)
            if stripe_subscription_id:
                updates.append("stripe_subscription_id = %s" if self.use_postgres else "stripe_subscription_id = ?")
                params.append(stripe_subscription_id)
            
            params.append(firm_id)
            
            query = f"UPDATE firms SET {', '.join(updates)} WHERE id = %s" if self.use_postgres else \
                    f"UPDATE firms SET {', '.join(updates)} WHERE id = ?"
            cursor.execute(query, params)
    
    # =========================================================================
    # MyCase Credentials Methods
    # =========================================================================
    
    def store_mycase_credentials(self, firm_id: str, access_token: str, refresh_token: str,
                                   expires_in: int, mycase_firm_id: int):
        """Store encrypted MyCase OAuth credentials for a firm."""
        expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            encrypted_access = self._encrypt(access_token)
            encrypted_refresh = self._encrypt(refresh_token)
            
            if self.use_postgres:
                cursor.execute("""
                    UPDATE firms SET
                        mycase_connected = TRUE,
                        mycase_firm_id = %s,
                        mycase_oauth_token = %s,
                        mycase_oauth_refresh = %s,
                        mycase_token_expires_at = %s,
                        updated_at = %s
                    WHERE id = %s
                """, (mycase_firm_id, encrypted_access, encrypted_refresh, 
                      expires_at, datetime.utcnow(), firm_id))
            else:
                cursor.execute("""
                    UPDATE firms SET
                        mycase_connected = 1,
                        mycase_firm_id = ?,
                        mycase_oauth_token = ?,
                        mycase_oauth_refresh = ?,
                        mycase_token_expires_at = ?,
                        updated_at = ?
                    WHERE id = ?
                """, (mycase_firm_id, encrypted_access, encrypted_refresh,
                      expires_at.isoformat(), datetime.utcnow().isoformat(), firm_id))
    
    def get_mycase_credentials(self, firm_id: str) -> Optional[FirmCredentials]:
        """Get decrypted MyCase credentials for a firm."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            if self.use_postgres:
                cursor.execute("""
                    SELECT mycase_firm_id, mycase_oauth_token, mycase_oauth_refresh, mycase_token_expires_at
                    FROM firms WHERE id = %s AND mycase_connected = TRUE
                """, (firm_id,))
            else:
                cursor.execute("""
                    SELECT mycase_firm_id, mycase_oauth_token, mycase_oauth_refresh, mycase_token_expires_at
                    FROM firms WHERE id = ? AND mycase_connected = 1
                """, (firm_id,))
            
            row = cursor.fetchone()
            if not row:
                return None
            
            row = dict(row)
            expires_at = row['mycase_token_expires_at']
            if isinstance(expires_at, str):
                expires_at = datetime.fromisoformat(expires_at)
            
            return FirmCredentials(
                firm_id=firm_id,
                access_token=self._decrypt(row['mycase_oauth_token']),
                refresh_token=self._decrypt(row['mycase_oauth_refresh']),
                token_expires_at=expires_at,
                mycase_firm_id=row['mycase_firm_id']
            )
    
    def update_mycase_tokens(self, firm_id: str, access_token: str, refresh_token: str, expires_in: int):
        """Update MyCase tokens after refresh."""
        expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            encrypted_access = self._encrypt(access_token)
            encrypted_refresh = self._encrypt(refresh_token)
            
            if self.use_postgres:
                cursor.execute("""
                    UPDATE firms SET
                        mycase_oauth_token = %s,
                        mycase_oauth_refresh = %s,
                        mycase_token_expires_at = %s,
                        updated_at = %s
                    WHERE id = %s
                """, (encrypted_access, encrypted_refresh, expires_at, datetime.utcnow(), firm_id))
            else:
                cursor.execute("""
                    UPDATE firms SET
                        mycase_oauth_token = ?,
                        mycase_oauth_refresh = ?,
                        mycase_token_expires_at = ?,
                        updated_at = ?
                    WHERE id = ?
                """, (encrypted_access, encrypted_refresh, expires_at.isoformat(),
                      datetime.utcnow().isoformat(), firm_id))
    
    # =========================================================================
    # User Methods
    # =========================================================================
    
    def create_user(self, firm_id: str, email: str, name: str, role: str = 'admin',
                    auth_provider_id: str = None) -> User:
        """Create a new user."""
        user_id = secrets.token_urlsafe(16)
        now = datetime.utcnow()
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            if self.use_postgres:
                cursor.execute("""
                    INSERT INTO users (id, firm_id, email, name, role, auth_provider_id, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (user_id, firm_id, email, name, role, auth_provider_id, now))
            else:
                cursor.execute("""
                    INSERT INTO users (id, firm_id, email, name, role, auth_provider_id, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (user_id, firm_id, email, name, role, auth_provider_id, now.isoformat()))
        
        return User(
            id=user_id,
            firm_id=firm_id,
            email=email,
            name=name,
            role=role,
            mycase_staff_id=None,
            auth_provider_id=auth_provider_id,
            created_at=now,
            last_login_at=None,
            is_active=True
        )
    
    def get_user(self, user_id: str) -> Optional[User]:
        """Get a user by ID."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            if self.use_postgres:
                cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
            else:
                cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
            
            row = cursor.fetchone()
            if not row:
                return None
            
            row = dict(row)
            return User(
                id=row['id'],
                firm_id=row['firm_id'],
                email=row['email'],
                name=row['name'],
                role=row['role'],
                mycase_staff_id=row['mycase_staff_id'],
                auth_provider_id=row['auth_provider_id'],
                created_at=row['created_at'] if isinstance(row['created_at'], datetime) else datetime.fromisoformat(row['created_at']),
                last_login_at=row.get('last_login_at'),
                is_active=bool(row['is_active'])
            )
    
    def get_user_by_email(self, email: str) -> Optional[User]:
        """Get a user by email."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            if self.use_postgres:
                cursor.execute("SELECT id FROM users WHERE email = %s AND is_active = TRUE", (email,))
            else:
                cursor.execute("SELECT id FROM users WHERE email = ? AND is_active = 1", (email,))
            
            row = cursor.fetchone()
            if row:
                return self.get_user(dict(row)['id'])
            return None
    
    def get_user_by_auth_provider(self, auth_provider_id: str) -> Optional[User]:
        """Get a user by Auth0/Clerk ID."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            if self.use_postgres:
                cursor.execute("SELECT id FROM users WHERE auth_provider_id = %s", (auth_provider_id,))
            else:
                cursor.execute("SELECT id FROM users WHERE auth_provider_id = ?", (auth_provider_id,))
            
            row = cursor.fetchone()
            if row:
                return self.get_user(dict(row)['id'])
            return None
    
    def get_firm_users(self, firm_id: str) -> List[User]:
        """Get all users for a firm."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            if self.use_postgres:
                cursor.execute("SELECT id FROM users WHERE firm_id = %s AND is_active = TRUE", (firm_id,))
            else:
                cursor.execute("SELECT id FROM users WHERE firm_id = ? AND is_active = 1", (firm_id,))
            
            users = []
            for row in cursor.fetchall():
                user = self.get_user(dict(row)['id'])
                if user:
                    users.append(user)
            return users
    
    def update_user_login(self, user_id: str):
        """Update user's last login timestamp."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            now = datetime.utcnow()
            if self.use_postgres:
                cursor.execute("UPDATE users SET last_login_at = %s WHERE id = %s", (now, user_id))
            else:
                cursor.execute("UPDATE users SET last_login_at = ? WHERE id = ?", (now.isoformat(), user_id))
    
    # =========================================================================
    # Sync Status Methods
    # =========================================================================
    
    def update_sync_status(self, firm_id: str, status: str, records_synced: int = None,
                           error_message: str = None):
        """Update sync status for a firm."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            now = datetime.utcnow()
            
            if self.use_postgres:
                cursor.execute("""
                    INSERT INTO sync_status (firm_id, status, started_at, completed_at, records_synced, error_message)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (firm_id) DO UPDATE SET
                        status = EXCLUDED.status,
                        completed_at = CASE WHEN EXCLUDED.status IN ('completed', 'failed') THEN %s ELSE sync_status.completed_at END,
                        records_synced = COALESCE(EXCLUDED.records_synced, sync_status.records_synced),
                        error_message = EXCLUDED.error_message
                """, (firm_id, status, now if status == 'running' else None,
                      now if status in ('completed', 'failed') else None, records_synced, error_message, now))
            else:
                cursor.execute("""
                    INSERT OR REPLACE INTO sync_status (firm_id, status, started_at, completed_at, records_synced, error_message)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (firm_id, status,
                      now.isoformat() if status == 'running' else None,
                      now.isoformat() if status in ('completed', 'failed') else None,
                      records_synced, error_message))
    
    def get_sync_status(self, firm_id: str) -> Dict[str, Any]:
        """Get sync status for a firm."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            if self.use_postgres:
                cursor.execute("SELECT * FROM sync_status WHERE firm_id = %s", (firm_id,))
            else:
                cursor.execute("SELECT * FROM sync_status WHERE firm_id = ?", (firm_id,))
            
            row = cursor.fetchone()
            return dict(row) if row else {'status': 'never', 'records_synced': 0}
    
    # =========================================================================
    # Audit Log Methods
    # =========================================================================
    
    def log_audit(self, firm_id: str, user_id: str, action: str, details: Dict = None,
                  ip_address: str = None):
        """Log an audit event."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            if self.use_postgres:
                cursor.execute("""
                    INSERT INTO audit_log (firm_id, user_id, action, details, ip_address)
                    VALUES (%s, %s, %s, %s, %s)
                """, (firm_id, user_id, action, json.dumps(details) if details else None, ip_address))
            else:
                cursor.execute("""
                    INSERT INTO audit_log (firm_id, user_id, action, details, ip_address)
                    VALUES (?, ?, ?, ?, ?)
                """, (firm_id, user_id, action, json.dumps(details) if details else None, ip_address))


# Singleton instance
_platform_db: Optional[PlatformDB] = None


def get_platform_db() -> PlatformDB:
    """Get or create singleton platform database instance."""
    global _platform_db
    if _platform_db is None:
        _platform_db = PlatformDB()
    return _platform_db
