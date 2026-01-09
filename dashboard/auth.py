"""
Dashboard Authentication for FastAPI
"""
from functools import wraps
from fastapi import Request, HTTPException, Depends
from fastapi.responses import RedirectResponse
from werkzeug.security import check_password_hash
import dashboard.config as config


def login_user(request: Request, username: str, password: str) -> bool:
    """
    Authenticate user credentials.

    Returns:
        bool: True if authentication successful, False otherwise
    """
    if username == config.ADMIN_USERNAME:
        if check_password_hash(config.ADMIN_PASSWORD_HASH, password):
            request.session["logged_in"] = True
            request.session["username"] = username
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


async def require_auth(request: Request):
    """Dependency that requires authentication."""
    if not is_authenticated(request):
        raise HTTPException(status_code=303, headers={"Location": "/login"})
    return request.session.get("username")
