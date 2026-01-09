"""
MyCase OAuth 2.0 Authentication Module

Handles the OAuth 2.0 Authorization Code flow:
1. Generate authorization URL for user consent
2. Exchange authorization code for tokens
3. Refresh expired access tokens
4. Store and retrieve tokens securely
"""
import json
import time
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlencode, urlparse, parse_qs
from datetime import datetime, timedelta
from typing import Optional
import httpx

from config import (
    MYCASE_AUTH_URL,
    CLIENT_ID,
    CLIENT_SECRET,
    REDIRECT_URI,
    TOKEN_FILE,
)


class TokenStorage:
    """Handles secure storage and retrieval of OAuth tokens."""

    def __init__(self, token_file=TOKEN_FILE):
        self.token_file = token_file

    def save(self, tokens: dict) -> None:
        """Save tokens to file with expiration timestamp."""
        tokens["saved_at"] = datetime.now().isoformat()
        if "expires_in" in tokens:
            expires_at = datetime.now() + timedelta(seconds=tokens["expires_in"])
            tokens["expires_at"] = expires_at.isoformat()

        self.token_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.token_file, "w") as f:
            json.dump(tokens, f, indent=2)

    def load(self) -> Optional[dict]:
        """Load tokens from file if they exist."""
        if not self.token_file.exists():
            return None

        with open(self.token_file, "r") as f:
            return json.load(f)

    def clear(self) -> None:
        """Remove stored tokens."""
        if self.token_file.exists():
            self.token_file.unlink()

    def is_access_token_expired(self) -> bool:
        """Check if the access token is expired."""
        tokens = self.load()
        if not tokens or "expires_at" not in tokens:
            return True

        expires_at = datetime.fromisoformat(tokens["expires_at"])
        # Consider expired if within 5 minutes of expiration
        return datetime.now() >= (expires_at - timedelta(minutes=5))

    def is_refresh_token_valid(self) -> bool:
        """Check if refresh token is still valid (2 week validity)."""
        tokens = self.load()
        if not tokens or "saved_at" not in tokens:
            return False

        saved_at = datetime.fromisoformat(tokens["saved_at"])
        # Refresh tokens valid for 2 weeks
        return datetime.now() < (saved_at + timedelta(weeks=2))


class OAuthCallbackHandler(BaseHTTPRequestHandler):
    """HTTP handler to capture OAuth callback with authorization code."""

    authorization_code = None

    def do_GET(self):
        """Handle the OAuth callback GET request."""
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        if "code" in params:
            OAuthCallbackHandler.authorization_code = params["code"][0]
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(b"""
                <html>
                <head><title>Authorization Successful</title></head>
                <body style="font-family: Arial; text-align: center; padding: 50px;">
                    <h1>Authorization Successful!</h1>
                    <p>You can close this window and return to the application.</p>
                </body>
                </html>
            """)
        elif "error" in params:
            error = params.get("error", ["Unknown error"])[0]
            self.send_response(400)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(f"""
                <html>
                <head><title>Authorization Failed</title></head>
                <body style="font-family: Arial; text-align: center; padding: 50px;">
                    <h1>Authorization Failed</h1>
                    <p>Error: {error}</p>
                </body>
                </html>
            """.encode())
        else:
            self.send_response(400)
            self.end_headers()

    def log_message(self, format, *args):
        """Suppress HTTP server logs."""
        pass


class MyCaseAuth:
    """Handles MyCase OAuth 2.0 authentication flow."""

    def __init__(
        self,
        client_id: str = CLIENT_ID,
        client_secret: str = CLIENT_SECRET,
        redirect_uri: str = REDIRECT_URI,
    ):
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.storage = TokenStorage()
        self._http_client = httpx.Client(timeout=30.0)

    def get_authorization_url(self, scopes: list = None) -> str:
        """Generate the URL to redirect users for authorization.

        Args:
            scopes: List of scopes to request. If None, requests all available scopes.
        """
        # Default scopes - request all read permissions including time_entries
        if scopes is None:
            scopes = [
                "read_cases",
                "read_contacts",
                "read_invoices",
                "read_events",
                "read_tasks",
                "read_staff",
                "read_time_entries",  # This was missing!
                "read_expenses",
                "read_payments",
                "read_documents",
                "read_notes",
                "read_messages",
                "read_leads",
                "read_custom_fields",
                "read_call_log",
                "read_webhooks",
            ]

        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": " ".join(scopes),
        }
        return f"{MYCASE_AUTH_URL}/login_sessions/new?{urlencode(params)}"

    def authorize_interactive(self) -> dict:
        """
        Run interactive OAuth flow:
        1. Open browser for user to authorize
        2. Prompt user to paste the callback URL or code
        3. Exchange code for tokens
        """
        # Open browser for authorization
        auth_url = self.get_authorization_url()
        print(f"\nOpening browser for authorization...")
        print(f"If browser doesn't open, visit:\n{auth_url}\n")
        webbrowser.open(auth_url)

        # Since callback goes to external server, user needs to provide the code
        print("After authorizing, you'll be redirected to:")
        print(f"  {self.redirect_uri}?code=AUTHORIZATION_CODE")
        print("\nPaste the full callback URL or just the authorization code:")

        user_input = input("> ").strip()

        # Extract code from URL or use as-is
        if "code=" in user_input:
            parsed = urlparse(user_input)
            params = parse_qs(parsed.query)
            code = params.get("code", [None])[0]
            if not code:
                raise ValueError("Could not extract authorization code from URL")
        else:
            code = user_input

        print("Authorization code received!")

        # Exchange code for tokens
        return self.exchange_code(code)

    def exchange_code(self, code: str) -> dict:
        """Exchange authorization code for access and refresh tokens."""
        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": self.redirect_uri,
        }

        response = self._http_client.post(
            f"{MYCASE_AUTH_URL}/tokens",
            data=data,
        )
        response.raise_for_status()

        tokens = response.json()
        self.storage.save(tokens)
        print("Tokens saved successfully!")
        return tokens

    def refresh_access_token(self) -> dict:
        """Use refresh token to get a new access token."""
        tokens = self.storage.load()
        if not tokens or "refresh_token" not in tokens:
            raise ValueError("No refresh token available. Please re-authorize.")

        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": tokens["refresh_token"],
            "grant_type": "refresh_token",
        }

        response = self._http_client.post(
            f"{MYCASE_AUTH_URL}/tokens",
            data=data,
        )
        response.raise_for_status()

        new_tokens = response.json()
        self.storage.save(new_tokens)
        print("Access token refreshed successfully!")
        return new_tokens

    def get_access_token(self) -> str:
        """
        Get a valid access token, refreshing if necessary.
        Raises an error if no valid tokens are available.
        """
        if self.storage.is_access_token_expired():
            if self.storage.is_refresh_token_valid():
                self.refresh_access_token()
            else:
                raise ValueError(
                    "Tokens expired. Please re-authorize with: mycase-agent auth"
                )

        tokens = self.storage.load()
        if not tokens or "access_token" not in tokens:
            raise ValueError(
                "No tokens available. Please authorize with: mycase-agent auth"
            )

        return tokens["access_token"]

    def is_authenticated(self) -> bool:
        """Check if we have valid authentication."""
        try:
            self.get_access_token()
            return True
        except ValueError:
            return False

    def get_firm_uuid(self) -> Optional[str]:
        """Get the firm UUID from stored tokens."""
        tokens = self.storage.load()
        return tokens.get("firm_uuid") if tokens else None


# Convenience function for quick access token retrieval
def get_access_token() -> str:
    """Get a valid access token."""
    auth = MyCaseAuth()
    return auth.get_access_token()


if __name__ == "__main__":
    # Test the auth flow
    auth = MyCaseAuth()

    if auth.is_authenticated():
        print("Already authenticated!")
        print(f"Firm UUID: {auth.get_firm_uuid()}")
    else:
        print("Starting authorization flow...")
        tokens = auth.authorize_interactive()
        print(f"\nFirm UUID: {tokens.get('firm_uuid')}")
        print(f"Scopes: {tokens.get('scope')}")
