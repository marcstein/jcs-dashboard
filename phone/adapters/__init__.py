"""
phone/adapters/ — VoIP Provider Webhook Adapters

Each adapter normalizes a provider-specific webhook payload into
our internal CallEvent format. The adapter registry maps provider
names to adapter classes.
"""
from phone.adapters.base import BaseAdapter
from phone.adapters.ringcentral import RingCentralAdapter
from phone.adapters.quo import QuoAdapter
from phone.adapters.vonage import VonageAdapter

# Registry: provider name → adapter class
ADAPTERS = {
    "ringcentral": RingCentralAdapter,
    "quo": QuoAdapter,
    "vonage": VonageAdapter,
}


def get_adapter(provider: str) -> BaseAdapter:
    """Get an adapter instance for the given provider."""
    cls = ADAPTERS.get(provider)
    if not cls:
        raise ValueError(f"Unknown VoIP provider: {provider}. Available: {list(ADAPTERS.keys())}")
    return cls()
