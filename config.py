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

# OAuth Credentials (load from environment or use defaults for dev)
CLIENT_ID = os.getenv("MYCASE_CLIENT_ID", "q6TmALUXVPbqZscL")
CLIENT_SECRET = os.getenv("MYCASE_CLIENT_SECRET", "DH2mQVLkyXXU3Zeuu5nvyNDD5bfdQaCE")
REDIRECT_URI = os.getenv("MYCASE_REDIRECT_URI", "https://legal.practical.ai/oauth/callback")

# Token storage
TOKEN_FILE = DATA_DIR / "tokens.json"

# Rate limiting
RATE_LIMIT_PER_SECOND = 25

# Dunning configuration (days after invoice due date)
DUNNING_INTERVALS = [15, 30, 60, 90]

# Database for tracking
DB_FILE = DATA_DIR / "mycase_agent.db"
