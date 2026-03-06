"""
FirmSettings — Per-Firm Configuration Service

Single access point for all firm-specific configuration. Replaces os.getenv()
calls for firm-specific values (SendGrid, Twilio, Slack, MyCase, etc.).

Usage:
    from firm_settings import FirmSettings

    settings = FirmSettings("jcs_law")
    key = settings.get_sendgrid_key()
    config = settings.get_dunning_config()
    creds = settings.get_mycase_credentials()

All configuration is stored in the firms table (db/firms.py).
No environment variable fallback — if the firm doesn't have a value configured,
you get None or a specified default.
"""
import logging
from typing import Optional, Dict, Any
from functools import lru_cache

logger = logging.getLogger(__name__)


class FirmSettings:
    """
    Loads per-firm configuration from the firms table.

    The firm record is loaded once at construction; call refresh() to reload.
    Notification config is stored as JSONB in firms.notification_config.
    """

    def __init__(self, firm_id: str):
        self.firm_id = firm_id
        self._firm = None
        self._load()

    def _load(self):
        """Load the firm record from the database."""
        from db.firms import get_firm
        self._firm = get_firm(self.firm_id)
        if not self._firm:
            raise ValueError(f"Firm '{self.firm_id}' not found in database")

    def refresh(self):
        """Reload the firm record from the database."""
        self._load()

    @property
    def firm(self) -> dict:
        return self._firm

    # ── Notification Config (from JSONB column) ──────────────────

    def _nc(self, key: str, default: Any = None) -> Any:
        """Get a value from notification_config JSONB."""
        nc = self._firm.get("notification_config") or {}
        return nc.get(key, default)

    # SendGrid
    def get_sendgrid_key(self) -> Optional[str]:
        return self._nc("sendgrid_api_key") or None

    def get_sendgrid_from_email(self) -> str:
        return self._nc("sendgrid_from_email", "")

    def get_sendgrid_from_name(self) -> str:
        return self._nc("sendgrid_from_name", "")

    # Dunning
    def get_dunning_config(self) -> dict:
        """Get dunning-specific config: from_email, from_name, firm phone/name."""
        return {
            "from_email": self._nc("dunning_from_email") or self._nc("sendgrid_from_email", ""),
            "from_name": self._nc("dunning_from_name") or self._firm.get("name", ""),
            "firm_name": self._firm.get("name", ""),
            "firm_phone": self._firm.get("firm_phone", ""),
            "firm_email": self._firm.get("firm_email", ""),
            "firm_website": self._firm.get("firm_website", ""),
        }

    # Slack
    def get_slack_webhook(self) -> Optional[str]:
        return self._nc("slack_webhook_url") or None

    # Twilio
    def get_twilio_config(self) -> dict:
        return {
            "account_sid": self._nc("twilio_account_sid", ""),
            "auth_token": self._nc("twilio_auth_token", ""),
            "from_number": self._nc("twilio_from_number", ""),
        }

    def has_twilio(self) -> bool:
        tc = self.get_twilio_config()
        return bool(tc["account_sid"] and tc["auth_token"] and tc["from_number"])

    # SMTP (for non-SendGrid email)
    def get_smtp_config(self) -> dict:
        return {
            "server": self._nc("smtp_server", "smtp.gmail.com"),
            "port": self._nc("smtp_port", 587),
            "username": self._nc("smtp_username", ""),
            "password": self._nc("smtp_password", ""),
            "from_email": self._nc("smtp_from_email", ""),
        }

    # ── MyCase Credentials ───────────────────────────────────────

    def get_mycase_credentials(self) -> dict:
        """Get MyCase OAuth credentials for this firm."""
        return {
            "client_id": self._firm.get("mycase_client_id", ""),
            "client_secret": self._firm.get("mycase_client_secret", ""),
            "oauth_token": self._firm.get("mycase_oauth_token", ""),
            "oauth_refresh": self._firm.get("mycase_oauth_refresh", ""),
            "token_expires_at": self._firm.get("mycase_token_expires_at"),
            "mycase_firm_id": self._firm.get("mycase_firm_id"),
            "connected": bool(self._firm.get("mycase_connected")),
        }

    def is_mycase_connected(self) -> bool:
        return bool(self._firm.get("mycase_connected"))

    # ── Firm Identity & Branding ─────────────────────────────────

    def get_firm_info(self) -> dict:
        """Get firm identity: name, phone, email, website, logo."""
        return {
            "id": self.firm_id,
            "name": self._firm.get("name", ""),
            "phone": self._firm.get("firm_phone", ""),
            "email": self._firm.get("firm_email", ""),
            "website": self._firm.get("firm_website", ""),
            "logo_url": self._firm.get("logo_url", ""),
        }

    @property
    def firm_name(self) -> str:
        return self._firm.get("name", "")

    @property
    def firm_phone(self) -> str:
        return self._firm.get("firm_phone", "")

    # ── Subscription ─────────────────────────────────────────────

    def get_subscription_status(self) -> str:
        return self._firm.get("subscription_status", "trial")

    def get_subscription_tier(self) -> str:
        return self._firm.get("subscription_tier", "standard")

    def is_active(self) -> bool:
        return self.get_subscription_status() in ("trial", "active")

    # ── Sync Configuration ───────────────────────────────────────

    def get_sync_config(self) -> dict:
        return {
            "frequency_minutes": self._firm.get("sync_frequency_minutes", 240),
            "next_sync_at": self._firm.get("next_sync_at"),
            "last_sync_at": self._firm.get("last_sync_at"),
            "last_sync_status": self._firm.get("last_sync_status"),
        }

    # ── Generic Settings (JSONB) ─────────────────────────────────

    def get_setting(self, key: str, default: Any = None) -> Any:
        """Get a value from the settings JSONB column (feature flags, schedule, etc.)."""
        settings = self._firm.get("settings") or {}
        return settings.get(key, default)

    def get_schedule_config(self) -> dict:
        """Get scheduling preferences from settings JSONB."""
        schedule = self.get_setting("schedule", {})
        return {
            "sync_time": schedule.get("sync_time", "06:00"),
            "dunning_time": schedule.get("dunning_time", "07:30"),
            "reports_time": schedule.get("reports_time", "08:00"),
            "timezone": schedule.get("timezone", "America/Chicago"),
        }

    # ── Mutators ─────────────────────────────────────────────────

    def update_notification_config(self, **kwargs):
        """Update specific keys in notification_config JSONB."""
        from db.firms import update_firm_notification_config
        update_firm_notification_config(self.firm_id, **kwargs)
        self.refresh()

    def update_mycase_tokens(self, access_token: str, refresh_token: str,
                              expires_in: int):
        """Update OAuth tokens after a refresh."""
        from datetime import datetime, timedelta
        from db.connection import get_connection

        expires_at = datetime.utcnow() + timedelta(seconds=expires_in)

        with get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                UPDATE firms SET
                    mycase_oauth_token = %s,
                    mycase_oauth_refresh = %s,
                    mycase_token_expires_at = %s,
                    mycase_connected = TRUE,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
            """, (access_token, refresh_token, expires_at, self.firm_id))
            conn.commit()
        self.refresh()

    def __repr__(self):
        return f"FirmSettings(firm_id={self.firm_id!r}, name={self.firm_name!r})"


# ── Module-level convenience ─────────────────────────────────────

_settings_cache: Dict[str, FirmSettings] = {}


def get_firm_settings(firm_id: str, use_cache: bool = True) -> FirmSettings:
    """
    Get FirmSettings for a firm, optionally caching.

    In request-handling contexts (dashboard routes, API endpoints),
    you may want use_cache=False to ensure fresh data.
    In background tasks (Celery), caching is fine.
    """
    if use_cache and firm_id in _settings_cache:
        return _settings_cache[firm_id]

    settings = FirmSettings(firm_id)
    if use_cache:
        _settings_cache[firm_id] = settings
    return settings


def clear_settings_cache(firm_id: str = None):
    """Clear cached settings for a firm (or all firms)."""
    if firm_id:
        _settings_cache.pop(firm_id, None)
    else:
        _settings_cache.clear()
