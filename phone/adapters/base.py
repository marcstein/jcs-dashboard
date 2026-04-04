"""
phone/adapters/base.py — Abstract Base Adapter for VoIP Providers

Each provider adapter must implement:
1. verify_signature() — Validate webhook authenticity
2. parse_event() — Extract call data from provider payload
3. is_ringing_event() — Filter to only incoming ringing events
"""
from abc import ABC, abstractmethod
from typing import Optional

from phone.events import CallEvent


class BaseAdapter(ABC):
    """Abstract base class for VoIP provider adapters."""

    provider_name: str = ""

    @abstractmethod
    def verify_signature(
        self,
        body: bytes,
        headers: dict,
        webhook_secret: str,
    ) -> bool:
        """
        Verify the webhook signature to prevent spoofed events.

        Args:
            body: Raw request body bytes
            headers: Request headers dict
            webhook_secret: Provider-specific verification secret

        Returns:
            True if signature is valid
        """
        ...

    @abstractmethod
    def parse_event(
        self,
        payload: dict,
        firm_id: str,
    ) -> Optional[CallEvent]:
        """
        Parse a provider-specific webhook payload into a CallEvent.

        Args:
            payload: Parsed JSON body from webhook
            firm_id: The firm this webhook is for

        Returns:
            CallEvent if this is a relevant call event, None to skip
        """
        ...

    @abstractmethod
    def is_ringing_event(self, payload: dict) -> bool:
        """
        Check if the webhook payload represents an incoming call ringing.

        Used to filter out irrelevant events (call ended, voicemail, etc.)
        before doing the more expensive parse_event().
        """
        ...

    def get_validation_response(self, payload: dict, headers: dict) -> Optional[dict]:
        """
        Return a validation/challenge response if the provider requires it.

        Some providers (RingCentral) send a validation request on webhook
        registration that requires a specific response. Return the response
        dict or None if not a validation request.
        """
        return None
