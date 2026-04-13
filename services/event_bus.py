"""
AuraEventBus — lightweight pub/sub for device events.

Any component can publish an event. Every subscriber receives all events.
Used to broadcast gesture results, voice commands, and screen changes
across all connected clients (MCP, voice, API).
"""

import asyncio
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class DeviceEvent:
    event_type: str  # "gesture_executed" | "voice_command" | "screen_changed"
    source: str  # "mcp" | "voice" | "api"
    client_id: str  # who triggered it
    payload: dict = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


class AuraEventBus:
    def __init__(self) -> None:
        self._subscribers: dict[str, asyncio.Queue] = {}

    async def publish(self, event: DeviceEvent) -> None:
        """Broadcast event to all subscribers."""
        for queue in self._subscribers.values():
            await queue.put(event)

    def subscribe(self, client_id: str) -> asyncio.Queue:
        """Register a subscriber. Returns the queue to read events from."""
        if client_id not in self._subscribers:
            self._subscribers[client_id] = asyncio.Queue()
        return self._subscribers[client_id]

    def unsubscribe(self, client_id: str) -> None:
        """Remove a subscriber and its queue."""
        self._subscribers.pop(client_id, None)

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)


# Module-level singleton — shared across MCP tools and FastAPI handlers
_event_bus: Optional[AuraEventBus] = None


def get_event_bus() -> AuraEventBus:
    global _event_bus
    if _event_bus is None:
        _event_bus = AuraEventBus()
    return _event_bus
