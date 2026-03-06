"""
MyCase API Configuration
"""
import os
from pathlib import Path

# Load environment variables from .env file
try:
    from dotenv import dotenv_values
    _env_path = Path(__file__).parent / ".env"
    if _env_path.exists():
        _env_values = dotenv_values(_env_path)
        for key, value in _env_values.items():
            if value and not os.environ.get(key):  # Set if value exists and env not already set
                os.environ[key] = value
except ImportError:
    pass  # python-dotenv not installed, rely on system env vars

# Base paths
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
TEMPLATES_DIR = BASE_DIR / "templates"
LOGS_DIR = BASE_DIR / "logs"

# Ensure directories exist
DATA_DIR.mkdir(exist_ok=True)
TEMPLATES_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)

# MyCase OAuth Configuration
MYCASE_AUTH_URL = "https://auth.mycase.com"
MYCASE_API_URL = "https://external-integrations.mycase.com/v1"

# OAuth Credentials
# DEPRECATED: These module-level constants are for backward compatibility only.
# New code should use FirmSettings(firm_id).get_mycase_credentials() instead.
# These still work for single-firm deployments and CLI tools.
CLIENT_ID = os.getenv("MYCASE_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("MYCASE_CLIENT_SECRET", "")
REDIRECT_URI = os.getenv("MYCASE_REDIRECT_URI", "https://legal.practical.ai/oauth/callback")

# Token storage (legacy — single-firm only; multi-firm uses DB)
TOKEN_FILE = DATA_DIR / "tokens.json"


def get_mycase_credentials(firm_id: str = None) -> dict:
    """Get MyCase OAuth credentials, preferring database over env vars.

    Returns dict with: client_id, client_secret, oauth_token, oauth_refresh,
                       token_expires_at, mycase_firm_id, connected
    """
    if firm_id:
        try:
            from firm_settings import get_firm_settings
            fs = get_firm_settings(firm_id)
            creds = fs.get_mycase_credentials()
            if creds.get("client_id"):
                return creds
        except (ValueError, Exception):
            pass

    # Fallback to env vars
    return {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "oauth_token": "",
        "oauth_refresh": "",
        "token_expires_at": None,
        "mycase_firm_id": None,
        "connected": bool(CLIENT_ID),
    }

# Rate limiting
RATE_LIMIT_PER_SECOND = 25

# Dunning configuration (days after invoice due date)
DUNNING_INTERVALS = [15, 30, 60, 90]

# Database for tracking
DB_FILE = DATA_DIR / "mycase_agent.db"
