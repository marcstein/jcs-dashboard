"""
phone/adapters/quo.py — Quo (OpenPhone) Webhook Adapter

Quo/OpenPhone sends webhook events for call.ringing, call.completed, etc.

Webhook format:
{
    "id": "evt_xxx",
    "object": "event",
    "type": "call.ringing",
    "createdAt": "2026-04-04T10:30:00.000Z",
    "data": {
        "object": "call",
        "id": "call_xxx",
        "from": "+13145551234",
        "to": "+13145559999",
        "direction": "incoming",
        "status": "ringing",
        "userId": "usr_xxx",
        "phoneNumberId": "pn_xxx"
    }
}

Signature verification:
OpenPhone signs webhooks with HMAC-SHA256.
Header: X-Openphone-Signature: <signature>
"""
import hashlib
import hmac
import logging
from datetime import datetime
from typing import Optional

from phone.adapters.base import BaseAdapter
from phone.events import CallEvent
from phone.normalize import normalize_phone

logger = logging.getLogger(__name__)


class QuoAdapter(BaseAdapter):
    """Adapter for Quo (OpenPhone) call webhooks."""

    provider_name = "quo"

    def verify_signature(
        self,
        body: bytes,
        headers: dict,
        webhook_secret: str,
    ) -> bool:
        """Verify Quo/OpenPhone HMAC-SHA256 signature."""
        if not webhook_secret:
            logger.warning("No webhook_secret configured for Quo — skipping verification")
            return True

        signature = headers.get("x-openphone-signature", "")
        if not signature:
            logger.warning("No signature header in Quo webhook")
            return False

        expected = hmac.new(
            webhook_secret.encode('utf-8'),
            body,
            hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(signature, expected)

    def is_ringing_event(self, payload: dict) -> bool:
        """Check if this is an incoming call ringing event."""
        event_type = payload.get("type", "")
        data = payload.get("data", {})
        direction = data.get("direction", "")

        return event_type == "call.ringing" and direction == "incoming"

    def parse_event(
        self,
        payload: dict,
        firm_id: str,
    ) -> Optional[CallEvent]:
        """Parse Quo/OpenPhone call event into a CallEvent."""
        data = payload.get("data", {})

        if data.get("direction") != "incoming":
            return None

        caller_number = data.get("from", "")
        called_number = data.get("to", "")

        caller_normalized = normalize_phone(caller_number)
        if not caller_normalized:
            logger.warning("Could not normalize caller number: %s", caller_number)
            caller_normalized = ""

        # Parse timestamp
        ts_str = payload.get("createdAt", "")
        try:
            timestamp = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            timestamp = datetime.utcnow()

        # OpenPhone doesn't provide extension info directly,
        # but userId could be mapped if needed
        return CallEvent(
            firm_id=firm_id,
            event_type="call.ringing",
            caller_number=caller_number,
            caller_number_normalized=caller_normalized,
            called_number=called_number,
            called_extension=None,
            provider=self.provider_name,
            raw_event_id=payload.get("id", ""),
            timestamp=timestamp,
            raw_payload=payload,
        )
