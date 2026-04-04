"""
phone/ — VoIP Phone Integration Package

Handles incoming call webhooks from multiple VoIP providers, normalizes
caller phone numbers, looks up clients in the database, and delivers
screen pop notifications to the dashboard in real-time.

Submodules:
- normalize: E.164 phone number normalization
- lookup: Client lookup by phone number
- events: Internal call event model
- delivery: SSE push to dashboard
- adapters/: Per-provider webhook adapters (RingCentral, Quo, Vonage)
"""
