"""
phone/events.py — Internal Call Event Model

Provider-agnostic representation of an incoming call event.
Each VoIP adapter normalizes its provider-specific payload into this format.
"""
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional


@dataclass
class CallEvent:
    """Normalized incoming call event (provider-agnostic)."""
    firm_id: str
    event_type: str                          # call.ringing, call.answered, call.ended
    caller_number: str                       # Original format from provider
    caller_number_normalized: str            # E.164 format
    called_number: str = ""                  # Firm's number that was called
    called_extension: Optional[str] = None   # Extension ringing (if available)
    provider: str = ""                       # ringcentral, quo, vonage, etc.
    raw_event_id: str = ""                   # Provider's event ID for dedup
    timestamp: datetime = field(default_factory=datetime.utcnow)
    raw_payload: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to dict for JSON serialization."""
        d = asdict(self)
        d['timestamp'] = self.timestamp.isoformat()
        return d


@dataclass
class ScreenPopPayload:
    """Data package delivered to the dashboard for screen pop display."""
    firm_id: str
    call_event_id: int                       # ID from call_events table
    caller_number: str                       # Display format: (314) 555-1234
    caller_number_normalized: str            # E.164 for dedup
    matched: bool = False
    client_id: Optional[int] = None
    client_name: str = "Unknown Caller"
    client_email: Optional[str] = None
    cases: list = field(default_factory=list)  # List of active case dicts
    last_payment: Optional[dict] = None      # {date, amount} or None
    balance_due: Optional[float] = None
    mycase_url: Optional[str] = None         # Deep link to client in MyCase
    target_username: Optional[str] = None    # If extension-mapped, target this user
    timestamp: str = ""

    def to_dict(self) -> dict:
        """Convert to dict for JSON/SSE serialization."""
        return asdict(self)
