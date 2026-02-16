"""
Platform Database Module

Manages the shared PostgreSQL database for multi-tenant platform data:
- Firms (customers)
- Users (firm members)
- Subscriptions
- Audit logs
- Sync status / history

PostgreSQL only — no SQLite fallback. Requires DATABASE_URL env var.
"""
import os
import json
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from contextlib import contextmanager
import secrets

import psycopg2
from psycopg2.extras import RealDictCursor

try:
    from cryptography.fernet import Fernet
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False

logger = logging.getLogger(__name__)


@dataclass
class Firm:
    id: str
    name: str
    subscription_status: str
    subscription_tier: str
    mycase_connected: bool
    mycase_firm_id: Optional[int]
    created_at: datetime
    updated_at: datetime
    trial_ends_at: Optional[datetime] = None
    stripe_customer_id: Optional[str] = None
    stripe_subscription_id: Optional[str] = None


@dataclass
class User:
    id: str
    firm_id: str
    email: str
    name: str
    role: str
    mycase_staff_id: Optional[int]
    auth_provider_id: Optional[str]
    created_at: datetime
    last_login_at: Optional[datetime]
    is_active: bool


@dataclass
class FirmCredentials:
    firm_id: str
    access_token: str
    refresh_token: str
    token_expires_at: datetime
    mycase_firm_id: int


class PlatformDB:
    """Platform database manager. PostgreSQL only."""

    def __init__(self, database_url: str = None):
        self.database_url = database_url or os.environ.get('DATABASE_URL')
        if not self.database_url:
            raise ValueError(
                "DATABASE_URL environment variable is required. "
                "Set it to your PostgreSQL connection string."
            )

        self.encryption_key = os.environ.get('ENCRYPTION_KEY')
        if HAS_CRYPTO and self.encryption_key:
            self.fernet = Fernet(
                self.encryption_key.encode()
                if isinstance(self.encryption_key, str)
                else self.encryption_key
            )
        else:
            self.fernet = None

        self._init_tables()

    @contextmanager
    def _get_connection(self):
        conn = psycopg2.connect(self.database_url, cursor_factory=RealDictCursor)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_tables(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()

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
                    sync_frequency_minutes INTEGER DEFAULT 240,
                    next_sync_at TIMESTAMP,
                    last_sync_at TIMESTAMP,
                    last_sync_status VARCHAR(20),
                    last_sync_error TEXT,
                    last_sync_records INTEGER,
                    last_sync_duration_seconds REAL,
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
                CREATE TABLE IF NOT EXISTS sync_history (
                    id SERIAL PRIMARY KEY,
                    firm_id VARCHAR(36) REFERENCES firms(id) ON DELETE CASCADE,
                    status VARCHAR(20) DEFAULT 'started',
                    triggered_by VARCHAR(50) DEFAULT 'scheduler',
                    celery_task_id VARCHAR(255),
                    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    completed_at TIMESTAMP,
                    duration_seconds REAL,
                    records_synced INTEGER DEFAULT 0,
                    entity_results JSONB,
                    error_message TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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

            cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_firm ON users(firm_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_firm ON audit_log(firm_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_log(created_at)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_sync_history_firm ON sync_history(firm_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_firms_next_sync ON firms(next_sync_at)")

    def _encrypt(self, value: str) -> str:
        if self.fernet:
            return self.fernet.encrypt(value.encode()).decode()
        import base64
        return base64.b64encode(value.encode()).decode()

    def _decrypt(self, value: str) -> str:
        if self.fernet:
            return self.fernet.decrypt(value.encode()).decode()
        import base64
        return base64.b64decode(value.encode()).decode()

    # === Firm Methods ===

    def create_firm(self, name: str, trial_days: int = 14) -> Firm:
        firm_id = secrets.token_urlsafe(16)
        now = datetime.utcnow()
        trial_ends = now + timedelta(days=trial_days)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO firms (id, name, subscription_status, trial_ends_at, created_at, updated_at)
                VALUES (%s, %s, 'trial', %s, %s, %s)
            """, (firm_id, name, trial_ends, now, now))
        return Firm(id=firm_id, name=name, subscription_status='trial',
                    subscription_tier='standard', mycase_connected=False,
                    mycase_firm_id=None, created_at=now, updated_at=now,
                    trial_ends_at=trial_ends)

    def get_firm(self, firm_id: str) -> Optional[Firm]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM firms WHERE id = %s", (firm_id,))
            row = cursor.fetchone()
            if not row:
                return None
            row = dict(row)
            return Firm(
                id=row['id'], name=row['name'],
                subscription_status=row['subscription_status'],
                subscription_tier=row['subscription_tier'],
                mycase_connected=bool(row['mycase_connected']),
                mycase_firm_id=row['mycase_firm_id'],
                created_at=row['created_at'], updated_at=row['updated_at'],
                trial_ends_at=row.get('trial_ends_at'),
                stripe_customer_id=row.get('stripe_customer_id'),
                stripe_subscription_id=row.get('stripe_subscription_id'),
            )

    def get_firm_by_mycase_id(self, mycase_firm_id: int) -> Optional[Firm]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM firms WHERE mycase_firm_id = %s", (mycase_firm_id,))
            row = cursor.fetchone()
            return self.get_firm(dict(row)['id']) if row else None

    def get_active_firms(self) -> List[Firm]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id FROM firms
                WHERE subscription_status IN ('trial', 'active')
                AND mycase_connected = TRUE
            """)
            return [self.get_firm(dict(r)['id']) for r in cursor.fetchall()]

    def update_firm_subscription(self, firm_id: str, status: str, tier: str = None,
                                 stripe_customer_id: str = None,
                                 stripe_subscription_id: str = None):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            updates = ["subscription_status = %s", "updated_at = %s"]
            params: list = [status, datetime.utcnow()]
            if tier:
                updates.append("subscription_tier = %s"); params.append(tier)
            if stripe_customer_id:
                updates.append("stripe_customer_id = %s"); params.append(stripe_customer_id)
            if stripe_subscription_id:
                updates.append("stripe_subscription_id = %s"); params.append(stripe_subscription_id)
            params.append(firm_id)
            cursor.execute(f"UPDATE firms SET {', '.join(updates)} WHERE id = %s", params)

    # === MyCase Credentials ===

    def store_mycase_credentials(self, firm_id: str, access_token: str,
                                 refresh_token: str, expires_in: int,
                                 mycase_firm_id: int):
        expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE firms SET
                    mycase_connected = TRUE, mycase_firm_id = %s,
                    mycase_oauth_token = %s, mycase_oauth_refresh = %s,
                    mycase_token_expires_at = %s, updated_at = %s
                WHERE id = %s
            """, (mycase_firm_id, self._encrypt(access_token),
                  self._encrypt(refresh_token), expires_at,
                  datetime.utcnow(), firm_id))

    def get_mycase_credentials(self, firm_id: str) -> Optional[FirmCredentials]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT mycase_firm_id, mycase_oauth_token, mycase_oauth_refresh,
                       mycase_token_expires_at
                FROM firms WHERE id = %s AND mycase_connected = TRUE
            """, (firm_id,))
            row = cursor.fetchone()
            if not row:
                return None
            row = dict(row)
            return FirmCredentials(
                firm_id=firm_id,
                access_token=self._decrypt(row['mycase_oauth_token']),
                refresh_token=self._decrypt(row['mycase_oauth_refresh']),
                token_expires_at=row['mycase_token_expires_at'],
                mycase_firm_id=row['mycase_firm_id'],
            )

    def update_mycase_tokens(self, firm_id: str, access_token: str,
                             refresh_token: str, expires_in: int):
        expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE firms SET
                    mycase_oauth_token = %s, mycase_oauth_refresh = %s,
                    mycase_token_expires_at = %s, updated_at = %s
                WHERE id = %s
            """, (self._encrypt(access_token), self._encrypt(refresh_token),
                  expires_at, datetime.utcnow(), firm_id))

    # === User Methods ===

    def create_user(self, firm_id: str, email: str, name: str, role: str = 'admin',
                    auth_provider_id: str = None) -> User:
        user_id = secrets.token_urlsafe(16)
        now = datetime.utcnow()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO users (id, firm_id, email, name, role, auth_provider_id, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (user_id, firm_id, email, name, role, auth_provider_id, now))
        return User(id=user_id, firm_id=firm_id, email=email, name=name,
                    role=role, mycase_staff_id=None,
                    auth_provider_id=auth_provider_id, created_at=now,
                    last_login_at=None, is_active=True)

    def get_user(self, user_id: str) -> Optional[User]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
            row = cursor.fetchone()
            if not row:
                return None
            row = dict(row)
            return User(
                id=row['id'], firm_id=row['firm_id'], email=row['email'],
                name=row['name'], role=row['role'],
                mycase_staff_id=row['mycase_staff_id'],
                auth_provider_id=row['auth_provider_id'],
                created_at=row['created_at'],
                last_login_at=row.get('last_login_at'),
                is_active=bool(row['is_active']),
            )

    def get_user_by_email(self, email: str) -> Optional[User]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM users WHERE email = %s AND is_active = TRUE", (email,))
            row = cursor.fetchone()
            return self.get_user(dict(row)['id']) if row else None

    def get_firm_users(self, firm_id: str) -> List[User]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM users WHERE firm_id = %s AND is_active = TRUE", (firm_id,))
            return [self.get_user(dict(r)['id']) for r in cursor.fetchall()]

    def update_user_login(self, user_id: str):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET last_login_at = %s WHERE id = %s",
                           (datetime.utcnow(), user_id))

    # === Sync Status ===

    def update_sync_status(self, firm_id: str, status: str,
                           records_synced: int = None, error_message: str = None):
        now = datetime.utcnow()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO sync_status (firm_id, status, started_at, completed_at,
                                         records_synced, error_message)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (firm_id) DO UPDATE SET
                    status = EXCLUDED.status,
                    completed_at = CASE WHEN EXCLUDED.status IN ('completed', 'failed')
                                   THEN %s ELSE sync_status.completed_at END,
                    records_synced = COALESCE(EXCLUDED.records_synced, sync_status.records_synced),
                    error_message = EXCLUDED.error_message
            """, (firm_id, status,
                  now if status == 'running' else None,
                  now if status in ('completed', 'failed') else None,
                  records_synced, error_message, now))

    def get_sync_status(self, firm_id: str) -> Dict[str, Any]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM sync_status WHERE firm_id = %s", (firm_id,))
            row = cursor.fetchone()
            return dict(row) if row else {'status': 'never', 'records_synced': 0}

    # === Audit Log ===

    def log_audit(self, firm_id: str, user_id: str, action: str,
                  details: Dict = None, ip_address: str = None):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO audit_log (firm_id, user_id, action, details, ip_address)
                VALUES (%s, %s, %s, %s, %s)
            """, (firm_id, user_id, action,
                  json.dumps(details) if details else None, ip_address))

    # === Sync Scheduling ===

    def get_firms_due_for_sync(self, limit: int = 10) -> List[Dict]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, name, sync_frequency_minutes, last_sync_at, next_sync_at
                FROM firms
                WHERE subscription_status IN ('trial', 'active')
                AND mycase_connected = TRUE
                AND (last_sync_status IS NULL OR last_sync_status != 'running')
                AND (next_sync_at IS NULL OR next_sync_at <= NOW())
                ORDER BY next_sync_at ASC NULLS FIRST,
                         last_sync_at ASC NULLS FIRST
                LIMIT %s
            """, (limit,))
            return [dict(row) for row in cursor.fetchall()]

    def schedule_next_sync(self, firm_id: str, delay_minutes: int = None):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if delay_minutes:
                cursor.execute("""
                    UPDATE firms SET next_sync_at = NOW() + (%s || ' minutes')::INTERVAL
                    WHERE id = %s
                """, (str(delay_minutes), firm_id))
            else:
                cursor.execute("""
                    UPDATE firms
                    SET next_sync_at = NOW() + (COALESCE(sync_frequency_minutes, 240) || ' minutes')::INTERVAL
                    WHERE id = %s
                """, (firm_id,))

    def get_active_firms_list(self) -> List[Dict]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, name FROM firms
                WHERE subscription_status IN ('trial', 'active')
                AND mycase_connected = TRUE
            """)
            return [dict(row) for row in cursor.fetchall()]

    # === Token Expiration ===

    def get_firms_with_expiring_tokens(self, within_minutes: int = 60) -> List[Dict]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, name, mycase_token_expires_at
                FROM firms
                WHERE subscription_status IN ('trial', 'active')
                AND mycase_connected = TRUE
                AND mycase_token_expires_at IS NOT NULL
                AND mycase_token_expires_at <= NOW() + (%s || ' minutes')::INTERVAL
                AND mycase_token_expires_at > NOW()
            """, (str(within_minutes),))
            return [dict(row) for row in cursor.fetchall()]

    # === Sync History ===

    def record_sync_start(self, firm_id: str, triggered_by: str = "scheduler",
                          celery_task_id: str = None) -> Optional[int]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO sync_history (firm_id, status, triggered_by, started_at, celery_task_id)
                VALUES (%s, 'started', %s, NOW(), %s)
                RETURNING id
            """, (firm_id, triggered_by, celery_task_id))
            row = cursor.fetchone()
            return dict(row)["id"] if row else None

    def record_sync_complete(self, firm_id: str, records_synced: int = 0,
                             duration_seconds: float = 0, entity_results: dict = None):
        entity_json = json.dumps(entity_results) if entity_results else None
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE sync_history
                SET status = 'completed', completed_at = NOW(),
                    duration_seconds = %s, records_synced = %s,
                    entity_results = %s::jsonb
                WHERE id = (
                    SELECT id FROM sync_history
                    WHERE firm_id = %s AND status = 'started'
                    ORDER BY started_at DESC LIMIT 1
                )
            """, (duration_seconds, records_synced, entity_json, firm_id))
            cursor.execute("""
                UPDATE firms
                SET last_sync_at = NOW(), last_sync_status = 'completed',
                    last_sync_error = NULL, last_sync_records = %s,
                    last_sync_duration_seconds = %s, updated_at = NOW()
                WHERE id = %s
            """, (records_synced, duration_seconds, firm_id))

    def record_sync_failure(self, firm_id: str, error: str = None):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE sync_history
                SET status = 'failed', completed_at = NOW(), error_message = %s
                WHERE id = (
                    SELECT id FROM sync_history
                    WHERE firm_id = %s AND status = 'started'
                    ORDER BY started_at DESC LIMIT 1
                )
            """, (error, firm_id))
            cursor.execute("""
                UPDATE firms
                SET last_sync_status = 'failed', last_sync_error = %s, updated_at = NOW()
                WHERE id = %s
            """, (error, firm_id))

    def get_sync_history(self, firm_id: str, limit: int = 20) -> List[Dict]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, status, triggered_by, started_at, completed_at,
                       duration_seconds, records_synced, entity_results, error_message
                FROM sync_history WHERE firm_id = %s
                ORDER BY started_at DESC LIMIT %s
            """, (firm_id, limit))
            return [dict(row) for row in cursor.fetchall()]

    # === Stale Sync Detection ===

    def detect_and_fail_stale_syncs(self, stale_minutes: int = 45) -> List[str]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, name FROM firms
                WHERE last_sync_status = 'running'
                AND last_sync_at < NOW() - (%s || ' minutes')::INTERVAL
            """, (str(stale_minutes),))
            stale_firms = [dict(row) for row in cursor.fetchall()]
            for firm in stale_firms:
                cursor.execute("""
                    UPDATE firms
                    SET last_sync_status = 'failed',
                        last_sync_error = 'Sync timed out (stale detection)',
                        updated_at = NOW()
                    WHERE id = %s
                """, (firm["id"],))
                self.schedule_next_sync(firm["id"], delay_minutes=15)
            return [f["id"] for f in stale_firms]

    def cleanup_old_sync_history(self, days: int = 90) -> int:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                DELETE FROM sync_history
                WHERE created_at < NOW() - (%s || ' days')::INTERVAL
            """, (str(days),))
            return cursor.rowcount

    # === Dashboard Queries ===

    def get_sync_health_summary(self) -> Dict[str, Any]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT
                    COUNT(*) FILTER (WHERE last_sync_status = 'completed') AS healthy,
                    COUNT(*) FILTER (WHERE last_sync_status = 'failed') AS failed,
                    COUNT(*) FILTER (WHERE last_sync_status = 'running') AS running,
                    COUNT(*) FILTER (WHERE last_sync_at IS NULL) AS never_synced,
                    COUNT(*) FILTER (WHERE next_sync_at < NOW()) AS overdue,
                    COUNT(*) AS total
                FROM firms
                WHERE subscription_status IN ('trial', 'active')
                AND mycase_connected = TRUE
            """)
            row = cursor.fetchone()
            return dict(row) if row else {}

    def get_firm_sync_dashboard(self, firm_id: str) -> Optional[Dict]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT last_sync_at, last_sync_status, last_sync_records,
                       last_sync_duration_seconds, last_sync_error,
                       next_sync_at, sync_frequency_minutes
                FROM firms WHERE id = %s
            """, (firm_id,))
            row = cursor.fetchone()
            if not row:
                return None
            result = dict(row)
            result["recent_history"] = self.get_sync_history(firm_id, limit=5)
            return result


_platform_db: Optional[PlatformDB] = None


def get_platform_db() -> PlatformDB:
    global _platform_db
    if _platform_db is None:
        _platform_db = PlatformDB()
    return _platform_db
