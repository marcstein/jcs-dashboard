"""
phone/adapters/ringcentral.py — RingCentral Webhook Adapter

RingCentral sends webhook events via their Subscription API.
We subscribe to `/restapi/v1.0/account/~/extension/~/telephony/sessions`
which fires on incoming/outgoing call events.

Webhook format:
{
    "uuid": "...",
    "event": "/restapi/v1.0/account/.../telephony/sessions",
    "timestamp": "2026-04-04T10:30:00.000Z",
    "subscriptionId": "...",
    "body": {
        "parties": [
            {
                "direction": "Inbound",
                "from": {"phoneNumber": "+13145551234"},
                "to": {"phoneNumber": "+13145559999", "extensionId": "101"},
                "status": {"code": "Proceeding"}
            }
        ]
    }
}

Validation request (on subscription creation):
{
    "validationToken": "some-token-value"
}
Header: Validation-Token: some-token-value

Signature verification:
RingCentral signs webhooks with HMAC-SHA256 using the webhook secret.
Header: X-RingCentral-Signature: base64_encoded_hmac
"""
import hashlib
import hmac
import base64
import logging
from datetime import datetime
from typing import Optional

from phone.adapters.base import BaseAdapter
from phone.events import CallEvent
from phone.normalize import normalize_phone

logger = logging.getLogger(__name__)


class RingCentralAdapter(BaseAdapter):
    """Adapter for RingCentral telephony session webhooks."""

    provider_name = "ringcentral"

    def verify_signature(
        self,
        body: bytes,
        headers: dict,
        webhook_secret: str,
    ) -> bool:
        """Verify RingCentral HMAC-SHA256 webhook signature."""
        if not webhook_secret:
            logger.warning("No webhook_secret configured for RingCentral — skipping verification")
            return True

        signature = headers.get("x-ringcentral-signature", "")
        if not signature:
            # Also check the older header format
            signature = headers.get("verification-token", "")
            if not signature:
                logger.warning("No signature header in RingCentral webhook")
                return False

        expected = hmac.new(
            webhook_secret.encode('utf-8'),
            body,
            hashlib.sha256,
        ).digest()
        expected_b64 = base64.b64encode(expected).decode('utf-8')

        return hmac.compare_digest(signature, expected_b64)

    def get_validation_response(self, payload: dict, headers: dict) -> Optional[dict]:
        """
        Handle RingCentral's validation request.

        When creating a webhook subscription, RingCentral sends a request with
        a Validation-Token header. We must respond with the same token.
        """
        validation_token = headers.get("validation-token")
        if validation_token:
            return {"validation_token": validation_token}
        return None

    def is_ringing_event(self, payload: dict) -> bool:
        """Check if this is an incoming call ringing event."""
        body = payload.get("body", {})
        parties = body.get("parties", [])

        for party in parties:
            direction = party.get("direction", "")
            status_code = party.get("status", {}).get("code", "")

            if direction == "Inbound" and status_code in ("Proceeding", "Ringing"):
                return True

        return False

    def parse_event(
        self,
        payload: dict,
        firm_id: str,
    ) -> Optional[CallEvent]:
        """Parse RingCentral telephony session event into a CallEvent."""
        body = payload.get("body", {})
        parties = body.get("parties", [])

        # Find the inbound ringing party
        for party in parties:
            direction = party.get("direction", "")
            status_code = party.get("status", {}).get("code", "")

            if direction != "Inbound":
                continue
            if status_code not in ("Proceeding", "Ringing"):
                continue

            from_info = party.get("from", {})
            to_info = party.get("to", {})

            caller_number = from_info.get("phoneNumber", "")
            called_number = to_info.get("phoneNumber", "")
            extension_id = to_info.get("extensionId", "")

            # Normalize caller number
            caller_normalized = normalize_phone(caller_number)
            if not caller_normalized:
                logger.warning("Could not normalize caller number: %s", caller_number)
                # Still create the event with raw number
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
                called_extension=str(extension_id) if extension_id else None,
                provider=self.provider_name,
                raw_event_id=payload.get("uuid", ""),
                timestamp=timestamp,
                raw_payload=payload,
            )

        return None
