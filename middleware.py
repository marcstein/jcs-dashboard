"""
Multi-Tenant FastAPI Middleware

Extracts tenant context from authentication and makes it available
throughout the request lifecycle.

Also provides RBAC (Role-Based Access Control) for route protection.
"""
import os
import jwt
from typing import Optional, Callable
from datetime import datetime
from functools import wraps

from fastapi import Request, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from tenant import (
    current_tenant, current_context, TenantContext,
    set_tenant_context, reset_tenant_context
)
from platform_db import get_platform_db


# JWT settings (use environment variables in production)
JWT_SECRET = os.environ.get('JWT_SECRET', 'dev-secret-change-in-production')
JWT_ALGORITHM = os.environ.get('JWT_ALGORITHM', 'HS256')

# Security scheme for Swagger UI
security = HTTPBearer(auto_error=False)


class TenantMiddleware(BaseHTTPMiddleware):
    """
    Middleware that extracts tenant context from JWT tokens.
    
    For authenticated requests, sets the tenant context for the duration
    of the request, making firm_id available throughout the call stack.
    """
    
    # Routes that don't require authentication
    PUBLIC_ROUTES = [
        '/',
        '/health',
        '/docs',
        '/openapi.json',
        '/redoc',
        '/auth/login',
        '/auth/callback',
        '/auth/logout',
        '/onboard/signup',
        '/connect/mycase/callback',
    ]
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Skip auth for public routes
        if self._is_public_route(request.url.path):
            return await call_next(request)
        
        # Skip auth for static files
        if request.url.path.startswith('/static'):
            return await call_next(request)
        
        # Try to extract and validate token
        token = self._extract_token(request)
        
        if not token:
            # For API routes, require authentication
            if request.url.path.startswith('/api'):
                return Response(
                    content='{"detail": "Not authenticated"}',
                    status_code=401,
                    media_type='application/json'
                )
            # For web routes, redirect to login
            return Response(
                status_code=302,
                headers={'Location': '/auth/login'}
            )
        
        try:
            # Decode and validate JWT
            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            
            # Extract user info from token
            firm_id = payload.get('firm_id')
            user_id = payload.get('user_id')
            user_email = payload.get('email')
            user_role = payload.get('role', 'readonly')
            mycase_staff_id = payload.get('mycase_staff_id')
            firm_name = payload.get('firm_name')
            
            if not firm_id:
                raise HTTPException(status_code=403, detail="No firm associated with user")
            
            # Set tenant context for this request
            tokens = set_tenant_context(
                firm_id=firm_id,
                user_id=user_id,
                user_email=user_email,
                user_role=user_role,
                mycase_staff_id=mycase_staff_id,
                firm_name=firm_name
            )
            
            # Store context in request state for route handlers
            request.state.user_id = user_id
            request.state.firm_id = firm_id
            request.state.user_email = user_email
            request.state.user_role = user_role
            request.state.mycase_staff_id = mycase_staff_id
            request.state.firm_name = firm_name
            
            try:
                response = await call_next(request)
                return response
            finally:
                # Always reset context after request
                reset_tenant_context(tokens)
                
        except jwt.ExpiredSignatureError:
            return Response(
                content='{"detail": "Token expired"}',
                status_code=401,
                media_type='application/json'
            )
        except jwt.InvalidTokenError as e:
            return Response(
                content=f'{{"detail": "Invalid token: {str(e)}"}}',
                status_code=401,
                media_type='application/json'
            )
    
    def _is_public_route(self, path: str) -> bool:
        """Check if a route is public (no auth required)."""
        # Exact matches
        if path in self.PUBLIC_ROUTES:
            return True
        
        # Prefix matches for nested public routes
        public_prefixes = ['/auth/', '/onboard/', '/static/', '/connect/mycase/callback']
        for prefix in public_prefixes:
            if path.startswith(prefix):
                return True
        
        return False
    
    def _extract_token(self, request: Request) -> Optional[str]:
        """Extract JWT token from request."""
        # Try Authorization header first
        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            return auth_header[7:]
        
        # Try cookie
        token = request.cookies.get('access_token')
        if token:
            return token
        
        return None


# =============================================================================
# Dependency Injection Helpers
# =============================================================================

async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> dict:
    """
    Dependency to get current user from request state.
    
    Use in route handlers:
        @app.get("/api/profile")
        async def get_profile(user: dict = Depends(get_current_user)):
            return {"user_id": user["user_id"]}
    """
    if not hasattr(request.state, 'user_id'):
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    return {
        'user_id': request.state.user_id,
        'firm_id': request.state.firm_id,
        'email': request.state.user_email,
        'role': request.state.user_role,
        'mycase_staff_id': request.state.mycase_staff_id,
        'firm_name': request.state.firm_name
    }


async def get_current_firm_id(request: Request) -> str:
    """
    Dependency to get current firm ID.
    
    Use in route handlers:
        @app.get("/api/cases")
        async def get_cases(firm_id: str = Depends(get_current_firm_id)):
            cache = get_cache(firm_id)
            return cache.get_cases()
    """
    if not hasattr(request.state, 'firm_id'):
        raise HTTPException(status_code=401, detail="Not authenticated")
    return request.state.firm_id


def require_role(minimum_role: str):
    """
    Dependency factory for role-based access control.
    
    Use in route handlers:
        @app.post("/api/settings")
        async def update_settings(
            user: dict = Depends(require_role('admin'))
        ):
            # Only admins can access this endpoint
            pass
    """
    ROLE_HIERARCHY = {
        'admin': 4,
        'attorney': 3,
        'staff': 2,
        'readonly': 1
    }
    
    async def role_checker(
        request: Request,
        credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
    ) -> dict:
        if not hasattr(request.state, 'user_role'):
            raise HTTPException(status_code=401, detail="Not authenticated")
        
        user_level = ROLE_HIERARCHY.get(request.state.user_role, 0)
        required_level = ROLE_HIERARCHY.get(minimum_role, 0)
        
        if user_level < required_level:
            raise HTTPException(
                status_code=403,
                detail=f"Requires {minimum_role} role or higher"
            )
        
        return {
            'user_id': request.state.user_id,
            'firm_id': request.state.firm_id,
            'email': request.state.user_email,
            'role': request.state.user_role,
            'mycase_staff_id': request.state.mycase_staff_id,
            'firm_name': request.state.firm_name
        }
    
    return role_checker


# =============================================================================
# Token Generation Helpers
# =============================================================================

def create_access_token(
    user_id: str,
    firm_id: str,
    email: str,
    role: str,
    mycase_staff_id: int = None,
    firm_name: str = None,
    expires_hours: int = 24
) -> str:
    """
    Create a JWT access token for a user.
    
    Args:
        user_id: Platform user ID
        firm_id: Firm ID
        email: User's email
        role: User's role (admin, attorney, staff, readonly)
        mycase_staff_id: Optional MyCase staff ID for attorney filtering
        firm_name: Optional firm name for display
        expires_hours: Token validity in hours (default 24)
    
    Returns:
        JWT token string
    """
    from datetime import timedelta
    
    payload = {
        'user_id': user_id,
        'firm_id': firm_id,
        'email': email,
        'role': role,
        'mycase_staff_id': mycase_staff_id,
        'firm_name': firm_name,
        'iat': datetime.utcnow(),
        'exp': datetime.utcnow() + timedelta(hours=expires_hours)
    }
    
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    """
    Decode and validate a JWT token.
    
    Args:
        token: JWT token string
        
    Returns:
        Token payload dict
        
    Raises:
        jwt.ExpiredSignatureError: If token is expired
        jwt.InvalidTokenError: If token is invalid
    """
    return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])


# =============================================================================
# Analytics Dependency
# =============================================================================

from firm_analytics_mt import FirmAnalytics


async def get_analytics(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> FirmAnalytics:
    """
    Dependency to get analytics instance for current firm.
    
    Automatically applies attorney filtering based on user role:
    - Admins see all data
    - Attorneys see only their own cases
    - Staff/readonly see aggregate data
    
    Use in route handlers:
        @app.get("/api/revenue/by-type")
        async def get_revenue(analytics: FirmAnalytics = Depends(get_analytics)):
            return analytics.get_revenue_by_case_type()
    """
    if not hasattr(request.state, 'firm_id'):
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    # Apply attorney filtering for attorney role
    attorney_id = None
    if request.state.user_role == 'attorney' and request.state.mycase_staff_id:
        attorney_id = request.state.mycase_staff_id
    
    return FirmAnalytics(
        firm_id=request.state.firm_id,
        attorney_id=attorney_id
    )
