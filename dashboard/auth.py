"""
Dashboard Authentication for FastAPI

Supports multiple users stored in SQLite database.
"""
import sqlite3
from functools import wraps
from pathlib import Path
from fastapi import Request, HTTPException, Depends
from fastapi.responses import RedirectResponse
from werkzeug.security import check_password_hash, generate_password_hash
import dashboard.config as config


# Database path
USERS_DB = config.DATA_DIR / "mycase_cache.db"


def _get_db_connection():
    """Get database connection."""
    conn = sqlite3.connect(USERS_DB)
    conn.row_factory = sqlite3.Row
    return conn


def init_users_table():
    """Create users table if it doesn't exist."""
    conn = _get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS dashboard_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            email TEXT,
            role TEXT DEFAULT 'user',
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()


def create_user(username: str, password: str, email: str = None, role: str = "user") -> bool:
    """
    Create a new user.

    Args:
        username: Unique username
        password: Plain text password (will be hashed)
        email: Optional email address
        role: User role ('admin' or 'user')

    Returns:
        bool: True if created successfully
    """
    init_users_table()
    conn = _get_db_connection()
    cursor = conn.cursor()

    try:
        password_hash = generate_password_hash(password)
        cursor.execute("""
            INSERT INTO dashboard_users (username, password_hash, email, role)
            VALUES (?, ?, ?, ?)
        """, (username, password_hash, email, role))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        # Username already exists
        return False
    finally:
        conn.close()


def get_user(username: str) -> dict | None:
    """Get user by username."""
    init_users_table()
    conn = _get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, username, password_hash, email, role, is_active, created_at, last_login
        FROM dashboard_users
        WHERE username = ? AND is_active = 1
    """, (username,))

    row = cursor.fetchone()
    conn.close()

    if row:
        return dict(row)
    return None


def list_users() -> list:
    """List all users."""
    init_users_table()
    conn = _get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, username, email, role, is_active, created_at, last_login
        FROM dashboard_users
        ORDER BY created_at DESC
    """)

    users = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return users


def update_user_password(username: str, new_password: str) -> bool:
    """Update user's password."""
    conn = _get_db_connection()
    cursor = conn.cursor()

    password_hash = generate_password_hash(new_password)
    cursor.execute("""
        UPDATE dashboard_users
        SET password_hash = ?
        WHERE username = ?
    """, (password_hash, username))

    success = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return success


def delete_user(username: str) -> bool:
    """Delete a user (soft delete - sets is_active=0)."""
    conn = _get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE dashboard_users
        SET is_active = 0
        WHERE username = ?
    """, (username,))

    success = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return success


def update_last_login(username: str):
    """Update user's last login timestamp."""
    conn = _get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE dashboard_users
        SET last_login = CURRENT_TIMESTAMP
        WHERE username = ?
    """, (username,))

    conn.commit()
    conn.close()


def login_user(request: Request, username: str, password: str) -> bool:
    """
    Authenticate user credentials.

    Checks database users first, then falls back to env-based admin.

    Returns:
        bool: True if authentication successful, False otherwise
    """
    # Check database users first
    user = get_user(username)
    if user and check_password_hash(user["password_hash"], password):
        request.session["logged_in"] = True
        request.session["username"] = username
        request.session["role"] = user["role"]
        update_last_login(username)
        return True

    # Fallback to env-based admin (for backwards compatibility)
    if username == config.ADMIN_USERNAME:
        if check_password_hash(config.ADMIN_PASSWORD_HASH, password):
            request.session["logged_in"] = True
            request.session["username"] = username
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
