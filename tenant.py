"""
Multi-Tenant Context Management

Provides request-scoped tenant context using Python's contextvars.
This allows the current firm_id to be accessed anywhere in the call stack
without explicitly passing it through every function.
"""
from contextvars import ContextVar
from typing import Optional
from dataclasses import dataclass
from datetime import datetime


# Context variable for current tenant - set by middleware, read anywhere
current_tenant: ContextVar[Optional[str]] = ContextVar('current_tenant', default=None)


@dataclass
class TenantContext:
    """Full tenant context including user information."""
    firm_id: str
    user_id: str
    user_email: str
    user_role: str  # 'admin', 'attorney', 'staff', 'readonly'
    mycase_staff_id: Optional[int] = None  # For attorney-specific filtering
    firm_name: Optional[str] = None


# Context variable for full tenant context
current_context: ContextVar[Optional[TenantContext]] = ContextVar('current_context', default=None)


def get_current_firm_id() -> str:
    """
    Get the current firm ID from context.
    
    Raises:
        ValueError: If no tenant context is set
    """
    firm_id = current_tenant.get()
    if firm_id is None:
        raise ValueError("No tenant context set - this operation requires a firm context")
    return firm_id


def get_current_context() -> TenantContext:
    """
    Get the full current tenant context.
    
    Raises:
        ValueError: If no tenant context is set
    """
    ctx = current_context.get()
    if ctx is None:
        raise ValueError("No tenant context set - this operation requires authentication")
    return ctx


def set_tenant_context(firm_id: str, user_id: str = None, user_email: str = None,
                       user_role: str = 'readonly', mycase_staff_id: int = None,
                       firm_name: str = None) -> tuple:
    """
    Set the tenant context for the current request.
    
    Returns:
        Tuple of context tokens that can be used to reset the context
    """
    token1 = current_tenant.set(firm_id)
    
    ctx = TenantContext(
        firm_id=firm_id,
        user_id=user_id or '',
        user_email=user_email or '',
        user_role=user_role,
        mycase_staff_id=mycase_staff_id,
        firm_name=firm_name
    )
    token2 = current_context.set(ctx)
    
    return (token1, token2)


def reset_tenant_context(tokens: tuple) -> None:
    """Reset the tenant context using the tokens from set_tenant_context."""
    token1, token2 = tokens
    current_tenant.reset(token1)
    current_context.reset(token2)


class TenantContextManager:
    """
    Context manager for temporarily setting tenant context.
    
    Usage:
        with TenantContextManager(firm_id='abc123'):
            # All code here has access to firm_id
            analytics = FirmAnalytics()  # Uses current tenant automatically
    """
    
    def __init__(self, firm_id: str, **kwargs):
        self.firm_id = firm_id
        self.kwargs = kwargs
        self.tokens = None
    
    def __enter__(self):
        self.tokens = set_tenant_context(self.firm_id, **self.kwargs)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.tokens:
            reset_tenant_context(self.tokens)
        return False


# Decorator for functions that require tenant context
def require_tenant(func):
    """
    Decorator that ensures a function is called with tenant context.
    
    Usage:
        @require_tenant
        def my_function():
            firm_id = get_current_firm_id()  # Guaranteed to work
    """
    def wrapper(*args, **kwargs):
        if current_tenant.get() is None:
            raise ValueError(f"{func.__name__} requires tenant context")
        return func(*args, **kwargs)
    return wrapper


def require_role(minimum_role: str):
    """
    Decorator factory that ensures user has minimum role level.
    
    Role hierarchy: admin > attorney > staff > readonly
    
    Usage:
        @require_role('attorney')
        def view_case_details():
            pass
    """
    ROLE_HIERARCHY = {
        'admin': 4,
        'attorney': 3,
        'staff': 2,
        'readonly': 1
    }
    
    def decorator(func):
        def wrapper(*args, **kwargs):
            ctx = current_context.get()
            if ctx is None:
                raise ValueError(f"{func.__name__} requires authentication")
            
            user_level = ROLE_HIERARCHY.get(ctx.user_role, 0)
            required_level = ROLE_HIERARCHY.get(minimum_role, 0)
            
            if user_level < required_level:
                raise PermissionError(
                    f"{func.__name__} requires {minimum_role} role or higher "
                    f"(current: {ctx.user_role})"
                )
            
            return func(*args, **kwargs)
        return wrapper
    return decorator
