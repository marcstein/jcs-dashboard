"""
Dashboard Authentication for FastAPI

Supports multiple users stored in PostgreSQL database.
"""
from fastapi import Request, HTTPException, Depends
from fastapi.responses import RedirectResponse
from werkzeug.security import check_password_hash, generate_password_hash
import dashboard.config as config
from db.connection import get_connection


def _row_to_dict(row, keys):
    """Convert a row (tuple or dict) to a dict using the given keys."""
    if row is None:
        return None
    if isinstance(row, dict):
        return {k: row.get(k) for k in keys}
    return {k: row[i] for i, k in enumerate(keys)}


USER_KEYS = ["id", "firm_id", "username", "password_hash", "email", "role", "is_active", "created_at", "last_login"]
USER_LIST_KEYS = ["id", "firm_id", "username", "email", "role", "is_active", "created_at", "last_login"]


def init_users_table():
    """Create users table if it doesn't exist."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS dashboard_users (
                    id SERIAL PRIMARY KEY,
                    firm_id TEXT NOT NULL DEFAULT 'default',
                    username TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    email TEXT,
                    role TEXT DEFAULT 'user',
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_login TIMESTAMP,
                    UNIQUE(firm_id, username)
                )
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_dashboard_users_firm_id
                ON dashboard_users(firm_id)
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_dashboard_users_username
                ON dashboard_users(username)
            """)
        conn.commit()


def create_user(username: str, password: str, email: str = None, role: str = "user", firm_id: str = "default") -> bool:
    """
    Create a new user.

    Args:
        username: Unique username
        password: Plain text password (will be hashed)
        email: Optional email address
        role: User role ('admin' or 'user')
        firm_id: Firm ID for multi-tenant isolation

    Returns:
        bool: True if created successfully
    """
    init_users_table()

    try:
        password_hash = generate_password_hash(password)
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO dashboard_users (firm_id, username, password_hash, email, role)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (firm_id, username) DO UPDATE SET
                        password_hash = EXCLUDED.password_hash,
                        email = EXCLUDED.email,
                        role = EXCLUDED.role,
                        is_active = TRUE
                """, (firm_id, username, password_hash, email, role))
            conn.commit()
        return True
    except Exception:
        return False


def get_user(username: str, firm_id: str = "default") -> dict | None:
    """Get user by username and firm_id."""
    init_users_table()

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, firm_id, username, password_hash, email, role, is_active, created_at, last_login
                FROM dashboard_users
                WHERE username = %s AND firm_id = %s AND is_active = TRUE
            """, (username, firm_id))

            row = cur.fetchone()

    return _row_to_dict(row, USER_KEYS)


def list_users(firm_id: str = "default") -> list:
    """List all users for a firm."""
    init_users_table()

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, firm_id, username, email, role, is_active, created_at, last_login
                FROM dashboard_users
                WHERE firm_id = %s
                ORDER BY created_at DESC
            """, (firm_id,))

            rows = cur.fetchall()

    return [_row_to_dict(row, USER_LIST_KEYS) for row in rows]


def update_user_password(username: str, new_password: str, firm_id: str = "default") -> bool:
    """Update user's password."""
    password_hash = generate_password_hash(new_password)

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE dashboard_users
                SET password_hash = %s
                WHERE username = %s AND firm_id = %s
            """, (password_hash, username, firm_id))

            success = cur.rowcount > 0
        conn.commit()

    return success


def delete_user(username: str, firm_id: str = "default") -> bool:
    """Delete a user (soft delete - sets is_active=FALSE)."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE dashboard_users
                SET is_active = FALSE
                WHERE username = %s AND firm_id = %s
            """, (username, firm_id))

            success = cur.rowcount > 0
        conn.commit()

    return success


def update_last_login(username: str, firm_id: str = "default"):
    """Update user's last login timestamp."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE dashboard_users
                SET last_login = CURRENT_TIMESTAMP
                WHERE username = %s AND firm_id = %s
            """, (username, firm_id))
        conn.commit()


def login_user(request: Request, username: str, password: str, firm_id: str = "default") -> bool:
    """
    Authenticate user credentials.

    Checks database users first, then falls back to env-based admin.

    Returns:
        bool: True if authentication successful, False otherwise
    """
    # Check database users first
    user = get_user(username, firm_id)
    if user and check_password_hash(user["password_hash"], password):
        request.session["logged_in"] = True
        request.session["username"] = username
        request.session["firm_id"] = firm_id
        request.session["role"] = user["role"]
        update_last_login(username, firm_id)
        return True

    # Fallback to env-based admin (for backwards compatibility)
    if username == config.ADMIN_USERNAME:
        if check_password_hash(config.ADMIN_PASSWORD_HASH, password):
            request.session["logged_in"] = True
            request.session["username"] = username
            request.session["firm_id"] = firm_id
            request.session["role"] = "admin"
            return True

    return False


def logout_user(request: Request):
    """Clear user session."""
    request.session.clear()


def is_authenticated(request: Request) -> bool:
    """Check if current user is authenticated."""
    return request.session.get("logged_in", False)


def get_current_user(request: Request) -> str | None:
    """Get the current logged in username."""
    if is_authenticated(request):
        return request.session.get("username")
    return None


def get_current_firm_id(request: Request) -> str:
    """Get the current user's firm_id."""
    if is_authenticated(request):
        return request.session.get("firm_id", "default")
    return "default"


def get_current_role(request: Request) -> str | None:
    """Get the current user's role."""
    if is_authenticated(request):
        return request.session.get("role", "user")
    return None


def is_admin(request: Request) -> bool:
    """Check if current user is an admin."""
    return get_current_role(request) == "admin"


async def require_auth(request: Request):
    """Dependency that requires authentication."""
    if not is_authenticated(request):
        raise HTTPException(status_code=303, headers={"Location": "/login"})
    return request.session.get("username")


async def require_admin(request: Request):
    """Dependency that requires admin role."""
    if not is_authenticated(request):
        raise HTTPException(status_code=303, headers={"Location": "/login"})
    if not is_admin(request):
        raise HTTPException(status_code=403, detail="Admin access required")
    return request.session.get("username")
