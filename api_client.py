"""
MyCase API Client

A robust HTTP client for the MyCase API with:
- Automatic token refresh
- Rate limiting (25 req/sec)
- Retry logic with exponential backoff
- Comprehensive endpoint coverage
"""
import time
import re
from typing import Any, Optional, Dict, List, Tuple
from datetime import datetime
from urllib.parse import urlparse, parse_qs
import httpx
from functools import wraps

from config import MYCASE_API_URL, RATE_LIMIT_PER_SECOND
from auth import MyCaseAuth


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
    MyCase API Client with automatic authentication and rate limiting.

    Usage:
        client = MyCaseClient()
        cases = client.get_cases()
        contacts = client.get_contacts()
    """

    def __init__(self, base_url: str = MYCASE_API_URL):
        self.base_url = base_url
        self.auth = MyCaseAuth()
        self.rate_limiter = RateLimiter()
        self._client = httpx.Client(timeout=30.0)

    def _get_headers(self) -> dict:
        """Get headers with current access token."""
        token = self.auth.get_access_token()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _parse_link_header(self, link_header: str) -> Dict[str, str]:
        """
        Parse the Link header to extract pagination URLs.

        Args:
            link_header: The Link header value

        Returns:
            Dict mapping rel type to URL (e.g., {"next": "https://...", "prev": "https://..."})
        """
        links = {}
        if not link_header:
            return links

        # Parse format: <url>; rel="next", <url>; rel="prev"
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
        """
        Make an authenticated request to the MyCase API.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE, PATCH)
            endpoint: API endpoint (e.g., "/cases")
            params: Query parameters
            json_data: JSON body for POST/PUT/PATCH
            retry_count: Number of retries for failed requests (not counting 429s)
            max_throttle_retries: Maximum retries for 429 rate limit responses
            return_headers: If True, return (data, headers) tuple

        Returns:
            JSON response from the API, or (data, headers) if return_headers=True
        """
        self.rate_limiter.acquire()

        url = f"{self.base_url}{endpoint}"
        throttle_count = 0

        for attempt in range(retry_count):
            try:
                response = self._client.request(
                    method=method,
                    url=url,
                    headers=self._get_headers(),
                    params=params,
                    json=json_data,
                )

                if response.status_code == 401:
                    # Token expired, try refresh
                    self.auth.refresh_access_token()
                    continue

                if response.status_code == 429:
                    # Rate limited - handle separately from error retries
                    throttle_count += 1
                    if throttle_count > max_throttle_retries:
                        raise MyCaseAPIError(
                            f"Rate limited too many times ({throttle_count})",
                            status_code=429,
                        )
                    # Use Retry-After header with exponential backoff as fallback
                    retry_after = int(response.headers.get("Retry-After", 0))
                    backoff = max(retry_after, 2 ** throttle_count)
                    print(f"  Rate limited, waiting {backoff}s (attempt {throttle_count}/{max_throttle_retries})...")
                    time.sleep(backoff)
                    # Don't count 429 against regular retry attempts
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
                time.sleep(2 ** attempt)  # Exponential backoff

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
        """Get all staff members in the firm (lawyers, paralegals, etc.)."""
        return self.get("/staff")

    def get_staff(self, active_only: bool = False) -> List[dict]:
        """
        Get all staff members in the firm.

        Args:
            active_only: If True, only return active staff members

        Returns:
            List of staff member dicts with id, name, email, title, type, etc.
        """
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
    ) -> dict:
        """
        Get all cases with optional filtering.

        Args:
            page: Page number for pagination
            per_page: Results per page (max 100)
            status: Filter by status (open, closed)
            updated_since: Only cases updated after this date
        """
        params = {"page": page, "per_page": per_page}
        if status:
            params["status"] = status
        if updated_since:
            params["updated_since"] = updated_since.isoformat()
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
    ) -> dict:
        """
        Get all contacts with optional filtering.

        Args:
            page: Page number for pagination
            per_page: Results per page
            contact_type: Filter by type (client, lead, etc.)
            updated_since: Only contacts updated after this date
        """
        params = {"page": page, "per_page": per_page}
        if contact_type:
            params["type"] = contact_type
        if updated_since:
            params["updated_since"] = updated_since.isoformat()
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
    ) -> List[dict]:
        """
        Get all clients with full details including addresses.

        This endpoint returns more data than /contacts, including:
        - Full address (address1, address2, city, state, zip_code, country)
        - Phone numbers (cell, work, home)
        - Email
        - Birthdate
        - Cases associated with client

        Args:
            page: Page number for pagination
            per_page: Results per page
            archived: Filter by archived status
            updated_since: Only clients updated after this date

        Returns:
            List of client dictionaries with full details
        """
        params = {"page": page, "per_page": per_page}
        if archived is not None:
            params["archived"] = archived
        if updated_since:
            params["updated_since"] = updated_since.isoformat()
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
    ) -> dict:
        """
        Get all leads with optional filtering.

        Args:
            page: Page number for pagination
            per_page: Results per page
            status: Filter by status (New Intake, Contacted, etc.)
            archived: Filter by archived status
            updated_since: Only leads updated after this date
        """
        params = {"page": page, "per_page": per_page}
        if status:
            params["status"] = status
        if archived is not None:
            params["archived"] = archived
        if updated_since:
            params["updated_since"] = updated_since.isoformat()
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
    ) -> dict:
        """
        Get all invoices with optional filtering.

        Args:
            page: Page number
            per_page: Results per page
            status: Filter by status (draft, sent, paid, partial, overdue)
            case_id: Filter by case
            contact_id: Filter by contact
        """
        params = {"page": page, "per_page": per_page}
        if status:
            params["status"] = status
        if case_id:
            params["case_id"] = case_id
        if contact_id:
            params["contact_id"] = contact_id
        return self.get("/invoices", params=params)

    def get_invoice(self, invoice_id: int) -> dict:
        """Get a specific invoice by ID."""
        return self.get(f"/invoices/{invoice_id}")

    def get_payments(
        self,
        page: int = 1,
        per_page: int = 50,
        invoice_id: int = None,
    ) -> dict:
        """Get all payments with optional filtering."""
        params = {"page": page, "per_page": per_page}
        if invoice_id:
            params["invoice_id"] = invoice_id
        return self.get("/payments", params=params)

    # ========== Events & Calendar Endpoints ==========

    def get_events(
        self,
        page: int = 1,
        per_page: int = 50,
        start_date: datetime = None,
        end_date: datetime = None,
        case_id: int = None,
    ) -> dict:
        """
        Get calendar events with optional filtering.

        Args:
            page: Page number
            per_page: Results per page
            start_date: Events starting after this date
            end_date: Events ending before this date
            case_id: Filter by case
        """
        params = {"page": page, "per_page": per_page}
        if start_date:
            params["start_date"] = start_date.isoformat()
        if end_date:
            params["end_date"] = end_date.isoformat()
        if case_id:
            params["case_id"] = case_id
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
    ) -> dict:
        """
        Get all tasks with optional filtering.

        Args:
            page: Page number
            per_page: Results per page
            status: Filter by status (pending, completed)
            case_id: Filter by case
            assignee_id: Filter by assigned user
        """
        params = {"page": page, "per_page": per_page}
        if status:
            params["status"] = status
        if case_id:
            params["case_id"] = case_id
        if assignee_id:
            params["assignee_id"] = assignee_id
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
    ) -> dict:
        """
        Get time entries with optional filtering.

        Args:
            page: Page number
            per_page: Results per page
            case_id: Filter by case
            user_id: Filter by user
            start_date: Entries after this date
            end_date: Entries before this date
        """
        params = {"page": page, "per_page": per_page}
        if case_id:
            params["case_id"] = case_id
        if user_id:
            params["user_id"] = user_id
        if start_date:
            params["start_date"] = start_date.isoformat()
        if end_date:
            params["end_date"] = end_date.isoformat()
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
        """
        Fetch all pages of a paginated endpoint using token-based pagination.

        The MyCase API uses Link headers with page_token for pagination.
        Example: <url?page_token=xxx>; rel="next"

        Args:
            endpoint_method: Method to call (e.g., self.get_cases)
            max_pages: Maximum pages to fetch (safety limit)
            page_delay: Seconds to wait between page requests (reduces throttling)
            per_page: Number of items per page (max 100 for most endpoints)
            **kwargs: Additional arguments to pass to the method

        Returns:
            List of all items from all pages
        """
        all_items = []
        page_count = 0
        page_token = None
        consecutive_empty = 0
        max_consecutive_empty = 3  # Stop after 3 empty pages in a row

        # Always request maximum items per page to reduce total requests
        kwargs["per_page"] = per_page

        while page_count < max_pages:
            page_count += 1

            # Build params with page_token if we have one
            params = dict(kwargs)
            if page_token:
                params["page_token"] = page_token

            # Get response with headers
            response, headers = self._get_paginated(endpoint_method, params)

            # Extract items from response
            items_this_page = []
            if isinstance(response, dict):
                items = response.get("data", response.get("items", []))
                if isinstance(items, list):
                    items_this_page = items
                    all_items.extend(items)
                else:
                    # Single item response
                    all_items.append(response)
                    break
            elif isinstance(response, list):
                items_this_page = response
                all_items.extend(response)
            else:
                break

            # Track consecutive empty pages
            if len(items_this_page) == 0:
                consecutive_empty += 1
                if consecutive_empty >= max_consecutive_empty:
                    print(f"  Stopping after {consecutive_empty} consecutive empty pages")
                    break
            else:
                consecutive_empty = 0

            # Check for next page in Link header
            link_header = headers.get("link", headers.get("Link", ""))
            links = self._parse_link_header(link_header)

            if "next" not in links:
                # No more pages
                break

            # Extract page_token from next URL
            next_token = self._extract_page_token(links["next"])
            if not next_token:
                break

            page_token = next_token

            # Progress indicator for large fetches
            total = headers.get("item-count", headers.get("Item-Count", "?"))
            if page_count % 5 == 0 or page_count <= 3:
                print(f"  Page {page_count}: fetched {len(all_items)} of {total} items...")

            # Delay between pages to avoid throttling
            if page_delay > 0:
                time.sleep(page_delay)

        # Final summary
        print(f"  Pagination complete: {len(all_items)} items from {page_count} pages")
        return all_items

    def _get_paginated(self, endpoint_method, params: dict) -> Tuple[Any, dict]:
        """
        Call an endpoint method and return response with headers.

        This is a helper for get_all_pages that handles the different
        endpoint method signatures.
        """
        # Get the endpoint path from the method
        method_name = endpoint_method.__name__

        # Map methods to endpoints
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
            # Fallback: call method directly without headers
            response = endpoint_method(**params)
            return response, {}

        # Make request with headers
        return self.get(endpoint, params=params, return_headers=True)


# Singleton client instance
_client_instance = None


def get_client() -> MyCaseClient:
    """Get or create a singleton API client instance."""
    global _client_instance
    if _client_instance is None:
        _client_instance = MyCaseClient()
    return _client_instance


if __name__ == "__main__":
    # Test the client
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
