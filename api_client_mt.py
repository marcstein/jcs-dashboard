"""
Multi-Tenant MyCase API Client

A robust HTTP client for the MyCase API with multi-tenant support:
- Per-firm OAuth credentials from platform database
- Automatic token refresh with persistence
- Rate limiting (25 req/sec)
- Retry logic with exponential backoff
- Comprehensive endpoint coverage

Key changes from single-tenant:
1. Credentials loaded from platform database per firm
2. Token refresh updates platform database
3. Factory function to get client for specific firm
"""
import time
import re
import os
from typing import Any, Optional, Dict, List, Tuple
from datetime import datetime, timedelta
from urllib.parse import urlparse, parse_qs
import httpx
from functools import wraps

from config import MYCASE_API_URL, RATE_LIMIT_PER_SECOND, MYCASE_AUTH_URL
from tenant import current_tenant, get_current_firm_id


class RateLimiter:
    """Simple rate limiter to stay within API limits."""

    def __init__(self, max_per_second: int = RATE_LIMIT_PER_SECOND):
        self.max_per_second = max_per_second
        self.tokens = max_per_second
        self.last_update = time.time()

    def acquire(self):
        """Wait if necessary to acquire a rate limit token."""
        now = time.time()
        time_passed = now - self.last_update
        self.tokens = min(
            self.max_per_second,
            self.tokens + time_passed * self.max_per_second
        )
        self.last_update = now

        if self.tokens < 1:
            sleep_time = (1 - self.tokens) / self.max_per_second
            time.sleep(sleep_time)
            self.tokens = 0
        else:
            self.tokens -= 1


class MyCaseAPIError(Exception):
    """Custom exception for MyCase API errors."""

    def __init__(self, message: str, status_code: int = None, response: dict = None):
        super().__init__(message)
        self.status_code = status_code
        self.response = response


class MyCaseClient:
    """
    MyCase API Client with multi-tenant support.
    
    In multi-tenant mode, credentials are loaded from platform database.
    In legacy mode, credentials come from environment/token file.

    Usage (multi-tenant):
        client = get_client_for_firm('firm_abc123')
        cases = client.get_cases()
        
    Usage (legacy):
        client = MyCaseClient()  # Uses env vars/token file
        cases = client.get_cases()
    """

    def __init__(self, firm_id: str = None, base_url: str = MYCASE_API_URL):
        """
        Initialize API client.
        
        Args:
            firm_id: The firm ID for multi-tenant mode. If None, uses legacy auth.
            base_url: API base URL
        """
        self.base_url = base_url
        self.firm_id = firm_id or current_tenant.get()
        self.rate_limiter = RateLimiter()
        self._http_client = httpx.Client(timeout=30.0)
        
        # Credentials (loaded lazily in multi-tenant mode)
        self._access_token = None
        self._refresh_token = None
        self._token_expires_at = None
        
        # If no firm_id, fall back to legacy auth
        if not self.firm_id:
            self._init_legacy_auth()

    def _init_legacy_auth(self):
        """Initialize using legacy token file auth."""
        from auth import MyCaseAuth
        self._legacy_auth = MyCaseAuth()
    
    def _load_credentials(self):
        """Load credentials from platform database."""
        if not self.firm_id:
            return  # Legacy mode, credentials loaded elsewhere
        
        from platform_db import get_platform_db
        
        db = get_platform_db()
        creds = db.get_mycase_credentials(self.firm_id)
        
        if not creds:
            raise MyCaseAPIError(
                f"No MyCase credentials found for firm {self.firm_id}. "
                "Please connect your MyCase account."
            )
        
        self._access_token = creds.access_token
        self._refresh_token = creds.refresh_token
        self._token_expires_at = creds.token_expires_at
    
    def _ensure_token_valid(self):
        """Ensure we have a valid access token, refreshing if needed."""
        if not self.firm_id:
            # Legacy mode - use MyCaseAuth
            return
        
        # Load credentials if we haven't yet
        if self._access_token is None:
            self._load_credentials()
        
        # Check if token needs refresh (within 5 minutes of expiration)
        if self._token_expires_at and \
           datetime.utcnow() >= (self._token_expires_at - timedelta(minutes=5)):
            self._refresh_access_token()
    
    def _refresh_access_token(self):
        """Refresh the access token using the refresh token."""
        if not self.firm_id:
            # Legacy mode
            self._legacy_auth.refresh_access_token()
            return
        
        # Multi-tenant refresh
        response = self._http_client.post(
            f"{MYCASE_AUTH_URL}/tokens",
            data={
                "client_id": os.environ.get('MYCASE_CLIENT_ID'),
                "client_secret": os.environ.get('MYCASE_CLIENT_SECRET'),
                "refresh_token": self._refresh_token,
                "grant_type": "refresh_token",
            }
        )
        
        if not response.is_success:
            raise MyCaseAPIError(
                f"Failed to refresh token: {response.text}",
                status_code=response.status_code
            )
        
        data = response.json()
        
        # Update in-memory credentials
        self._access_token = data['access_token']
        self._refresh_token = data['refresh_token']
        self._token_expires_at = datetime.utcnow() + timedelta(seconds=data['expires_in'])
        
        # Persist to platform database
        from platform_db import get_platform_db
        db = get_platform_db()
        db.update_mycase_tokens(
            firm_id=self.firm_id,
            access_token=data['access_token'],
            refresh_token=data['refresh_token'],
            expires_in=data['expires_in']
        )
        
        print(f"Token refreshed for firm {self.firm_id}")

    def _get_headers(self) -> dict:
        """Get headers with current access token."""
        self._ensure_token_valid()
        
        if self.firm_id:
            token = self._access_token
        else:
            # Legacy mode
            token = self._legacy_auth.get_access_token()
        
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _parse_link_header(self, link_header: str) -> Dict[str, str]:
        """Parse the Link header to extract pagination URLs."""
        links = {}
        if not link_header:
            return links

        for part in link_header.split(","):
            match = re.match(r'<([^>]+)>;\s*rel="([^"]+)"', part.strip())
            if match:
                url, rel = match.groups()
                links[rel] = url
        return links

    def _extract_page_token(self, url: str) -> Optional[str]:
        """Extract page_token from a URL."""
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        tokens = params.get("page_token", [])
        return tokens[0] if tokens else None

    def _request(
        self,
        method: str,
        endpoint: str,
        params: dict = None,
        json_data: dict = None,
        retry_count: int = 3,
        max_throttle_retries: int = 10,
        return_headers: bool = False,
    ) -> dict:
        """Make an authenticated request to the MyCase API."""
        self.rate_limiter.acquire()

        url = f"{self.base_url}{endpoint}"
        throttle_count = 0

        for attempt in range(retry_count):
            try:
                response = self._http_client.request(
                    method=method,
                    url=url,
                    headers=self._get_headers(),
                    params=params,
                    json=json_data,
                )

                if response.status_code == 401:
                    # Token expired, try refresh
                    if self.firm_id:
                        self._refresh_access_token()
                    else:
                        self._legacy_auth.refresh_access_token()
                    continue

                if response.status_code == 429:
                    throttle_count += 1
                    if throttle_count > max_throttle_retries:
                        raise MyCaseAPIError(
                            f"Rate limited too many times ({throttle_count})",
                            status_code=429,
                        )
                    retry_after = int(response.headers.get("Retry-After", 0))
                    backoff = max(retry_after, 2 ** throttle_count)
                    print(f"  Rate limited, waiting {backoff}s (attempt {throttle_count}/{max_throttle_retries})...")
                    time.sleep(backoff)
                    attempt -= 1
                    continue

                response.raise_for_status()
                data = response.json() if response.content else {}

                if return_headers:
                    return data, dict(response.headers)
                return data

            except httpx.HTTPStatusError as e:
                if attempt == retry_count - 1:
                    raise MyCaseAPIError(
                        f"API request failed: {e}",
                        status_code=e.response.status_code,
                        response=e.response.json() if e.response.content else None,
                    )
                time.sleep(2 ** attempt)

            except httpx.RequestError as e:
                if attempt == retry_count - 1:
                    raise MyCaseAPIError(f"Request failed: {e}")
                time.sleep(2 ** attempt)

    def get(self, endpoint: str, params: dict = None, return_headers: bool = False):
        """Make a GET request."""
        return self._request("GET", endpoint, params=params, return_headers=return_headers)

    def post(self, endpoint: str, data: dict = None) -> dict:
        """Make a POST request."""
        return self._request("POST", endpoint, json_data=data)

    def put(self, endpoint: str, data: dict = None) -> dict:
        """Make a PUT request."""
        return self._request("PUT", endpoint, json_data=data)

    def patch(self, endpoint: str, data: dict = None) -> dict:
        """Make a PATCH request."""
        return self._request("PATCH", endpoint, json_data=data)

    def delete(self, endpoint: str) -> dict:
        """Make a DELETE request."""
        return self._request("DELETE", endpoint)

    # ========== Firm Endpoints ==========

    def get_firm(self) -> dict:
        """Get the current firm information."""
        return self.get("/firm")

    def get_firm_users(self) -> List[dict]:
        """Get all staff members in the firm."""
        return self.get("/staff")

    def get_staff(self, active_only: bool = False) -> List[dict]:
        """Get all staff members in the firm."""
        staff = self.get("/staff")
        if active_only and isinstance(staff, list):
            staff = [s for s in staff if s.get("active", False)]
        return staff

    # ========== Cases Endpoints ==========

    def get_cases(
        self,
        page: int = 1,
        per_page: int = 50,
        status: str = None,
        updated_since: datetime = None,
        **kwargs  # Accept extra kwargs for pagination
    ) -> dict:
        """Get all cases with optional filtering."""
        params = {"page": page, "per_page": per_page}
        if status:
            params["status"] = status
        if updated_since:
            params["updated_since"] = updated_since.isoformat()
        # Include any extra params (like page_token)
        params.update({k: v for k, v in kwargs.items() if v is not None})
        return self.get("/cases", params=params)

    def get_case(self, case_id: int) -> dict:
        """Get a specific case by ID."""
        return self.get(f"/cases/{case_id}")

    def get_cases_for_client(self, client_id: int) -> List[dict]:
        """Get all cases for a specific client."""
        return self.get(f"/contacts/{client_id}/cases")

    def get_case_stages(self) -> List[dict]:
        """Get all firm case stages."""
        return self.get("/case_stages")

    # ========== Contacts Endpoints ==========

    def get_contacts(
        self,
        page: int = 1,
        per_page: int = 50,
        contact_type: str = None,
        updated_since: datetime = None,
        **kwargs
    ) -> dict:
        """Get all contacts with optional filtering."""
        params = {"page": page, "per_page": per_page}
        if contact_type:
            params["type"] = contact_type
        if updated_since:
            params["updated_since"] = updated_since.isoformat()
        params.update({k: v for k, v in kwargs.items() if v is not None})
        return self.get("/contacts", params=params)

    def get_contact(self, contact_id: int) -> dict:
        """Get a specific contact by ID."""
        return self.get(f"/contacts/{contact_id}")

    def create_contact(self, contact_data: dict) -> dict:
        """Create a new contact."""
        return self.post("/contacts", data=contact_data)

    def update_contact(self, contact_id: int, contact_data: dict) -> dict:
        """Update an existing contact."""
        return self.patch(f"/contacts/{contact_id}", data=contact_data)

    # ========== Clients Endpoints ==========

    def get_clients(
        self,
        page: int = 1,
        per_page: int = 50,
        archived: bool = None,
        updated_since: datetime = None,
        **kwargs
    ) -> List[dict]:
        """Get all clients with full details including addresses."""
        params = {"page": page, "per_page": per_page}
        if archived is not None:
            params["archived"] = archived
        if updated_since:
            params["updated_since"] = updated_since.isoformat()
        params.update({k: v for k, v in kwargs.items() if v is not None})
        return self.get("/clients", params=params)

    def get_client(self, client_id: int) -> dict:
        """Get a specific client by ID with full details."""
        return self.get(f"/clients/{client_id}")

    # ========== Leads Endpoints ==========

    def get_leads(
        self,
        page: int = 1,
        per_page: int = 50,
        status: str = None,
        archived: bool = None,
        updated_since: datetime = None,
        **kwargs
    ) -> dict:
        """Get all leads with optional filtering."""
        params = {"page": page, "per_page": per_page}
        if status:
            params["status"] = status
        if archived is not None:
            params["archived"] = archived
        if updated_since:
            params["updated_since"] = updated_since.isoformat()
        params.update({k: v for k, v in kwargs.items() if v is not None})
        return self.get("/leads", params=params)

    def get_lead(self, lead_id: int) -> dict:
        """Get a specific lead by ID."""
        return self.get(f"/leads/{lead_id}")

    # ========== Invoices & Billing Endpoints ==========

    def get_invoices(
        self,
        page: int = 1,
        per_page: int = 50,
        status: str = None,
        case_id: int = None,
        contact_id: int = None,
        **kwargs
    ) -> dict:
        """Get all invoices with optional filtering."""
        params = {"page": page, "per_page": per_page}
        if status:
            params["status"] = status
        if case_id:
            params["case_id"] = case_id
        if contact_id:
            params["contact_id"] = contact_id
        params.update({k: v for k, v in kwargs.items() if v is not None})
        return self.get("/invoices", params=params)

    def get_invoice(self, invoice_id: int) -> dict:
        """Get a specific invoice by ID."""
        return self.get(f"/invoices/{invoice_id}")

    def get_payments(
        self,
        page: int = 1,
        per_page: int = 50,
        invoice_id: int = None,
        **kwargs
    ) -> dict:
        """Get all payments with optional filtering."""
        params = {"page": page, "per_page": per_page}
        if invoice_id:
            params["invoice_id"] = invoice_id
        params.update({k: v for k, v in kwargs.items() if v is not None})
        return self.get("/payments", params=params)

    # ========== Events & Calendar Endpoints ==========

    def get_events(
        self,
        page: int = 1,
        per_page: int = 50,
        start_date: datetime = None,
        end_date: datetime = None,
        case_id: int = None,
        **kwargs
    ) -> dict:
        """Get calendar events with optional filtering."""
        params = {"page": page, "per_page": per_page}
        if start_date:
            params["start_date"] = start_date.isoformat()
        if end_date:
            params["end_date"] = end_date.isoformat()
        if case_id:
            params["case_id"] = case_id
        params.update({k: v for k, v in kwargs.items() if v is not None})
        return self.get("/events", params=params)

    def get_event(self, event_id: int) -> dict:
        """Get a specific event by ID."""
        return self.get(f"/events/{event_id}")

    def create_event(self, event_data: dict) -> dict:
        """Create a new calendar event."""
        return self.post("/events", data=event_data)

    # ========== Tasks Endpoints ==========

    def get_tasks(
        self,
        page: int = 1,
        per_page: int = 50,
        status: str = None,
        case_id: int = None,
        assignee_id: int = None,
        **kwargs
    ) -> dict:
        """Get all tasks with optional filtering."""
        params = {"page": page, "per_page": per_page}
        if status:
            params["status"] = status
        if case_id:
            params["case_id"] = case_id
        if assignee_id:
            params["assignee_id"] = assignee_id
        params.update({k: v for k, v in kwargs.items() if v is not None})
        return self.get("/tasks", params=params)

    def get_task(self, task_id: int) -> dict:
        """Get a specific task by ID."""
        return self.get(f"/tasks/{task_id}")

    def create_task(self, task_data: dict) -> dict:
        """Create a new task."""
        return self.post("/tasks", data=task_data)

    def update_task(self, task_id: int, task_data: dict) -> dict:
        """Update an existing task."""
        return self.patch(f"/tasks/{task_id}", data=task_data)

    # ========== Documents Endpoints ==========

    def get_case_documents(self, case_id: int) -> dict:
        """Get all documents for a case."""
        return self.get(f"/cases/{case_id}/documents")

    def get_document(self, document_id: int) -> dict:
        """Get a specific document by ID."""
        return self.get(f"/documents/{document_id}")

    # ========== Time Entries Endpoints ==========

    def get_time_entries(
        self,
        page: int = 1,
        per_page: int = 50,
        case_id: int = None,
        user_id: int = None,
        start_date: datetime = None,
        end_date: datetime = None,
        **kwargs
    ) -> dict:
        """Get time entries with optional filtering."""
        params = {"page": page, "per_page": per_page}
        if case_id:
            params["case_id"] = case_id
        if user_id:
            params["user_id"] = user_id
        if start_date:
            params["start_date"] = start_date.isoformat()
        if end_date:
            params["end_date"] = end_date.isoformat()
        params.update({k: v for k, v in kwargs.items() if v is not None})
        return self.get("/time_entries", params=params)

    # ========== Pagination Helpers ==========

    def get_all_pages(
        self,
        endpoint_method,
        max_pages: int = 1000,
        page_delay: float = 0.5,
        per_page: int = 100,
        **kwargs
    ) -> List[dict]:
        """Fetch all pages of a paginated endpoint using token-based pagination."""
        all_items = []
        page_count = 0
        page_token = None
        consecutive_empty = 0
        max_consecutive_empty = 3

        kwargs["per_page"] = per_page

        while page_count < max_pages:
            page_count += 1

            params = dict(kwargs)
            if page_token:
                params["page_token"] = page_token

            response, headers = self._get_paginated(endpoint_method, params)

            items_this_page = []
            if isinstance(response, dict):
                items = response.get("data", response.get("items", []))
                if isinstance(items, list):
                    items_this_page = items
                    all_items.extend(items)
                else:
                    all_items.append(response)
                    break
            elif isinstance(response, list):
                items_this_page = response
                all_items.extend(response)
            else:
                break

            if len(items_this_page) == 0:
                consecutive_empty += 1
                if consecutive_empty >= max_consecutive_empty:
                    print(f"  Stopping after {consecutive_empty} consecutive empty pages")
                    break
            else:
                consecutive_empty = 0

            link_header = headers.get("link", headers.get("Link", ""))
            links = self._parse_link_header(link_header)

            if "next" not in links:
                break

            next_token = self._extract_page_token(links["next"])
            if not next_token:
                break

            page_token = next_token

            total = headers.get("item-count", headers.get("Item-Count", "?"))
            if page_count % 5 == 0 or page_count <= 3:
                print(f"  Page {page_count}: fetched {len(all_items)} of {total} items...")

            if page_delay > 0:
                time.sleep(page_delay)

        print(f"  Pagination complete: {len(all_items)} items from {page_count} pages")
        return all_items

    def _get_paginated(self, endpoint_method, params: dict) -> Tuple[Any, dict]:
        """Call an endpoint method and return response with headers."""
        method_name = endpoint_method.__name__

        endpoint_map = {
            "get_cases": "/cases",
            "get_contacts": "/contacts",
            "get_clients": "/clients",
            "get_invoices": "/invoices",
            "get_payments": "/payments",
            "get_events": "/events",
            "get_tasks": "/tasks",
            "get_time_entries": "/time_entries",
            "get_firm_users": "/staff",
            "get_staff": "/staff",
            "get_leads": "/leads",
        }

        endpoint = endpoint_map.get(method_name)
        if not endpoint:
            response = endpoint_method(**params)
            return response, {}

        return self.get(endpoint, params=params, return_headers=True)


# =========================================================================
# Multi-Tenant Client Factory
# =========================================================================

# Client instances per firm
_client_instances: Dict[str, MyCaseClient] = {}


def get_client(firm_id: str = None) -> MyCaseClient:
    """
    Get or create an API client for a firm.
    
    Args:
        firm_id: The firm ID. If None, uses current tenant context or legacy mode.
        
    Returns:
        MyCaseClient instance for the firm
    """
    # Get firm_id from parameter or context
    firm_id = firm_id or current_tenant.get()
    
    if firm_id is None:
        # Legacy/single-tenant mode
        return MyCaseClient()
    
    # Check if we have a cached instance
    if firm_id not in _client_instances:
        _client_instances[firm_id] = MyCaseClient(firm_id=firm_id)
    
    return _client_instances[firm_id]


def get_client_for_firm(firm_id: str) -> MyCaseClient:
    """
    Explicit factory function to get client for a specific firm.
    
    Use this when you need to specify the firm explicitly rather than
    relying on tenant context.
    
    Args:
        firm_id: The firm ID
        
    Returns:
        MyCaseClient instance for the firm
    """
    if firm_id not in _client_instances:
        _client_instances[firm_id] = MyCaseClient(firm_id=firm_id)
    
    return _client_instances[firm_id]


def clear_client(firm_id: str) -> None:
    """
    Clear a firm's client instance from cache.
    
    Useful for forcing credential reload after token issues.
    """
    if firm_id in _client_instances:
        del _client_instances[firm_id]


if __name__ == "__main__":
    # Test the client (legacy mode)
    client = get_client()

    print("Testing MyCase API Client...")

    try:
        firm = client.get_firm()
        print(f"Connected to firm: {firm}")
    except MyCaseAPIError as e:
        print(f"API Error: {e}")
    except ValueError as e:
        print(f"Auth Error: {e}")
        print("Run: python auth.py to authenticate")
