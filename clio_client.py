"""
Clio Manage API Client (v4)

A robust HTTP client for the Clio Manage API with:
- OAuth 2.0 authentication with automatic token refresh
- Rate limiting (respects 429 with Retry-After)
- Retry logic with exponential backoff
- Cursor-based pagination
- Field selection (Clio returns only id+etag by default)

API Base: https://app.clio.com/api/v4
Auth: OAuth 2.0 (7-day access tokens, non-expiring refresh tokens)
Docs: https://docs.developers.clio.com/clio-manage/api-reference/
"""
import time
import json
import logging
from typing import Any, Optional, Dict, List, Generator
from datetime import datetime, timedelta

import httpx

from db.connection import get_connection

logger = logging.getLogger(__name__)

# Clio API base URL
CLIO_API_BASE = "https://app.clio.com/api/v4"
CLIO_AUTH_URL = "https://app.clio.com/oauth/authorize"
CLIO_TOKEN_URL = "https://app.clio.com/oauth/token"

# Rate limiting: Clio uses 429 with Retry-After header
# No fixed rate published, but be conservative
DEFAULT_RATE_LIMIT = 10  # requests per second


class ClioAPIError(Exception):
    """Custom exception for Clio API errors."""

    def __init__(self, message: str, status_code: int = None, response: dict = None):
        super().__init__(message)
        self.status_code = status_code
        self.response = response


class ClioAuth:
    """
    Clio OAuth 2.0 token management.

    Tokens stored in firms table: clio_oauth_token, clio_oauth_refresh,
    clio_token_expires_at, clio_connected.
    """

    def __init__(self, firm_id: str):
        self.firm_id = firm_id
        self._credentials = None
        self._load_credentials()

    def _load_credentials(self):
        """Load Clio OAuth credentials from firms table."""
        with get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT clio_client_id, clio_client_secret,
                       clio_oauth_token, clio_oauth_refresh,
                       clio_token_expires_at, clio_connected
                FROM firms WHERE id = %s
            """, (self.firm_id,))
            row = cur.fetchone()
            if not row:
                raise ClioAPIError(f"Firm '{self.firm_id}' not found")
            self._credentials = row

    @property
    def client_id(self) -> str:
        return self._credentials.get('clio_client_id', '')

    @property
    def client_secret(self) -> str:
        return self._credentials.get('clio_client_secret', '')

    @property
    def access_token(self) -> str:
        return self._credentials.get('clio_oauth_token', '')

    @property
    def refresh_token(self) -> str:
        return self._credentials.get('clio_oauth_refresh', '')

    @property
    def is_connected(self) -> bool:
        return bool(self._credentials.get('clio_connected'))

    def is_token_expired(self) -> bool:
        """Check if access token is expired or will expire within 1 hour."""
        expires_at = self._credentials.get('clio_token_expires_at')
        if not expires_at:
            return True
        if isinstance(expires_at, str):
            expires_at = datetime.fromisoformat(expires_at)
        return datetime.utcnow() >= (expires_at - timedelta(hours=1))

    def get_authorization_url(self, redirect_uri: str) -> str:
        """Get the OAuth authorization URL for user consent."""
        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
        }
        qs = "&".join(f"{k}={v}" for k, v in params.items())
        return f"{CLIO_AUTH_URL}?{qs}"

    def exchange_code(self, code: str, redirect_uri: str) -> dict:
        """Exchange authorization code for access + refresh tokens."""
        response = httpx.post(CLIO_TOKEN_URL, data={
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
        }, timeout=30)

        if response.status_code != 200:
            raise ClioAPIError(
                f"Token exchange failed: {response.status_code} {response.text}",
                status_code=response.status_code,
            )

        token_data = response.json()
        self._save_tokens(token_data)
        return token_data

    def refresh_access_token(self) -> str:
        """Refresh the access token using the refresh token."""
        if not self.refresh_token:
            raise ClioAPIError("No refresh token available — re-authorization required")

        response = httpx.post(CLIO_TOKEN_URL, data={
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token,
        }, timeout=30)

        if response.status_code != 200:
            raise ClioAPIError(
                f"Token refresh failed: {response.status_code} {response.text}",
                status_code=response.status_code,
            )

        token_data = response.json()
        self._save_tokens(token_data)
        logger.info("Refreshed Clio access token for firm %s", self.firm_id)
        return token_data["access_token"]

    def get_access_token(self) -> str:
        """Get a valid access token, refreshing if needed."""
        if self.is_token_expired():
            return self.refresh_access_token()
        return self.access_token

    def _save_tokens(self, token_data: dict):
        """Save tokens to firms table."""
        access_token = token_data["access_token"]
        refresh_token = token_data.get("refresh_token", self.refresh_token)
        expires_in = token_data.get("expires_in", 604800)  # 7 days default
        expires_at = datetime.utcnow() + timedelta(seconds=expires_in)

        with get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                UPDATE firms SET
                    clio_oauth_token = %s,
                    clio_oauth_refresh = %s,
                    clio_token_expires_at = %s,
                    clio_connected = TRUE,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
            """, (access_token, refresh_token, expires_at, self.firm_id))
            conn.commit()

        # Reload credentials
        self._load_credentials()


class ClioClient:
    """
    Clio Manage API Client with OAuth authentication, rate limiting, and pagination.

    Usage:
        client = ClioClient("firm_id")
        matters = client.get_all_matters()
        contacts = client.get_all_contacts()
    """

    def __init__(self, firm_id: str):
        self.firm_id = firm_id
        self.auth = ClioAuth(firm_id)
        self._client = httpx.Client(timeout=30.0)
        self._last_request_time = 0.0

    def _rate_limit(self):
        """Simple rate limiter — minimum 100ms between requests."""
        now = time.time()
        elapsed = now - self._last_request_time
        if elapsed < 0.1:
            time.sleep(0.1 - elapsed)
        self._last_request_time = time.time()

    def _get_headers(self) -> dict:
        """Get headers with current access token."""
        token = self.auth.get_access_token()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _request(
        self,
        method: str,
        endpoint: str,
        params: dict = None,
        json_data: dict = None,
        retry_count: int = 3,
    ) -> dict:
        """
        Make an authenticated request to the Clio API.

        Returns parsed JSON response.
        """
        self._rate_limit()

        url = f"{CLIO_API_BASE}{endpoint}"

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
                    # Token expired, refresh and retry
                    self.auth.refresh_access_token()
                    continue

                if response.status_code == 429:
                    # Rate limited — use Retry-After header
                    retry_after = int(response.headers.get("Retry-After", 5))
                    logger.warning("Clio rate limited, waiting %ds", retry_after)
                    time.sleep(retry_after)
                    continue

                response.raise_for_status()
                return response.json() if response.content else {}

            except httpx.HTTPStatusError as e:
                if attempt == retry_count - 1:
                    raise ClioAPIError(
                        f"Clio API request failed: {e}",
                        status_code=e.response.status_code,
                        response=e.response.json() if e.response.content else None,
                    )
                time.sleep(2 ** attempt)

            except httpx.RequestError as e:
                if attempt == retry_count - 1:
                    raise ClioAPIError(f"Clio request failed: {e}")
                time.sleep(2 ** attempt)

    def get(self, endpoint: str, params: dict = None) -> dict:
        """Make a GET request."""
        return self._request("GET", endpoint, params=params)

    def post(self, endpoint: str, data: dict = None) -> dict:
        """Make a POST request."""
        return self._request("POST", endpoint, json_data=data)

    def patch(self, endpoint: str, data: dict = None) -> dict:
        """Make a PATCH request."""
        return self._request("PATCH", endpoint, json_data=data)

    def delete(self, endpoint: str) -> dict:
        """Make a DELETE request."""
        return self._request("DELETE", endpoint)

    # ========== Pagination Helper ==========

    def get_all(
        self,
        endpoint: str,
        fields: str = None,
        params: dict = None,
        limit: int = 200,
        updated_since: datetime = None,
    ) -> List[dict]:
        """
        Fetch all records from a paginated endpoint using cursor-based pagination.

        Clio uses cursor pagination: response includes meta.paging.next URL.
        Default page size is 200 (max).

        Args:
            endpoint: API endpoint path
            fields: Comma-separated field list (Clio returns only id+etag by default)
            params: Additional query parameters
            limit: Records per page (max 200)
            updated_since: Only records updated after this time

        Returns:
            List of all records across all pages
        """
        all_records = []
        request_params = params.copy() if params else {}
        request_params["limit"] = limit

        if fields:
            request_params["fields"] = fields
        if updated_since:
            request_params["updated_since"] = updated_since.isoformat()

        while True:
            data = self.get(endpoint, params=request_params)

            records = data.get("data", [])
            all_records.extend(records)

            # Check for next page via cursor
            meta = data.get("meta", {})
            paging = meta.get("paging", {})

            if not paging.get("next"):
                break

            # Clio's next URL is a full URL; extract cursor param
            next_url = paging["next"]
            # Parse cursor from next URL
            from urllib.parse import urlparse, parse_qs
            parsed = urlparse(next_url)
            qs = parse_qs(parsed.query)
            if "cursor" in qs:
                request_params["cursor"] = qs["cursor"][0]
            else:
                break

            logger.debug("Fetched %d records, continuing pagination...", len(all_records))

        return all_records

    # ========== Matters (Cases) ==========

    # Standard fields to request for matters
    MATTER_FIELDS = (
        "id,etag,display_number,custom_number,description,status,open_date,"
        "close_date,pending_date,created_at,updated_at,"
        "client{id,name,type},"
        "practice_area{id,name},"
        "responsible_attorney{id,name,enabled},"
        "originating_attorney{id,name},"
        "statute_of_limitations{due_at},"
        "custom_rate{rate,type},"
        "group{id,name},"
        "matter_stage{id,name}"
    )

    def get_all_matters(self, updated_since: datetime = None) -> List[dict]:
        """Get all matters with full field set."""
        return self.get_all(
            "/matters",
            fields=self.MATTER_FIELDS,
            updated_since=updated_since,
        )

    def get_matter(self, matter_id: int) -> dict:
        """Get a single matter by ID."""
        data = self.get(f"/matters/{matter_id}", params={"fields": self.MATTER_FIELDS})
        return data.get("data", {})

    # ========== Contacts ==========

    CONTACT_FIELDS = (
        "id,etag,name,first_name,last_name,middle_name,type,title,company,"
        "is_client,created_at,updated_at,"
        "primary_email_address,primary_phone_number,"
        "email_addresses{id,address,name},"
        "phone_numbers{id,number,name},"
        "addresses{id,street,city,province,postal_code,country,name},"
        "custom_field_values{id,field_name,value}"
    )

    def get_all_contacts(self, updated_since: datetime = None) -> List[dict]:
        """Get all contacts with emails, phones, and addresses."""
        return self.get_all(
            "/contacts",
            fields=self.CONTACT_FIELDS,
            updated_since=updated_since,
        )

    def get_contact(self, contact_id: int) -> dict:
        """Get a single contact by ID."""
        data = self.get(f"/contacts/{contact_id}", params={"fields": self.CONTACT_FIELDS})
        return data.get("data", {})

    # ========== Tasks ==========

    TASK_FIELDS = (
        "id,etag,name,description,priority,status,due_at,completed_at,"
        "created_at,updated_at,is_private,is_statute_of_limitations,"
        "assignee{id,name},"
        "matter{id,display_number},"
        "task_type{id,name}"
    )

    def get_all_tasks(self, updated_since: datetime = None, status: str = None) -> List[dict]:
        """Get all tasks. Status: 'pending', 'complete', or None for all."""
        params = {}
        if status:
            params["status"] = status
        return self.get_all(
            "/tasks",
            fields=self.TASK_FIELDS,
            params=params,
            updated_since=updated_since,
        )

    # ========== Bills (Invoices) ==========

    BILL_FIELDS = (
        "id,etag,number,subject,purchase_order,type,status,issued_at,"
        "created_at,updated_at,due_at,tax_rate,secondary_tax_rate,"
        "total,paid,pending,due,discount,"
        "start_at,end_at,"
        "matter{id,display_number},"
        "client{id,name},"
        "responsible_attorney{id,name},"
        "originating_attorney{id,name}"
    )

    def get_all_bills(self, updated_since: datetime = None, status: str = None) -> List[dict]:
        """Get all bills/invoices. Status: 'draft', 'awaiting_approval', 'awaiting_payment', 'paid', 'void'."""
        params = {}
        if status:
            params["status"] = status
        return self.get_all(
            "/bills",
            fields=self.BILL_FIELDS,
            params=params,
            updated_since=updated_since,
        )

    # ========== Activities (Time Entries) ==========

    ACTIVITY_FIELDS = (
        "id,etag,type,date,quantity,price,total,note,flat_rate,"
        "billed,on_bill,created_at,updated_at,"
        "matter{id,display_number},"
        "user{id,name},"
        "activity_description{id,name},"
        "expense_category{id,name}"
    )

    def get_all_activities(self, updated_since: datetime = None) -> List[dict]:
        """Get all activities (time entries + expenses)."""
        return self.get_all(
            "/activities",
            fields=self.ACTIVITY_FIELDS,
            updated_since=updated_since,
        )

    # ========== Users (Staff) ==========

    USER_FIELDS = (
        "id,etag,name,first_name,last_name,email,enabled,type,"
        "phone_number,rate,subscription_type,created_at,updated_at"
    )

    def get_all_users(self) -> List[dict]:
        """Get all users/staff in the firm."""
        return self.get_all("/users", fields=self.USER_FIELDS)

    # ========== Calendar Entries (Events) ==========

    CALENDAR_FIELDS = (
        "id,etag,summary,description,location,start_at,end_at,"
        "all_day,recurrence_rule,created_at,updated_at,"
        "matter{id,display_number},"
        "attendees{id,name,type},"
        "calendar_owner{id,name}"
    )

    def get_all_calendar_entries(self, updated_since: datetime = None) -> List[dict]:
        """Get all calendar entries/events."""
        return self.get_all(
            "/calendar_entries",
            fields=self.CALENDAR_FIELDS,
            updated_since=updated_since,
        )

    # ========== Payments ==========

    PAYMENT_FIELDS = (
        "id,etag,date,amount,apply_interest,created_at,updated_at,"
        "contact{id,name},"
        "allocation{id,amount,bill{id,number},matter{id,display_number}}"
    )

    def get_all_payments(self, updated_since: datetime = None) -> List[dict]:
        """Get all payments."""
        return self.get_all(
            "/payments",
            fields=self.PAYMENT_FIELDS,
            updated_since=updated_since,
        )

    # ========== Trust Requests (Trust/IOLTA) ==========

    TRUST_FIELDS = (
        "id,etag,date,description,total,type,created_at,updated_at,"
        "matter{id,display_number},"
        "contact{id,name},"
        "bank_account{id,name}"
    )

    def get_all_trust_line_items(self, updated_since: datetime = None) -> List[dict]:
        """Get all trust line items."""
        return self.get_all(
            "/trust_line_items",
            fields=self.TRUST_FIELDS,
            updated_since=updated_since,
        )

    # ========== Practice Areas ==========

    def get_practice_areas(self) -> List[dict]:
        """Get all practice areas."""
        return self.get_all("/practice_areas", fields="id,etag,name,code,created_at,updated_at")

    # ========== Matter Stages ==========

    def get_matter_stages(self) -> List[dict]:
        """Get all matter stages (for phase mapping)."""
        return self.get_all("/matter_stages", fields="id,etag,name,order")

    # ========== Utility ==========

    def test_connection(self) -> Dict[str, Any]:
        """Test the API connection and return basic info."""
        try:
            data = self.get("/users/who_am_i", params={"fields": "id,name,email,enabled"})
            user = data.get("data", {})
            return {
                "connected": True,
                "user_id": user.get("id"),
                "user_name": user.get("name"),
                "user_email": user.get("email"),
            }
        except Exception as e:
            return {"connected": False, "error": str(e)}

    def close(self):
        """Close the HTTP client."""
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
