"""
Dashboard Configuration
"""
import os
from pathlib import Path

# Base paths
BASE_DIR = Path(__file__).parent.parent
DASHBOARD_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
REPORTS_DIR = DATA_DIR / "reports"
DB_FILE = DATA_DIR / "mycase_agent.db"

# Flask configuration
SECRET_KEY = os.getenv("DASHBOARD_SECRET_KEY", "dev-secret-key-change-in-production")
SESSION_COOKIE_SECURE = os.getenv("DASHBOARD_HTTPS", "false").lower() == "true"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
PERMANENT_SESSION_LIFETIME = 3600  # 1 hour

# Admin credentials (set via environment variables)
ADMIN_USERNAME = os.getenv("DASHBOARD_ADMIN_USER", "admin")
ADMIN_PASSWORD_HASH = os.getenv("DASHBOARD_ADMIN_PASSWORD_HASH")

# If no hash is set, generate a default one for development (password: "admin")
# In production, generate with: python -c "from werkzeug.security import generate_password_hash; print(generate_password_hash('your_password'))"
if not ADMIN_PASSWORD_HASH:
    from werkzeug.security import generate_password_hash
    ADMIN_PASSWORD_HASH = generate_password_hash("admin")
    print("WARNING: Using default admin password. Set DASHBOARD_ADMIN_PASSWORD_HASH environment variable!")

# Application settings
APP_NAME = "MyCase Legal Dashboard"
APP_VERSION = "1.0.0"
