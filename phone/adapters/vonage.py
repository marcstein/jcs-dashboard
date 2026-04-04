"""
phone/adapters/vonage.py — Vonage (Nexmo) Webhook Adapter

Vonage sends call events to the configured Answer URL and Event URL.
For incoming calls, Vonage sends a POST/GET to the Answer URL with call details.

Answer URL webhook format (incoming call):
{
    "uuid": "call-uuid",
    "conversation_uuid": "conv-uuid",
    "to": "13145559999",
    "from": "13145551234",
    "status": "ringing",
    "direction": "inbound",
    "timestamp": "2026-04-04T10:30:00.000Z"
}

Event URL (call status updates):
{
    "uuid": "call-uuid",
    "status": "ringing" | "answered" | "completed",
    "direction": "inbound",
    "from": "13145551234",
    "to": "13145559999",
    "timestamp": "..."
}

Signature verification:
Vonage signs webhooks with JWT (RS256) or shared secret.
Header: Authorization: Bearer <jwt>
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


class VonageAdapter(BaseAdapter):
    """Adapter for Vonage (Nexmo) call webhooks."""

    provider_name = "vonage"

    def verify_signature(
        self,
        body: bytes,
        headers: dict,
        webhook_secret: str,
    ) -> bool:
        """
        Verify Vonage webhook signature.

        Vonage supports multiple verification methods:
        1. JWT-signed webhooks (recommended) — requires public key
        2. Shared secret HMAC — simpler setup

        For now we support the shared secret method.
        """
        if not webhook_secret:
            logger.warning("No webhook_secret configured for Vonage — skipping verification")
            return True

        # Vonage shared secret: HMAC-SHA256 of sorted query params or body
        signature = headers.get("x-vonage-signature", "")
        if not signature:
            # Vonage may also use a different header depending on configuration
            logger.debug("No signature header — allowing (configure for production)")
            return True

        expected = hmac.new(
            webhook_secret.encode('utf-8'),
            body,
            hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(signature, expected)

    def is_ringing_event(self, payload: dict) -> bool:
        """Check if this is an incoming call ringing event."""
        status = payload.get("status", "")
        direction = payload.get("direction", "")

        return status == "ringing" and direction == "inbound"

    def parse_event(
        self,
        payload: dict,
        firm_id: str,
    ) -> Optional[CallEvent]:
        """Parse Vonage call event into a CallEvent."""
        direction = payload.get("direction", "")
        if direction != "inbound":
            return None

        caller_number = payload.get("from", "")
        called_number = payload.get("to", "")

        caller_normalized = normalize_phone(caller_number)
        if not caller_normalized:
            logger.warning("Could not normalize caller number: %s", caller_number)
            caller_normalized = ""

        # Parse timestamp
        ts_str = payload.get("timestamp", "")
        try:
            timestamp = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            timestamp = datetime.utcnow()

        return CallEvent(
            firm_id=firm_id,
            event_type="call.ringing",
            caller_number=caller_number,
            caller_number_normalized=caller_normalized,
            called_number=called_number,
            called_extension=None,
            provider=self.provider_name,
            raw_event_id=payload.get("uuid", ""),
            timestamp=timestamp,
            raw_payload=payload,
        )
