"""
Subdomain Resolution Middleware

Extracts firm_id from the Host header subdomain for multi-tenant routing.
Each firm gets a branded URL: jcs.lawmetrics.ai, smith.lawmetrics.ai, etc.

The middleware sets request.state.firm_id_from_subdomain which the login
route uses to auto-fill firm_id (so users don't have to type it).

Reserved subdomains (www, app, api) are skipped — no firm context.
Local development (localhost, 127.0.0.1) is skipped entirely.
"""
import os
import logging

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

logger = logging.getLogger(__name__)

# The base domain. Override with LAWMETRICS_DOMAIN env var for staging.
DOMAIN = os.environ.get("LAWMETRICS_DOMAIN", "lawmetrics.ai")

# These subdomains don't map to a firm — they're platform-level.
RESERVED_SUBDOMAINS = frozenset({
    "www", "app", "api", "admin", "mail", "smtp", "ftp",
    "staging", "dev", "test",
})


class SubdomainResolutionMiddleware(BaseHTTPMiddleware):
    """
    Resolves firm_id from the Host header subdomain.

    Examples:
        jcs.lawmetrics.ai     → firm_id from DB (e.g. 'jcs_law')
        app.lawmetrics.ai     → None (generic login with firm_id field)
        www.lawmetrics.ai     → None (marketing site)
        localhost:3000        → None (local dev, skip)
    """

    async def dispatch(self, request: Request, call_next):
        host = request.headers.get("host", "").lower()
        subdomain = _extract_subdomain(host)

        # Always set request.state so routes can check without AttributeError
        request.state.subdomain = subdomain
        request.state.firm_id_from_subdomain = None

        # Skip reserved and empty subdomains
        if subdomain and subdomain not in RESERVED_SUBDOMAINS:
            firm_id = _resolve_firm_id(subdomain)
            if firm_id:
                request.state.firm_id_from_subdomain = firm_id
                logger.debug("Subdomain '%s' → firm_id '%s'", subdomain, firm_id)
            else:
                logger.info("Unknown subdomain: %s", subdomain)

        response = await call_next(request)
        return response


def _extract_subdomain(host: str) -> str | None:
    """
    Extract the subdomain prefix from the Host header.

    'jcs.lawmetrics.ai'       → 'jcs'
    'jcs.lawmetrics.ai:3000'  → 'jcs'
    'app.lawmetrics.ai'       → 'app'
    'lawmetrics.ai'           → None (apex)
    'localhost:3000'           → None (not our domain)
    '127.0.0.1:3000'          → None (local dev)
    """
    # Strip port
    if ":" in host:
        host = host.split(":")[0]

    # Must end with our domain
    if not host.endswith(DOMAIN):
        return None

    # Extract prefix before the domain
    prefix = host[: -len(DOMAIN)].rstrip(".")
    return prefix if prefix else None


def _resolve_firm_id(subdomain: str) -> str | None:
    """
    Look up firm_id in the database by subdomain.

    Returns firm_id (e.g. 'jcs_law') or None if not found/not verified.
    Uses get_firm_by_subdomain() from db/firms.py.
    """
    try:
        from db.firms import get_firm_by_subdomain
        firm = get_firm_by_subdomain(subdomain)
        return firm["id"] if firm else None
    except Exception as e:
        logger.error("Subdomain resolution error for '%s': %s", subdomain, e)
        return None
