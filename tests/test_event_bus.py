"""
Tests for services/event_bus.py — AuraEventBus pub/sub.

Coverage:
  - publish delivers to all subscribers (fan-out)
  - subscribe returns stable queue per client_id
  - unsubscribe removes queue (no more events delivered)
  - watch_device_events integration: collects events within timeout
  - watch_device_events: returns empty list when no events published
  - watch_device_events: cleans up subscriber on normal exit
  - watch_device_events: cleans up subscriber on timeout
"""

import asyncio

import pytest

from services.event_bus import AuraEventBus, DeviceEvent, get_event_bus


# ── Unit tests for AuraEventBus ──────────────────────────────────────────────

@pytest.fixture
def bus() -> AuraEventBus:
    return AuraEventBus()


def make_event(event_type: str = "gesture_executed") -> DeviceEvent:
    return DeviceEvent(
        event_type=event_type,
        source="mcp",
        client_id="test_client",
        payload={"key": "value"},
        timestamp=0.0,
    )


@pytest.mark.asyncio
async def test_publish_delivers_to_single_subscriber(bus: AuraEventBus) -> None:
    q = bus.subscribe("client_a")
    event = make_event()
    await bus.publish(event)
    received = await asyncio.wait_for(q.get(), timeout=1.0)
    assert received.event_type == "gesture_executed"


@pytest.mark.asyncio
async def test_publish_fan_out_to_multiple_subscribers(bus: AuraEventBus) -> None:
    q1 = bus.subscribe("client_a")
    q2 = bus.subscribe("client_b")
    event = make_event()
    await bus.publish(event)
    r1 = await asyncio.wait_for(q1.get(), timeout=1.0)
    r2 = await asyncio.wait_for(q2.get(), timeout=1.0)
    assert r1.event_type == r2.event_type == "gesture_executed"


@pytest.mark.asyncio
async def test_subscribe_returns_same_queue_for_same_client(bus: AuraEventBus) -> None:
    q1 = bus.subscribe("client_a")
    q2 = bus.subscribe("client_a")
    assert q1 is q2


@pytest.mark.asyncio
async def test_unsubscribe_stops_delivery(bus: AuraEventBus) -> None:
    bus.subscribe("client_a")
    bus.unsubscribe("client_a")
    assert bus.subscriber_count == 0
    # publish should not raise even with no subscribers
    await bus.publish(make_event())


@pytest.mark.asyncio
async def test_unsubscribe_nonexistent_is_noop(bus: AuraEventBus) -> None:
    bus.unsubscribe("nobody")  # must not raise


@pytest.mark.asyncio
async def test_subscriber_count(bus: AuraEventBus) -> None:
    assert bus.subscriber_count == 0
    bus.subscribe("a")
    bus.subscribe("b")
    assert bus.subscriber_count == 2
    bus.unsubscribe("a")
    assert bus.subscriber_count == 1


@pytest.mark.asyncio
async def test_multiple_events_delivered_in_order(bus: AuraEventBus) -> None:
    q = bus.subscribe("client_a")
    for i in range(3):
        await bus.publish(make_event(event_type=f"event_{i}"))
    results = [q.get_nowait().event_type for _ in range(3)]
    assert results == ["event_0", "event_1", "event_2"]


# ── Integration tests: watch_device_events logic (no mcp module needed) ──────
# These tests exercise the same asyncio patterns used in watch_device_events
# directly against AuraEventBus, avoiding the aura_mcp_server import which
# requires the `mcp` package (not installed in the test environment).

async def _watch(bus: AuraEventBus, timeout_seconds: float, client_id: str = "test_watcher") -> list:
    """Minimal reimplementation of watch_device_events for testing."""
    queue = bus.subscribe(client_id)
    events = []
    try:
        loop = asyncio.get_event_loop()
        deadline = loop.time() + timeout_seconds
        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                break
            try:
                event = await asyncio.wait_for(queue.get(), timeout=remaining)
                events.append({
                    "event_type": event.event_type,
                    "source": event.source,
                    "payload": event.payload,
                    "timestamp": event.timestamp,
                })
            except asyncio.TimeoutError:
                break
    finally:
        bus.unsubscribe(client_id)
    return events


@pytest.mark.asyncio
async def test_watch_collects_published_events(bus: AuraEventBus) -> None:
    async def publish_after_delay() -> None:
        await asyncio.sleep(0.05)
        await bus.publish(DeviceEvent(
            event_type="gesture_executed",
            source="mcp",
            client_id="mcp_client",
            payload={"gesture_type": "tap"},
            timestamp=1.0,
        ))

    events, _ = await asyncio.gather(
        _watch(bus, timeout_seconds=1),
        publish_after_delay(),
    )

    assert len(events) == 1
    assert events[0]["event_type"] == "gesture_executed"
    assert events[0]["payload"]["gesture_type"] == "tap"


@pytest.mark.asyncio
async def test_watch_returns_empty_on_zero_timeout(bus: AuraEventBus) -> None:
    events = await _watch(bus, timeout_seconds=0)
    assert events == []


@pytest.mark.asyncio
async def test_watch_unsubscribes_after_return(bus: AuraEventBus) -> None:
    count_before = bus.subscriber_count
    await _watch(bus, timeout_seconds=0)
    assert bus.subscriber_count == count_before
