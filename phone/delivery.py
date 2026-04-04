"""
phone/delivery.py — Real-Time Screen Pop Delivery via SSE

Manages Server-Sent Events (SSE) connections for each logged-in dashboard user.
When a call event matches a client, the screen pop payload is pushed to the
appropriate user(s) via their SSE connection.

Architecture:
- Each logged-in user opens an SSE connection to /api/phone/events/stream
- The connection is registered in a global registry keyed by (firm_id, username)
- When a call comes in, we either:
  1. Push to a specific user (if extension mapping exists)
  2. Push to all users at the firm (broadcast)
- SSE connections auto-reconnect on the client side via EventSource API

Thread safety:
- Uses asyncio.Queue per connection for async push
- Registry protected by a lock for concurrent access
"""
import asyncio
import json
import logging
import time
from collections import defaultdict
from typing import Optional

from phone.events import ScreenPopPayload

logger = logging.getLogger(__name__)


class SSEConnectionRegistry:
    """
    Registry of active SSE connections.

    Each connection is an asyncio.Queue that the SSE endpoint reads from.
    Screen pop events are pushed to the queue and streamed to the client.
    """

    def __init__(self):
        # {firm_id: {username: asyncio.Queue}}
        self._connections: dict[str, dict[str, asyncio.Queue]] = defaultdict(dict)
        self._lock = asyncio.Lock()

    async def register(self, firm_id: str, username: str) -> asyncio.Queue:
        """Register a new SSE connection and return its event queue."""
        async with self._lock:
            queue = asyncio.Queue(maxsize=50)
            self._connections[firm_id][username] = queue
            logger.info("SSE registered: %s@%s (%d total for firm)",
                        username, firm_id, len(self._connections[firm_id]))
            return queue

    async def unregister(self, firm_id: str, username: str):
        """Remove an SSE connection when the client disconnects."""
        async with self._lock:
            self._connections.get(firm_id, {}).pop(username, None)
            # Clean up empty firm entries
            if firm_id in self._connections and not self._connections[firm_id]:
                del self._connections[firm_id]
            logger.info("SSE unregistered: %s@%s", username, firm_id)

    async def push_to_user(self, firm_id: str, username: str, payload: dict) -> bool:
        """Push an event to a specific user. Returns True if delivered."""
        async with self._lock:
            queue = self._connections.get(firm_id, {}).get(username)

        if queue:
            try:
                queue.put_nowait(payload)
                return True
            except asyncio.QueueFull:
                logger.warning("SSE queue full for %s@%s, dropping event", username, firm_id)
                return False
        return False

    async def broadcast_to_firm(self, firm_id: str, payload: dict) -> int:
        """Push an event to all connected users at a firm. Returns delivery count."""
        async with self._lock:
            firm_queues = dict(self._connections.get(firm_id, {}))

        delivered = 0
        for username, queue in firm_queues.items():
            try:
                queue.put_nowait(payload)
                delivered += 1
            except asyncio.QueueFull:
                logger.warning("SSE queue full for %s@%s, dropping event", username, firm_id)

        return delivered

    async def get_connected_count(self, firm_id: str = None) -> int:
        """Get count of connected users, optionally for a specific firm."""
        async with self._lock:
            if firm_id:
                return len(self._connections.get(firm_id, {}))
            return sum(len(users) for users in self._connections.values())

    async def get_connected_users(self, firm_id: str) -> list:
        """Get list of connected usernames for a firm."""
        async with self._lock:
            return list(self._connections.get(firm_id, {}).keys())


# Global singleton registry
_registry = SSEConnectionRegistry()


def get_registry() -> SSEConnectionRegistry:
    """Get the global SSE connection registry."""
    return _registry


async def deliver_screen_pop(pop: ScreenPopPayload) -> dict:
    """
    Deliver a screen pop to the appropriate dashboard user(s).

    If target_username is set (from extension mapping), deliver to that user only.
    Otherwise, broadcast to all connected users at the firm.

    Returns delivery stats.
    """
    registry = get_registry()
    payload = {
        "type": "screen_pop",
        "data": pop.to_dict(),
        "timestamp": time.time(),
    }

    if pop.target_username:
        # Targeted delivery to specific user
        delivered = await registry.push_to_user(pop.firm_id, pop.target_username, payload)
        return {
            "mode": "targeted",
            "target": pop.target_username,
            "delivered": delivered,
        }
    else:
        # Broadcast to all firm users
        count = await registry.broadcast_to_firm(pop.firm_id, payload)
        return {
            "mode": "broadcast",
            "delivered_count": count,
        }


def format_sse_event(data: dict, event_type: str = "screen_pop") -> str:
    """Format a dict as an SSE event string."""
    json_data = json.dumps(data)
    return f"event: {event_type}\ndata: {json_data}\n\n"
